#!/usr/bin/env python3
"""
dev_log.py - timestamped Developer Mode event log.

Every important Developer Mode event (auth attempts, factor changes,
calibration saves, PicoLog connect/disconnect, HDT state transitions,
report exports) lands here: printed to the server journal and appended to
server/data/dev_events.jsonl so the history survives restarts. Best-effort
by design - logging must never break a calibration.
"""

import json
import os
import threading
import time

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'data', 'dev_events.jsonl')
_lock = threading.Lock()


def log_event(event, detail=None):
    """Record one Developer Mode event with a timestamp."""
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[DEV] {stamp} {event}'
          + (f' {json.dumps(detail, default=str)}' if detail else ''), flush=True)
    try:
        with _lock:
            os.makedirs(os.path.dirname(_PATH), exist_ok=True)
            with open(_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'ts': stamp, 'event': str(event),
                                    'detail': detail or {}}, default=str) + '\n')
    except Exception as e:  # noqa: BLE001 - never fail the caller
        print(f'[DEV] event log write failed: {e}', flush=True)
