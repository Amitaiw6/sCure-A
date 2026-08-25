#!/usr/bin/env python3
"""One-command demo of the whole factory flow, no hardware needed.

    python demo.py            # from appliance/ (uses the repo's .venv python)

What it does:
  1. starts the Serial + Image + License service on :8440 (SQLite in demo/)
  2. publishes a fake 2 MB image build 1.4.7 (qa) and 1.5.0-beta.12 (development)
  3. approves 1.4.7 for production (release role)
  4. provisions two simulated CM5 modules — the second one via
     "Generate New Serial Number" (--previous-serial)
  5. prints the manufacturing audit trail and stops the service
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request as u
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
DEMO = HERE / "demo"
B = "http://127.0.0.1:8440"


def call(path, body=None, role="engineering"):
    data = json.dumps(body).encode() if body is not None else None
    req = u.Request(B + path, data=data, method="POST" if data is not None else "GET",
                    headers={"Content-Type": "application/json", "X-Stratasys-Role": role,
                             "X-Stratasys-Operator": "demo"})
    return json.load(u.urlopen(req, timeout=10))


def main():
    (DEMO / "images").mkdir(parents=True, exist_ok=True)
    (DEMO / "trust").mkdir(exist_ok=True)
    img = DEMO / "images" / "SCURE-2026-08-25-147.img.zst"
    if not img.exists():
        img.write_bytes(os.urandom(2_000_000))
    env = dict(os.environ, SERIAL_DB=str(DEMO / "mfg.db"), IMAGES_DIR=str(DEMO / "images"), PORT="8440")
    srv = subprocess.Popen([PY, str(HERE / "serial-service" / "app.py")], env=env,
                           stdout=(DEMO / "server.log").open("w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(40):
            try:
                keys = call("/keys/public"); break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("service did not start — see demo/server.log")
        (DEMO / "trust" / "serial-service.pub").write_text(keys["serialServiceKeyPem"])
        (DEMO / "trust" / "license.pub").write_text(keys["licenseKeyPem"])
        data = img.read_bytes()
        m = {"imageVersion": "1.4.7", "buildId": "SCURE-2026-08-25-147", "product": "SCURE-A", "channel": "qa",
             "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data), "releaseDate": "2026-08-25",
             "minHardwareRevision": 3, "requiredFirmwareVersion": "2025-05-08", "productionApproved": False,
             "appVersion": "0.6.7", "url": "/images/file/SCURE-2026-08-25-147"}
        call("/images/publish", {"manifest": m})
        call("/images/publish", {"manifest": dict(m, imageVersion="1.5.0-beta.12", buildId="B150", channel="development")})
        print("== catalogue before approval:", call("/images/latest?product=SCURE-A&channel=development")["versions"])
        call("/images/SCURE-2026-08-25-147/approve", {"approvedBy": "qa-lead"}, role="release")
        print("== catalogue after approval: ", call("/images/latest?product=SCURE-A&channel=production")["versions"])
        print()
        base = [PY, str(HERE / "provisioning-tool" / "provision.py"), "run", "--station", "ST-01", "--operator", "demo",
                "--server", B, "--workdir", str(DEMO / "work"), "--trust", str(DEMO / "trust"), "--fake"]
        print("== provisioning module #1")
        subprocess.run(base, check=False)
        print("\n== provisioning module #2 with Generate New Serial Number (previous SC000001)")
        subprocess.run(base + ["--previous-serial", "SC000001"], check=False)
        print("\n== audit trail (Serial Service)")
        for e in call("/audit", role="factory")["entries"]:
            print(f"  {e['ts']}  {e['serial'] or '-':9} {e['event']}")
        print("\nservice log: demo/server.log · records: demo/work/*.record.json · DB: demo/mfg.db")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
