"""DVT-OPT-001 / DVT-OPT-002 — UV irradiance against the commanded LED power.

The Ophir StarBright is plugged into the MACHINE's USB, not the console: the
machine runs the sweep (server/uv_sweep.py — LEDs off for a dark reading,
then 30 → 100 % in 10 % steps, 10 s each, meter at 5 Hz, LEDs off) and the
console drives it through the DUT client (`uv_sweep_start` / `uv_sweep_status`
/ `uv_sweep_abort`), watches it live, analyses the settled step values and
draws the graph of measured irradiance against the command.

    UvSweepRunner(dut, cfg).run() -> UvSweepResult     (blocking; worker thread)
    analyze(res)                                      linear fit, R², max deviation, monotonic, gains
    values(res)                                       the catalog fields
    write_csv / plot_png                              the artefacts attached to the run
"""

from __future__ import annotations

import csv
import math
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

DEFAULT_STEPS = (30, 40, 50, 60, 70, 80, 90, 100)
TESTS = {405: "DVT-OPT-001", 450: "DVT-OPT-002"}


@dataclass
class UvSweepConfig:
    wavelength: int = 405
    steps: tuple = DEFAULT_STEPS
    dwell_s: float = 10.0
    baseline_s: float = 5.0
    settle_s: float = 5.0
    hz: float = 5.0
    poll_s: float = 1.0
    force: bool = False              # run even if the meter is set to another wavelength (recorded as unverified)
    timeout_s: float | None = None   # None = baseline + steps x dwell + 30 s

    def __post_init__(self):
        if self.wavelength not in TESTS:
            raise ValueError(f"wavelength must be 405 or 450 (got {self.wavelength})")
        self.steps = tuple(int(s) for s in self.steps)
        if not self.steps or any(not 10 <= s <= 100 for s in self.steps):
            raise ValueError("steps must be percentages between 10 and 100")
        if self.timeout_s is None:
            self.timeout_s = self.baseline_s + len(self.steps) * self.dwell_s + 30.0

    @property
    def test_id(self) -> str:
        return TESTS[self.wavelength]

    def query(self) -> dict:
        return {"wavelength": self.wavelength, "steps": ",".join(map(str, self.steps)), "dwell": self.dwell_s, "baseline": self.baseline_s,
                "settle": self.settle_s, "hz": self.hz, "force": 1 if self.force else 0}


@dataclass
class StepResult:
    intensity: int
    mean: float | None
    sd: float | None = None
    n: int = 0
    led_max_c: float | None = None
    fit: float | None = None          # the straight-line value at this intensity
    dev_pct: float | None = None      # (mean - fit) / fit_at_100 x 100

    @property
    def gain(self) -> float | None:   # mW/cm2 per commanded %
        return None if self.mean is None else self.mean / self.intensity


@dataclass
class UvSweepResult:
    status: str = "NOT_RUN"          # OK | INCOMPLETE | ABORTED | ERROR | REFUSED
    wavelength: int = 405
    test_id: str = "DVT-OPT-001"
    meter: dict = field(default_factory=dict)
    meter_detected: bool = False
    meter_wavelength_nm: int | None = None
    meter_wavelength_verified: bool = False
    dark: float | None = None
    steps: list[StepResult] = field(default_factory=list)
    samples: list = field(default_factory=list)      # [t_s, mW/cm2 | None, intensity, phase, led_max_c, uv_on]
    slope: float | None = None
    intercept: float | None = None
    r2: float | None = None
    max_dev_pct: float | None = None
    monotonic: bool | None = None
    gain_first: float | None = None
    gain_last: float | None = None
    led_max_c: float | None = None
    notes: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    @property
    def all_steps_measured(self) -> bool:
        want = list(self.config.get("steps") or [])
        return bool(want) and [s.intensity for s in self.steps] == want and all(s.mean is not None for s in self.steps)

    def summary(self) -> dict:
        d = asdict(self); d.pop("samples"); d["n_samples"] = len(self.samples); return d

    def final_text(self) -> str:
        if not self.steps:
            return self.status + (": " + "; ".join(self.notes) if self.notes else "")
        first, last = self.steps[0], self.steps[-1]
        parts = [f"{self.wavelength} nm: {first.intensity} % → {first.mean:.2f} mW/cm² … {last.intensity} % → {last.mean:.2f} mW/cm²" if first.mean is not None and last.mean is not None else self.status]
        if self.slope is not None:
            parts.append(f"fit {self.slope:.3f} mW/cm² per % (intercept {self.intercept:+.2f}), R² {self.r2:.4f}, max deviation {self.max_dev_pct:.1f} % of full scale")
        if self.gain_first is not None and self.gain_last is not None:
            parts.append(f"gain {self.gain_first:.3f} → {self.gain_last:.3f} mW/cm² per % ({'bends over' if self.gain_last < 0.95 * self.gain_first else 'flat'})")
        parts.append("monotonic" if self.monotonic else "NOT monotonic")
        return "; ".join(parts)


