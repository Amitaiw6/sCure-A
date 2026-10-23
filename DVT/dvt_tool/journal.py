"""Shared campaign through the Google Drive folder — several consoles at once.

No server: the campaign is shared through the folder Google Drive for Desktop
already synchronises (Settings → Google Drive sync, mode "folder", e.g.
G:\\My Drive\\sCure DVT). SQLite must never be shared that way, so instead:

    * every console keeps its own local campaign.db (its cache and its wizard state)
    * every write a console makes is appended, as an event, to ITS OWN journal file
        <shared>/journal/<client-id>.jsonl          one writer per file — Drive never
                                                    has to merge anything
    * every console pulls the other consoles' journals (every JOURNAL_PULL_S
      seconds and after each of its own writes) and replays the events it has
      not applied yet into its local campaign.db — so every dashboard shows
      the whole team's campaign
    * attachments (CSV, PNG, logs) are copied into <shared>/attachments/<run>/ and
      the event carries the relative path, so every console resolves them

Rules that make this safe:
    - one writer per file, append only; events carry a uuid, so replaying is
      idempotent (journal_applied) and a re-read of a file never duplicates
    - events are applied in timestamp order; ids created on one console
      (redlines, waivers, supplementary runs, NCRs) are re-used on replay
    - a run belongs to whoever started it first: a later `start_run` from
      another console is recorded as a CLAIM CONFLICT (events log + a toast),
      not applied over the owner
    - local-only settings (machine address, language, meter, SSH) are never
      journaled — only campaign data is

`Journal.open()` is a no-op object when there is no shared folder (mode api /
off), so the rest of the console does not care.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .store import Store, now

JOURNAL_PULL_S = 15
JOURNAL_DIR, ATTACH_DIR = "journal", "attachments"
RESET_MARKER, RESET_LOG = "reset.json", "reset_log.jsonl"   # campaign reset: events older than the marker are never replayed again

# Store methods that change campaign data -> journaled. Value: attribute of the
# returned id to re-use on replay (table, id column) or None.
OPS = {
    "freeze_config": None, "start_run": None, "confirm_preconditions": None, "confirm_safety": None, "set_step": None,
    "set_values": None, "finish_run": None, "reject_run": None, "link_parent": None,
    "add_supplementary": ("runs", "run_id"), "add_redline": ("redlines", "id"), "open_ncr": ("ncrs", "ncr_id"),
    "close_ncr": None, "waive": ("waivers", "waiver_id"), "add_attachment": ("attachments", "id"),
    "set_calibration": None, "sign_phase": None, "reset_unit": None,
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_applied (id TEXT PRIMARY KEY, client TEXT, ts TEXT, op TEXT);
CREATE TABLE IF NOT EXISTS journal_cursor (file TEXT PRIMARY KEY, lines INTEGER NOT NULL);
"""


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=-]+", "_", s)


@dataclass
class PullResult:
    applied: int = 0
    conflicts: list[str] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    at: str = ""


