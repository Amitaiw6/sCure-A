#!/usr/bin/env python3
# toggle_gpio.py

import time
import argparse
import signal
import sys
from datetime import datetime

from gpio_manager import GpioManager

running = True

def signal_handler(sig, frame):
    global running
    running = False


def main():
    parser = argparse.ArgumentParser(description='Toggle a GPIO pin HIGH/LOW with configurable intervals')
    parser.add_argument('--pin', '-p', type=int, required=True, help='BCM pin number to toggle')
    parser.add_argument('--high', type=float, default=1.0, help='Seconds to hold HIGH (default: 1.0)')
    parser.add_argument('--low', type=float, default=1.0, help='Seconds to hold LOW (default: 1.0)')
    parser.add_argument('--count', '-c', type=int, default=0, help='Number of cycles to run (0 = infinite)')
    parser.add_argument('--log', '-l', type=str, default=None, help='Optional CSV log file to append toggle events')

    args = parser.parse_args()

    gm = GpioManager()
    print(f'GPIO driver available: {gm.available}')

    if args.pin is None:
        print('Please provide --pin')
        sys.exit(2)

    pin = args.pin
    gm.set_mode(pin, 'OUT')

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    cycle = 0
    try:
        while running and (args.count == 0 or cycle < args.count):
            # set HIGH
            gm.write_pin(pin, 1)
            t = datetime.utcnow().isoformat()
            msg = f'{t},cycle={cycle+1},pin={pin},state=HIGH'
            print(msg)
            if args.log:
                with open(args.log, 'a') as f:
                    f.write(msg + '\n')
            time.sleep(args.high)
            if not running:
                break

            # set LOW
            gm.write_pin(pin, 0)
            t = datetime.utcnow().isoformat()
            msg = f'{t},cycle={cycle+1},pin={pin},state=LOW'
            print(msg)
            if args.log:
                with open(args.log, 'a') as f:
                    f.write(msg + '\n')
            time.sleep(args.low)

            cycle += 1
    finally:
        gm.cleanup()
        print('Exiting, cleaned up GPIO')


if __name__ == '__main__':
    main()