# ---------------------------------------------------------------- analysis (pure)
def linear_fit(points):
    pts = [(float(x), float(y)) for x, y in points if y is not None and not (isinstance(y, float) and math.isnan(y))]
    if len(pts) < 2:
        return None, None, None
    n = len(pts); sx = sum(x for x, _ in pts); sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts); sxy = sum(x * y for x, y in pts); syy = sum(y * y for _, y in pts)
    d = n * sxx - sx * sx
    if d == 0:
        return None, None, None
    m = (n * sxy - sx * sy) / d; b = (sy - m * sx) / n
    ss_tot = syy - sy * sy / n; ss_res = sum((y - (m * x + b)) ** 2 for x, y in pts)
    return m, b, (1 - ss_res / ss_tot) if ss_tot else 1.0


def analyze(res: UvSweepResult) -> UvSweepResult:
    """Fit, deviation from the line (as % of the fitted full-scale value), monotonic check, gain at the ends."""
    measured = [s for s in res.steps if s.mean is not None]
    if len(measured) >= 2:
        m, b, r2 = linear_fit([(s.intensity, s.mean) for s in measured])
        res.slope, res.intercept, res.r2 = m, b, r2
        if m is not None:
            full = m * 100 + b
            for s in measured:
                s.fit = m * s.intensity + b
                s.dev_pct = (s.mean - s.fit) / full * 100 if full else None
            devs = [abs(s.dev_pct) for s in measured if s.dev_pct is not None]
            res.max_dev_pct = max(devs) if devs else None
        res.monotonic = all(b_.mean > a_.mean for a_, b_ in zip(measured, measured[1:]))
        res.gain_first, res.gain_last = measured[0].gain, measured[-1].gain
    elif measured:
        res.monotonic = None
    leds = [s.led_max_c for s in res.steps if s.led_max_c is not None]
    if leds:
        res.led_max_c = max(leds)
    return res


def values(res: UvSweepResult) -> dict:
    """The catalog fields this measurement fills."""
    out = {"meter_detected": res.meter_detected, "meter_wavelength_verified": res.meter_wavelength_verified, "all_steps_measured": res.all_steps_measured}
    if res.meter_wavelength_nm is not None: out["meter_wavelength_nm"] = res.meter_wavelength_nm
    head = res.meter.get("head") if isinstance(res.meter, dict) else None
    if head: out["meter_head"] = str(head)
    if res.dark is not None: out["dark_mw_cm2"] = round(res.dark, 4)
    for s in res.steps:
        if s.mean is not None: out[f"irradiance_{s.intensity}"] = round(s.mean, 3)
    for k in ("slope_mw_per_pct", "intercept_mw_cm2", "r2", "max_dev_pct", "gain_30", "gain_100", "led_max_c"):
        v = {"slope_mw_per_pct": res.slope, "intercept_mw_cm2": res.intercept, "r2": res.r2, "max_dev_pct": res.max_dev_pct,
             "gain_30": res.gain_first, "gain_100": res.gain_last, "led_max_c": res.led_max_c}[k]
        if v is not None: out[k] = round(v, 4)
    if res.monotonic is not None: out["monotonic"] = bool(res.monotonic)
    return out


