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

# ---- display profile (image/display-profiles/<name>.conf), default: DSI Touch Display 2
PROFILE="${DISPLAY_PROFILE:-dsi-touch-display-2}"
PROFILE_FILE="$(dirname "$0")/../display-profiles/$PROFILE.conf"
[ -f "$PROFILE_FILE" ] || { echo "unknown DISPLAY_PROFILE $PROFILE"; exit 2; }
# shellcheck disable=SC1090
. "$PROFILE_FILE"
echo "display profile: $DISPLAY_NAME"
awk -v cfg="$CONFIG_TXT" '{ if ($0 == "@DISPLAY_CONFIG@") print cfg; else print }' "$BOOTFILES/config.txt" > "$WORK/config.txt"
sed -e "s/@ROOTHASH@/$ROOTHASH/" -e "s/@SLOT@/$SLOT/" -e "s|@VIDEO@|$VIDEO|" "$BOOTFILES/cmdline.txt" > "$WORK/cmdline.txt"
if grep -Eq "@[A-Z_]+@" "$WORK/cmdline.txt" "$WORK/config.txt"; then
    echo "placeholder not replaced:"; grep -En "@[A-Z_]+@" "$WORK/cmdline.txt" "$WORK/config.txt"; exit 1
fi

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
