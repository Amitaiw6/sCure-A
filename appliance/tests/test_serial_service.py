import base64
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
from stratasys_appliance import crypto, identity, manifests  # noqa: E402


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("SERIAL_DB", str(tmp_path / "t.db"))
    spec = importlib.util.spec_from_file_location("serial_app", ROOT / "serial-service" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DB_PATH = str(tmp_path / "t.db")
    mod.app.config["TESTING"] = True
    return mod


def H(role="factory", op="tester"):
    return {"X-Stratasys-Role": role, "X-Stratasys-Operator": op}


def test_allocation_is_sequential_never_reused_and_role_gated(svc):
    c = svc.app.test_client()
    assert c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}).status_code == 403   # no role
    r1 = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    r2 = c.post("/serials/allocate", json={"stationId": "ST2", "operator": "b"}, headers=H()).get_json()
    assert (r1["serial"], r2["serial"]) == ("SC000001", "SC000002")
    # voiding a reserved serial burns it: the next allocation is still 3
    assert c.post(f"/serials/{r2['serial']}/void", json={"allocationId": r2["allocationId"], "reason": "failed"}, headers=H()).get_json()["state"] == "VOID"
    r3 = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    assert r3["serial"] == "SC000003"
    assert c.post(f"/serials/{r1['serial']}/commit", json={"allocationId": r1["allocationId"]}, headers=H()).get_json()["state"] == "ASSIGNED"
    assert c.post(f"/serials/{r1['serial']}/void", json={"allocationId": r1["allocationId"]}, headers=H()).status_code == 409
    last = c.get("/serials/last", headers=H()).get_json()
    assert last["lastSerial"] == "SC000003" and last["nextSerial"] == "SC000004"


def test_generate_new_serial_records_previous_and_audits(svc):
    c = svc.app.test_client()
    r1 = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    bad = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a", "reason": "reassignment"}, headers=H())
    assert bad.status_code == 400                       # reassignment must name the previous serial
    r2 = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a", "reason": "reassignment",
                                           "previousSerial": r1["serial"]}, headers=H("service")).get_json()
    assert r2["serial"] == "SC000002" and r2["previousSerial"] == "SC000001"
    a = c.get("/audit", headers=H()).get_json()
    assert a["chainIntact"] and any(e["event"] == "Serial number reassigned" for e in a["entries"])


def test_concurrent_allocations_are_unique(svc):
    results, errors = [], []

    def worker():
        try:
            with svc.app.test_client() as c:
                r = c.post("/serials/allocate", json={"stationId": "ST", "operator": "x"}, headers=H()).get_json()
                results.append(r["serial"])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert len(results) == 20 and len(set(results)) == 20
    assert sorted(results) == [f"SC{n:06d}" for n in range(1, 21)]


def test_offline_range_token_and_reconcile(svc):
    c = svc.app.test_client()
    tok = c.post("/serials/ranges", json={"stationId": "ST9", "operator": "o", "size": 5}, headers=H()).get_json()["token"]
    pub = crypto.load_public_key(c.get("/keys/public").get_json()["serialServiceKeyPem"].encode())
    p = crypto.verify(tok, crypto.TrustStore.of([pub]))
    assert (p["first"], p["last"], p["stationId"]) == ("SC000001", "SC000005", "ST9")
    # the range burned the numbers: online allocation continues after it
    assert c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()["serial"] == "SC000006"
    rec = c.post(f"/serials/ranges/{p['rangeId']}/reconcile", json={"used": ["SC000001", "SC000002"]}, headers=H()).get_json()
    assert rec["assigned"] == ["SC000001", "SC000002"] and rec["voided"] == ["SC000003", "SC000004", "SC000005"]


