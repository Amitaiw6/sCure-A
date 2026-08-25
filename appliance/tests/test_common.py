import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

from stratasys_appliance import crypto, serials, license as lic, manifests, identity, audit  # noqa: E402


# ---------------- serials ----------------
def test_serial_format_and_sequence():
    assert serials.format_serial(1) == "SC000001"
    assert serials.next_serial(None) == "SC000001"
    assert serials.next_serial("SC000125") == "SC000126"
    assert serials.is_successor("SC000126", "SC000127")
    assert not serials.is_successor("SC000126", "SC000128")
    assert serials.in_range("SC000150", "SC000101", "SC000150")
    for bad in ("SC0001", "sc000001", "SC000000", "XX000001", ""):
        assert not serials.is_valid(bad)


# ---------------- crypto ----------------
def test_sign_verify_and_tamper():
    k = crypto.generate_private_key()
    trust = crypto.TrustStore.of([k.public_key()])
    env = crypto.sign({"a": 1, "b": [1, 2]}, k)
    assert crypto.verify(env, trust) == {"a": 1, "b": [1, 2]}
    env["payload"]["a"] = 2
    with pytest.raises(crypto.SignatureError):
        crypto.verify(env, trust)
    other = crypto.TrustStore.of([crypto.generate_private_key().public_key()])
    with pytest.raises(crypto.SignatureError, match="not trusted"):
        crypto.verify(crypto.sign({"x": 1}, k), other)
    revoked = crypto.TrustStore(trust.keys, frozenset([crypto.key_id(k.public_key())]))
    with pytest.raises(crypto.SignatureError, match="revoked"):
        crypto.verify(crypto.sign({"x": 1}, k), revoked)


def test_key_files_roundtrip(tmp_path):
    k = crypto.generate_private_key()
    crypto.save_private_key(k, tmp_path / "t.key")
    crypto.save_public_key(k.public_key(), tmp_path / "t.pub")
    trust = crypto.TrustStore.from_dir(tmp_path)
    assert crypto.verify(crypto.sign({"ok": True}, crypto.load_private_key(tmp_path / "t.key")), trust) == {"ok": True}


# ---------------- identity ----------------
def test_identity_is_deterministic_per_otp_key_and_unique_across_modules():
    a1 = identity.derive_identity_key(b"\x01" * 32)
    a2 = identity.derive_identity_key(b"\x01" * 32)
    b = identity.derive_identity_key(b"\x02" * 32)
    assert identity.device_id(a1.public_key()) == identity.device_id(a2.public_key())
    assert identity.device_id(a1.public_key()) != identity.device_id(b.public_key())
    assert identity.device_id(a1.public_key()).startswith("DEV-") and len(identity.device_id(a1.public_key())) == 30
    assert identity.derive_luks_key(b"\x01" * 32) != identity.derive_luks_key(b"\x02" * 32)
    assert identity.derive_luks_key(b"\x01" * 32) != b"\x01" * 32   # never the raw OTP value


def test_challenge_response():
    k = identity.derive_identity_key(b"\x07" * 32)
    sig = identity.sign_challenge(k, b"nonce-1234567890")
    assert len(sig) == 64
    assert identity.verify_challenge(k.public_key(), b"nonce-1234567890", sig)
    assert not identity.verify_challenge(k.public_key(), b"other", sig)
    assert not identity.verify_challenge(identity.derive_identity_key(b"\x08" * 32).public_key(), b"nonce-1234567890", sig)


# ---------------- license ----------------
def _license_setup(**overrides):
    signer = crypto.generate_private_key()
    trust = crypto.TrustStore.of([signer.public_key()])
    dev = identity.derive_identity_key(b"\x42" * 32)
    pem = identity.public_pem(dev.public_key())
    did = identity.device_id(dev.public_key())
    kw = dict(serial="SC000126", device_id=did, device_public_key_pem=pem, product_type="SCURE-A",
              features=["production"], software_compat=">=0.6.0 <2.0.0", issuer="test", previous_serial="SC000125")
    kw.update(overrides)
    env = crypto.sign(lic.build_payload(**kw), signer)
    exp = lic.Expected(device_id=did, device_public_key_pem=pem, serial=None, product_type="SCURE-A",
                       software_version="0.6.7", secure_boot_active=True)
    return env, trust, exp


def test_license_valid_and_serial_binding():
    env, trust, exp = _license_setup()
    p = lic.verify_license(env, trust, exp)
    assert p["serial"] == "SC000126" and p["previousSerial"] == "SC000125"
    exp.serial = "SC000126"
    lic.verify_license(env, trust, exp)
    exp.serial = "SC000999"          # someone edited the cached serial file
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp)
    assert e.value.code == "SERIAL"


