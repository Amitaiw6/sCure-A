"""Temperature statistics per component, per machine (SRS-DVT-095 / SRS-DVT-195).

Every temperature field (unit C) recorded in any test is grouped by the
physical component it measures — LED panel right / left / back / door, LED
(unspecified side), heater body, chamber, ambient — and summarised per unit
under test: n, mean, std, min, max. Across the machines: the spread of the
unit means, the between-unit std, and the outliers — a unit whose mean sits
further from the MEDIAN of the unit means than the largest of 3x the scaled
MAD, 2x the pooled within-unit std and ABS_MIN C (so an even spread across
machines or measurement noise never flags anyone; needs >= 3 machines).

Pure logic over Catalog + Store; `render_png` (matplotlib) is optional and
degrades to "no charts" when matplotlib is missing.
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

ABS_MIN = 2.0                         # C — a unit is never an outlier for less than this
COMPONENTS = [("led_right", "LED panel — right"), ("led_left", "LED panel — left"), ("led_back", "LED panel — back"),
              ("led_door", "LED panel — door"), ("led", "LED panel"), ("heater", "Heater body"),
              ("chamber", "Chamber"), ("ambient", "Ambient"), ("other", "Other")]
COMPONENT_LABEL = dict(COMPONENTS)


def component_of(field_name: str, test: dict | None = None, field_def: dict | None = None) -> str:
    """Which physical component a temperature field measures. A catalog field may
    say so explicitly (`component:`); otherwise the field name, then the test."""
    if field_def and field_def.get("component"):
        return field_def["component"]
    f = field_name.lower()
    if "ambient" in f:
        return "ambient"
    if any(k in f for k in ("heater", "cutout", "element")):
        return "heater"
    for side in ("right", "left", "back", "door"):
        if side in f:
            return f"led_{side}"
    if any(k in f for k in ("led", "tj", "thermistor", "panel", "mcpcb")):
        return "led"
    if any(k in f for k in ("chamber", "plateau", "overshoot", "uniformity", "undershoot", "steady", "settle", "start_temp", "peak_temp", "min_temp", "max_temp", "reference", "displayed", "temp_at", "trip")):
        # chamber-ish names — unless the test itself is about the LEDs
        if test and "led" in str(test.get("title", "")).lower() and "chamber" not in f:
            return "led"
        return "chamber"
    if test and "led" in str(test.get("title", "")).lower():
        return "led"
    return "chamber" if "temp" in f else "other"


@dataclass
class UnitStat:
    n: int
    mean: float
    std: float          # sample std (0 when n == 1)
    min: float
    max: float
    values: list = field(default_factory=list)


@dataclass
class FieldStat:
    test_id: str
    field: str
    component: str
    per_unit: dict = field(default_factory=dict)      # unit_id -> UnitStat
    grand_mean: float = 0.0
    between_std: float = 0.0                          # std of the unit means
    spread: float = 0.0                               # max unit mean - min unit mean
    pooled_std: float = 0.0                           # within-unit std pooled over units with n >= 2
    outliers: list = field(default_factory=list)      # unit ids

    @property
    def n_units(self) -> int:
        return len(self.per_unit)


def _unit_stat(vals: list[float]) -> UnitStat:
    return UnitStat(len(vals), statistics.fmean(vals), statistics.stdev(vals) if len(vals) > 1 else 0.0, min(vals), max(vals), list(vals))


def summarise(test_id: str, field_name: str, component: str, values_by_unit: dict[str, list[float]]) -> FieldStat:
    """Pure: per-unit stats + the cross-machine figures + outliers for one field."""
    fs = FieldStat(test_id, field_name, component)
    for u in sorted(values_by_unit):
        vals = [float(v) for v in values_by_unit[u]]
        if vals:
            fs.per_unit[u] = _unit_stat(vals)
    if not fs.per_unit:
        return fs
    means = {u: s.mean for u, s in fs.per_unit.items()}
    fs.grand_mean = statistics.fmean(means.values())
    fs.between_std = statistics.stdev(means.values()) if len(means) > 1 else 0.0
    fs.spread = max(means.values()) - min(means.values())
    variances = [s.std ** 2 for s in fs.per_unit.values() if s.n >= 2]
    fs.pooled_std = math.sqrt(statistics.fmean(variances)) if variances else 0.0
    if len(means) >= 3:
        # robust rule: distance from the MEDIAN of the machine means (one hot machine cannot drag the
        # reference with it), against the largest of 3x the scaled MAD, 2x the pooled within-unit std
        # and ABS_MIN — so an even spread across machines or measurement noise never flags anyone
        med = statistics.median(means.values())
        mad = statistics.median(abs(m - med) for m in means.values()) * 1.4826
        threshold = max(3.0 * mad, 2.0 * fs.pooled_std, ABS_MIN)
        fs.outliers = [u for u, m in means.items() if abs(m - med) > threshold]
    return fs


def collect(cat, store, statuses=("DONE", "IN_PROGRESS")) -> list[FieldStat]:
    """Every temperature field of every test with at least one recorded value."""
    out: list[FieldStat] = []
    for tid in cat.ordered_test_ids():
        t = cat.tests[tid]
        temp_fields = [f for f in t.get("data_fields") or [] if str(f.get("unit", "")) == "C" and f.get("type") in ("float", "int")]
        if not temp_fields:
            continue
        runs = [r for r in store.runs(tid) if r["status"] in statuses]
        by_field: dict[str, dict[str, list[float]]] = {f["name"]: {} for f in temp_fields}
        for r in runs:
            vals = {**r["variant"], **store.values(r["run_id"])}
            for f in temp_fields:
                x = vals.get(f["name"])
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    by_field[f["name"]].setdefault(r["unit_id"], []).append(float(x))
        for f in temp_fields:
            if any(by_field[f["name"]].values()):
                out.append(summarise(tid, f["name"], component_of(f["name"], t, f), by_field[f["name"]]))
    return out


def component_summary(stats: list[FieldStat]) -> dict:
    """{component: {fields, worst_between_std, outliers: {unit: count}, spread_max}} — the 'which component, which machine' view."""
    out: dict[str, dict] = {}
    for fs in stats:
        c = out.setdefault(fs.component, {"label": COMPONENT_LABEL.get(fs.component, fs.component), "fields": 0,
                                          "worst_between_std": 0.0, "spread_max": 0.0, "outliers": {}})
        c["fields"] += 1
        c["worst_between_std"] = max(c["worst_between_std"], fs.between_std)
        c["spread_max"] = max(c["spread_max"], fs.spread)
        for u in fs.outliers:
            c["outliers"][u] = c["outliers"].get(u, 0) + 1
    return out


def rows(stats: list[FieldStat], units: list[str]) -> tuple[list[str], list[list]]:
    """Flat table (CSV / XLSX / Markdown): one row per field, mean / std / n per unit, then the cross-machine figures."""
    header = ["component", "test", "field"]
    for u in units:
        header += [f"{u} mean", f"{u} std", f"{u} n"]
    header += ["grand mean", "between-unit std", "spread", "pooled within std", "outliers"]
    body = []
    for fs in stats:
        row = [COMPONENT_LABEL.get(fs.component, fs.component), fs.test_id, fs.field]
        for u in units:
            s = fs.per_unit.get(u)
            row += [round(s.mean, 2), round(s.std, 2), s.n] if s else ["", "", 0]
        row += [round(fs.grand_mean, 2), round(fs.between_std, 2), round(fs.spread, 2), round(fs.pooled_std, 2), ", ".join(fs.outliers)]
        body.append(row)
    return header, body


def write_csv(stats: list[FieldStat], units: list[str], path: Path) -> Path:
    header, body = rows(stats, units)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(body)
    return path


def render_png(stats: list[FieldStat], units: list[str], out_dir: Path, campaign: str = "sCure-DVT") -> list[Path]:
    """One PNG per component: a panel per field, x = machines, mean ± std, outliers in red.
    Returns [] when matplotlib is not installed or there is nothing to draw."""
    if not stats:
        return []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001 - charts are optional
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for comp, _label in COMPONENTS:
        group = [fs for fs in stats if fs.component == comp]
        if not group:
            continue
        cols = min(3, len(group)); rws = math.ceil(len(group) / cols)
        fig, axes = plt.subplots(rws, cols, figsize=(5.2 * cols, 3.6 * rws), squeeze=False)
        for ax, fs in zip(axes.flat, group):
            xs = list(range(len(units)))
            means = [fs.per_unit[u].mean if u in fs.per_unit else float("nan") for u in units]
            stds = [fs.per_unit[u].std if u in fs.per_unit else 0.0 for u in units]
            colors = ["#d62839" if u in fs.outliers else "#2f6fdb" for u in units]
            ax.errorbar(xs, means, yerr=stds, fmt="none", ecolor="#8a94a6", capsize=4, lw=1.2)
            ax.scatter(xs, means, c=colors, s=46, zorder=3)
            ax.axhline(fs.grand_mean, color="#8a94a6", ls="--", lw=1)
            ax.set_xticks(xs); ax.set_xticklabels(units, fontsize=8)
            ax.set_title(f"{fs.test_id} · {fs.field}", fontsize=9)
            ax.set_ylabel("°C", fontsize=8)
            ax.text(0.01, 0.97, f"between-unit std {fs.between_std:.2f} °C · spread {fs.spread:.1f} °C" + (f" · outlier {', '.join(fs.outliers)}" if fs.outliers else ""),
                    transform=ax.transAxes, fontsize=7.5, va="top", color="#d62839" if fs.outliers else "#445")
            ax.grid(axis="y", color="#e5e8ef", lw=0.8)
        for ax in list(axes.flat)[len(group):]:
            ax.axis("off")
        fig.suptitle(f"{campaign} — {COMPONENT_LABEL[comp]}: temperature per machine (mean ± std)", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        p = out_dir / f"temp_{comp}.png"
        fig.savefig(p, dpi=130); plt.close(fig); paths.append(p)
    return paths