def test_device_registration_requires_proof_and_license_binds(svc):
    c = svc.app.test_client()
    dev = identity.derive_identity_key(b"\x11" * 32)
    pem = identity.public_pem(dev.public_key())
    nonce = b"n" * 32
    body = {"publicKeyPem": pem, "identityBackend": "otp-hkdf", "boardSerial": "abc", "secureBoot": True,
            "nonce": base64.b64encode(nonce).decode(),
            "nonceSignature": base64.b64encode(identity.sign_challenge(dev, b"wrong")).decode()}
    assert c.post("/devices/register", json=body, headers=H()).status_code == 400
    body["nonceSignature"] = base64.b64encode(identity.sign_challenge(dev, nonce)).decode()
    r = c.post("/devices/register", json=body, headers=H()).get_json()
    assert r["deviceId"] == identity.device_id(dev.public_key())
    s = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    lic_resp = c.post("/licenses/issue", json={"serial": s["serial"], "deviceId": r["deviceId"]}, headers=H()).get_json()
    env = lic_resp["license"]
    lic_pub = crypto.load_public_key(c.get("/keys/public").get_json()["licenseKeyPem"].encode())
    p = crypto.verify(env, crypto.TrustStore.of([lic_pub]))
    assert p["serial"] == s["serial"] and p["deviceId"] == r["deviceId"] and "production" in p["features"]
    # a module without secure boot never gets a production license
    body["secureBoot"] = False
    dev2 = identity.derive_identity_key(b"\x12" * 32)
    body.update(publicKeyPem=identity.public_pem(dev2.public_key()),
                nonceSignature=base64.b64encode(identity.sign_challenge(dev2, nonce)).decode())
    r2 = c.post("/devices/register", json=body, headers=H()).get_json()
    s2 = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    p2 = c.post("/licenses/issue", json={"serial": s2["serial"], "deviceId": r2["deviceId"]}, headers=H()).get_json()["license"]["payload"]
    assert "production" not in p2["features"]


def test_image_catalog_only_serves_production_approved(svc):
    c = svc.app.test_client()
    base = {"imageVersion": "1.4.7", "buildId": "B147", "product": "SCURE-A", "channel": "qa", "sha256": "a" * 64,
            "sizeBytes": 1, "releaseDate": "2026-08-25", "minHardwareRevision": 3, "requiredFirmwareVersion": "2025-05-08",
            "productionApproved": False, "appVersion": "0.6.7", "url": "/images/B147"}
    assert c.post("/images/publish", json={"manifest": base}, headers=H("factory")).status_code == 403
    assert c.post("/images/publish", json={"manifest": base}, headers=H("engineering")).get_json()["ok"]
    dev = dict(base, imageVersion="1.5.0-beta.12", buildId="B150", channel="development")
    assert c.post("/images/publish", json={"manifest": dev}, headers=H("engineering")).get_json()["ok"]
    assert c.get("/images/latest?product=SCURE-A&channel=production").status_code == 404
    assert c.post("/images/B147/approve", json={"approvedBy": "qa-lead"}, headers=H("engineering")).status_code == 403
    assert c.post("/images/B147/approve", json={"approvedBy": "qa-lead"}, headers=H("release")).get_json()["ok"]
    latest = c.get("/images/latest?product=SCURE-A&channel=production").get_json()
    assert latest["manifest"]["payload"]["imageVersion"] == "1.4.7"
    assert latest["versions"] == {"development": "1.5.0-beta.12", "qa": None, "production": "1.4.7"}
    pub = crypto.load_public_key(latest["signerPublicKeyPem"].encode())
    p = manifests.verify_manifest(latest["manifest"], crypto.TrustStore.of([pub]))
    manifests.check_installable(p, manifests.DetectedHardware("SCURE-A", 3, "2025-05-08"))
    assert c.post("/images/B147/withdraw", headers=H("release")).get_json()["ok"]
    assert c.get("/images/withdrawn").get_json()["withdrawn"] == ["B147"]
    assert c.get("/images/latest?product=SCURE-A&channel=production").status_code == 404


def test_provisioning_run_record_and_traceability(svc):
    c = svc.app.test_client()
    s = c.post("/serials/allocate", json={"stationId": "ST1", "operator": "a"}, headers=H()).get_json()
    rec = {"runId": "r1", "serial": s["serial"], "stationId": "ST1", "operator": "a", "imageVersion": "1.4.7",
           "buildId": "B147", "imageSha256": "a" * 64, "appVersion": "0.6.7", "online": False,
           "result": "READY_FOR_PRODUCTION", "stepLog": [], "startedAt": "2026-08-25T10:00:00Z", "finishedAt": "2026-08-25T10:20:00Z"}
    assert c.post("/provisioning/runs", json=rec, headers=H()).get_json()["ok"]
    a = c.get(f"/audit?serial={s['serial']}", headers=H()).get_json()
    ev = [e for e in a["entries"] if e["event"] == "Provisioning run recorded"][0]
    assert ev["detail"]["online"] is False and ev["detail"]["imageVersion"] == "1.4.7"
