#!/bin/bash -e
# Build + sign boot.img for one slot (Raspberry Pi secure boot).
#   make-boot-img.sh <bootfiles-dir> <root-hash> <slot a|b> <boot-signing.key|pkcs11-uri> <out-dir>
# Produces boot.img (FAT image with kernel, DTBs, initramfs, config.txt,
# cmdline.txt) and boot.sig (sha256 + RSA-2048 signature, the format the
# EEPROM bootloader verifies against the OTP customer key hash).
# Requires: rpi-eeprom (rpi-eeprom-digest), mtools/mkfs.fat, openssl.
BOOTFILES="$1"; ROOTHASH="$2"; SLOT="$3"; KEY="$4"; OUT="$5"
[ -d "$BOOTFILES" ] && [ -n "$ROOTHASH" ] && [ -n "$SLOT" ] && [ -n "$KEY" ] && [ -n "$OUT" ] || {
    echo "usage: $0 <bootfiles-dir> <root-hash> <slot a|b> <boot-signing.key> <out-dir>"; exit 2; }
mkdir -p "$OUT"
WORK=$(mktemp -d)
cp -a "$BOOTFILES/." "$WORK/"
sed -e "s/@ROOTHASH@/$ROOTHASH/" -e "s/@SLOT@/$SLOT/" "$BOOTFILES/cmdline.txt" > "$WORK/cmdline.txt"
grep -q "@ROOTHASH@" "$WORK/cmdline.txt" && { echo "cmdline placeholder not replaced"; exit 1; }

SIZE_KB=$(( $(du -sk "$WORK" | cut -f1) + 8192 ))
IMG="$OUT/boot.img"
rm -f "$IMG"
mkfs.fat -C -n BOOT "$IMG" "$SIZE_KB" >/dev/null
mcopy -i "$IMG" -s "$WORK"/* ::/
rm -rf "$WORK"

# boot.sig: sha256 digest line + RSA signature over the image (rpi-eeprom-digest format)
if [[ "$KEY" == pkcs11:* ]]; then
    rpi-eeprom-digest -i "$IMG" -o "$OUT/boot.sig" -H "$KEY"        # HSM-resident key
else
    rpi-eeprom-digest -i "$IMG" -o "$OUT/boot.sig" -k "$KEY"
fi
echo "signed $IMG ($(stat -c %s "$IMG") bytes) -> $OUT/boot.sig"
sha256sum "$IMG" "$OUT/boot.sig"
