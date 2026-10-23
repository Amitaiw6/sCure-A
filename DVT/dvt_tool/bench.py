"""Bench order — tests that use the same instrument run one after the other
(SRS-DVT-196).

Every catalog test lists its `equipment`. Each entry is reduced to a canonical
*instrument* (the thing that has to be set up, calibrated and wired on the
bench: PicoLog TC-08, Ophir StarBright, O2 analyser, AC source, …);
consumables and fixtures (spare fuses, a shorting link, a break-out lead) are
not instruments and do not drive the order.

Inside a phase the tests are ordered greedily: start from the first test the
catalog lists, then always continue with the runnable test (all its
dependencies inside the phase already placed) that shares the most
instruments with the setup currently on the bench; ties fall back to the
catalog order. Dependencies always win over grouping — the order never asks
for a test before the one it depends on. The engine follows this order for
the unit's next action, and the Test Plans page shows the groups.

Pure logic over the Catalog; no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

# Equipment entries that are NOT external devices: fixtures, consumables, accessories, access notes, the machine's own
# telemetry. They are needed on the bench but never calibrated and never listed as instruments. Checked first.
NON_INSTRUMENT_KEYS: tuple[str, ...] = (
    "spare ", "fixture", "access to", "means of", "break-out", "breakout", "indicator", "stopwatch", "machine log",
    "logged timestamps", "system timestamps", "leak-detection", "tape", "foil", "build heads", "resistor", "kelvin probes",
    "obstruction", "tachometer readback", "room volume", "uv-sensitive card",
)

# (keywords in the lower-cased equipment name) -> canonical instrument. First match wins.
INSTRUMENT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("tc-08", "picolog", "thermocouple logger"), "PicoLog TC-08"),
    (("ophir",), "Ophir StarBright"),
    (("o2 analy", "oxygen analy", "o2 monitor", "oxygen monitor", "oxygen probe", "o2 probe"), "O2 analyser"),
    (("nitrogen supply", "n2 regulator", "regulated nitrogen", "flow meter at the nitrogen", "flow meter on the supply"), "N2 supply + flow meter"),
    (("manometer",), "Pressure manometer"),
    (("power analyser", "power analyzer"), "Power analyser"),
    (("hipot",), "Hipot tester"),
    (("insulation resistance tester", "insulation tester"), "Insulation tester"),
    (("bonding/ground", "bonding / ground", "earth bond", "ground continuity"), "Earth bond tester"),
    (("touch current meter",), "Touch-current meter"),
    (("ac source", "variac", "isolation transformer"), "AC source"),
    (("thermal camera",), "Thermal camera"),
    (("true-rms", "clamp meter", "dmm", "multimeter"), "DMM / clamp meter"),
    (("current probe", "oscilloscope", "current clamp"), "Current probe / scope"),
    (("uv radiometer", "uv irradiance meter", "radiometer"), "UV radiometer"),
    (("shock", "vibration"), "Shock logger"),
    (("anemometer",), "Anemometer"),
    (("humidity logger", "ambient temperature logger", "ambient temperature and humidity"), "Ambient logger"),
    (("caliper",), "Vernier caliper"),
    (("logic probe", "scope on the valve"), "Logic probe"),
    (("dmm",), "DMM"),
    (("contactor",), "Remote mains contactor"),
    (("thermocouple",), "Thermocouples (bonded)"),
]


def instrument_key(equipment_name: str) -> str | None:
    """Canonical instrument for an equipment entry, or None for consumables / fixtures / access notes."""
    n = equipment_name.lower()
    if any(k in n for k in NON_INSTRUMENT_KEYS):
        return None
    for keys, label in INSTRUMENT_RULES:
        if any(k in n for k in keys):
            return label
    return None


def instruments(cat) -> tuple[dict[str, dict], list[dict]]:
    """The external devices the campaign needs, deduplicated across the catalog's wordings:
    {device: {"entries": [equipment names…], "tests": [test ids…]}} sorted by device, plus the list of
    fixtures / consumables / access items [{name, tests}] that are needed on the bench but are not devices."""
    devices: dict[str, dict] = {}; others: dict[str, list[str]] = {}
    for tid in cat.ordered_test_ids():
        for e in cat.tests[tid].get("equipment") or []:
            key = instrument_key(e["name"])
            if key is None or e.get("verify") == "none":
                others.setdefault(e["name"], [])
                if tid not in others[e["name"]]: others[e["name"]].append(tid)
                continue
            d = devices.setdefault(key, {"entries": [], "tests": []})
            if e["name"] not in d["entries"]: d["entries"].append(e["name"])
            if tid not in d["tests"]: d["tests"].append(tid)
    return dict(sorted(devices.items())), [{"name": n, "tests": ts} for n, ts in sorted(others.items())]


def instruments_of(test: dict) -> frozenset[str]:
    return frozenset(k for e in test.get("equipment") or [] if (k := instrument_key(e["name"])))


def bench_order(cat, phase: dict) -> list[str]:
    """The phase's tests ordered so shared instruments run consecutively; dependencies inside the phase always first."""
    tests = list(phase.get("tests") or [])
    if len(tests) < 2:
        return tests
    in_phase = set(tests)
    deps = {t: [d for d in (cat.tests[t].get("dependencies") or []) if d in in_phase] for t in tests}
    instr = {t: instruments_of(cat.tests[t]) for t in tests}
    rank = {t: i for i, t in enumerate(tests)}
    placed: list[str] = []
    bench: frozenset[str] = frozenset()
    remaining = list(tests)
    while remaining:
        runnable = [t for t in remaining if all(d in placed for d in deps[t])]
        if not runnable:                       # dependency cycle inside the phase: fall back to catalog order
            runnable = [remaining[0]]
        if not placed:
            pick = runnable[0]
        else:
            # keep the current setup: most shared instruments first; among equals, the one that needs the
            # fewest new instruments; then the catalog order
            pick = min(runnable, key=lambda t: (-len(instr[t] & bench), len(instr[t] - bench), rank[t]))
        placed.append(pick); remaining.remove(pick)
        if instr[pick]:
            bench = instr[pick]
    return placed


@dataclass
class BenchGroup:
    instruments: frozenset
    tests: list


def bench_groups(cat, phase: dict) -> list[BenchGroup]:
    """Consecutive tests of the bench order that share the same instrument set — the 'set up once, run these' view."""
    groups: list[BenchGroup] = []
    for tid in bench_order(cat, phase):
        ins = instruments_of(cat.tests[tid])
        if groups and groups[-1].instruments == ins:
            groups[-1].tests.append(tid)
        else:
            groups.append(BenchGroup(ins, [tid]))
    return groups


def setup_change(cat, prev_test: str | None, next_test: str) -> tuple[set[str], set[str], set[str]]:
    """(kept, added, removed) instruments when moving from prev_test to next_test on the bench."""
    nxt = instruments_of(cat.tests[next_test])
    prev = instruments_of(cat.tests[prev_test]) if prev_test else frozenset()
    return set(nxt & prev), set(nxt - prev), set(prev - nxt)
