#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
system_log.py - centralized logging for the CureBox.

A single rotating log file collects every system event and fault (LED / heater /
fan actions, door interlock, wavelength switches, driver-verify failures, etc.).
Other modules log via:  from system_log import log;  log.info("...")

  - file:    logs/curebox.log  (rotating, 1 MB x 5)
  - console: mirrored to stderr
  - recent(n): tail the log (for the dashboard log panel)
  - export(dest): copy the log out (e.g. to a USB path)
"""

import os
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "curebox.log")
_FMT = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")


def _build():
    logger = logging.getLogger("curebox")
    if logger.handlers:                  # already configured
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(_FMT)
        logger.addHandler(fh)
    except Exception:                    # noqa: BLE001 - file logging optional
        pass
    ch = logging.StreamHandler()
    ch.setFormatter(_FMT)
    logger.addHandler(ch)
    return logger


log = _build()


def recent(n=300):
    """Return the last n log lines (oldest first). Empty list if no file yet."""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            return f.readlines()[-n:]
    except Exception:                    # noqa: BLE001
        return []


def export(dest):
    """Copy the current log file to `dest` (a directory or a file path).
    Returns the written path. Raises on failure."""
    import shutil
    if os.path.isdir(dest):
        dest = os.path.join(dest, "curebox.log")
    shutil.copy2(LOG_FILE, dest)
    return dest


def clear():
    """Truncate the current log file."""
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()
    except Exception:                    # noqa: BLE001
        pass
