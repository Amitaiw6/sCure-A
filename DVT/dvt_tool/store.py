"""SQLite campaign store — the single place everything lives (SRS-DVT-090).

Tables: units, runs, run_values, redlines, ncrs, waivers, attachments,
calibration, phase_signoff, events, sync_queue.
Every write is committed immediately; the export/sync layer reads from here.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS units (unit_id TEXT PRIMARY KEY, role TEXT, serial TEXT, config_frozen INTEGER DEFAULT 0,
    config_frozen_by TEXT, config_frozen_at TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, test_id TEXT NOT NULL, unit_id TEXT NOT NULL, variant TEXT NOT NULL,
    repetition INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'NOT_STARTED',   -- NOT_STARTED|IN_PROGRESS|DONE|REJECTED
    verdict TEXT,                       -- PASS|FAIL|BLOCKED|WAIVED|null
    verdict_detail TEXT, operator TEXT, witness TEXT, started_at TEXT, finished_at TEXT,
    current_step INTEGER DEFAULT 0, preconditions_confirmed INTEGER DEFAULT 0, safety_confirmed INTEGER DEFAULT 0,
    supplementary INTEGER DEFAULT 0, parent_run_id TEXT, reject_reason TEXT, notes TEXT, catalog_version TEXT);
CREATE TABLE IF NOT EXISTS run_values (run_id TEXT NOT NULL, field TEXT NOT NULL, value TEXT, recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, field));
CREATE TABLE IF NOT EXISTS redlines (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_index INTEGER NOT NULL,
    as_run TEXT NOT NULL, reason TEXT NOT NULL, by_whom TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ncrs (ncr_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, opened_at TEXT NOT NULL, opened_by TEXT,
    description TEXT NOT NULL, disposition TEXT, closed_at TEXT, closed_by TEXT);
CREATE TABLE IF NOT EXISTS waivers (waiver_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, approver TEXT NOT NULL,
    rationale TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attachments (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL,
    kind TEXT, added_at TEXT NOT NULL, sha256 TEXT);
CREATE TABLE IF NOT EXISTS calibration (instrument TEXT PRIMARY KEY, calibration_id TEXT, valid_until TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS phase_signoff (unit_id TEXT NOT NULL, phase_id INTEGER NOT NULL, signed_by TEXT NOT NULL,
    signed_at TEXT NOT NULL, checklist TEXT, PRIMARY KEY (unit_id, phase_id));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT, event TEXT NOT NULL,
    run_id TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS sync_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, queued_at TEXT NOT NULL, kind TEXT NOT NULL,
    ref TEXT, attempts INTEGER DEFAULT 0, last_error TEXT, done_at TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---------------- meta / units ----------------
    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)); self.db.commit()

    def get_meta(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def ensure_units(self, units: Iterable[dict]) -> None:
        for u in units:
            self.db.execute("INSERT OR IGNORE INTO units (unit_id, role, notes) VALUES (?,?,?)",
                            (u["id"], u.get("role"), u.get("notes")))
        self.db.commit()

    def units(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM units ORDER BY unit_id")]

    def freeze_config(self, unit_id: str, by: str, serial: str | None = None) -> None:
        self.db.execute("UPDATE units SET config_frozen=1, config_frozen_by=?, config_frozen_at=?, serial=COALESCE(?, serial) WHERE unit_id=?",
                        (by, now(), serial, unit_id))
        self.log("Configuration frozen", by, None, {"unit": unit_id, "serial": serial}); self.db.commit()

    # ---------------- runs ----------------
    def ensure_runs(self, specs: Iterable, catalog_version: str) -> None:
        for s in specs:
            self.db.execute("INSERT OR IGNORE INTO runs (run_id, test_id, unit_id, variant, repetition, supplementary, catalog_version) "
                            "VALUES (?,?,?,?,?,?,?)", (s.run_id, s.test_id, s.unit_id, json.dumps(s.variant, sort_keys=True),
                                                       s.repetition, 1 if s.supplementary else 0, catalog_version))
        self.db.commit()

    def run(self, run_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(r) if r else None

    def runs(self, test_id: str | None = None, unit_id: str | None = None, include_supplementary=False) -> list[dict]:
        q, args = "SELECT * FROM runs WHERE 1=1", []
        if test_id: q += " AND test_id=?"; args.append(test_id)
        if unit_id: q += " AND unit_id=?"; args.append(unit_id)
        if not include_supplementary: q += " AND supplementary=0"
        return [self._run_row(r) for r in self.db.execute(q + " ORDER BY test_id, unit_id, variant, repetition", args)]

    def _run_row(self, r) -> dict:
        d = dict(r); d["variant"] = json.loads(d["variant"] or "{}"); return d

    def start_run(self, run_id: str, operator: str) -> None:
        self.db.execute("UPDATE runs SET status='IN_PROGRESS', operator=?, started_at=COALESCE(started_at, ?) WHERE run_id=?",
                        (operator, now(), run_id))
        self.log("Run started", operator, run_id); self.db.commit()

    def confirm_preconditions(self, run_id: str, by: str) -> None:
        self.db.execute("UPDATE runs SET preconditions_confirmed=1 WHERE run_id=?", (run_id,))
        self.log("Preconditions confirmed", by, run_id); self.db.commit()

    def confirm_safety(self, run_id: str, by: str) -> None:
        self.db.execute("UPDATE runs SET safety_confirmed=1 WHERE run_id=?", (run_id,))
        self.log("Safety plan acknowledged", by, run_id); self.db.commit()

    def set_step(self, run_id: str, step_index: int) -> None:
        self.db.execute("UPDATE runs SET current_step=? WHERE run_id=?", (step_index, run_id)); self.db.commit()

    def set_values(self, run_id: str, values: dict[str, Any], by: str | None = None) -> None:
        for k, v in values.items():
            self.db.execute("INSERT OR REPLACE INTO run_values (run_id, field, value, recorded_at) VALUES (?,?,?,?)",
                            (run_id, k, json.dumps(v), now()))
        self.log("Values recorded", by, run_id, {"fields": sorted(values)}); self.db.commit()

    def values(self, run_id: str) -> dict[str, Any]:
        return {r["field"]: json.loads(r["value"]) for r in self.db.execute("SELECT field, value FROM run_values WHERE run_id=?", (run_id,))}

    def finish_run(self, run_id: str, verdict: str, detail: str = "", by: str | None = None, witness: str | None = None) -> None:
        self.db.execute("UPDATE runs SET status='DONE', verdict=?, verdict_detail=?, finished_at=?, witness=COALESCE(?, witness) WHERE run_id=?",
                        (verdict, detail, now(), witness, run_id))
        self.log(f"Run finished: {verdict}", by, run_id, {"detail": detail})
        self.queue("run", run_id); self.db.commit()

    def reject_run(self, run_id: str, reason: str, by: str) -> list[str]:
        """Reject a run (e.g. ambient drift). Co-executed children are rescinded
        with the reason carried across (SRS-DVT-099). Returns affected run ids."""
        affected = [run_id]
        self.db.execute("UPDATE runs SET status='REJECTED', verdict=NULL, reject_reason=? WHERE run_id=?", (reason, run_id))
        for r in self.db.execute("SELECT run_id FROM runs WHERE parent_run_id=?", (run_id,)):
            self.db.execute("UPDATE runs SET status='REJECTED', verdict=NULL, reject_reason=? WHERE run_id=?",
                            (f"parent rejected: {reason}", r["run_id"]))
            affected.append(r["run_id"])
        self.log("Run rejected", by, run_id, {"reason": reason, "rescinded": affected[1:]})
        for a in affected:
            self.queue("run", a)
        self.db.commit()
        return affected

    def link_parent(self, child_run_id: str, parent_run_id: str) -> None:
        self.db.execute("UPDATE runs SET parent_run_id=? WHERE run_id=?", (parent_run_id, child_run_id)); self.db.commit()

    def add_supplementary(self, test_id: str, unit_id: str, variant: dict, parent_run_id: str | None, catalog_version: str) -> str:
        rid = f"{test_id}|{unit_id}|{','.join(f'{k}={v}' for k, v in variant.items())}|S{uuid.uuid4().hex[:6]}"
        self.db.execute("INSERT INTO runs (run_id, test_id, unit_id, variant, repetition, supplementary, parent_run_id, catalog_version) "
                        "VALUES (?,?,?,?,0,1,?,?)", (rid, test_id, unit_id, json.dumps(variant, sort_keys=True), parent_run_id, catalog_version))
        self.db.commit(); return rid

    # ---------------- redlines / NCR / waivers / attachments ----------------
    def add_redline(self, run_id: str, step_index: int, as_run: str, reason: str, by: str) -> str:
        rid = str(uuid.uuid4())
        self.db.execute("INSERT INTO redlines VALUES (?,?,?,?,?,?,?)", (rid, run_id, step_index, as_run, reason, by, now()))
        self.log("Redline", by, run_id, {"step": step_index, "reason": reason}); self.db.commit(); return rid

    def redlines(self, run_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM redlines WHERE run_id=? ORDER BY step_index", (run_id,))]

    def open_ncr(self, run_id: str, description: str, by: str) -> str:
        n = self.db.execute("SELECT COUNT(*) c FROM ncrs").fetchone()["c"] + 1
        ncr_id = f"NCR-{n:04d}"
        self.db.execute("INSERT INTO ncrs (ncr_id, run_id, opened_at, opened_by, description) VALUES (?,?,?,?,?)",
                        (ncr_id, run_id, now(), by, description))
        self.log("NCR opened", by, run_id, {"ncr": ncr_id}); self.queue("ncr", ncr_id); self.db.commit(); return ncr_id

    def close_ncr(self, ncr_id: str, disposition: str, by: str) -> None:
        self.db.execute("UPDATE ncrs SET disposition=?, closed_at=?, closed_by=? WHERE ncr_id=?", (disposition, now(), by, ncr_id))
        self.log("NCR closed", by, None, {"ncr": ncr_id, "disposition": disposition}); self.queue("ncr", ncr_id); self.db.commit()

    def ncrs(self, open_only=False) -> list[dict]:
        q = "SELECT * FROM ncrs" + (" WHERE closed_at IS NULL" if open_only else "") + " ORDER BY opened_at"
        return [dict(r) for r in self.db.execute(q)]

    def waive(self, run_id: str, approver: str, rationale: str, by: str) -> str:
        if not approver.strip() or not rationale.strip():
            raise ValueError("a waiver needs an approver and a rationale (SRS-DVT-087)")
        wid = str(uuid.uuid4())
        self.db.execute("INSERT INTO waivers VALUES (?,?,?,?,?)", (wid, run_id, approver, rationale, now()))
        self.db.execute("UPDATE runs SET verdict='WAIVED', status='DONE', finished_at=COALESCE(finished_at, ?) WHERE run_id=?", (now(), run_id))
        self.log("Waiver approved", by, run_id, {"approver": approver}); self.queue("run", run_id); self.db.commit(); return wid

    def waivers(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM waivers ORDER BY at")]

    def add_attachment(self, run_id: str, filename: str, path: str, kind: str, sha256: str | None = None) -> str:
        aid = str(uuid.uuid4())
        self.db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?)", (aid, run_id, filename, path, kind, now(), sha256))
        self.queue("attachment", aid); self.db.commit(); return aid

    def attachments(self, run_id: str | None = None) -> list[dict]:
        q, a = ("SELECT * FROM attachments WHERE run_id=?", (run_id,)) if run_id else ("SELECT * FROM attachments", ())
        return [dict(r) for r in self.db.execute(q, a)]

    # ---------------- calibration / phase sign-off ----------------
    def set_calibration(self, instrument: str, calibration_id: str, valid_until: str, notes: str = "") -> None:
        self.db.execute("INSERT OR REPLACE INTO calibration VALUES (?,?,?,?)", (instrument, calibration_id, valid_until, notes)); self.db.commit()

    def calibration(self, instrument: str) -> dict | None:
        r = self.db.execute("SELECT * FROM calibration WHERE instrument=?", (instrument,)).fetchone()
        return dict(r) if r else None

    def sign_phase(self, unit_id: str, phase_id: int, by: str, checklist: list[str]) -> None:
        self.db.execute("INSERT OR REPLACE INTO phase_signoff VALUES (?,?,?,?,?)", (unit_id, phase_id, by, now(), json.dumps(checklist)))
        self.log("Phase readiness signed", by, None, {"unit": unit_id, "phase": phase_id}); self.db.commit()

    def phase_signed(self, unit_id: str, phase_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM phase_signoff WHERE unit_id=? AND phase_id=?", (unit_id, phase_id)).fetchone() is not None

    # ---------------- events / sync queue ----------------
    def log(self, event: str, actor: str | None, run_id: str | None, detail: dict | None = None) -> None:
        self.db.execute("INSERT INTO events (at, actor, event, run_id, detail) VALUES (?,?,?,?,?)",
                        (now(), actor, event, run_id, json.dumps(detail or {})))

    def events(self, limit=200) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def queue(self, kind: str, ref: str) -> None:
        self.db.execute("INSERT INTO sync_queue (queued_at, kind, ref) VALUES (?,?,?)", (now(), kind, ref))

    def pending_sync(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sync_queue WHERE done_at IS NULL ORDER BY id")]

    def mark_synced(self, ids: Iterable[int]) -> None:
        for i in ids:
            self.db.execute("UPDATE sync_queue SET done_at=? WHERE id=?", (now(), i))
        self.db.commit()

    def mark_sync_failed(self, ids: Iterable[int], error: str) -> None:
        for i in ids:
            self.db.execute("UPDATE sync_queue SET attempts=attempts+1, last_error=? WHERE id=?", (error[:400], i))
        self.db.commit()

    # ---------------- search (SRS-DVT-092) ----------------
    def search(self, text: str) -> list[dict]:
        like = f"%{text}%"
        out = []
        for r in self.db.execute("SELECT run_id, test_id, unit_id, verdict FROM runs WHERE run_id LIKE ? OR verdict_detail LIKE ? OR notes LIKE ?", (like, like, like)):
            out.append({"kind": "run", **dict(r)})
        for r in self.db.execute("SELECT run_id, field, value FROM run_values WHERE value LIKE ?", (like,)):
            out.append({"kind": "value", **dict(r)})
        for r in self.db.execute("SELECT ncr_id, run_id, description FROM ncrs WHERE description LIKE ? OR disposition LIKE ?", (like, like)):
            out.append({"kind": "ncr", **dict(r)})
        return out
