"""End-to-end provisioning flow against the real serial service (in-process)
with a fake CM5 (rpiboot) and a fake module-side agent."""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "provisioning-tool"))
from stratasys_appliance import crypto, manifests  # noqa: E402
import provision  # noqa: E402
from image_catalog import ImageCatalog, CatalogError  # noqa: E402
from rpiboot import FakeRpiboot  # noqa: E402
from tests_support import FakeDeviceAgent  # noqa: E402


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FlaskOpener:
    """urllib.urlopen replacement that routes to a Flask test client; can be
    switched offline to simulate a disconnected station."""

    def __init__(self, client, image_bytes):
        self.c, self.image, self.online = client, image_bytes, True

    def __call__(self, req, timeout=None):
        if not self.online:
            raise urllib.error.URLError("station offline")
        url = req if isinstance(req, str) else req.full_url
        path = url.split("://", 1)[1].split("/", 1)[1]
        path = "/" + path
        if path.startswith("/images/file/"):
            return _Resp(self.image)
        if isinstance(req, str) or req.get_method() == "GET":
            r = self.c.get(path)
        else:
            r = self.c.post(path, data=req.data, headers=dict(req.header_items()))
        if r.status_code >= 400:
            raise urllib.error.HTTPError(url, r.status_code, "err", {}, io.BytesIO(r.data))
        return _Resp(r.data)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SERIAL_DB", str(tmp_path / "s.db"))
    spec = importlib.util.spec_from_file_location("serial_app", ROOT / "serial-service" / "app.py")
    svc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(svc)
    svc.DB_PATH = str(tmp_path / "s.db")
    client = svc.app.test_client()
    keys = client.get("/keys/public").get_json()
    trust = tmp_path / "trust"
    trust.mkdir()
    (trust / "serial-service.pub").write_text(keys["serialServiceKeyPem"])
    (trust / "license.pub").write_text(keys["licenseKeyPem"])
    image = b"fake-image-" * 100
    manifest = {"imageVersion": "1.4.7", "buildId": "SCURE-2026-08-25-147", "product": "SCURE-A", "channel": "qa",
                "sha256": crypto.sha256_hex(image), "sizeBytes": len(image), "releaseDate": "2026-08-25",
                "minHardwareRevision": 3, "requiredFirmwareVersion": "2025-05-08", "productionApproved": False,
                "appVersion": "0.6.7", "url": "/images/file/147"}
    eng = {"X-Stratasys-Role": "engineering", "X-Stratasys-Operator": "e"}
    rel = {"X-Stratasys-Role": "release", "X-Stratasys-Operator": "r"}
    client.post("/images/publish", json={"manifest": manifest}, headers=eng)
    client.post("/images/publish", json={"manifest": dict(manifest, imageVersion="1.5.0-beta.12", buildId="B150",
                                                            channel="development")}, headers=eng)
    opener = FlaskOpener(client, image)
    lic_trust = crypto.TrustStore.from_dir(trust, pattern="license.pub")
    cfg = provision.Config("ST-01", "amitai", "http://svc", tmp_path / "work", trust,
                           profiles_file=ROOT / "provisioning-tool" / "hardware-profiles.yaml",
                           signed_eeprom_dir=tmp_path / "eeprom")
    (tmp_path / "eeprom").mkdir()
    (tmp_path / "eeprom" / "config.txt").write_text("program_pubkey=1\nrevoke_devkey=1\nprogram_jtag_lock=1\n")

    def make_run(agent=None, rpi=None, offline_token=None, station_key=None, previous=None):
        cfg.offline_token, cfg.station_key = offline_token, station_key
        catalog = ImageCatalog("http://svc", crypto.TrustStore.from_dir(trust), tmp_path / "work" / "cache",
                               opener=opener)
        server = provision.ServerClient("http://svc", "factory", "amitai", opener=opener)
        run = provision.ProvisioningRun(cfg, rpi or FakeRpiboot(), agent or FakeDeviceAgent(lic_trust),
                                        catalog=catalog, server=server)
        run.state.previous_serial = previous
        return run

    return dict(client=client, opener=opener, make_run=make_run, rel=rel, lic_trust=lic_trust, tmp=tmp_path, image=image)


def test_refuses_to_flash_when_nothing_is_production_approved(world):
    run = world["make_run"]()
    st = run.run()
    assert st.result == "FAILED" and st.step.value == "FAILED"
    assert "no production image" in st.error or "approved" in st.error.lower()


