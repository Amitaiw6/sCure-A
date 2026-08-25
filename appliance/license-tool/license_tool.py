#!/usr/bin/env python3
"""Stratasys license / signing-key tool (offline signer host).

    license_tool.py keygen  --name license-2026 --out keys/
    license_tool.py sign    --key keys/license-2026.key --request request.json --out license.json
    license_tool.py verify  --trust keys/ --license license.json [--device-id DEV-.. --serial SC000126]
    license_tool.py sign-manifest --key keys/image-2026.key --manifest manifest.json --out manifest.signed.json
    license_tool.py inspect --file license.json

`request.json` is what the provisioning tool / serial service hands to the
signer: {serial, deviceId, devicePublicKey, productType, features,
softwareCompat, identityBackend, previousSerial?, provisional?}.

The private key file produced by `keygen` must live on the offline signer
(or be replaced by an HSM/KMS backend) — never on a factory station or a
production machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from stratasys_appliance import crypto, license as lic, manifests  # noqa: E402


def cmd_keygen(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    key = crypto.generate_private_key()
    crypto.save_private_key(key, out / f"{a.name}.key")
    crypto.save_public_key(key.public_key(), out / f"{a.name}.pub")
    print(f"key id {crypto.key_id(key.public_key())}: {out / (a.name + '.key')} (PRIVATE — keep offline), "
          f"{out / (a.name + '.pub')} (ship in the image)")


def cmd_sign(a):
    req = json.loads(Path(a.request).read_text())
    expires = None
    if req.get("provisional"):
        expires = datetime.now(timezone.utc) + timedelta(days=int(a.provisional_days))
    payload = lic.build_payload(
        serial=req["serial"], device_id=req["deviceId"], device_public_key_pem=req["devicePublicKey"],
        product_type=req.get("productType", "SCURE-A"), features=req.get("features", ["production"]),
        software_compat=req.get("softwareCompat", ">=0.6.0 <2.0.0"), issuer=a.issuer,
        identity_backend=req.get("identityBackend", "otp-hkdf"), previous_serial=req.get("previousSerial"),
        expires_at=expires, provisional=bool(req.get("provisional")))
    env = crypto.sign(payload, crypto.load_private_key(a.key))
    Path(a.out).write_text(json.dumps(env, indent=2))
    print(f"license for {payload['serial']} / {payload['deviceId']} signed with key {env['signerKeyId']} -> {a.out}")


def cmd_verify(a):
    env = json.loads(Path(a.license).read_text())
    trust = crypto.TrustStore.from_dir(a.trust)
    try:
        p = crypto.verify(env, trust)
    except crypto.SignatureError as e:
        print(f"INVALID: {e}")
        sys.exit(2)
    print(f"signature OK (key {env['signerKeyId']}): serial {p['serial']} device {p['deviceId']} "
          f"features {p['features']} compat {p['softwareCompat']}")
    if a.device_id and p["deviceId"] != a.device_id:
        print(f"MISMATCH: license device {p['deviceId']} != {a.device_id}")
        sys.exit(3)
    if a.serial and p["serial"] != a.serial:
        print(f"MISMATCH: license serial {p['serial']} != {a.serial}")
        sys.exit(3)


def cmd_sign_manifest(a):
    payload = json.loads(Path(a.manifest).read_text())
    if a.image:
        payload["sha256"] = crypto.sha256_file(a.image)
        payload["sizeBytes"] = Path(a.image).stat().st_size
    env = crypto.sign(payload, crypto.load_private_key(a.key))
    manifests.verify_manifest(env, crypto.TrustStore.of([crypto.load_private_key(a.key).public_key()]))
    Path(a.out).write_text(json.dumps(env, indent=2))
    print(f"manifest {payload['buildId']} ({payload['imageVersion']}, {payload['channel']}, "
          f"approved={payload['productionApproved']}) signed -> {a.out}")


def cmd_inspect(a):
    env = json.loads(Path(a.file).read_text())
    print(json.dumps(env.get("payload", env), indent=2))
    print(f"signerKeyId: {env.get('signerKeyId')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen"); k.add_argument("--name", required=True); k.add_argument("--out", default="keys")
    s = sub.add_parser("sign"); s.add_argument("--key", required=True); s.add_argument("--request", required=True)
    s.add_argument("--out", required=True); s.add_argument("--issuer", default="stratasys-license-ca-2026")
    s.add_argument("--provisional-days", default="30")
    v = sub.add_parser("verify"); v.add_argument("--trust", required=True); v.add_argument("--license", required=True)
    v.add_argument("--device-id"); v.add_argument("--serial")
    m = sub.add_parser("sign-manifest"); m.add_argument("--key", required=True); m.add_argument("--manifest", required=True)
    m.add_argument("--image", help="compute sha256/size from this file"); m.add_argument("--out", required=True)
    i = sub.add_parser("inspect"); i.add_argument("--file", required=True)
    a = ap.parse_args(argv)
    {"keygen": cmd_keygen, "sign": cmd_sign, "verify": cmd_verify,
     "sign-manifest": cmd_sign_manifest, "inspect": cmd_inspect}[a.cmd](a)


if __name__ == "__main__":
    main()
