"""Signed image-catalog manifests (ARCHITECTURE.md §4.5).

The Image Server publishes one signed manifest per build. The Factory
Provisioning Tool may only flash a manifest that passes `check_installable`
— never "the newest build", only the newest *production-approved* one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from . import crypto

CHANNELS = ("development", "qa", "production")
REQUIRED = ("imageVersion", "buildId", "product", "channel", "sha256",
            "sizeBytes", "releaseDate", "minHardwareRevision",
            "requiredFirmwareVersion", "productionApproved", "appVersion", "url")


class ManifestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.\-]+))?$")


def version_key(v: str) -> tuple:
    """Sort key: 1.4.7 > 1.4.7-rc2 > 1.4.6 (a pre-release sorts below its release)."""
    m = _SEMVER.match(v)
    if not m:
        raise ValueError(f"bad version {v!r}")
    major, minor, patch, pre = m.groups()
    return (int(major), int(minor), int(patch), 1 if pre is None else 0, pre or "")


def firmware_key(v: str) -> tuple:
    """Raspberry Pi EEPROM versions are dates: 2025-05-08 (or YYYYMMDD)."""
    digits = re.sub(r"\D", "", v or "")
    return (int(digits[:8] or 0),)


@dataclass(frozen=True)
class DetectedHardware:
    product: str
    hardware_revision: int          # carrier board revision
    firmware_version: str           # EEPROM bootloader version (date)


def verify_manifest(envelope: Mapping[str, Any], trust: crypto.TrustStore) -> dict:
    try:
        p = crypto.verify(envelope, trust)
    except crypto.SignatureError as e:
        raise ManifestError("SIGNATURE", str(e))
    missing = [k for k in REQUIRED if k not in p]
    if missing:
        raise ManifestError("MALFORMED", f"manifest missing {missing}")
    if p["channel"] not in CHANNELS:
        raise ManifestError("MALFORMED", f"unknown channel {p['channel']!r}")
    if not re.fullmatch(r"[0-9a-f]{64}", p["sha256"]):
        raise ManifestError("MALFORMED", "sha256 must be 64 hex chars")
    version_key(p["imageVersion"])           # raises on garbage
    return p


def check_installable(p: Mapping[str, Any], hw: DetectedHardware | None,
                      withdrawn: set[str] = frozenset(),
                      allow_channel: str = "production") -> None:
    """Policy after signature verification. `allow_channel` is 'production'
    for the factory role; engineering may pass 'qa'/'development'."""
    if p["product"] != (hw.product if hw else p["product"]):
        raise ManifestError("PRODUCT", f"image is for {p['product']}, unit is {hw.product}")
    if p["buildId"] in withdrawn:
        raise ManifestError("WITHDRAWN", f"build {p['buildId']} was withdrawn by Stratasys")
    if p["channel"] != allow_channel:
        raise ManifestError("CHANNEL", f"channel {p['channel']} is not {allow_channel}")
    if allow_channel == "production" and p["productionApproved"] is not True:
        raise ManifestError("NOT_APPROVED", f"{p['imageVersion']} is not Production Approved")
    if hw is not None:
        if hw.hardware_revision < int(p["minHardwareRevision"]):
            raise ManifestError("HARDWARE", f"needs carrier rev >= {p['minHardwareRevision']}, unit is rev {hw.hardware_revision}")
        if firmware_key(hw.firmware_version) < firmware_key(p["requiredFirmwareVersion"]):
            raise ManifestError("FIRMWARE", f"needs EEPROM >= {p['requiredFirmwareVersion']}, unit has {hw.firmware_version}")


def check_file(p: Mapping[str, Any], path) -> None:
    """Integrity of a downloaded / cached image file against its manifest."""
    import os
    size = os.path.getsize(path)
    if size != int(p["sizeBytes"]):
        raise ManifestError("SIZE", f"file is {size} bytes, manifest says {p['sizeBytes']}")
    digest = crypto.sha256_file(path)
    if digest != p["sha256"]:
        raise ManifestError("HASH", "SHA-256 mismatch — image modified or corrupted")


def newest_approved(payloads, channel: str = "production"):
    """Pick the newest installable manifest payload (None if none)."""
    ok = [p for p in payloads
          if p.get("channel") == channel and (channel != "production" or p.get("productionApproved") is True)]
    return max(ok, key=lambda p: version_key(p["imageVersion"]), default=None)