class Journal:
    """One console's journal + the replay of everyone else's."""

    def __init__(self, store: Store, local_dir: Path, shared: Path | None, client_id: str, operator: str = "", catalog_version: str = ""):
        self.store, self.local_dir, self.shared, self.client_id = store, Path(local_dir), (Path(shared) if shared else None), client_id
        self.operator, self.catalog_version = operator, catalog_version
        self.replaying = False; self._attached = False; self.last_pull: PullResult | None = None
        self.store.db.executescript(SCHEMA); self.store.db.commit()
        self.local_file = self.local_dir / JOURNAL_DIR / f"{client_id}.jsonl"
        self.local_file.parent.mkdir(parents=True, exist_ok=True)
        self.local_file.touch(exist_ok=True)         # an empty journal is pushed too: the team sees this console right away

    # ------------------------------------------------------------ construction
    @classmethod
    def open(cls, store: Store, data_dir: Path, shared: Path | None, operator: str = "", catalog_version: str = "") -> "Journal":
        cid = store.get_meta("journal_client_id")
        if not cid:
            cid = _safe(f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"); store.set_meta("journal_client_id", cid)
        return cls(store, Path(data_dir), shared, cid, operator, catalog_version)

    @property
    def enabled(self) -> bool:
        return self.shared is not None

    def describe(self) -> str:
        return f"{self.shared}  ·  {self.client_id}" if self.enabled else "not shared (no synced folder)"

    # ------------------------------------------------------------ recording (this console's writes)
    def attach(self, store: Store | None = None) -> None:
        """Wrap the store's mutating methods so every call is journaled (unless replaying)."""
        store = store or self.store
        if self._attached: return
        for op in OPS:
            orig = getattr(getattr(store, op), "__wrapped__", getattr(store, op))   # re-attach (new shared folder): unwrap first
            setattr(store, op, self._wrap(op, orig))
        self._attached = True

    def _wrap(self, op, orig):
        sig = inspect.signature(orig)

        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs); bound.apply_defaults(); a = dict(bound.arguments)
            if op == "add_attachment" and not self.replaying and self.enabled:
                a["path"] = self._share_attachment(a["run_id"], a["filename"], a["path"])
                result = orig(**a)
            else:
                result = orig(*args, **kwargs)
            if not self.replaying:
                self.record(op, a, result)
            return result
        wrapper.__wrapped__ = orig; wrapper.__name__ = op
        return wrapper

    def _share_attachment(self, run_id: str, filename: str, path: str) -> str:
        """Copy the file into the shared attachments folder; the event carries the relative path."""
        dst_dir = self.shared / ATTACH_DIR / _safe(run_id); dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / filename
        try:
            if Path(path).resolve() != dst.resolve():
                shutil.copy2(path, dst)
        except OSError:
            return path                                  # keep the local path; the event still carries it
        return str(dst)

    def record(self, op: str, args: dict, result=None) -> dict | None:
        """Append one event to this console's journal (local file, then the shared copy)."""
        ev = {"id": uuid.uuid4().hex, "ts": now(), "by": self.operator or args.get("by") or args.get("operator") or "", "client": self.client_id,
              "op": op, "args": self._jsonable(args), "result": result if isinstance(result, (str, int, float, bool)) else None,
              "catalog": self.catalog_version}
        if op == "add_attachment" and self.enabled and str(args.get("path", "")).startswith(str(self.shared)):
            ev["args"]["path"] = os.path.relpath(args["path"], self.shared).replace("\\", "/")
            ev["args"]["shared"] = True
        with self.local_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.push()
        return ev

    @staticmethod
    def _jsonable(a: dict) -> dict:
        out = {}
        for k, v in a.items():
            if isinstance(v, (str, int, float, bool)) or v is None or isinstance(v, (list, dict)):
                out[k] = v
            else:
                out[k] = str(v)
        return out

    def push(self) -> bool:
        """Copy this console's journal into the shared folder (one writer per file)."""
        if not self.enabled or not self.local_file.exists():
            return False
        try:
            d = self.shared / JOURNAL_DIR; d.mkdir(parents=True, exist_ok=True)
            tmp = d / f".{self.client_id}.tmp"; shutil.copy2(self.local_file, tmp); os.replace(tmp, d / self.local_file.name)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------ campaign reset (erase everything, keep only the audit line)
    def reset_marker(self) -> dict | None:
        """The shared reset marker, if the campaign was ever erased: {ts, by, reason, client}."""
        if not self.enabled:
            return None
        p = self.shared / RESET_MARKER
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except (OSError, ValueError):
            return None

    def erase_shared(self, by: str, reason: str, campaign: str = "") -> dict:
        """Erase the shared campaign: every console's journal, the shared attachments and the campaign exports.
        Writes the reset marker (so stale journals pushed later are ignored by everyone) and one audit line."""
        marker = {"ts": now(), "by": by or "", "reason": reason, "client": self.client_id}
        if not self.enabled:
            return marker
        removed = []
        for name in (JOURNAL_DIR, ATTACH_DIR, "csv", "charts"):
            d = self.shared / name
            if d.exists():
                shutil.rmtree(d, ignore_errors=True); removed.append(name)
        for f in self.shared.iterdir() if self.shared.exists() else []:
            if f.is_file() and ((campaign and f.name.startswith(campaign + ".")) or f.name == "temperature_by_component.csv"):
                try: f.unlink(); removed.append(f.name)
                except OSError: pass
        marker["removed"] = removed
        try:
            self.shared.mkdir(parents=True, exist_ok=True)
            (self.shared / RESET_MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=1), encoding="utf-8")
            with (self.shared / RESET_LOG).open("a", encoding="utf-8") as f:
                f.write(json.dumps(marker, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return marker

    # ------------------------------------------------------------ replay (other consoles' writes)
    def pull(self) -> PullResult:
        res = PullResult(at=now())
        if not self.enabled:
            self.last_pull = res; return res
        d = self.shared / JOURNAL_DIR
        if not d.exists():
            self.last_pull = res; return res
        new: list[tuple[dict, str, int]] = []
        for f in sorted(d.glob("*.jsonl")):
            if f.name == self.local_file.name:
                continue
            res.clients.append(f.stem)
            cur = self.store.db.execute("SELECT lines FROM journal_cursor WHERE file=?", (f.name,)).fetchone()
            seen = cur["lines"] if cur else 0
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                res.errors.append(f"{f.name}: {e}"); continue
            for i, line in enumerate(lines):
                if i < seen or not line.strip():
                    continue
                try:
                    new.append((json.loads(line), f.name, i + 1))
                except ValueError:
                    res.errors.append(f"{f.name}:{i + 1}: bad event")
        marker = self.reset_marker()
        if marker:                                   # the campaign was erased: anything written before that instant stays erased
            new = [x for x in new if x[0].get("ts", "") > marker.get("ts", "")]   # second resolution: the reset second itself is erased too
        new.sort(key=lambda t: (t[0].get("ts", ""), t[1], t[2]))
        for ev, fname, lineno in new:
            if self.store.db.execute("SELECT 1 FROM journal_applied WHERE id=?", (ev["id"],)).fetchone():
                continue
            try:
                conflict = self._apply(ev)
            except Exception as e:  # noqa: BLE001 - one bad event must not stop the others
                res.errors.append(f"{ev.get('op')} from {ev.get('client')}: {type(e).__name__}: {e}"); conflict = None
            else:
                res.applied += 1
            if conflict:
                res.conflicts.append(conflict)
            self.store.db.execute("INSERT OR IGNORE INTO journal_applied VALUES (?,?,?,?)", (ev["id"], ev.get("client"), ev.get("ts"), ev.get("op")))
        for fname in {t[1] for t in new} | {f.name for f in d.glob("*.jsonl") if f.name != self.local_file.name}:
            p = d / fname
            try:
                n = len(p.read_text(encoding="utf-8").splitlines())
            except OSError:
                continue
            self.store.db.execute("INSERT OR REPLACE INTO journal_cursor VALUES (?,?)", (fname, n))
        self.store.db.commit()
        self.last_pull = res
        return res

    def _apply(self, ev: dict) -> str | None:
        """Replay one foreign event into the local store. Returns a conflict text or None."""
        op, a = ev["op"], dict(ev.get("args") or {})
        if op not in OPS:
            return None
        orig = getattr(getattr(self.store, op), "__wrapped__", getattr(self.store, op))
        if op == "start_run":
            r = self.store.run(a["run_id"])
            if r and r["status"] != "NOT_STARTED" and r.get("operator") and r["operator"] != a.get("operator"):
                # the run belongs to whoever started it FIRST — the same answer on every console
                mine_first = (r.get("started_at") or "") <= (ev.get("ts") or "")
                if not mine_first:
                    self.store.db.execute("UPDATE runs SET operator=?, started_at=? WHERE run_id=?", (a.get("operator"), ev.get("ts"), a["run_id"]))
                self.store.log("Run claim conflict", ev.get("by"), a["run_id"],
                               {"kept": r["operator"] if mine_first else a.get("operator"), "lost": a.get("operator") if mine_first else r["operator"],
                                "client": ev.get("client"), "at": ev.get("ts")})
                self.store.db.commit()
                if mine_first:
                    return f"{a['run_id']}: also started by {a.get('operator')} ({ev.get('client')}) — kept {r['operator']}, who started first"
                return f"{a['run_id']}: {a.get('operator')} ({ev.get('client')}) started it first — {r['operator']}'s later claim was overridden"
        if op == "add_attachment" and a.pop("shared", False) and self.enabled:
            a["path"] = str(self.shared / a["path"])
        self.replaying = True
        try:
            result = orig(**a)
        finally:
            self.replaying = False
        want = ev.get("result"); spec = OPS[op]
        if spec and want and isinstance(result, str) and result != want:
            table, col = spec
            exists = self.store.db.execute(f"SELECT 1 FROM {table} WHERE {col}=?", (want,)).fetchone()
            if exists and op == "open_ncr":
                want = f"{want}-{ev.get('client', 'x')[:6]}"          # two consoles numbered an NCR the same second
            self.store.db.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (want, result))
            if op == "add_supplementary":
                self.store.db.execute("UPDATE runs SET parent_run_id=? WHERE parent_run_id=?", (want, result))
            self.store.db.commit()
        return None

    # ------------------------------------------------------------ status
    def status(self) -> dict:
        n_own = 0
        if self.local_file.exists():
            n_own = sum(1 for line in self.local_file.read_text(encoding="utf-8").splitlines() if line.strip())
        applied = self.store.db.execute("SELECT COUNT(*) c FROM journal_applied").fetchone()["c"]
        clients = [r["client"] for r in self.store.db.execute("SELECT DISTINCT client FROM journal_applied")]
        return {"enabled": self.enabled, "shared": str(self.shared) if self.shared else None, "client_id": self.client_id,
                "own_events": n_own, "applied_events": applied, "other_clients": sorted(c for c in clients if c),
                "last_pull": self.last_pull.at if self.last_pull else None,
                "last_pull_applied": self.last_pull.applied if self.last_pull else 0,
                "conflicts": list(self.last_pull.conflicts) if self.last_pull else []}
