"""Canonical JSON + Ed25519 signatures.

Every signed object in the appliance (license, image manifest, serial
range token, update SHA256SUMS, audit checkpoint) is:

    {"payload": {...}, "signature": base64(Ed25519(canonical(payload))),
     "signerKeyId": "<key id>"}

canonical() = JSON with sorted keys, no whitespace, UTF-8, NaN forbidden.
Key IDs are the first 12 hex chars of SHA-256 over the raw public key, so
a public key file is self-identifying and cannot be mislabelled.

Private keys are only ever loaded by the factory-side tools (serial
service, license signer, image publisher). The device side imports only
verify() and load_public_key().
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)


class SignatureError(Exception):
    """Raised when a signed object does not verify."""


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw,
                                  serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:12]


# --------------------------------------------------------------------------
#  key files (PEM)
# --------------------------------------------------------------------------
def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def save_private_key(key: Ed25519PrivateKey, path: str | os.PathLike) -> None:
    """PEM, unencrypted: meant for an HSM-backed or offline signer host
    only; factory-side callers must keep this file off any production
    machine. Mode 0600."""
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    p = Path(path)
    p.write_bytes(pem)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def save_public_key(key: Ed25519PublicKey, path: str | os.PathLike) -> None:
    Path(path).write_bytes(key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def load_private_key(path: str | os.PathLike) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path}: not an Ed25519 private key")
    return key


def load_public_key(path_or_pem: str | os.PathLike | bytes) -> Ed25519PublicKey:
    data = path_or_pem if isinstance(path_or_pem, bytes) else Path(path_or_pem).read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return key


def public_pem(key: Ed25519PublicKey) -> str:
    return key.public_bytes(serialization.Encoding.PEM,
                            serialization.PublicFormat.SubjectPublicKeyInfo).decode()


# --------------------------------------------------------------------------
#  trust store: the set of public keys a verifier accepts
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TrustStore:
    keys: Mapping[str, Ed25519PublicKey]          # keyId -> key
    revoked: frozenset[str] = frozenset()         # keyIds no longer accepted

    @classmethod
    def from_dir(cls, directory: str | os.PathLike, pattern: str = "*.pub",
                 revoked_file: str = "revoked-keys.txt") -> "TrustStore":
        d = Path(directory)
        keys = {}
        for f in sorted(d.glob(pattern)):
            k = load_public_key(f)
            keys[key_id(k)] = k
        revoked: set[str] = set()
        rf = d / revoked_file
        if rf.exists():
            revoked = {ln.strip() for ln in rf.read_text().splitlines()
                       if ln.strip() and not ln.startswith("#")}
        return cls(keys, frozenset(revoked))

    @classmethod
    def of(cls, keys: Iterable[Ed25519PublicKey]) -> "TrustStore":
        return cls({key_id(k): k for k in keys})


# --------------------------------------------------------------------------
#  sign / verify envelopes
# --------------------------------------------------------------------------
def sign(payload: Mapping[str, Any], private_key: Ed25519PrivateKey) -> dict:
    sig = private_key.sign(canonical(payload))
    return {"payload": dict(payload),
            "signature": base64.b64encode(sig).decode(),
            "signerKeyId": key_id(private_key.public_key())}


def verify(envelope: Mapping[str, Any], trust: TrustStore) -> dict:
    """Return the payload if the envelope is signed by a trusted, non-revoked
    key; raise SignatureError otherwise. Never returns a payload that did
    not verify."""
    try:
        payload = envelope["payload"]
        sig = base64.b64decode(envelope["signature"], validate=True)
        kid = str(envelope["signerKeyId"])
    except (KeyError, TypeError, ValueError) as e:
        raise SignatureError(f"malformed signed object: {e}") from None
    if kid in trust.revoked:
        raise SignatureError(f"signing key {kid} is revoked")
    key = trust.keys.get(kid)
    if key is None:
        raise SignatureError(f"signing key {kid} is not trusted")
    try:
        key.verify(sig, canonical(payload))
    except InvalidSignature:
        raise SignatureError("invalid signature") from None
    return payload