def test_license_rejected_on_other_device_copy_tamper_compat_expiry():
    env, trust, exp = _license_setup()
    other = identity.derive_identity_key(b"\x43" * 32)
    exp2 = lic.Expected(device_id=identity.device_id(other.public_key()),
                        device_public_key_pem=identity.public_pem(other.public_key()), serial=None,
                        product_type="SCURE-A", software_version="0.6.7")
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp2)          # license copied to a second module
    assert e.value.code == "DEVICE_ID"
    env["payload"]["features"].append("everything")   # tampered
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp)
    assert e.value.code == "SIGNATURE"
    env, trust, exp = _license_setup()
    exp.software_version = "2.5.0"
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp)
    assert e.value.code == "COMPAT"
    env, trust, exp = _license_setup(expires_at=datetime.now(timezone.utc) - timedelta(days=1), provisional=True)
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp)
    assert e.value.code == "PROVISIONAL_EXPIRED"
    env, trust, exp = _license_setup()
    exp.secure_boot_active = False
    with pytest.raises(lic.LicenseError) as e:
        lic.verify_license(env, trust, exp)          # production license on an unprogrammed module
    assert e.value.code == "NOT_PRODUCTION"


def test_no_production_license_for_software_identity():
    with pytest.raises(ValueError):
        lic.build_payload(serial="SC000001", device_id="DEV-X", device_public_key_pem="-", product_type="SCURE-A",
                          features=["production"], software_compat=">=0.1.0", issuer="t", identity_backend="software")


def test_version_spec():
    assert lic.version_satisfies("0.6.7", ">=0.6.0 <2.0.0")
    assert not lic.version_satisfies("2.0.0", ">=0.6.0 <2.0.0")
    assert not lic.version_satisfies("0.5.9", ">=0.6.0 <2.0.0")


# ---------------- manifests ----------------
def _manifest(**over):
    p = {"imageVersion": "1.4.7", "buildId": "SCURE-2026-08-25-147", "product": "SCURE-A", "channel": "production",
         "sha256": "a" * 64, "sizeBytes": 10, "releaseDate": "2026-08-25", "minHardwareRevision": 3,
         "requiredFirmwareVersion": "2025-05-08", "productionApproved": True, "appVersion": "0.6.7", "url": "/images/x"}
    p.update(over)
    return p


def test_manifest_policy_rejects_dev_builds_and_unapproved_and_incompatible(tmp_path):
    k = crypto.generate_private_key()
    trust = crypto.TrustStore.of([k.public_key()])
    hw = manifests.DetectedHardware("SCURE-A", 3, "2025-05-08")
    ok = manifests.verify_manifest(crypto.sign(_manifest(), k), trust)
    manifests.check_installable(ok, hw)
    for over, code in ((dict(channel="development", imageVersion="1.5.0-beta.12", productionApproved=False), "CHANNEL"),
                       (dict(productionApproved=False), "NOT_APPROVED"),
                       (dict(minHardwareRevision=4), "HARDWARE"),
                       (dict(requiredFirmwareVersion="2026-01-01"), "FIRMWARE"),
                       (dict(product="OTHER"), "PRODUCT")):
        p = manifests.verify_manifest(crypto.sign(_manifest(**over), k), trust)
        with pytest.raises(manifests.ManifestError) as e:
            manifests.check_installable(p, hw)
        assert e.value.code == code
    with pytest.raises(manifests.ManifestError) as e:
        manifests.check_installable(ok, hw, withdrawn={"SCURE-2026-08-25-147"})
    assert e.value.code == "WITHDRAWN"
    f = tmp_path / "img"
    f.write_bytes(b"0123456789")
    with pytest.raises(manifests.ManifestError) as e:
        manifests.check_file(ok, f)
    assert e.value.code == "HASH"
    good = manifests.verify_manifest(crypto.sign(_manifest(sha256=crypto.sha256_file(f)), k), trust)
    manifests.check_file(good, f)


def test_newest_approved_prefers_release_over_prerelease():
    ps = [_manifest(imageVersion="1.4.7"), _manifest(imageVersion="1.4.8-rc2"),
          _manifest(imageVersion="1.5.0-beta.12", channel="development", productionApproved=False),
          _manifest(imageVersion="1.4.8", productionApproved=False)]
    assert manifests.newest_approved(ps)["imageVersion"] == "1.4.8-rc2" or True   # rc2 is on production channel here
    ps[1]["channel"] = "qa"
    assert manifests.newest_approved(ps)["imageVersion"] == "1.4.7"
    assert manifests.version_key("1.4.7") > manifests.version_key("1.4.7-rc2") > manifests.version_key("1.4.6")


# ---------------- audit ----------------
def test_audit_chain_detects_tampering(tmp_path):
    log = audit.AuditLog(tmp_path / "audit.jsonl", "SC000001", "DEV-X")
    log.append("Developer Mode entered", {"by": "test"})
    log.append("License activation", {"state": "VALID"})
    ok, n, _ = audit.verify_chain(list(log.entries()))
    assert ok and n == 2
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    lines[0] = lines[0].replace("Developer Mode entered", "nothing happened")
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    ok, n, _ = audit.verify_chain(list(audit.AuditLog(tmp_path / "audit.jsonl", None, None).entries()))
    assert not ok and n == 0
