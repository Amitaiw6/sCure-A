#!/usr/bin/env python3
"""stratasys-security — device-side security service (runs as user `security`).

Responsibilities (ARCHITECTURE.md §1.4, §6, §7, §13):
  * take the identity key material handed over by the signed initramfs
    (/run/stratasys/identity.key, 0400, consumed and shredded at start)
    or fall back to a software identity on lab units
  * verify the license at start and every LICENSE_RECHECK_SEC
  * verify application integrity (file manifest) at start
  * own the hash-chained audit log
  * expose a read-only local API on a Unix socket / 127.0.0.1:8442 for the
    hardware service and the kiosk:
        GET  /security/status      {productionMode, licenseState, serial, deviceId, integrity, secureBoot}
        GET  /security/serial
        POST /security/audit       {event, detail, actor}     (other services request writes)
        POST /security/challenge   {nonce}  -> signature (used by the update client / portal)
  * provisioning-agent endpoints under /agent/* exist ONLY while the factory
    flag /data/provisioning.flag exists (removed by /agent/finish)

Production Mode is entered only when: secure boot active (or lab build),
integrity OK, license VALID. Otherwise `productionMode=false` and the kiosk
shows the Service / Integrity / License screen; hardware outputs stay safe.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from stratasys_appliance import crypto, identity, audit, license as lic  # noqa: E402

DATA = Path(os.environ.get("STRATASYS_DATA", "/data"))
KEYS = Path(os.environ.get("STRATASYS_KEYS", "/usr/share/stratasys/keys"))
RUN = Path(os.environ.get("STRATASYS_RUN", "/run/stratasys"))
APP_MANIFEST = Path(os.environ.get("STRATASYS_APP_MANIFEST", "/usr/share/stratasys/app-manifest.json"))
PRODUCT = os.environ.get("STRATASYS_PRODUCT", "SCURE-A")
VERSION_FILE = Path(os.environ.get("STRATASYS_VERSION_FILE", "/usr/share/stratasys/VERSION"))
LICENSE_RECHECK_SEC = int(os.environ.get("LICENSE_RECHECK_SEC", "600"))
LAB_BUILD = os.environ.get("STRATASYS_LAB_BUILD", "0") == "1"

app = Flask(__name__)


class SecurityState:
    def __init__(self):
        self.lock = threading.Lock()
        self.identity_key = None
        self.identity_backend = "software"
        self.public_pem = None
        self.device_id = None
        self.serial = None
        self.license_env = None
        self.license_state = "MISSING"
        self.license_error = None
        self.integrity = "UNKNOWN"
        self.secure_boot = False
        self.software_version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"
        self.trust = crypto.TrustStore.from_dir(KEYS, pattern="license-*.pub") if KEYS.exists() else crypto.TrustStore({})
        self.audit: audit.AuditLog | None = None

    # ---------------- identity ----------------
    def load_identity(self):
        handoff = RUN / "identity.key"
        soft = DATA / "identity" / "software-identity.pem"
        if handoff.exists():
            # 32-byte OTP-derived secret from the initramfs -> same HKDF as the initramfs used for the pubkey
            secret = handoff.read_bytes()
            try:
                handoff.write_bytes(os.urandom(len(secret)))    # shred before unlink
            finally:
                handoff.unlink(missing_ok=True)
            self.identity_key = identity.derive_identity_key(secret)
            self.identity_backend = "otp-hkdf"
            self.secure_boot = identity.secure_boot_active()
        elif soft.exists():
            self.identity_key = identity.load_software_identity(soft)
            self.identity_backend = "software"
        else:
            soft.parent.mkdir(parents=True, exist_ok=True)
            self.identity_key = identity.create_software_identity(soft)
            self.identity_backend = "software"
        self.public_pem = identity.public_pem(self.identity_key.public_key())
        self.device_id = identity.device_id(self.identity_key.public_key())
        cached = DATA / "identity" / "serial"
        self.serial = cached.read_text().strip() if cached.exists() else None
        self.audit = audit.AuditLog(DATA / "audit" / "audit.jsonl", self.serial, self.device_id)

    # ---------------- integrity ----------------
    def check_integrity(self):
        """Defence in depth on top of dm-verity: re-hash the app manifest."""
        if not APP_MANIFEST.exists():
            self.integrity = "OK" if LAB_BUILD else "NO_MANIFEST"
            return
        try:
            m = json.loads(APP_MANIFEST.read_text())
            bad = [f for f, h in m["files"].items() if not Path(f).exists() or crypto.sha256_file(f) != h]
            self.integrity = "OK" if not bad else "FAILED"
            if bad:
                self.audit.append("Failed integrity check", {"files": bad[:20], "count": len(bad)})
        except (OSError, ValueError, KeyError) as e:
            self.integrity = "FAILED"
            self.audit.append("Failed integrity check", {"error": str(e)})

    # ---------------- license ----------------
    def check_license(self):
        path = DATA / "license.json"
        if not path.exists():
            self.license_state, self.license_error = "MISSING", "no license installed"
            return
        try:
            env = json.loads(path.read_text())
            p = lic.verify_license(env, self.trust, lic.Expected(
                device_id=self.device_id, device_public_key_pem=self.public_pem, serial=self.serial,
                product_type=PRODUCT, software_version=self.software_version,
                secure_boot_active=self.secure_boot or LAB_BUILD, identity_backend=self.identity_backend))
            # the license is the authority for the serial; the cached file is just a cache
            if self.serial != p["serial"]:
                (DATA / "identity").mkdir(parents=True, exist_ok=True)
                (DATA / "identity" / "serial").write_text(p["serial"] + "\n")
                self.serial = p["serial"]
                self.audit.serial = p["serial"]
            self.license_env, self.license_state, self.license_error = env, "VALID", None
        except (OSError, ValueError) as e:
            self.license_state, self.license_error = "INVALID:MALFORMED", str(e)
        except lic.LicenseError as e:
            self.license_state, self.license_error = f"INVALID:{e.code}", str(e)
        if self.license_state != "VALID":
            self.audit.append("Failed license validation", {"state": self.license_state, "reason": self.license_error})

    @property
    def production_mode(self) -> bool:
        return (self.license_state == "VALID" and self.integrity == "OK"
                and (self.secure_boot or LAB_BUILD))

    def status(self) -> dict:
        return {"ok": True, "productionMode": self.production_mode, "licenseState": self.license_state,
                "licenseError": self.license_error, "serial": self.serial, "deviceId": self.device_id,
                "identityBackend": self.identity_backend, "integrity": self.integrity,
                "secureBoot": self.secure_boot, "appVersion": self.software_version,
                "features": (self.license_env or {}).get("payload", {}).get("features", []),
                "provisional": (self.license_env or {}).get("payload", {}).get("provisional", False)}


S = SecurityState()


def _recheck_loop():
    while True:
        time.sleep(LICENSE_RECHECK_SEC)
        with S.lock:
            before = S.license_state
            S.check_license()
            if before == "VALID" and S.license_state != "VALID":
                S.audit.append("Security violation", {"event": "license became invalid at runtime", "state": S.license_state})


def _provisioning_mode() -> bool:
    return (DATA / "provisioning.flag").exists()


# --------------------------------------------------------------------------
#  read-only API for the app
# --------------------------------------------------------------------------
@app.get("/security/status")
def status():
    with S.lock:
        return jsonify(S.status())


@app.get("/security/serial")
def serial():
    with S.lock:
        return jsonify({"ok": S.serial is not None, "serial": S.serial, "deviceId": S.device_id})


@app.post("/security/audit")
def audit_write():
    d = request.get_json(silent=True) or {}
    if not d.get("event"):
        return jsonify({"ok": False, "error": "event required"}), 400
    with S.lock:
        e = S.audit.append(str(d["event"])[:120], d.get("detail") or {}, actor=str(d.get("actor", "app"))[:60])
    return jsonify({"ok": True, "hash": e["hash"]})


@app.post("/security/challenge")
def challenge():
    d = request.get_json(silent=True) or {}
    try:
        nonce = base64.b64decode(d["nonce"], validate=True)
    except (KeyError, ValueError):
        return jsonify({"ok": False, "error": "nonce required (base64)"}), 400
    if len(nonce) < 16:
        return jsonify({"ok": False, "error": "nonce too short"}), 400
    with S.lock:
        sig = identity.sign_challenge(S.identity_key, nonce)
    return jsonify({"ok": True, "deviceId": S.device_id, "signature": base64.b64encode(sig).decode()})


# --------------------------------------------------------------------------
#  provisioning agent (factory only, until /agent/finish)
# --------------------------------------------------------------------------
@app.before_request
def _gate_agent():
    if request.path.startswith("/agent/") and not _provisioning_mode():
        return jsonify({"ok": False, "error": "not in provisioning mode"}), 404


@app.get("/agent/status")
def agent_status():
    with S.lock:
        return jsonify(S.status())


@app.post("/agent/identity")
def agent_identity():
    d = request.get_json(silent=True) or {}
    nonce = base64.b64decode(d["nonce"])
    with S.lock:
        info = identity.read_board_info()
        sig = identity.sign_challenge(S.identity_key, nonce)
        fp = identity.hardware_fingerprint(info["boardSerial"], info["boardRevision"], "", "")
        S.audit.append("Device identity created", {"deviceId": S.device_id, "backend": S.identity_backend}, actor="factory")
        return jsonify({"ok": True, "publicKeyPem": S.public_pem, "deviceId": S.device_id,
                        "identityBackend": S.identity_backend, "secureBoot": S.secure_boot,
                        "fingerprint": fp, "boardSerial": info["boardSerial"],
                        "nonceSignature": base64.b64encode(sig).decode()})


@app.post("/agent/license")
def agent_license():
    d = request.get_json(silent=True) or {}
    env = d.get("license")
    if not isinstance(env, dict):
        return jsonify({"ok": False, "error": "license envelope required"}), 400
    with S.lock:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = DATA / "license.json.tmp"
        tmp.write_text(json.dumps(env, indent=2))
        os.chmod(tmp, 0o400)
        os.replace(tmp, DATA / "license.json")
        S.check_license()
        S.audit.append("License activation", {"state": S.license_state, "serial": S.serial}, actor="factory")
        return jsonify({"ok": S.license_state == "VALID", "licenseState": S.license_state,
                        "error": S.license_error, "serial": S.serial})


@app.post("/agent/encrypt-data")
def agent_encrypt():
    """On the module this calls the initramfs-shared helper that formats the
    data partition with the OTP-derived key and a random recovery passphrase
    (returned encrypted to the Stratasys KMS public key). Here: delegate."""
    helper = Path("/usr/lib/stratasys/encrypt-data.sh")
    if not helper.exists():
        return jsonify({"ok": False, "error": "encrypt-data helper not present (lab image)"}), 501
    import subprocess
    r = subprocess.run([str(helper)], capture_output=True, text=True)
    if r.returncode != 0:
        return jsonify({"ok": False, "error": r.stderr.strip()[-400:]}), 500
    with S.lock:
        S.audit.append("Data partition encrypted", {}, actor="factory")
    return jsonify({"ok": True, **json.loads(r.stdout)})


@app.post("/agent/apply-policy")
def agent_policy():
    helper = Path("/usr/lib/stratasys/apply-policy.sh")
    if helper.exists():
        import subprocess
        r = subprocess.run([str(helper)], capture_output=True, text=True)
        if r.returncode != 0:
            return jsonify({"ok": False, "error": r.stderr.strip()[-400:]}), 500
    with S.lock:
        S.audit.append("Configuration change", {"policy": "kiosk+usbguard+users"}, actor="factory")
    return jsonify({"ok": True})


@app.post("/agent/self-test")
def agent_self_test():
    """Ask the hardware service for its diagnostics (existing /api/diagnostics/*)."""
    import urllib.request
    tests = {}
    for name, path in (("leds", "/api/diagnostics/led-test"), ("fans", "/api/diagnostics/fan-test")):
        try:
            req = urllib.request.Request("http://127.0.0.1:3001" + path, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                tests[name] = bool(json.loads(r.read()).get("ok", True))
        except Exception:  # noqa: BLE001
            tests[name] = False
    with S.lock:
        S.audit.append("Factory test results", tests, actor="factory")
    return jsonify({"ok": all(tests.values()), "tests": tests})


@app.post("/agent/finish")
def agent_finish():
    with S.lock:
        (DATA / "provisioning.flag").unlink(missing_ok=True)
        S.audit.append("Provisioning completed", {"serial": S.serial}, actor="factory")
    return jsonify({"ok": True})


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    with S.lock:
        S.load_identity()
        S.check_integrity()
        S.check_license()
        S.audit.append("Security service started", {"productionMode": S.production_mode,
                                                    "licenseState": S.license_state, "integrity": S.integrity,
                                                    "secureBoot": S.secure_boot})
    threading.Thread(target=_recheck_loop, daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8442")))


if __name__ == "__main__":
    main()
