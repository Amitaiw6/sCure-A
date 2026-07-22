#!/usr/bin/env python3
# write_gpio_example.py

from gpio_manager import GpioManager

PIN = 18  # BCM numbering

if __name__ == '__main__':
    gm = GpioManager()
    print('GPIO driver available:', gm.available)

    # Set pin mode to output
    gm.set_mode(PIN, 'OUT')
    print('Pin mode set to:', gm.get_mode(PIN))

    # Write HIGH
    gm.write_pin(PIN, 1)
    print('Wrote HIGH to pin', PIN)

    # Write LOW
    gm.write_pin(PIN, 0)
    print('Wrote LOW to pin', PIN)

    # Cleanup
    gm.cleanup()
    print('Cleanup done')
