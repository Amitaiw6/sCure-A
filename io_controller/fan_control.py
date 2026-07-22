#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fan_control.py - simple CLI for the four chamber fans (right/left/back/front).

Drives the fans only through io_controller's verified PCA9685 functions
(set_duty_verified: write, read back, retry) - no new hardware-access paths.

Usage:
  python3 fan_control.py on [percent]       all four fans (default 100%)
  python3 fan_control.py off                stop all four fans
  python3 fan_control.py <fan> <percent>    one fan: right / left / back / front
  python3 fan_control.py status             current state of each fan

Examples:
  python3 fan_control.py on                 # right+left+back+front at 100%
  python3 fan_control.py on 70              # all four at 70%
  python3 fan_control.py right 50           # right fan only at 50%
  python3 fan_control.py front 0            # stop the front (door) fan
  python3 fan_control.py off                # stop all four
"""
import sys

import io_controller as ioc

FANS = {
    "right": "FAN_RIGHT",
    "left":  "FAN_LEFT",
    "back":  "FAN_BACK",
    "front": "FAN_DOOR",     # the front fan is the door fan
}


def set_fan(pca, channel_name, percent):
    percent = max(0.0, min(100.0, percent))
    ch = ioc.PCA_CHANNELS[channel_name]
    attempt, _ = pca.set_duty_verified(ch, percent)
    print(f"  {channel_name:<10} -> {percent:.0f}%  (verified, attempt {attempt}/{ioc.VERIFY_RETRIES})")


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    pca = ioc.PCA9685()
    try:
        if args[0] == "on":
            pct = float(args[1]) if len(args) > 1 else 100.0
            for name in FANS.values():
                set_fan(pca, name, pct)
        elif args[0] == "off":
            for name in FANS.values():
                set_fan(pca, name, 0)
        elif args[0] == "status":
            for label, name in FANS.items():
                state = pca.read_state(ioc.PCA_CHANNELS[name])
                print(f"  {label:<6} ({name}): {state}")
        elif args[0] in FANS and len(args) > 1:
            set_fan(pca, FANS[args[0]], float(args[1]))
        else:
            raise SystemExit(f"unknown command: {' '.join(args)}  (run with --help)")
    finally:
        close = getattr(pca, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
