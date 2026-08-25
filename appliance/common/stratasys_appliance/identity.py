"""Device identity (ARCHITECTURE.md §5).

    device_id(pubkey)           DEV-<base32 of sha256(SPKI DER)>[:26]
    derive_identity_key(otp)    HKDF(otp_key, "stratasys-identity-v1") -> P-256 key
    derive_luks_key(otp)        HKDF(otp_key, "stratasys-luks-v1")     -> 32 bytes
    hardware_fingerprint(...)   sha256 over stable board identifiers
    read_otp_private_key()      CM5 OTP device key via vcmailbox (Linux only)

The OTP-derived paths run only inside the signed initramfs on a module
with secure boot; the software backend is for lab units and tests.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, encode_dss_signature)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ID_PREFIX = "DEV-"
_P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def device_id(public_key: ec.EllipticCurvePublicKey) -> str:
    der = public_key.public_bytes(serialization.Encoding.DER,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    b32 = base64.b32encode(hashlib.sha256(der).digest()).decode().rstrip("=")
    return ID_PREFIX + b32[:26]


def public_pem(public_key: ec.EllipticCurvePublicKey) -> str:
    return public_key.public_bytes(serialization.Encoding.PEM,
                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def load_public_pem(pem: str | bytes) -> ec.EllipticCurvePublicKey:
    key = serialization.load_pem_public_key(pem if isinstance(pem, bytes) else pem.encode())
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("not an EC public key")
    return key


def _hkdf(secret: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(secret)


def derive_identity_key(otp_key: bytes) -> ec.EllipticCurvePrivateKey:
    """Deterministic P-256 key from the 32-byte OTP secret. Rejection
    sampling on a 48-byte HKDF output keeps the scalar uniform in [1, n-1]."""
    if len(otp_key) < 32:
        raise ValueError("OTP key must be at least 32 bytes")
    counter = 0
    while True:
        material = _hkdf(otp_key, b"stratasys-identity-v1|" + counter.to_bytes(2, "big"), 48)
        scalar = int.from_bytes(material, "big") % (_P256_ORDER - 1) + 1
        if 1 <= scalar < _P256_ORDER:
            return ec.derive_private_key(scalar, ec.SECP256R1())
        counter += 1


def derive_luks_key(otp_key: bytes) -> bytes:
    return _hkdf(otp_key, b"stratasys-luks-v1", 32)


def sign_challenge(private_key: ec.EllipticCurvePrivateKey, challenge: bytes) -> bytes:
    """Raw r||s (64 bytes) ECDSA-SHA256 — fixed size, easy to transport."""
    der = private_key.sign(challenge, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_challenge(public_key: ec.EllipticCurvePublicKey, challenge: bytes, sig: bytes) -> bool:
    if len(sig) != 64:
        return False
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    try:
        public_key.verify(der, challenge, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:  # noqa: BLE001 - InvalidSignature and malformed input alike
        return False


def hardware_fingerprint(board_serial: str, board_revision: str,
                         storage_serial: str, carrier_id: str) -> str:
    parts = [board_serial, board_revision, storage_serial, carrier_id]
    return hashlib.sha256("|".join(x.strip().lower() for x in parts).encode()).hexdigest()


# --------------------------------------------------------------------------
#  Raspberry Pi specifics (only meaningful on the module)
# --------------------------------------------------------------------------
def read_board_info() -> dict:
    """/proc/cpuinfo + device-tree: serial, revision, model."""
    info = {"boardSerial": "", "boardRevision": "", "model": ""}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if k == "Serial":
                info["boardSerial"] = v
            elif k == "Revision":
                info["boardRevision"] = v
            elif k == "Model":
                info["model"] = v
    except OSError:
        pass
    try:
        info["model"] = info["model"] or Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode()
    except OSError:
        pass
    return info


def read_otp_private_key() -> bytes:
    """The CM5 device-specific private key (32 bytes) via `rpi-otp-private-key`
    (rpi-eeprom package). Only readable before the initramfs locks it."""
    out = subprocess.run(["rpi-otp-private-key", "-b"], check=True,
                         capture_output=True, text=True).stdout.strip()
    key = bytes.fromhex(out)
    if len(key) != 32 or key == bytes(32):
        raise RuntimeError("OTP private key not programmed")
    return key


def secure_boot_active() -> bool:
    """`vcgencmd otp_dump` row 30 bit 23 marks a programmed customer key
    (secure-boot mode) on Pi 4/5-family devices."""
    try:
        out = subprocess.run(["vcgencmd", "otp_dump"], check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        if line.startswith("30:"):
            return bool(int(line.split(":")[1], 16) & (1 << 23))
    return False


def load_software_identity(path: str | os.PathLike) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("not an EC private key")
    return key


def create_software_identity(path: str | os.PathLike) -> ec.EllipticCurvePrivateKey:
    key = ec.generate_private_key(ec.SECP256R1())
    Path(path).write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    try:
        os.chmod(path, 0o400)
    except OSError:
        pass
    return key
