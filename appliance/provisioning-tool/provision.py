#!/usr/bin/env python3
"""Stratasys Factory Provisioning Tool — CM5 over USB (rpiboot).

    provision.py run   --station ST-01 --operator amitai [--server URL] [--offline-token token.json]
    provision.py new-serial --station ST-01 --operator amitai --previous SC000126 --reason "board swap"
    provision.py status

The whole flow is a state machine (ProvisioningRun) whose steps are
idempotent and journaled to <workdir>/<runId>.jsonl so a power loss resumes
at the last completed step. UI (Textual TUI, `ui.py`) and this module are
separate: the machine never touches the screen, the UI only observes.

Server access is optional per step: serial + license need the Serial
Service (or an offline range token + station key); the image needs the
Image Server (or the local cache). Every run records online/offline.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stratasys_appliance import crypto, serials, manifests, audit  # noqa: E402
from stratasys_appliance.identity import load_public_pem, device_id as derive_device_id, verify_challenge  # noqa: E402
from image_catalog import ImageCatalog, Resolution, CatalogError  # noqa: E402
from rpiboot import Rpiboot, FakeRpiboot, ModuleInfo, RpibootError  # noqa: E402

try:
    import yaml
except ImportError:      # profiles are simple enough for a JSON fallback
    yaml = None


class Step(str, Enum):
    FETCH_APPROVED_IMAGE = "FETCH_APPROVED_IMAGE"
    DETECT_HARDWARE = "DETECT_HARDWARE"
    VERIFY_COMPAT = "VERIFY_COMPAT"
    FLASH_IMAGE = "FLASH_IMAGE"
    CONFIGURE_BOOT = "CONFIGURE_BOOT"
    CREATE_IDENTITY = "CREATE_IDENTITY"
    ALLOCATE_SERIAL = "ALLOCATE_SERIAL"
    REQUEST_LICENSE = "REQUEST_LICENSE"
    BIND_LICENSE = "BIND_LICENSE"
    ENCRYPT_DATA = "ENCRYPT_DATA"
    APPLY_POLICY = "APPLY_POLICY"
    VERIFY_MACHINE = "VERIFY_MACHINE"
    VERIFY_SOFTWARE = "VERIFY_SOFTWARE"
    RECORD = "RECORD"
    READY = "READY"
    FAILED = "FAILED"


ORDER = [s for s in Step if s not in (Step.READY, Step.FAILED)]


class ProvisioningError(Exception):
    pass


@dataclass
class Config:
    station_id: str
    operator: str
    server_url: str | None
    workdir: Path
    trust_dir: Path                     # image-manifest + serial-service public keys
    product: str = "SCURE-A"
    channel: str = "production"
    role: str = "factory"
    profiles_file: Path = Path(__file__).with_name("hardware-profiles.yaml")
    signed_eeprom_dir: Path | None = None
    offline_token: Path | None = None   # signed serial range for offline stations
    station_key: Path | None = None     # station signing key for provisional licenses
    app_version: str = ""


@dataclass
class RunState:
    run_id: str
    started_at: str
    step: Step = Step.FETCH_APPROVED_IMAGE
    online: bool = False
    image: dict = field(default_factory=dict)        # version, buildId, sha256, path
    module: dict = field(default_factory=dict)
    device_id: str | None = None
    device_public_key: str | None = None
    serial: str | None = None
    allocation_id: str | None = None
    previous_serial: str | None = None
    license: dict | None = None
    provisional: bool = False
    completed: list[str] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    result: str | None = None
    error: str | None = None


class ServerClient:
    """Thin JSON client for the Serial/Image service. Raises OSError family on
    network failure so the run can fall back to offline paths."""

    def __init__(self, url: str | None, role: str, operator: str, opener=urllib.request.urlopen, timeout=10):
        self.url = (url or "").rstrip("/") or None
        self.headers = {"Content-Type": "application/json", "X-Stratasys-Role": role, "X-Stratasys-Operator": operator}
        self._open = opener
        self.timeout = timeout

    def post(self, path: str, body: dict) -> dict:
        if not self.url:
            raise OSError("no server configured")
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers=self.headers, method="POST")
        try:
            with self._open(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:          # server answered: a refusal is not "offline"
            try:
                return json.loads(e.read().decode())
            except ValueError:
                return {"ok": False, "error": f"HTTP {e.code}"}


class DeviceAgent:
    """The provisioning agent running on the module's signed image (USB
    Ethernet gadget, link-local). Replace with FakeDeviceAgent in tests."""

    def __init__(self, base="http://169.254.71.1:8441", opener=urllib.request.urlopen, timeout=30):
        self.base, self._open, self.timeout = base, opener, timeout

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        with self._open(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def wait_ready(self, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.call("/agent/status").get("ok"):
                    return
            except OSError:
                time.sleep(2)
        raise ProvisioningError("module did not come up in provisioning mode")


class ProvisioningRun:
    def __init__(self, cfg: Config, rpi: Rpiboot, agent, catalog: ImageCatalog | None = None,
                 server: ServerClient | None = None, on_event: Callable[[str, dict], None] | None = None,
                 state: RunState | None = None):
        self.cfg = cfg
        self.rpi = rpi
        self.agent = agent
        self.server = server or ServerClient(cfg.server_url, cfg.role, cfg.operator)
        trust = crypto.TrustStore.from_dir(cfg.trust_dir)
        self.catalog = catalog or ImageCatalog(cfg.server_url, trust, cfg.workdir / "image-cache", cfg.product, cfg.channel)
        self.on_event = on_event or (lambda e, d: None)
        self.state = state or RunState(run_id=str(uuid.uuid4()), started_at=_now())
        cfg.workdir.mkdir(parents=True, exist_ok=True)
        self.ledger = audit.AuditLog(cfg.workdir / "station-audit.jsonl", None, None)
        self.profiles = self._load_profiles()
        self._resolution: Resolution | None = None

    # ---------------- journal ----------------
    @property
    def journal(self) -> Path:
        return self.cfg.workdir / f"{self.state.run_id}.jsonl"

    def _log(self, event: str, **detail):
        entry = {"ts": _now(), "step": self.state.step.value, "event": event, **detail}
        self.state.log.append(entry)
        with self.journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        self.on_event(event, entry)

    def _save(self):
        (self.cfg.workdir / f"{self.state.run_id}.state.json").write_text(
            json.dumps({**self.state.__dict__, "step": self.state.step.value}, indent=2, default=str))

    @classmethod
    def resume(cls, cfg: Config, run_id: str, **kw) -> "ProvisioningRun":
        data = json.loads((cfg.workdir / f"{run_id}.state.json").read_text())
        data["step"] = Step(data["step"])
        return cls(cfg, state=RunState(**data), **kw)

    def _load_profiles(self) -> dict:
        p = self.cfg.profiles_file
        text = p.read_text() if p.exists() else "{}"
        if yaml:
            return yaml.safe_load(text) or {}
        return json.loads(text) if text.strip().startswith("{") else {}

    # ---------------- driver ----------------
    def run(self) -> RunState:
        try:
            start = ORDER.index(self.state.step) if self.state.step in ORDER else 0
            for step in ORDER[start:]:
                if step.value in self.state.completed:
                    continue
                self.state.step = step
                self._save()
                self._log("step started")
                getattr(self, f"step_{step.value.lower()}")()
                self.state.completed.append(step.value)
                self._log("step completed")
                self._save()
            self.state.step = Step.READY
            self.state.result = "READY_FOR_PRODUCTION"
            self._log("Provisioning Successful", serial=self.state.serial)
        except Exception as e:  # noqa: BLE001 - any failure -> safe stop, recorded
            self.state.step = Step.FAILED
            self.state.result = "FAILED"
            self.state.error = f"{type(e).__name__}: {e}"
            self._log("Provisioning failed", error=self.state.error)
            self._void_serial_if_reserved()
        self._save()
        self.ledger.append("Provisioning run finished", {"runId": self.state.run_id, "result": self.state.result,
                                                          "serial": self.state.serial, "online": self.state.online},
                           actor=f"{self.cfg.role}:{self.cfg.operator}")
        return self.state

    # ---------------- steps ----------------
    def step_fetch_approved_image(self):
        res = self.catalog.resolve(None)
        self._resolution = res
        self.state.online = res.online
        self._log("image resolved", status=res.status, latestProduction=res.version,
                  localVersion=res.local_version, versions=res.server_versions, online=res.online)
        if res.local_version != res.version:
            self._log("Downloading latest approved image...", version=res.version)
        path = self.catalog.ensure_downloaded(res, progress=lambda d, t: self.on_event("download", {"done": d, "total": t}))
        self.state.image = {"version": res.version, "buildId": res.build_id, "sha256": res.payload["sha256"],
                            "appVersion": res.payload.get("appVersion"), "path": str(path),
                            "minHardwareRevision": res.payload["minHardwareRevision"],
                            "requiredFirmwareVersion": res.payload["requiredFirmwareVersion"]}
        self._log("Image Signature: VALID · Image Status: READY FOR INSTALLATION", version=res.version)

    def step_detect_hardware(self):
        self.rpi.expose_mass_storage()
        disk = self.rpi.find_target_disk()
        info: ModuleInfo = self.rpi.read_module_info(disk)
        self.state.module = info.__dict__.copy()
        self._log("module detected", **self.state.module)

    def step_verify_compat(self):
        m = self.state.module
        prof = self.profiles.get("modules", {})
        rev = (m.get("board_revision") or "").lower()
        supported = prof.get("supported_revisions", [])
        if supported and rev not in [r.lower() for r in supported]:
            raise ProvisioningError(f"unsupported module revision {rev}")
        if m.get("storage_size_bytes", 0) < int(prof.get("min_storage_bytes", 0)):
            raise ProvisioningError("storage too small")
        if m.get("memory_mb", 0) < int(prof.get("min_memory_mb", 0)):
            raise ProvisioningError("not enough RAM")
        hw = manifests.DetectedHardware(self.cfg.product, int(prof.get("carrier_revision", 1)), m.get("eeprom_version", ""))
        manifests.check_installable(self._resolution.payload, hw, self.catalog.withdrawn(), self.cfg.channel)
        self._log("hardware compatible", profile=prof.get("name"))

    def step_flash_image(self):
        path = Path(self.state.image["path"])
        self.catalog.verify_before_flash(self._resolution, path)      # signature + hash, again
        self.rpi.flash(path, self.state.module["storage_device"],
                       progress=lambda d, t: self.on_event("flash", {"done": d, "total": t}))
        self._log("image flashed", version=self.state.image["version"], sha256=self.state.image["sha256"])

    def step_configure_boot(self):
        if self.cfg.signed_eeprom_dir is None:
            self._log("secure boot NOT programmed (no signed EEPROM payload configured) — lab unit")
            return
        self.rpi.program_secure_boot(self.cfg.signed_eeprom_dir)
        self.state.module["secure_boot"] = True
        self._log("secure boot programmed (OTP key hash, dev key revoked, JTAG locked)")

    def step_create_identity(self):
        self.agent.wait_ready()
        nonce = secrets.token_bytes(32)
        r = self.agent.call("/agent/identity", {"nonce": base64.b64encode(nonce).decode()})
        pub = load_public_pem(r["publicKeyPem"])
        if not verify_challenge(pub, nonce, base64.b64decode(r["nonceSignature"])):
            raise ProvisioningError("module failed the identity challenge")
        self.state.device_public_key = r["publicKeyPem"]
        self.state.device_id = derive_device_id(pub)
        if r.get("deviceId") and r["deviceId"] != self.state.device_id:
            raise ProvisioningError("module reports a device ID that does not match its key")
        try:
            resp = self.server.post("/devices/register", {
                "publicKeyPem": r["publicKeyPem"], "identityBackend": r.get("identityBackend", "otp-hkdf"),
                "boardSerial": self.state.module.get("board_serial"), "boardRevision": self.state.module.get("board_revision"),
                "fingerprint": r.get("fingerprint"), "secureBoot": bool(r.get("secureBoot")),
                "nonce": base64.b64encode(nonce).decode(), "nonceSignature": r["nonceSignature"]})
            if not resp.get("ok"):
                raise ProvisioningError(f"device registration refused: {resp.get('error')}")
        except OSError:
            self.state.online = False
            self._log("device registration deferred (offline)")
        self._log("device identity created", deviceId=self.state.device_id, backend=r.get("identityBackend"))

    def step_allocate_serial(self):
        if self.state.serial:
            return
        try:
            resp = self.server.post("/serials/allocate", {"stationId": self.cfg.station_id, "operator": self.cfg.operator,
                                                          "reason": "reassignment" if self.state.previous_serial else "provisioning",
                                                          "previousSerial": self.state.previous_serial})
            if not resp.get("ok"):
                raise ProvisioningError(f"serial allocation refused: {resp.get('error')}")
            self.state.serial, self.state.allocation_id = resp["serial"], resp["allocationId"]
            self.state.online = True
        except OSError:
            self.state.online = False
            self.state.serial = self._take_offline_serial()
        self.ledger.append("Serial number assigned", {"serial": self.state.serial, "previousSerial": self.state.previous_serial,
                                                      "online": self.state.online, "runId": self.state.run_id},
                           actor=f"{self.cfg.role}:{self.cfg.operator}")
        self._log("serial assigned", serial=self.state.serial, online=self.state.online)

    def _take_offline_serial(self) -> str:
        """Next unused number from the signed range token; the local ledger
        (hash-chained) is the source of truth until reconciliation."""
        if not self.cfg.offline_token:
            raise ProvisioningError("server unreachable and no offline serial-range token configured")
        env = json.loads(Path(self.cfg.offline_token).read_text())
        p = crypto.verify(env, crypto.TrustStore.from_dir(self.cfg.trust_dir))
        if p.get("type") != "serial-range" or p.get("stationId") != self.cfg.station_id:
            raise ProvisioningError("range token is not for this station")
        if datetime.fromisoformat(p["expiresAt"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
            raise ProvisioningError("range token expired — reconnect and request a new range")
        used = [e["detail"]["serial"] for e in self.ledger.entries()
                if e["event"] == "Serial number assigned" and serials.in_range(e["detail"]["serial"], p["first"], p["last"])]
        nxt = serials.next_serial(max(used, key=serials.parse_serial)) if used else p["first"]
        if not serials.in_range(nxt, p["first"], p["last"]):
            raise ProvisioningError("offline serial range exhausted")
        return nxt

    def step_request_license(self):
        body = {"serial": self.state.serial, "deviceId": self.state.device_id, "productType": self.cfg.product,
                "features": ["production"] if self.cfg.channel == "production" else ["engineering"],
                "previousSerial": self.state.previous_serial}
        try:
            resp = self.server.post("/licenses/issue", body)
            if not resp.get("ok"):
                raise ProvisioningError(f"license refused: {resp.get('error')}")
            self.state.license = resp["license"]
        except OSError:
            self.state.online = False
            self.state.license = self._provisional_license(body)
            self.state.provisional = True
        self._log("license obtained", provisional=self.state.provisional, signerKeyId=self.state.license["signerKeyId"])

    def _provisional_license(self, body: dict) -> dict:
        from stratasys_appliance import license as lic
        if not self.cfg.station_key:
            raise ProvisioningError("server unreachable and no station key for provisional licenses")
        payload = lic.build_payload(serial=body["serial"], device_id=body["deviceId"],
                                    device_public_key_pem=self.state.device_public_key, product_type=body["productType"],
                                    features=body["features"], software_compat=">=0.6.0 <2.0.0",
                                    issuer=f"station:{self.cfg.station_id}", previous_serial=body.get("previousSerial"),
                                    expires_at=datetime.now(timezone.utc).replace(microsecond=0) + __import__("datetime").timedelta(days=30),
                                    provisional=True)
        return crypto.sign(payload, crypto.load_private_key(self.cfg.station_key))

    def step_bind_license(self):
        r = self.agent.call("/agent/license", {"license": self.state.license, "serial": self.state.serial})
        if not r.get("ok") or r.get("licenseState") != "VALID":
            raise ProvisioningError(f"module rejected the license: {r.get('error') or r.get('licenseState')}")
        self._log("license bound and verified on device", serial=self.state.serial)

    def step_encrypt_data(self):
        r = self.agent.call("/agent/encrypt-data", {})
        if not r.get("ok"):
            raise ProvisioningError(f"data partition setup failed: {r.get('error')}")
        # the recovery passphrase is returned encrypted to the Stratasys KMS key and escrowed, never shown
        try:
            self.server.post("/recovery-keys", {"serial": self.state.serial, "ciphertext": r["recoveryKeyCiphertext"],
                                                "kmsKeyId": r["kmsKeyId"]})
        except OSError:
            (self.cfg.workdir / f"{self.state.serial}.recovery.enc").write_text(json.dumps(r))
            self._log("recovery key escrow deferred (offline, stored encrypted on station)")
        self._log("data partition encrypted", keySource=r.get("keySource"))

    def step_apply_policy(self):
        r = self.agent.call("/agent/apply-policy", {"kiosk": True, "usbguard": True, "lockUsers": True})
        if not r.get("ok"):
            raise ProvisioningError(f"policy apply failed: {r.get('error')}")
        self._log("kiosk + USB + user policy applied")

    def step_verify_machine(self):
        r = self.agent.call("/agent/self-test", {})
        failed = [t for t, ok in (r.get("tests") or {}).items() if not ok]
        if not r.get("ok") or failed:
            raise ProvisioningError(f"machine self-test failed: {failed}")
        self._log("machine self-test passed", tests=list((r.get("tests") or {}).keys()))

    def step_verify_software(self):
        r = self.agent.call("/agent/status")
        checks = {"secureBoot": bool(r.get("secureBoot")) or self.cfg.signed_eeprom_dir is None,
                  "license": r.get("licenseState") == "VALID", "integrity": r.get("integrity") == "OK",
                  "appVersion": bool(r.get("appVersion"))}
        if not all(checks.values()):
            raise ProvisioningError(f"software verification failed: {checks}")
        self.state.image["appVersion"] = r.get("appVersion") or self.state.image.get("appVersion")
        self._log("software verified", **checks)

    def step_record(self):
        record = {"runId": self.state.run_id, "serial": self.state.serial, "deviceId": self.state.device_id,
                  "stationId": self.cfg.station_id, "operator": self.cfg.operator,
                  "imageVersion": self.state.image["version"], "buildId": self.state.image["buildId"],
                  "imageSha256": self.state.image["sha256"], "appVersion": self.state.image.get("appVersion"),
                  "online": self.state.online, "result": "READY_FOR_PRODUCTION", "stepLog": self.state.log,
                  "startedAt": self.state.started_at, "finishedAt": _now()}
        (self.cfg.workdir / f"{self.state.serial}.record.json").write_text(json.dumps(record, indent=2))
        try:
            if self.state.allocation_id:
                self.server.post(f"/serials/{self.state.serial}/commit", {"allocationId": self.state.allocation_id})
            self.server.post("/provisioning/runs", record)
        except OSError:
            (self.cfg.workdir / "pending-uploads").mkdir(exist_ok=True)
            (self.cfg.workdir / "pending-uploads" / f"{self.state.run_id}.json").write_text(json.dumps(record))
            self._log("manufacturing record queued for upload (offline)")
        self.agent.call("/agent/finish", {})          # deletes the provisioning flag: agent never starts again
        self._log("manufacturing record written", online=self.state.online)

    def _void_serial_if_reserved(self):
        if self.state.serial and self.state.allocation_id and "RECORD" not in self.state.completed:
            try:
                self.server.post(f"/serials/{self.state.serial}/void",
                                 {"allocationId": self.state.allocation_id, "reason": self.state.error})
            except OSError:
                pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
#  CLI
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Stratasys Factory Provisioning Tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    for p in (r,):
        p.add_argument("--station", required=True); p.add_argument("--operator", required=True)
        p.add_argument("--server"); p.add_argument("--workdir", default=os.path.expanduser("~/.stratasys-provisioning"))
        p.add_argument("--trust", default=str(Path(__file__).with_name("trust")))
        p.add_argument("--channel", default="production"); p.add_argument("--role", default="factory")
        p.add_argument("--signed-eeprom"); p.add_argument("--offline-token"); p.add_argument("--station-key")
        p.add_argument("--previous-serial", help="Generate New Serial Number for a re-provisioned unit")
        p.add_argument("--fake", action="store_true", help="dry run with a simulated module")
    a = ap.parse_args(argv)
    if a.channel != "production" and a.role not in ("engineering", "release"):
        ap.error("non-production channels require --role engineering")
    cfg = Config(a.station, a.operator, a.server, Path(a.workdir), Path(a.trust), channel=a.channel, role=a.role,
                 signed_eeprom_dir=Path(a.signed_eeprom) if a.signed_eeprom else None,
                 offline_token=Path(a.offline_token) if a.offline_token else None,
                 station_key=Path(a.station_key) if a.station_key else None)
    if a.fake:
        from tests_support import FakeDeviceAgent   # noqa: F401 - dev only
        # the simulated module trusts the same license keys as a real image would ship
        run = ProvisioningRun(cfg, FakeRpiboot(), FakeDeviceAgent(crypto.TrustStore.from_dir(cfg.trust_dir)),
                              on_event=lambda e, d: print(f"[{d.get('step')}] {e}"))
    else:
        run = ProvisioningRun(cfg, Rpiboot(), DeviceAgent(), on_event=lambda e, d: print(f"[{d.get('step')}] {e}"))
    run.state.previous_serial = a.previous_serial
    st = run.run()
    print()
    if st.result == "READY_FOR_PRODUCTION":
        print("Provisioning Successful\n")
        print(f"Machine Serial:  {st.serial}")
        print(f"Device ID:       {st.device_id}")
        print(f"Image Version:   {st.image['version']}  (build {st.image['buildId']})")
        print(f"Provisioning:    {'Online' if st.online else 'OFFLINE'}")
        print("Device Status:   READY FOR PRODUCTION")
    else:
        print(f"Provisioning FAILED at {st.step.value}: {st.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
