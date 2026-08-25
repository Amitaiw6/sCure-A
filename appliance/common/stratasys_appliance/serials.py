"""Machine serial numbers: SC000001, SC000002, … — ascending, never reused.

The *only* place a serial number is ever generated is the Serial Service's
database counter (serial-service/app.py). This module holds the pure
rules so the service, the provisioning tool and the device agree on them.
"""

from __future__ import annotations

import re

PREFIX = "SC"
DIGITS = 6
PATTERN = re.compile(rf"^{PREFIX}(\d{{{DIGITS}}})$")
MAX_NUMBER = 10 ** DIGITS - 1


def format_serial(number: int) -> str:
    if not 1 <= number <= MAX_NUMBER:
        raise ValueError(f"serial number {number} outside 1..{MAX_NUMBER}")
    return f"{PREFIX}{number:0{DIGITS}d}"


def parse_serial(serial: str) -> int:
    m = PATTERN.match(serial or "")
    if not m:
        raise ValueError(f"invalid serial {serial!r} (expected {PREFIX}{'0' * DIGITS})")
    n = int(m.group(1))
    if n < 1:
        raise ValueError("serial numbers start at 1")
    return n


def is_valid(serial: str) -> bool:
    try:
        parse_serial(serial)
        return True
    except ValueError:
        return False


def next_serial(last_assigned: str | None) -> str:
    """The serial that follows `last_assigned` (None → the very first)."""
    return format_serial(1 if not last_assigned else parse_serial(last_assigned) + 1)


def is_successor(previous: str, candidate: str) -> bool:
    return parse_serial(candidate) == parse_serial(previous) + 1


def in_range(serial: str, first: str, last: str) -> bool:
    n = parse_serial(serial)
    return parse_serial(first) <= n <= parse_serial(last)
