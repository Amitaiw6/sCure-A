"""Hash-chained audit log (ARCHITECTURE.md §13).

One JSON object per line:
    {"ts","serial","deviceId","actor","event","detail","prevHash","hash"}
hash = sha256(prevHash + canonical(entry without hash)).

Used by the device security service (/data/audit/audit.jsonl), by the
provisioning tool (station ledger) and by the serial service (DB rows carry
the same chain so an exported device log can be cross-checked).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .crypto import canonical, sha256_hex

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: str | os.PathLike, serial: str | None, device_id: str | None):
        self.path = Path(path)
        self.serial = serial
        self.device_id = device_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last = self._tail_hash()

    def _tail_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open("rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)["hash"]
        return last

    def append(self, event: str, detail: dict | None = None, actor: str = "system") -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "serial": self.serial,
            "deviceId": self.device_id,
            "actor": actor,
            "event": event,
            "detail": detail or {},
            "prevHash": self._last,
        }
        entry["hash"] = sha256_hex(self._last.encode() + canonical(entry))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._last = entry["hash"]
        return entry

    def entries(self) -> Iterator[dict]:
        if not self.path.exists():
            return iter(())
        return (json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip())

    @property
    def last_hash(self) -> str:
        return self._last


def verify_chain(entries: Iterator[dict] | list[dict]) -> tuple[bool, int, str]:
    """(ok, count, last_hash). ok=False at the first broken link — a
    modified, removed or reordered line."""
    prev = GENESIS
    n = 0
    for e in entries:
        body = {k: v for k, v in e.items() if k != "hash"}
        if body.get("prevHash") != prev:
            return False, n, prev
        if sha256_hex(prev.encode() + canonical(body)) != e.get("hash"):
            return False, n, prev
        prev = e["hash"]
        n += 1
    return True, n, prev
