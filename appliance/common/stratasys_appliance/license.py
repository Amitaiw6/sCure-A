"""Signed machine license (see ARCHITECTURE.md §6).

    build_payload(...)          factory side: the statement to sign
    verify_license(env, trust, expected)   device side: full policy check

The device never holds a private key for this format; it verifies with the
public keys shipped inside the dm-verity root.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from . import crypto
from .serials import is_valid as serial_is_valid

LICENSE_VERSION = 1
IDENTITY_BACKENDS = ("otp-hkdf", "tpm2", "software")
PRODUCTION_FEATURE = "production"


class LicenseError(Exception):
    """A license that verified cryptographically but fails policy — or did
    not verify at all. `code` is machine-readable for the UI/audit log."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def build_payload(*, serial: str, device_id: str, device_public_key_pem: str,
                  product_type: str, features: Sequence[str],
                  software_compat: str, issuer: str,
                  identity_backend: str = "otp-hkdf",
                  previous_serial: str | None = None,
                  not_before: datetime | None = None,
                  expires_at: datetime | None = None,
                  provisional: bool = False) -> dict:
    if not serial_is_valid(serial):
        raise ValueError(f"invalid serial {serial!r}")
    if previous_serial is not None and not serial_is_valid(previous_serial):
        raise ValueError(f"invalid previous serial {previous_serial!r}")
    if identity_backend not in IDENTITY_BACKENDS:
        raise ValueError(f"unknown identity backend {identity_backend!r}")
    if identity_backend == "software" and PRODUCTION_FEATURE in features:
        raise ValueError("production licenses are never issued for software identities")
    now = _now()
    return {
        "licenseVersion": LICENSE_VERSION,
        "serial": serial,
        "previousSerial": previous_serial,
        "deviceId": device_id,
        "devicePublicKey": device_public_key_pem,
        "identityBackend": identity_backend,
        "productType": product_type,
        "features": sorted(set(features)),
        "softwareCompat": software_compat,
        "issuedAt": _iso(now),
        "notBefore": _iso(not_before or now),
        "expiresAt": _iso(expires_at) if expires_at else None,
        "issuer": issuer,
        "provisional": bool(provisional),
        "nonce": secrets.token_hex(16),
    }


# --------------------------------------------------------------------------
#  software compatibility ranges: ">=0.6.0 <2.0.0"
# --------------------------------------------------------------------------
_VER = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
_CMP = re.compile(r"(>=|<=|>|<|==)\s*(\d+\.\d+\.\d+)")


def _vt(v: str) -> tuple[int, int, int]:
    m = _VER.match(v.strip())
    if not m:
        raise ValueError(f"bad version {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def version_satisfies(version: str, spec: str) -> bool:
    v = _vt(version)
    clauses = _CMP.findall(spec)
    if not clauses:
        raise ValueError(f"bad compat spec {spec!r}")
    ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
           ">": lambda a, b: a > b, "<": lambda a, b: a < b, "==": lambda a, b: a == b}
    return all(ops[op](v, _vt(ver)) for op, ver in clauses)


# --------------------------------------------------------------------------
#  device-side verification
# --------------------------------------------------------------------------
@dataclass
class Expected:
    device_id: str
    device_public_key_pem: str
    serial: str | None                 # cached serial on the device (None = first boot)
    product_type: str
    software_version: str
    secure_boot_active: bool = True
    identity_backend: str = "otp-hkdf"
    now: datetime = field(default_factory=_now)


def verify_license(envelope: Mapping[str, Any], trust: crypto.TrustStore,
                   expected: Expected) -> dict:
    """Full check. Returns the payload; raises LicenseError with a code:
    SIGNATURE, VERSION, DEVICE_ID, DEVICE_KEY, SERIAL, PRODUCT, COMPAT,
    NOT_YET_VALID, EXPIRED, BACKEND, PROVISIONAL_EXPIRED, NOT_PRODUCTION."""
    try:
        p = crypto.verify(envelope, trust)
    except crypto.SignatureError as e:
        raise LicenseError("SIGNATURE", str(e))
    if p.get("licenseVersion") != LICENSE_VERSION:
        raise LicenseError("VERSION", f"unsupported license version {p.get('licenseVersion')}")
    if p.get("deviceId") != expected.device_id:
        raise LicenseError("DEVICE_ID", "license was issued to a different device")
    if (p.get("devicePublicKey") or "").strip() != expected.device_public_key_pem.strip():
        raise LicenseError("DEVICE_KEY", "license public key does not match this device")
    if p.get("identityBackend") != expected.identity_backend:
        raise LicenseError("BACKEND", "identity backend mismatch")
    if not serial_is_valid(p.get("serial", "")):
        raise LicenseError("SERIAL", "license carries an invalid serial")
    if expected.serial is not None and p["serial"] != expected.serial:
        raise LicenseError("SERIAL", f"license serial {p['serial']} != device serial {expected.serial}")
    if p.get("productType") != expected.product_type:
        raise LicenseError("PRODUCT", "license is for a different product")
    if not version_satisfies(expected.software_version, p.get("softwareCompat", "")):
        raise LicenseError("COMPAT", f"software {expected.software_version} outside {p.get('softwareCompat')}")
    now = expected.now
    if _parse_iso(p["notBefore"]) > now:
        raise LicenseError("NOT_YET_VALID", "license not yet valid")
    if p.get("expiresAt") and _parse_iso(p["expiresAt"]) < now:
        raise LicenseError("EXPIRED" if not p.get("provisional") else "PROVISIONAL_EXPIRED",
                           "license expired")
    if PRODUCTION_FEATURE in p.get("features", []) and not expected.secure_boot_active:
        raise LicenseError("NOT_PRODUCTION",
                           "production license on a module without active secure boot")
    return p