def test_full_online_provisioning(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    agent = FakeDeviceAgent(world["lic_trust"])
    rpi = FakeRpiboot()
    run = world["make_run"](agent, rpi)
    st = run.run()
    assert st.result == "READY_FOR_PRODUCTION", st.error
    assert st.serial == "SC000001" and st.device_id == agent.device_id and st.online
    assert st.image["version"] == "1.4.7"                       # not the 1.5.0-beta.12 dev build
    assert rpi.flashed and rpi.programmed and agent.finished and agent.license_state == "VALID"
    events = [e["event"] for e in st.log]
    assert "Image Signature: VALID · Image Status: READY FOR INSTALLATION" in events
    # serial committed + run recorded + machine ready in the DB
    last = world["client"].get("/serials/last", headers={"X-Stratasys-Role": "factory"}).get_json()
    assert last["lastSerial"] == "SC000001"
    audit = world["client"].get("/audit?serial=SC000001", headers={"X-Stratasys-Role": "factory"}).get_json()
    assert {"Serial number committed", "License issued", "Provisioning run recorded"} <= {e["event"] for e in audit["entries"]}
    rec = json.loads((world["tmp"] / "work" / "SC000001.record.json").read_text())
    assert rec["buildId"] == "SCURE-2026-08-25-147" and rec["online"] is True

    # second unit: cache hit, next serial, distinct device
    run2 = world["make_run"](FakeDeviceAgent(world["lic_trust"], otp=b"\x99" * 32), FakeRpiboot())
    st2 = run2.run()
    assert st2.result == "READY_FOR_PRODUCTION" and st2.serial == "SC000002"
    assert st2.image["path"] == st.image["path"]


def test_generate_new_serial_for_reprovisioned_unit(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    st = world["make_run"](FakeDeviceAgent(world["lic_trust"])).run()
    assert st.serial == "SC000001"
    st2 = world["make_run"](FakeDeviceAgent(world["lic_trust"]), previous="SC000001").run()
    assert st2.result == "READY_FOR_PRODUCTION" and st2.serial == "SC000002"
    assert st2.license["payload"]["previousSerial"] == "SC000001"


def test_offline_station_uses_cache_range_token_and_provisional_license(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    # first unit online: fills the cache
    assert world["make_run"](FakeDeviceAgent(world["lic_trust"])).run().result == "READY_FOR_PRODUCTION"
    # station prepares for offline work: range token + station key trusted by the device image
    tok = world["client"].post("/serials/ranges", json={"stationId": "ST-01", "operator": "amitai", "size": 3},
                               headers={"X-Stratasys-Role": "factory", "X-Stratasys-Operator": "amitai"}).get_json()["token"]
    tok_path = world["tmp"] / "range.json"
    tok_path.write_text(json.dumps(tok))
    station_key = crypto.generate_private_key()
    crypto.save_private_key(station_key, world["tmp"] / "station.key")
    device_trust = crypto.TrustStore({**world["lic_trust"].keys, crypto.key_id(station_key.public_key()): station_key.public_key()})
    world["opener"].online = False
    agent = FakeDeviceAgent(device_trust, otp=b"\x77" * 32)
    st = world["make_run"](agent, offline_token=tok_path, station_key=world["tmp"] / "station.key").run()
    assert st.result == "READY_FOR_PRODUCTION", st.error
    assert st.online is False and st.provisional is True
    assert st.serial == "SC000002"                            # first number of the range
    assert st.license["payload"]["provisional"] and st.license["payload"]["expiresAt"]
    assert any("OFFLINE MODE" in e.get("status", "") for e in st.log)
    assert (world["tmp"] / "work" / "pending-uploads").exists()
    st2 = world["make_run"](FakeDeviceAgent(device_trust, otp=b"\x78" * 32), offline_token=tok_path,
                            station_key=world["tmp"] / "station.key").run()
    assert st2.serial == "SC000003"                           # strictly ascending from the station ledger


def test_corrupted_cache_is_rejected_and_redownloaded(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    run = world["make_run"](FakeDeviceAgent(world["lic_trust"]))
    run.step_fetch_approved_image()
    path = Path(run.state.image["path"])
    path.write_bytes(b"tampered" * 100)
    run2 = world["make_run"](FakeDeviceAgent(world["lic_trust"]))
    run2.step_fetch_approved_image()                          # re-downloads a good copy
    assert crypto.sha256_file(run2.state.image["path"]) == run2.state.image["sha256"]
    # offline with a corrupted cache: hard stop, nothing is flashed
    path.write_bytes(b"tampered" * 100)
    world["opener"].online = False
    with pytest.raises(CatalogError):
        run3 = world["make_run"](FakeDeviceAgent(world["lic_trust"]))
        run3.step_fetch_approved_image()


def test_unsupported_module_is_refused_before_flashing(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    rpi = FakeRpiboot()
    rpi.info.board_revision = "c03111"                        # a CM4
    st = world["make_run"](FakeDeviceAgent(world["lic_trust"]), rpi).run()
    assert st.result == "FAILED" and "unsupported module" in st.error and not rpi.flashed


def test_license_rejected_by_device_fails_run(world):
    world["client"].post("/images/SCURE-2026-08-25-147/approve", json={"approvedBy": "qa"}, headers=world["rel"])
    wrong_trust = crypto.TrustStore.of([crypto.generate_private_key().public_key()])
    st = world["make_run"](FakeDeviceAgent(wrong_trust)).run()
    assert st.result == "FAILED" and "rejected the license" in st.error
