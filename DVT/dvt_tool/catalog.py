"""Catalog loading, validation and run-set expansion (SRS-DVT-094/097).

A *run* is one executable unit of work: (test, unit, variant, repetition)
where `variant` is a sweep-matrix row or a case-matrix case (or None).
Run ids are stable strings so results survive catalog edits that do not
change the run's identity:  DVT-THM-001|UUT-02|setpoint=80,mains_voltage=110|1
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

TEST_ID_RE = re.compile(r"^DVT-[A-Z]{3}-\d{3}$")
METHODS = {"Test", "Analysis", "Inspection", "Demonstration"}
FIELD_TYPES = {"float", "int", "bool", "string", "enum"}


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    test_id: str
    unit_id: str
    variant: dict            # {} when the test has no sweep / case matrix
    repetition: int          # 1-based
    supplementary: bool = False

    @property
    def variant_label(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.variant.items()) if self.variant else "—"


@dataclass
class Catalog:
    version: str
    tests: dict[str, dict]
    units: list[dict]
    phases: list[dict]
    thresholds: dict = field(default_factory=dict)
    path: Path | None = None

    # ---------------- loading ----------------
    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        cat = cls(version=str(data.get("catalog_version", "0")),
                  tests={t["test_id"]: t for t in data.get("tests", [])},
                  units=list(data.get("units", [])),
                  phases=list(data.get("phases", [])),
                  thresholds={"led_temperature_thresholds": data.get("led_temperature_thresholds", {})},
                  path=p)
        cat.validate()
        return cat

    def validate(self) -> None:
        problems = []
        ids = set(self.tests)
        for tid, t in self.tests.items():
            if not TEST_ID_RE.match(tid):
                problems.append(f"{tid}: bad test_id format")
            if t.get("method") not in METHODS:
                problems.append(f"{tid}: method must be one of {sorted(METHODS)}")
            if not t.get("pass_criteria"):
                problems.append(f"{tid}: pass_criteria missing")
            app = t.get("applicability") or {}
            if app.get("rule") not in ("ALL", "SINGLE"):
                problems.append(f"{tid}: applicability.rule must be ALL or SINGLE")
            if app.get("rule") == "SINGLE" and not t.get("sample_rationale"):
                problems.append(f"{tid}: SINGLE applicability requires sample_rationale")
            for d in t.get("dependencies") or []:
                if d not in ids:
                    problems.append(f"{tid}: unknown dependency {d}")
            names = set()
            for f in t.get("data_fields") or []:
                if f.get("type") not in FIELD_TYPES:
                    problems.append(f"{tid}: field {f.get('name')} has bad type {f.get('type')}")
                if f.get("type") == "enum" and not f.get("values"):
                    problems.append(f"{tid}: enum field {f.get('name')} has no values")
                names.add(f["name"])
            for s in t.get("procedure_steps") or []:
                for c in s.get("capture") or []:
                    if c not in names:
                        problems.append(f"{tid}: step captures unknown field {c}")
            if t.get("sweep") and t.get("case_matrix"):
                problems.append(f"{tid}: a test has either a sweep or a case_matrix, not both")
            co = t.get("co_executed_with")
            if co and co.get("test_id") not in ids:
                problems.append(f"{tid}: co_executed_with unknown test {co.get('test_id')}")
        phase_tests = [x for p in self.phases for x in p.get("tests", [])]
        for tid in ids:
            if tid not in phase_tests:
                problems.append(f"{tid}: not assigned to any phase")
        if problems:
            raise CatalogError("catalog invalid:\n  " + "\n  ".join(problems))

    # ---------------- queries ----------------
    def unit_ids(self) -> list[str]:
        return [u["id"] for u in self.units]

    def phase_of(self, test_id: str) -> dict:
        for p in self.phases:
            if test_id in p.get("tests", []):
                return p
        raise KeyError(test_id)

    def ordered_test_ids(self) -> list[str]:
        """Phase order, then the order inside the phase list."""
        return [t for p in sorted(self.phases, key=lambda p: p["id"]) for t in p.get("tests", [])]

    def variants(self, test_id: str) -> list[dict]:
        t = self.tests[test_id]
        if t.get("sweep"):
            return [dict(row) for row in t["sweep"]["matrix"]]
        if t.get("case_matrix"):
            return [{"case": c["case"]} for c in t["case_matrix"]]
        return [{}]

    def applicable_units(self, test_id: str) -> list[str]:
        app = self.tests[test_id]["applicability"]
        if app["rule"] == "ALL":
            return self.unit_ids()
        return [app["unit"]] if app.get("unit") else []      # None = CONFIRM pending

    def runs(self, test_id: str | None = None) -> list[RunSpec]:
        out = []
        for tid in ([test_id] if test_id else self.ordered_test_ids()):
            t = self.tests[tid]
            reps = int(t.get("repetitions") or 1)
            for unit in self.applicable_units(tid):
                for variant in self.variants(tid):
                    for r in range(1, reps + 1):
                        vl = ",".join(f"{k}={v}" for k, v in variant.items())
                        out.append(RunSpec(f"{tid}|{unit}|{vl}|{r}", tid, unit, variant, r))
        return out

    def run_count(self) -> int:
        return len(self.runs())

    def field_map(self, test_id: str) -> dict[str, dict]:
        return {f["name"]: f for f in self.tests[test_id].get("data_fields") or []}

    def parent_row_for(self, test_id: str, variant: dict) -> dict | None:
        """For a co-executed child: the parent test's matrix row this run rides on."""
        co = self.tests[test_id].get("co_executed_with")
        if not co:
            return None
        for row in co.get("rows", []):
            if all(variant.get(k) == v for k, v in row.items() if k != "parent_row"):
                return {"test_id": co["test_id"], **row["parent_row"]}
        return None
