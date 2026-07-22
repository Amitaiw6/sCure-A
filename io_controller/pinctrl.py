#!/usr/bin/env python3
import argparse
import sys

from config import PINS
from gpio_manager import GpioManager


def find_pin(pin_number):
    try:
        num = int(pin_number)
    except ValueError:
        return None

    for pin in PINS:
        if pin['phys'] == num or pin['bcm'] == num:
            return pin
    return None


def main():
    parser = argparse.ArgumentParser(description='Simple GPIO pin control helper')
    parser.add_argument('command', choices=['get'], help='Command to run')
    parser.add_argument('pin', help='Physical or BCM pin number')
    args = parser.parse_args()

    pin = find_pin(args.pin)
    if not pin:
        print(f'Pin {args.pin} not found in config', file=sys.stderr)
        sys.exit(2)

    if args.command == 'get':
        bcm = pin['bcm']
        if bcm is None:
            print(f'Pin {args.pin} is not a GPIO pin')
            sys.exit(1)
        manager = GpioManager()
        mode = manager.get_mode(bcm)
        try:
            value = manager.read_pin(bcm)
        except Exception as exc:
            print(f'Error reading GPIO{bcm}: {exc}', file=sys.stderr)
            sys.exit(1)
        print(f'Pin {pin["phys"]} / BCM{bcm} ({pin["name"]}) mode={mode} value={value}')


if __name__ == '__main__':
    main()
