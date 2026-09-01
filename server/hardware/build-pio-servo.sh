#!/bin/bash
# Build pio_servo - the hardware-timed damper-servo helper (RP1 PIO, Pi 5/CM5).
#
# Needs: gcc, git (to fetch piolib), a kernel with /dev/pio0 (Pi OS Bookworm+).
# piolib (BSD-3-Clause, https://github.com/raspberrypi/utils) is compiled in
# directly - no cmake, no install.
#
# Run from server/hardware/:   chmod +x build-pio-servo.sh && ./build-pio-servo.sh
# Output: server/hardware/pio_servo   (io_controller's Servo class looks here)
#
# PIOLIB_SRC=<path to utils/piolib> skips the git fetch.

set -e
cd "$(dirname "$0")"

SRC="${PIOLIB_SRC:-}"
if [ -z "$SRC" ]; then
    SRC=/tmp/rpi-utils/piolib
    if [ ! -f "$SRC/piolib.c" ]; then
        echo "Fetching piolib (raspberrypi/utils)..."
        rm -rf /tmp/rpi-utils
        git clone -q --depth 1 https://github.com/raspberrypi/utils /tmp/rpi-utils
    fi
fi
[ -f "$SRC/piolib.c" ] || { echo "piolib sources not found at $SRC"; exit 1; }

echo "Building pio_servo against $SRC ..."
gcc -O2 -Wall -Wextra -Wno-unused-parameter -DLIBRARY_BUILD=1 \
    -I"$SRC/include" \
    -o pio_servo pio_servo.c \
    "$SRC/piolib.c" "$SRC/pio_rp1.c" "$SRC/library_piochips.c"

echo "Done: $(pwd)/pio_servo"
echo "Test (drives the damper servo on GPIO8 to 1500 us for 1 s):"
echo "  sudo ./pio_servo 8 --inverted --test 1500 1000"
