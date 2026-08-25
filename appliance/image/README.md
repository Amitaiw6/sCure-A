# Secure Linux Image — build (pi-gen, Debian 13 ARM64, CM5)

```
image/
├── config                         # pi-gen config: stages 0-2 (lite) + stage-stratasys
├── stage-stratasys/
│   ├── 00-packages                # cage chromium rauc usbguard cryptsetup plymouth …
│   ├── 01-run.sh                  # users, services, policy, remove apt, app install
│   └── files/                     # copied verbatim into the rootfs
│       ├── usr/lib/systemd/system/stratasys-*.service
│       ├── etc/chromium/policies/managed/stratasys.json
│       ├── etc/usbguard/rules.conf
│       ├── etc/rauc/system.conf
│       ├── etc/initramfs-tools/{hooks,scripts}/stratasys-*   # verity + LUKS unlock + identity
│       └── boot/{config.txt,cmdline.txt,autoboot.txt}
└── sign/
    ├── make-boot-img.sh           # boot partition -> boot.img + boot.sig (rpi-eeprom tooling)
    └── make-rauc-bundle.sh        # A/B update bundle, CMS-signed
```

Build (Linux host, Docker):

```sh
git clone https://github.com/RPi-Distro/pi-gen && cd pi-gen
cp -r ../appliance/image/config ../appliance/image/stage-stratasys .
touch stage2/SKIP_IMAGES            # we produce our own partitioned image
./build-docker.sh                   # -> deploy/SCURE-IMAGE-<version>.img.zst
../appliance/image/sign/make-boot-img.sh deploy/… keys/boot-signing.key
python ../appliance/license-tool/license_tool.py sign-manifest --key keys/image.key \
    --manifest manifest.json --image deploy/SCURE-IMAGE-<version>.img.zst --out manifest.signed.json
```

The resulting `manifest.signed.json` is published to the Image Server with
`channel=qa`; a release manager approves it (`/images/<buildId>/approve`)
before any factory station will install it.

Partition layout, boot chain and every setting are specified in
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §1.3, §3, §7, §8.