def from_status(st: dict, cfg: UvSweepConfig) -> UvSweepResult:
    """Build the result from the machine's /api/dvt/uv-sweep status document."""
    res = UvSweepResult(wavelength=cfg.wavelength, test_id=cfg.test_id, config=asdict(cfg))
    res.status = st.get("status") or ("RUNNING" if st.get("running") else "NOT_RUN")
    res.meter = st.get("meter") or {}; res.meter_detected = bool(res.meter)
    res.meter_wavelength_nm = st.get("meter_wavelength_nm"); res.meter_wavelength_verified = bool(st.get("meter_wavelength_verified"))
    res.dark = st.get("dark_mw_cm2"); res.samples = list(st.get("samples") or [])
    res.steps = [StepResult(int(s["intensity"]), s.get("mean_mw_cm2"), s.get("sd_mw_cm2"), int(s.get("n") or 0), s.get("led_max_c")) for s in st.get("steps") or []]
    if st.get("error"): res.notes.append(str(st["error"]))
    if not res.meter_wavelength_verified and res.meter_wavelength_nm is not None:
        res.notes.append(f"meter was set to {res.meter_wavelength_nm} nm, test is at {cfg.wavelength} nm — result recorded as UNVERIFIED")
    return analyze(res)


# ---------------------------------------------------------------- runner (drives the machine, watches it)
class UvSweepRunner:
    def __init__(self, dut, cfg: UvSweepConfig | None = None, on_status: Callable[[str, str], None] | None = None,
                 on_sample: Callable[[list], None] | None = None):
        self.dut, self.cfg = dut, cfg or UvSweepConfig()
        self.on_status = on_status or (lambda phase, text: None); self.on_sample = on_sample or (lambda s: None)
        self.result = UvSweepResult(wavelength=self.cfg.wavelength, test_id=self.cfg.test_id, config=asdict(self.cfg))
        self._abort = False

    def abort(self):
        self._abort = True
        try: self.dut.uv_sweep_abort()
        except Exception: pass  # noqa: BLE001

    def run(self) -> UvSweepResult:
        cfg, res = self.cfg, self.result
        self.on_status("meter", "checking the StarBright on the machine")
        try:
            m = self.dut.meter()
        except Exception as e:  # noqa: BLE001
            res.status = "ERROR"; res.notes.append(f"meter check failed: {e}"); return res
        if not m.get("present"):
            res.status = "REFUSED"; res.notes.append(m.get("message") or "no StarBright on the machine's USB"); return res
        res.meter = m; res.meter_detected = True; res.meter_wavelength_nm = m.get("wavelength_nm")
        self.on_status("start", f"starting the sweep at {cfg.wavelength} nm")
        try:
            r = self.dut.uv_sweep_start(cfg.query())
        except Exception as e:  # noqa: BLE001
            res.status = "ERROR"; res.notes.append(f"start failed: {e}"); return res
        if not r.get("ok"):
            res.status = "REFUSED"; res.notes.append(r.get("message") or "refused")
            if r.get("meter_wavelength_nm") is not None: res.meter_wavelength_nm = r["meter_wavelength_nm"]
            return res
        res.meter_wavelength_verified = bool(r.get("meter_wavelength_verified"))
        seen = 0; t_end = time.monotonic() + cfg.timeout_s; st = {}
        while time.monotonic() < t_end:
            time.sleep(cfg.poll_s)
            try:
                st = self.dut.uv_sweep_status()
            except Exception as e:  # noqa: BLE001
                res.notes.append(f"status poll failed: {e}"); continue
            samples = st.get("samples") or []
            for s in samples[seen:]:
                self.on_sample(s)
            seen = len(samples)
            self.on_status(st.get("phase") or "…", f"{st.get('phase')} · {st.get('intensity')} % · {('%.2f' % st['reading']) if st.get('reading') is not None else '—'} mW/cm²")
            if not st.get("running"):
                break
        else:
            res.notes.append("timed out waiting for the machine — LEDs switched off"); self.abort(); st = self.dut.uv_sweep_status()
        out = from_status(st, cfg)
        out.notes = res.notes + out.notes
        self.result = out
        self.on_status("done", out.final_text())
        return out


