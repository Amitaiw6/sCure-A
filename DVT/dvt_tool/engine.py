"""Wizard engine: phase gates, dependencies, next action, verdicts
(SRS-DVT-080…088, 094…100).

The engine is pure logic over Catalog + Store; the desktop app only renders
what it returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .catalog import Catalog, RunSpec
from .store import Store
from . import criteria

ROLLUP_ORDER = ["FAIL", "BLOCKED", "WAIVED", "PASS"]


@dataclass
class Blocker:
    code: str
    text: str


@dataclass
class NextAction:
    unit_id: str
    phase: dict | None
    run: dict | None            # store run row (NOT_STARTED / IN_PROGRESS)
    blockers: list[Blocker]
    message: str


class Engine:
    def __init__(self, catalog: Catalog, store: Store):
        self.cat, self.store = catalog, store
        store.ensure_units(catalog.units)
        store.ensure_runs(catalog.runs(), catalog.version)
        store.set_meta("catalog_version", catalog.version)

    # ---------------- status helpers ----------------
    def test_verdict(self, test_id: str, unit_id: str | None = None) -> str | None:
        """Rolled-up verdict (SRS-DVT-096): PASS only if every applicable run passed."""
        runs = [r for r in self.store.runs(test_id, unit_id) if r["status"] != "REJECTED"]
        if not runs:
            return None
        verdicts = [r["verdict"] for r in runs]
        if any(v is None for v in verdicts):
            return None
        for v in ROLLUP_ORDER:
            if v in verdicts:
                return v
        return None

    def test_done(self, test_id: str, unit_id: str) -> bool:
        runs = [r for r in self.store.runs(test_id, unit_id) if r["status"] != "REJECTED"]
        return bool(runs) and all(r["status"] == "DONE" for r in runs)

    def phase_closed(self, phase: dict, unit_id: str) -> bool:
        tests = [t for t in phase.get("tests", []) if unit_id in self.cat.applicable_units(t)]
        if not tests:                      # nothing owed by this unit in this phase
            return True
        for t in tests:
            v = self.test_verdict(t, unit_id)
            if v not in ("PASS", "WAIVED"):
                return False
        return True

    def current_phase(self, unit_id: str) -> dict | None:
        for p in sorted(self.cat.phases, key=lambda p: p["id"]):
            if p["id"] == 0:
                u = next((x for x in self.store.units() if x["unit_id"] == unit_id), None)
                if not (u and u["config_frozen"]):
                    return p
                continue
            if not self.phase_closed(p, unit_id):
                return p
        return None

    # ---------------- gating (SRS-DVT-082/085) ----------------
    def blockers_for(self, run: dict) -> list[Blocker]:
        b: list[Blocker] = []
        t = self.cat.tests[run["test_id"]]
        unit = run["unit_id"]
        u = next((x for x in self.store.units() if x["unit_id"] == unit), None)
        if not (u and u["config_frozen"]):
            b.append(Blocker("CONFIG", f"{unit}: configuration not frozen (Phase 0)"))
        phase = self.cat.phase_of(run["test_id"])
        for p in sorted(self.cat.phases, key=lambda p: p["id"]):
            if p["id"] >= phase["id"] or p["id"] == 0:
                continue
            if not self.phase_closed(p, unit):
                b.append(Blocker("PHASE", f"phase {p['id']} ({p['name']}) not closed for {unit}"))
        if not self.store.phase_signed(unit, phase["id"]):
            b.append(Blocker("TRR", f"readiness checklist for phase {phase['id']} not signed for {unit}"))
        # earth before power, destructive last, hipot once
        if run["test_id"] != "DVT-ELE-001" and self.test_verdict("DVT-ELE-001", unit) != "PASS" and "DVT-ELE-001" in self.cat.tests:
            b.append(Blocker("EARTH", "protective earth bonding (ELE-001) not PASS on this unit"))
        for d in t.get("dependencies") or []:
            dep_units = self.cat.applicable_units(d)
            check_unit = unit if unit in dep_units else (dep_units[0] if dep_units else None)
            if check_unit and self.test_verdict(d, check_unit) not in ("PASS", "WAIVED"):
                b.append(Blocker("DEP", f"dependency {d} not PASS/WAIVED"))
        if phase["id"] != 5 and self._destructive_done(unit):
            b.append(Blocker("DESTRUCTIVE", f"{unit} has already been through destructive testing — a different article"))
        today = date.today().isoformat()
        for e in t.get("equipment") or []:
            c = self.store.calibration(e["name"])
            if c is None or not c["valid_until"] or c["valid_until"] < today:
                b.append(Blocker("CAL", f"no valid calibration record for: {e['name']}"))
        return b

    def _destructive_done(self, unit: str) -> bool:
        for p in self.cat.phases:
            if p["id"] == 5:
                return any(r["status"] == "DONE" for t in p["tests"] for r in self.store.runs(t, unit))
        return False

    # ---------------- next action (SRS-DVT-080) ----------------
    def next_action(self, unit_id: str) -> NextAction:
        in_progress = [r for r in self.store.runs(unit_id=unit_id) if r["status"] == "IN_PROGRESS"]
        if in_progress:
            r = in_progress[0]
            return NextAction(unit_id, self.cat.phase_of(r["test_id"]), r, [], f"Resume {r['test_id']} at step {r['current_step'] + 1}")
        phase = self.current_phase(unit_id)
        if phase is None:
            return NextAction(unit_id, None, None, [], f"{unit_id}: all phases complete")
        if phase["id"] == 0:
            return NextAction(unit_id, phase, None, [Blocker("CONFIG", "freeze the unit configuration")],
                              "Phase 0 — record and freeze the configuration")
        for tid in phase["tests"]:
            if unit_id not in self.cat.applicable_units(tid):
                continue
            for r in self.store.runs(tid, unit_id):
                if r["status"] == "NOT_STARTED":
                    return NextAction(unit_id, phase, r, self.blockers_for(r),
                                      f"Next: {tid} — {self.cat.tests[tid]['title']} ({self._variant_text(r)}, rep {r['repetition']})")
        return NextAction(unit_id, phase, None, [Blocker("GATE", phase.get("gate") or "phase gate")],
                          f"Phase {phase['id']} runs are done but the gate is not met: {phase.get('gate')}")

    @staticmethod
    def _variant_text(run: dict) -> str:
        return ", ".join(f"{k}={v}" for k, v in run["variant"].items()) or "single"

    # ---------------- verdict ----------------
    def evaluate(self, run_id: str) -> tuple[str, str]:
        run = self.store.run(run_id)
        t = self.cat.tests[run["test_id"]]
        values = {**run["variant"], **self.store.values(run_id)}
        return criteria.evaluate(t["pass_criteria"], values, self.cat.thresholds)

    def finish(self, run_id: str, by: str, witness: str | None = None) -> tuple[str, str]:
        verdict, detail = self.evaluate(run_id)
        self.store.finish_run(run_id, verdict, detail, by, witness)
        if verdict == "FAIL":
            self.store.open_ncr(run_id, f"{run_id}: pass criteria not met", by)
        return verdict, detail

    # ---------------- dashboard summaries ----------------
    def test_status(self, test_id: str) -> dict:
        """One row of the test matrix: status ∈ Complete | Running | Failed |
        Pending | Blocked, rolled-up result, run counts."""
        runs = [r for r in self.store.runs(test_id) if r["status"] != "REJECTED"]
        done = sum(1 for r in runs if r["status"] == "DONE")
        running = any(r["status"] == "IN_PROGRESS" for r in runs)
        verdicts = [r["verdict"] for r in runs if r["verdict"]]
        rollup = self.test_verdict(test_id)
        if any(v == "FAIL" for v in verdicts):
            status = "Failed"
        elif running:
            status = "Running"
        elif runs and done == len(runs):
            status = "Complete"
        elif any(v == "BLOCKED" for v in verdicts):
            status = "Blocked"
        else:
            status = "Pending"
        t = self.cat.tests[test_id]
        app = t["applicability"]
        appl = ("ALL" if app["rule"] == "ALL" else
                f"{len(app.get('units') or [])} units" if app["rule"] == "SUBSET" else (app.get("unit") or "TBD"))
        return {"testId": test_id, "title": t["title"], "subsystem": t["subsystem"], "method": t["method"],
                "applicability": appl, "units": self.cat.applicable_units(test_id),
                "reps": int(t.get("repetitions") or 1) * len(self.cat.variants(test_id)),
                "durationMin": t.get("duration_est_min"), "phase": self.cat.phase_of(test_id)["id"],
                "status": status, "result": rollup, "runsDone": done, "runsTotal": len(runs),
                "pass": sum(1 for v in verdicts if v == "PASS"), "fail": sum(1 for v in verdicts if v == "FAIL"),
                "blocked": sum(1 for v in verdicts if v == "BLOCKED"), "waived": sum(1 for v in verdicts if v == "WAIVED")}

    def subsystem_summary(self) -> dict:
        """{subsystem: {tests, reps, durationMin, complete, running, failed, pending, blocked, pass, rows:[test_status…]}}"""
        out: dict[str, dict] = {}
        for tid in self.cat.ordered_test_ids():
            row = self.test_status(tid)
            s = out.setdefault(row["subsystem"], {"tests": 0, "reps": 0, "durationMin": 0, "complete": 0, "running": 0,
                                                  "failed": 0, "pending": 0, "blocked": 0, "pass": 0, "runsDone": 0, "runsTotal": 0, "rows": []})
            s["tests"] += 1; s["reps"] += row["reps"]; s["durationMin"] += (row["durationMin"] or 0) * row["reps"]
            s[row["status"].lower()] += 1
            s["runsDone"] += row["runsDone"]; s["runsTotal"] += row["runsTotal"]
            if row["result"] == "PASS": s["pass"] += 1
            s["rows"].append(row)
        for s in out.values():
            s["percent"] = round(100 * s["runsDone"] / s["runsTotal"]) if s["runsTotal"] else 0
        return out

    def remaining(self) -> list[dict]:
        """What is still owed, per test: pending runs per unit — the 'what is left' list."""
        out = []
        for tid in self.cat.ordered_test_ids():
            per_unit = {}
            for r in self.store.runs(tid):
                if r["status"] in ("NOT_STARTED", "IN_PROGRESS"):
                    per_unit[r["unit_id"]] = per_unit.get(r["unit_id"], 0) + 1
            if per_unit:
                t = self.cat.tests[tid]
                out.append({"testId": tid, "title": t["title"], "subsystem": t["subsystem"], "phase": self.cat.phase_of(tid)["id"],
                            "pendingRuns": sum(per_unit.values()), "perUnit": per_unit,
                            "estMin": (t.get("duration_est_min") or 0) * sum(per_unit.values())})
        return out

    def unit_matrix(self) -> dict:
        """tests × units verdict matrix for the cross-unit comparison."""
        units = self.cat.unit_ids(); rows = []
        for tid in self.cat.ordered_test_ids():
            appl = set(self.cat.applicable_units(tid))
            cells = {}
            for u in units:
                if u not in appl:
                    cells[u] = "N/A"
                else:
                    runs = [r for r in self.store.runs(tid, u) if r["status"] != "REJECTED"]
                    v = self.test_verdict(tid, u)
                    done = sum(1 for r in runs if r["status"] == "DONE")
                    cells[u] = v or (f"{done}/{len(runs)}" if runs else "—")
            rows.append({"testId": tid, "title": self.cat.tests[tid]["title"], "subsystem": self.cat.tests[tid]["subsystem"], "cells": cells})
        return {"units": units, "rows": rows}

    # ---------------- progress ----------------
    def progress(self) -> dict:
        runs = self.store.runs()
        total = len(runs)
        done = [r for r in runs if r["status"] == "DONE"]
        by_v = {v: sum(1 for r in done if r["verdict"] == v) for v in ("PASS", "FAIL", "BLOCKED", "WAIVED")}
        per_unit = {}
        for u in self.cat.unit_ids():
            ur = [r for r in runs if r["unit_id"] == u]
            per_unit[u] = {"total": len(ur), "done": sum(1 for r in ur if r["status"] == "DONE"),
                           "phase": (self.current_phase(u) or {}).get("id", "complete")}
        return {"total": total, "done": len(done), "rejected": sum(1 for r in runs if r["status"] == "REJECTED"),
                **by_v, "perUnit": per_unit, "openNcrs": len(self.store.ncrs(open_only=True))}
