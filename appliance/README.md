# Stratasys Secure Linux Appliance (CM5)

Design and implementation of the dedicated Linux image, factory
provisioning, device identity, licensing, secure update and service
architecture for Stratasys machines built on the Raspberry Pi CM5.

**Start with the documents** — the code implements them:

| Document | Content |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Phases 1, 3–10: component architecture (diagrams), distro selection, boot chain & kiosk, factory provisioning (incl. approved-image catalog, serial numbers, offline), device identity, licensing, filesystem security, secure update, service & recovery, firmware policy, USB policy, audit log, decision records |
| [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md) | Phase 2: assets, attacker classes, scenarios A–M with attack path / risk / mitigation / hardware / residual, protection matrix, explicit limitations |

## Layout (Phase 11)

```
appliance/
├── common/stratasys_appliance/   shared library (factory + device)
│   ├── crypto.py       canonical JSON, Ed25519 sign/verify, trust store, key files
│   ├── serials.py      SC000001 format + sequencing rules
│   ├── license.py      signed license payload build + device-side policy verify
│   ├── manifests.py    signed image-catalog manifest verify + install policy
│   ├── identity.py     device ID, OTP-derived identity/LUKS keys, challenge-response, board info
│   └── audit.py        hash-chained audit log
├── serial-service/     Serial Number + Image + Device + License API (Flask; SQLite dev / PostgreSQL prod)
│   ├── app.py
│   └── schema.sql      manufacturing database (PostgreSQL reference)
├── license-tool/       offline signer CLI: keygen / sign / verify / sign-manifest
├── provisioning-tool/  Factory Provisioning Tool: state machine, approved-image catalog+cache, rpiboot
├── security-service/   device-side: identity handoff, license + integrity checks, audit, provisioning agent
├── image/              pi-gen stage: packages, users, systemd units, kiosk policy, USB policy, RAUC, initramfs, boot files, signing
└── tests/              pytest: library rules, serial service (atomicity, roles, catalog), end-to-end provisioning
```

## Run the tests

```sh
cd appliance
pip install -r requirements.txt
pytest -q
```

## Factory Provisioning Tool — desktop application (the way the operator runs it)

```sh
python demo.py --ui                      # demo: service + approved image + the desktop app with a simulated module
# real station:
python provisioning-tool/app.py --station ST-01 --server https://mfg.stratasys.example \
       --trust trust/ --signed-eeprom eeprom-signed/
# package as a Windows program (no Python needed on the station):
pip install pyinstaller && pyinstaller stratasys-provisioning.spec   # -> dist/StratasysProvisioning/StratasysProvisioning.exe
```

`provisioning-tool/app.py` is a native Qt (PySide6) window; `provisioning-tool/ui.py`
is the same screen as a local web page for stations that prefer a browser.

One screen: step list with progress, approved-image panel (Latest Production
/ Local / Signature / Status, OFFLINE MODE banner), module detection, unit
panel (serial, previous serial, device ID, versions, secure boot, encryption,
license, final test), **Start Provisioning**, **Generate New Serial Number**
(Factory/Service only, never a typed serial), and the *Provisioning
Successful — READY FOR PRODUCTION* summary. The UI only observes a
`ProvisioningRun` running in a background thread.

## Try the flow (no hardware, command line)

```sh
# 1. serial / image server
SERIAL_DB=/tmp/mfg.db python serial-service/app.py &          # :8440
# 2. publish + approve an image (release role)
python license-tool/license_tool.py sign-manifest --key keys/image.key --manifest manifest.json \
       --image SCURE-IMAGE-1.4.7.img.zst --out manifest.signed.json
curl -H 'X-Stratasys-Role: engineering' -d @manifest.signed.json http://127.0.0.1:8440/images/publish
curl -X POST -H 'X-Stratasys-Role: release' http://127.0.0.1:8440/images/SCURE-2026-08-25-147/approve
# 3. provision a (simulated) module
python provisioning-tool/provision.py run --station ST-01 --operator amitai --server http://127.0.0.1:8440 --fake
```

Output ends with:

```
Provisioning Successful

Machine Serial:  SC000001
Device ID:       DEV-…
Image Version:   1.4.7  (build SCURE-2026-08-25-147)
Provisioning:    Online
Device Status:   READY FOR PRODUCTION
```

`--previous-serial SC000126` is the authorised **Generate New Serial
Number** path (role factory/service): the next number in the sequence is
assigned, the old one stays in the DB and the audit log.

## What is real and what is a stub

Real, tested: serial allocation (atomic, sequential, never reused, ranges,
reconciliation), device registration with proof-of-possession, license
issue/verify with device + serial binding, image catalog with approval
channel / signature / hash / withdrawn / hardware-compat policy, local cache
with re-verification, offline mode (range token + provisional station
license + queued records), hash-chained audit, provisioning state machine
with journal and safe failure (serial voided), device security service logic.

Requires the hardware / build host: `rpiboot` flashing, OTP programming,
the `pi-gen` build, initramfs unlock script, RAUC bundle signing, the
kiosk units — these are written to the documented design but have not been
executed on a CM5 in this repository.

## Security keys

Never commit a `.key` file. `license_tool.py keygen` produces the pair; the
`.key` goes to the offline signer / HSM, the `.pub` ships in the image
(`image/stage-stratasys/keys/`, `provisioning-tool/trust/`).