# ---------------------------------------------------------------- artefacts
def write_csv(res: UvSweepResult, path: str | Path) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([f"# {res.test_id} UV irradiance vs commanded LED power", f"wavelength={res.wavelength}", f"status={res.status}", f"meter_wavelength_nm={res.meter_wavelength_nm}",
                    f"verified={res.meter_wavelength_verified}", f"dark_mw_cm2={res.dark}", f"slope={res.slope}", f"intercept={res.intercept}", f"r2={res.r2}", f"max_dev_pct={res.max_dev_pct}", f"monotonic={res.monotonic}"])
        w.writerow(["# step", "intensity_pct", "mean_mw_cm2", "sd_mw_cm2", "n", "fit_mw_cm2", "dev_pct", "gain_mw_cm2_per_pct", "led_max_c"])
        for s in res.steps:
            w.writerow(["step", s.intensity, s.mean, s.sd, s.n, None if s.fit is None else round(s.fit, 4), None if s.dev_pct is None else round(s.dev_pct, 3), None if s.gain is None else round(s.gain, 4), s.led_max_c])
        w.writerow(["# sample", "t_s", "mw_cm2", "intensity_pct", "phase", "led_max_c", "uv_on"])
        for smp in res.samples:
            w.writerow(["sample", *smp])
    return p


def plot_png(res: UvSweepResult, path: str | Path, title: str | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    title = title or f"{res.test_id} · UV irradiance vs commanded LED power · {res.wavelength} nm"
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 5), dpi=120, gridspec_kw={"width_ratios": [3, 2]})
    xs = [s.intensity for s in res.steps if s.mean is not None]; ys = [s.mean for s in res.steps if s.mean is not None]
    sds = [s.sd or 0.0 for s in res.steps if s.mean is not None]
    color = "#7c5cbf" if res.wavelength == 405 else "#2f6fdb"
    ax.errorbar(xs, ys, yerr=sds, fmt="o-", color=color, lw=1.8, ms=6, capsize=3, label=f"measured ({res.wavelength} nm)")
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.2f}", (x, y), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, color=color)
    if res.slope is not None:
        fx = [0, 100]; ax.plot(fx, [res.slope * x + res.intercept for x in fx], "--", color="#6b7a8c", lw=1.2,
                               label=f"linear fit: {res.slope:.3f} mW/cm² per % {res.intercept:+.2f}   R² {res.r2:.4f}")
    if res.dark is not None:
        ax.axhline(res.dark, color="#d68a0c", ls=":", lw=1, label=f"dark {res.dark:.3f}")
    ax.set_xlim(0, 105); ax.set_ylim(bottom=0); ax.set_xlabel("commanded LED power [%]"); ax.set_ylabel("irradiance at the chamber centre [mW/cm²]")
    ax.set_title(f"{title} — {res.status}", fontsize=10); ax.grid(True, alpha=0.3); ax.legend(loc="upper left", fontsize=8)
    verdict = []
    if res.max_dev_pct is not None: verdict.append(f"max deviation {res.max_dev_pct:.1f} % of full scale")
    if res.gain_first is not None and res.gain_last is not None: verdict.append(f"gain {res.gain_first:.3f} → {res.gain_last:.3f} mW/cm²/%")
    if res.monotonic is not None: verdict.append("monotonic" if res.monotonic else "NOT monotonic")
    if not res.meter_wavelength_verified: verdict.append("METER WAVELENGTH UNVERIFIED")
    if verdict: ax.text(0.98, 0.04, "\n".join(verdict), transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color="#1b2430",
                        bbox=dict(boxstyle="round", fc="#ffffff", ec="#d9dee6"))
    # right: the raw trace (irradiance and the commanded staircase against time)
    ts = [s[0] for s in res.samples]; vs = [s[1] if s[1] is not None else float("nan") for s in res.samples]; cmd = [s[2] for s in res.samples]
    if ts:
        ax2.plot(ts, vs, color=color, lw=1.2, label="meter [mW/cm²]")
        ax3 = ax2.twinx(); ax3.step(ts, cmd, where="post", color="#e8461f", lw=1, alpha=0.7, label="command [%]"); ax3.set_ylim(0, 110); ax3.set_ylabel("command [%]", color="#e8461f")
        leds = [s[4] if len(s) > 4 and s[4] is not None else float("nan") for s in res.samples]
        if any(not math.isnan(v) for v in leds):
            ax4 = ax2.twinx(); ax4.spines["right"].set_position(("axes", 1.18)); ax4.plot(ts, leds, color="#d68a0c", lw=1, alpha=0.8); ax4.set_ylabel("hottest LED [°C]", color="#d68a0c")
        ax2.set_xlabel("time [s]"); ax2.set_ylabel("irradiance [mW/cm²]"); ax2.grid(True, alpha=0.3); ax2.set_title("raw trace", fontsize=10)
    fig.tight_layout(); fig.savefig(p); plt.close(fig)
    return p
