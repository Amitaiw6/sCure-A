#!/bin/bash
# io-safe-boot.sh - park the LED path in its rest state as EARLY as possible
# after power-on, before scure.service (Flask + io_controller) is up.
#
#   GPIO16 / GPIO20  450nm / 405nm SSR enables  -> LOW (drivers disconnected)
#   GPIO17           wavelength switch line     -> LOW (405 position)
#   TCA6424A P05     LED_SWITCH -> Q28 -> K4    -> output, 0 (LED_OUT1)
#
# The TCA6424A powers up with every pin as an INPUT with a pull-up, so the
# LED_SWITCH net floats HIGH (relay engaged) until software drives it; this
# unit closes that window to a few seconds. Installed by pi-setup.sh as
# scure-io-safe.service. Idempotent; every step is best-effort.
set +e
for p in 16 17 20; do pinctrl set "$p" op dl 2>/dev/null; done
# TCA6424A @ I2C0 0x23: port-0 output register 0x04, config register 0x0C.
# Port 0: keep NFC_RESET (P01) high (its safe level), everything else 0;
# make P01 + P05 outputs (bits cleared), leave the other bits as inputs.
if command -v i2cset >/dev/null 2>&1; then
  i2cset -y 0 0x23 0x04 0x02 2>/dev/null       # P01=1, P05=0
  i2cset -y 0 0x23 0x0C 0xDD 2>/dev/null       # P01, P05 -> outputs
fi
exit 0
