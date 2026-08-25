"""Fakes for dry runs and tests: a simulated module-side provisioning agent."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from stratasys_appliance import identity, license as lic, crypto  # noqa: E402


class FakeDeviceAgent:
    """Behaves like stratasys-provisioning-agent on a CM5 in provisioning
    mode: holds an identity key (derived from a fake OTP secret), verifies
    the license it is handed with the trust store, reports status."""

    def __init__(self, trust: crypto.TrustStore | None = None, secure_boot=True, otp=b"\x42" * 32,
                 app_version="0.6.7", product="SCURE-A"):
        self.key = identity.derive_identity_key(otp)
        self.pub_pem = identity.public_pem(self.key.public_key())
        self.device_id = identity.device_id(self.key.public_key())
        self.trust = trust
        self.secure_boot = secure_boot
        self.app_version = app_version
        self.product = product
        self.license = None
        self.license_state = "MISSING"
        self.serial = None
        self.encrypted = False
        self.policy = False
        self.finished = False
        self.calls: list[str] = []

    def wait_ready(self, timeout=180):
        return

    def call(self, path, body=None):
        self.calls.append(path)
        body = body or {}
        if path == "/agent/status":
            return {"ok": True, "secureBoot": self.secure_boot, "licenseState": self.license_state,
                    "integrity": "OK", "appVersion": self.app_version, "serial": self.serial}
        if path == "/agent/identity":
            nonce = base64.b64decode(body["nonce"])
            return {"ok": True, "publicKeyPem": self.pub_pem, "deviceId": self.device_id,
                    "identityBackend": "otp-hkdf", "secureBoot": self.secure_boot,
                    "fingerprint": identity.hardware_fingerprint("10000000a1b2c3d4", "d04170", "nvme-1", "carrier-3"),
                    "nonceSignature": base64.b64encode(identity.sign_challenge(self.key, nonce)).decode()}
        if path == "/agent/license":
            env = body["license"]
            try:
                p = lic.verify_license(env, self.trust, lic.Expected(
                    device_id=self.device_id, device_public_key_pem=self.pub_pem, serial=None,
                    product_type=self.product, software_version=self.app_version,
                    secure_boot_active=self.secure_boot))
            except lic.LicenseError as e:
                self.license_state = f"INVALID:{e.code}"
                return {"ok": False, "licenseState": self.license_state, "error": str(e)}
            self.license, self.serial, self.license_state = env, p["serial"], "VALID"
            return {"ok": True, "licenseState": "VALID", "serial": self.serial}
        if path == "/agent/encrypt-data":
            self.encrypted = True
            return {"ok": True, "keySource": "otp-hkdf", "recoveryKeyCiphertext": "b64...", "kmsKeyId": "kms-test"}
        if path == "/agent/apply-policy":
            self.policy = True
            return {"ok": True}
        if path == "/agent/self-test":
            return {"ok": True, "tests": {"leds": True, "fans": True, "heater": True, "door": True, "picolog": True}}
        if path == "/agent/finish":
            self.finished = True
            return {"ok": True}
        return {"ok": False, "error": f"unknown {path}"}
