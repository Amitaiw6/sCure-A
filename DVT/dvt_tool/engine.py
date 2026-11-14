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
from .ui.i18n import tr, trf          # pure strings module (no Qt) — messages follow the console language

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
    setup: str = ""             # bench-setup note: same instruments as the last test, or what to add / remove (SRS-DVT-196)


class Engine:
    def __init__(self, catalog: Catalog, store: Store):
        self.cat, self.store = catalog, store
        store.ensure_units(catalog.units)
        store.apply_renames(catalog.renames)          # before the run set is reconciled, so nothing recorded is orphaned
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
            b.append(Blocker("CONFIG", trf("{unit}: configuration not frozen (Phase 0)", unit=unit)))
        phase = self.cat.phase_of(run["test_id"])
        for p in sorted(self.cat.phases, key=lambda p: p["id"]):
            if p["id"] >= phase["id"] or p["id"] == 0:
                continue
            if not self.phase_closed(p, unit):
                b.append(Blocker("PHASE", trf("phase {phase} ({name}) not closed for {unit}", phase=p["id"], name=p["name"], unit=unit)))
        if not self.store.phase_signed(unit, phase["id"]):
            b.append(Blocker("TRR", trf("readiness checklist for phase {phase} not signed for {unit}", phase=phase["id"], unit=unit)))
        # earth before power, destructive last, hipot once
        # (DVT-ELE-001 is done once, by hand, on one unit: a unit without its own DVT-ELE-001 run relies on that unit's result)
        if run["test_id"] != "DVT-ELE-001" and "DVT-ELE-001" in self.cat.tests:
            earth_units = self.cat.applicable_units("DVT-ELE-001")
            earth_unit = unit if unit in earth_units else (earth_units[0] if earth_units else None)
            if earth_unit and self.test_verdict("DVT-ELE-001", earth_unit) != "PASS":
                b.append(Blocker("EARTH", tr("protective earth bonding (DVT-ELE-001) not PASS on this unit")))
        # after_all (the fault-alarm review): every other test owed by this unit must have a result first
        if t.get("after_all"):
            open_tests = [tid for tid in self.cat.tests if tid != run["test_id"] and unit in self.cat.applicable_units(tid)
                          and self.test_verdict(tid, unit) not in ("PASS", "FAIL", "WAIVED", "BLOCKED")]
            if open_tests:
                b.append(Blocker("LAST", trf("runs last: {n} other test(s) on {unit} have no result yet", n=len(open_tests), unit=unit)))
        for d in t.get("dependencies") or []:
            dep_units = self.cat.applicable_units(d)
            check_unit = unit if unit in dep_units else (dep_units[0] if dep_units else None)
            if check_unit and self.test_verdict(d, check_unit) not in ("PASS", "WAIVED"):
                b.append(Blocker("DEP", trf("dependency {dep} not PASS/WAIVED", dep=d)))
        if phase["id"] != 5 and self._destructive_done(unit):
            b.append(Blocker("DESTRUCTIVE", trf("{unit} has already been through destructive testing — a different article", unit=unit)))
        today = date.today().isoformat()
        for e in t.get("equipment") or []:
            from . import bench
            if e.get("verify") in ("live_meter", "none") or bench.instrument_key(e["name"]) is None:   # live-checked / fixture, consumable, access note: nothing to calibrate
                continue
            c = self.store.calibration(e["name"])
            if c is None or not c["valid_until"] or c["valid_until"] < today:
                b.append(Blocker("CAL", trf("no valid calibration record for: {name}", name=self.cat.equipment_label(e))))
        return b

    def pending_run(self, test_id: str, unit_id: str) -> dict | None:
        """The run to open when the operator picks a test directly: the IN_PROGRESS run of that test on
        that unit if there is one (resume), else its first NOT_STARTED run (catalog order), else None."""
        runs = [r for r in self.store.runs(test_id, unit_id) if r["status"] in ("NOT_STARTED", "IN_PROGRESS")]
        return next((r for r in runs if r["status"] == "IN_PROGRESS"), runs[0] if runs else None)

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
            return NextAction(unit_id, self.cat.phase_of(r["test_id"]), r, [], trf("Resume {test} at step {step}", test=r["test_id"], step=r["current_step"] + 1))
        phase = self.current_phase(unit_id)
        if phase is None:
            return NextAction(unit_id, None, None, [], trf("{unit}: all phases complete", unit=unit_id))
        if phase["id"] == 0:
            return NextAction(unit_id, phase, None, [Blocker("CONFIG", tr("freeze the unit configuration"))],
                              tr("Phase 0 — record and freeze the configuration"))
        # Bench order (SRS-DVT-196): tests sharing an instrument run one after the other. Inside the phase the
        # candidates are the not-started runs; keep the setup already on the bench for this unit — most shared
        # instruments with the unit's last finished test — then the phase's bench order. A candidate whose
        # in-phase dependency is not done never wins over one that is runnable.
        from . import bench
        order = bench.bench_order(self.cat, phase); rank = {t: i for i, t in enumerate(order)}
        last = self.store.get_meta(f"last_test:{unit_id}")
        if not last:
            done = [r for r in self.store.runs(unit_id=unit_id) if r["status"] == "DONE" and r.get("finished_at")]
            last = max(done, key=lambda r: r["finished_at"])["test_id"] if done else None
        last_instr = bench.instruments_of(self.cat.tests[last]) if last and last in self.cat.tests else frozenset()
        candidates = []
        for tid in order:
            if unit_id not in self.cat.applicable_units(tid):
                continue
            r = next((r for r in self.store.runs(tid, unit_id) if r["status"] == "NOT_STARTED"), None)
            if r is not None:
                bl = self.blockers_for(r); ins = bench.instruments_of(self.cat.tests[tid])
                # runnable first; then most instruments kept; among tests that keep something, the fewest new ones;
                # when nothing on the bench is reused anyway, the phase's bench order decides (not "the test with no instruments")
                kept = len(ins & last_instr)
                candidates.append(((any(b.code == "DEP" for b in bl), -kept, len(ins - last_instr) if kept else 0, rank[tid]), tid, r, bl))
        if candidates:
            _, tid, r, bl = min(candidates, key=lambda c: c[0])
            kept, added, removed = bench.setup_change(self.cat, last, tid)
            if last and not added and not removed and kept:
                setup = trf("Same bench setup as {prev} — keeps {kept}", prev=last, kept=", ".join(sorted(kept)))
            elif last and (added or removed):
                setup = trf("Setup change after {prev}: add {added}; remove {removed}", prev=last, added=", ".join(sorted(added)) or "—", removed=", ".join(sorted(removed)) or "—")
            else:
                ins = bench.instruments_of(self.cat.tests[tid])
                setup = trf("Bench setup: {instruments}", instruments=", ".join(sorted(ins))) if ins else ""
            return NextAction(unit_id, phase, r, bl,
                              trf("Next: {test} — {title} ({variant}, rep {rep})", test=tid, title=self.cat.tests[tid]["title"], variant=self._variant_text(r), rep=r["repetition"]), setup)
        return NextAction(unit_id, phase, None, [Blocker("GATE", phase.get("gate") or tr("phase gate"))],
                          trf("Phase {phase} runs are done but the gate is not met: {gate}", phase=phase["id"], gate=phase.get("gate")))

    @staticmethod
    def _variant_text(run: dict) -> str:
        return ", ".join(f"{k}={v}" for k, v in run["variant"].items()) or tr("single")

    # ---------------- verdict ----------------
    def evaluate(self, run_id: str) -> tuple[str, str]:
        run = self.store.run(run_id)
        t = self.cat.tests[run["test_id"]]
        values = {**run["variant"], **self.store.values(run_id)}
        return criteria.evaluate(t["pass_criteria"], values, self.cat.thresholds)

    def finish(self, run_id: str, by: str, witness: str | None = None) -> tuple[str, str]:
        verdict, detail = self.evaluate(run_id)
        self.store.finish_run(run_id, verdict, detail, by, witness)
        run = self.store.run(run_id)
        if run:
            self.store.set_meta(f"last_test:{run['unit_id']}", run["test_id"])     # bench order: what is on the bench for this unit (SRS-DVT-196)
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
        appl = (self.cat.label("rules", "ALL") if app["rule"] == "ALL" else
                trf("{n} units", n=len(app.get("units") or [])) if app["rule"] == "SUBSET" else (app.get("unit") or tr("TBD")))
        return {"testId": test_id, "title": t["title"], "subsystem": t["subsystem"], "subsystemLabel": self.cat.label("subsystems", t["subsystem"]),
                "method": t["method"], "methodLabel": self.cat.label("methods", t["method"]),
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

    def subsystem_progress(self, unit_id: str | None = None) -> dict:
        """{subsystem: {runsDone, runsTotal, percent}} + a "__total__" row over every test — for all units or one unit.
        Committed (DONE) runs over applicable runs; rejected and supplementary runs excluded."""
        runs = [r for r in self.store.runs() if r["status"] != "REJECTED" and not r.get("supplementary")]
        if unit_id:
            runs = [r for r in runs if r["unit_id"] == unit_id]
        sub_of = {tid: self.cat.tests[tid]["subsystem"] for tid in self.cat.tests}
        out: dict[str, dict] = {}
        for tid in self.cat.ordered_test_ids():
            out.setdefault(sub_of[tid], {"runsDone": 0, "runsTotal": 0})
        for r in runs:
            s = out.setdefault(sub_of.get(r["test_id"], "?"), {"runsDone": 0, "runsTotal": 0})
            s["runsTotal"] += 1
            if r["status"] == "DONE": s["runsDone"] += 1
        total = {"runsDone": sum(s["runsDone"] for s in out.values()), "runsTotal": sum(s["runsTotal"] for s in out.values())}
        for s in [*out.values(), total]:
            s["percent"] = round(100 * s["runsDone"] / s["runsTotal"]) if s["runsTotal"] else 0
        out["__total__"] = total
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
