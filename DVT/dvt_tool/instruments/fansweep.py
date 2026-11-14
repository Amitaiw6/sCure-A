"""DVT-THM-004, automatic: LED back-face temperature against LED-cooling fan
duty. The console drives the machine — no operator action during the run.

Sequence (`FanSweepRunner.run`, blocking — call it from a worker thread):

    for each duty in cfg.duties (100, 90, 80, 70 % by default):
        1. fans   POST /api/fans/led_cooling?speed=<duty>
        2. LEDs   on at cfg.intensity % (default 100) — first row only; later
                  rows continue on the same heat
        3. log    the machine's four LED thermistors (ledTemps) every
                  cfg.poll_s until every panel is settled — its rise over the
                  last cfg.settle_window_s is below cfg.settle_rate_c_per_min —
                  or any panel reaches cfg.limit_c (75, the working limit), or
                  cfg.row_timeout_s passes
        4. row    settled temperatures per panel, hottest panel, margin to the
                  limit, tach, alarm — one RowResult per duty
        stop the sweep at the first row that hits the limit or an alarm: the
        lower duties would only be hotter
    end: LEDs off, fans back to 100 %.

The final answer for the operator (`FanSweepResult.summary()`): the lowest
duty that settled below the limit with the required margin, per panel
temperatures per duty, and the temperature-vs-time graph (`plot_png`) with
one band per duty. `write_csv` keeps every sample.
"""

from __future__ import annotations

import csv
import statistics
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from .uvoff import raw_state, first_alert

PANELS = ("right", "left", "back", "door")


@dataclass
class FanSweepConfig:
    duties: tuple = (100, 90, 80, 70)
    fan_name: str = "led_cooling"
    intensity: int = 100
    wavelength: int = 405
    poll_s: float = 2.0
    settle_window_s: float = 300.0        # rise measured over this window
    settle_rate_c_per_min: float = 0.1    # settled when every panel rises slower than this
    min_row_s: float = 120.0              # never call a row settled before this
    row_timeout_s: float = 1800.0
    limit_c: float = 75.0                 # the LED working limit (catalog led_temperature_thresholds.working_limit)
    margin_c: float = 5.0                 # CONFIRM — margin below the limit for the recommended duty
    tach_key: str = "led_cooling"


@dataclass
class Sample:
    t: float
    duty: int
    temps: dict
    tach: float | None = None


@dataclass
class RowResult:
    duty: int
    settled: bool = False
    limit_reached: bool = False
    time_to_settle: float | None = None   # minutes
    temps: dict = field(default_factory=dict)          # settled (or peak) per panel
    max_settled_temp: float | None = None
    hottest_panel: str | None = None
    margin_to_working_limit: float | None = None
    tach_rpm: float | None = None
    chamber_temp: float | None = None
    ambient_temp: float | None = None
    alarm_raised: bool = False
    error_code: str | None = None
    status: str = "NOT_RUN"               # SETTLED | LIMIT | TIMEOUT | ALARM | ABORTED | ERROR

    def values(self) -> dict:
        """Catalog data fields for this duty row."""
        out = {"fan_duty": self.duty, "settled": self.settled, "limit_reached": self.limit_reached, "alarm_raised": self.alarm_raised}
        if self.time_to_settle is not None: out["time_to_settle"] = round(self.time_to_settle, 1)
        for p in PANELS:
            if self.temps.get(p) is not None: out[f"settled_temp_{p}"] = round(self.temps[p], 2)
        if self.max_settled_temp is not None: out["max_settled_temp"] = round(self.max_settled_temp, 2)
        if self.hottest_panel: out["hottest_panel"] = self.hottest_panel
        if self.margin_to_working_limit is not None: out["margin_to_working_limit"] = round(self.margin_to_working_limit, 2)
        if self.tach_rpm is not None: out["tach_rpm"] = round(self.tach_rpm)
        if self.chamber_temp is not None: out["chamber_temp"] = round(self.chamber_temp, 1)
        if self.ambient_temp is not None: out["ambient_temp"] = round(self.ambient_temp, 1)
        if self.error_code: out["error_code"] = self.error_code
        if self.max_settled_temp is not None: out["thermistor_hottest_panel"] = round(self.max_settled_temp, 2)
        return out


@dataclass
class FanSweepResult:
    status: str = "NOT_RUN"               # OK | STOPPED_AT_LIMIT | ABORTED | ERROR
    rows: list = field(default_factory=list)
    samples: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    t0: float | None = None

    def recommended_duty(self) -> int | None:
        """Lowest duty whose row settled at or below limit - margin."""
        lim = self.config.get("limit_c", 75.0) - self.config.get("margin_c", 5.0)
        ok = [r.duty for r in self.rows if r.settled and r.max_settled_temp is not None and r.max_settled_temp <= lim]
        return min(ok) if ok else None

    def summary(self) -> dict:
        return {"status": self.status, "recommended_duty": self.recommended_duty(), "notes": self.notes,
                "rows": [{k: v for k, v in asdict(r).items() if k != "temps"} | {"temps": {p: (round(v, 2) if v is not None else None) for p, v in r.temps.items()}} for r in self.rows],
                "n_samples": len(self.samples)}

    def final_text(self) -> str:
        """The one-paragraph answer for the operator."""
        lim = self.config.get("limit_c", 75.0); mg = self.config.get("margin_c", 5.0)
        parts = []
        for r in self.rows:
            if r.max_settled_temp is None:
                parts.append(f"{r.duty} %: {r.status.lower()}")
            else:
                parts.append(f"{r.duty} %: {r.max_settled_temp:.1f} C on the {r.hottest_panel} panel ({'settled' if r.settled else r.status.lower()}, margin {r.margin_to_working_limit:+.1f} C)")
        rec = self.recommended_duty()
        tail = (f"Lowest duty with at least {mg:.0f} C margin below the {lim:.0f} C working limit: {rec} %." if rec is not None
                else f"No duty settled with {mg:.0f} C margin below the {lim:.0f} C working limit — keep the fans at 100 % and review the cooling.")
        return " · ".join(parts) + ". " + tail


def _temps(s: dict) -> dict:
    led = s.get("ledTemps") or s.get("ledTemperatures") or {}
    out = {}
    for p in PANELS:
        v = led.get(p, led.get(f"LED_{p.upper()}")) if isinstance(led, dict) else None
        out[p] = float(v) if isinstance(v, (int, float)) else None
    return out


def settled(samples: list, window_s: float, rate_c_per_min: float, min_row_s: float, now: float, row_t0: float) -> bool:
    """Every panel's rise over the last `window_s` is below `rate_c_per_min`, and the row has run at least `min_row_s`."""
    if now - row_t0 < max(min_row_s, window_s):
        return False
    win = [s for s in samples if s.t >= now - window_s]
    if len(win) < 3:
        return False
    for p in PANELS:
        vals = [(s.t, s.temps.get(p)) for s in win if s.temps.get(p) is not None]
        if len(vals) < 3:
            continue
        (t0, v0), (t1, v1) = vals[0], vals[-1]
        if t1 > t0 and abs(v1 - v0) / ((t1 - t0) / 60.0) > rate_c_per_min:
            return False
    return True


class FanSweepRunner:
    def __init__(self, dut, cfg: FanSweepConfig | None = None, on_status: Callable[[str, str], None] | None = None,
                 on_sample: Callable[[Sample], None] | None = None):
        self.dut, self.cfg = dut, cfg or FanSweepConfig()
        self.on_status = on_status or (lambda ph, tx: None); self.on_sample = on_sample or (lambda s: None)
        self._abort = threading.Event()
        self.result = FanSweepResult(config=asdict(self.cfg))

    def abort(self):
        self._abort.set()

    def _safe(self):
        for fn in (lambda: self.dut.uv(False), lambda: self.dut.fan(self.cfg.fan_name, 100), lambda: self.dut.stop()):
            try: fn()
            except Exception: pass  # noqa: BLE001

    def _poll(self, duty: int) -> tuple[Sample, dict]:
        s = raw_state(self.dut)
        rpm = (s.get("fanRpm") or {}).get(self.cfg.tach_key)
        smp = Sample(time.monotonic(), duty, _temps(s), float(rpm) if isinstance(rpm, (int, float)) else None)
        self.result.samples.append(smp); self.on_sample(smp)
        return smp, s

    def run(self) -> FanSweepResult:
        cfg, res = self.cfg, self.result
        res.t0 = time.monotonic()
        try:
            s0 = raw_state(self.dut)
            if s0.get("doorOpen") or s0.get("doorClosed") is False:
                res.status = "ERROR"; res.notes.append("door open — close it and start again"); return res
            for i, duty in enumerate(cfg.duties):
                if self._abort.is_set():
                    res.status = "ABORTED"; break
                row = RowResult(duty=duty); res.rows.append(row); row_t0 = time.monotonic(); row_samples: list = []
                self.on_status("fans", f"LED-cooling fans → {duty} %")
                r = self.dut.fan(cfg.fan_name, duty)
                if isinstance(r, dict) and r.get("ok") is False:
                    row.status = "ERROR"; res.status = "ERROR"; res.notes.append(f"fan command refused at {duty} %: {r.get('message')}"); break
                if i == 0:
                    self.on_status("uv", f"LEDs on at {cfg.intensity} % / {cfg.wavelength} nm")
                    r = self.dut.uv(True, cfg.intensity, cfg.wavelength)
                    if isinstance(r, dict) and r.get("ok") is False:
                        row.status = "ERROR"; res.status = "ERROR"; res.notes.append(f"UV refused: {r.get('message')}"); break
                self.on_status("settle", f"{duty} % — waiting for the panels to settle")
                while not self._abort.is_set():
                    smp, st = self._poll(duty); row_samples.append(smp)
                    row.ambient_temp = st.get("ambientTemp") if isinstance(st.get("ambientTemp"), (int, float)) else row.ambient_temp
                    row.chamber_temp = st.get("chamberTemp") if isinstance(st.get("chamberTemp"), (int, float)) else row.chamber_temp
                    code, text = first_alert(st)
                    if code and not st.get("uvOn", True):
                        row.alarm_raised, row.error_code, row.status = True, code, "ALARM"; res.notes.append(f"{duty} %: alarm {code} — {text}"); break
                    hot = [(v, p) for p, v in smp.temps.items() if v is not None]
                    if hot and max(hot)[0] >= cfg.limit_c:
                        row.limit_reached, row.status = True, "LIMIT"; break
                    now = time.monotonic()
                    if settled(row_samples, cfg.settle_window_s, cfg.settle_rate_c_per_min, cfg.min_row_s, now, row_t0):
                        row.settled, row.status = True, "SETTLED"; row.time_to_settle = (now - row_t0) / 60.0; break
                    if now - row_t0 > cfg.row_timeout_s:
                        row.status = "TIMEOUT"; break
                    time.sleep(cfg.poll_s)
                if self._abort.is_set() and row.status == "NOT_RUN":
                    row.status = "ABORTED"
                # row figures: settled value = mean of the last window, peak otherwise
                if row_samples:
                    tail = [s for s in row_samples if s.t >= row_samples[-1].t - cfg.settle_window_s] or row_samples
                    for p in PANELS:
                        vals = [s.temps[p] for s in (tail if row.settled else row_samples) if s.temps.get(p) is not None]
                        row.temps[p] = (statistics.fmean(vals) if row.settled else max(vals)) if vals else None
                    have = [(v, p) for p, v in row.temps.items() if v is not None]
                    if have:
                        row.max_settled_temp, row.hottest_panel = max(have); row.margin_to_working_limit = cfg.limit_c - row.max_settled_temp
                    rpms = [s.tach for s in tail if s.tach is not None]
                    row.tach_rpm = statistics.fmean(rpms) if rpms else None
                self.on_status("row", f"{duty} %: {row.status} — max {row.max_settled_temp:.1f} C ({row.hottest_panel})" if row.max_settled_temp is not None else f"{duty} %: {row.status}")
                if row.status in ("LIMIT", "ALARM", "TIMEOUT", "ERROR", "ABORTED"):
                    res.status = {"LIMIT": "STOPPED_AT_LIMIT", "ALARM": "STOPPED_AT_LIMIT", "TIMEOUT": "STOPPED_AT_LIMIT", "ERROR": "ERROR", "ABORTED": "ABORTED"}[row.status]
                    if row.status in ("LIMIT", "ALARM"):
                        res.notes.append(f"stopped at {duty} % — the lower duties would only run hotter")
                    break
            else:
                res.status = "OK"
        except Exception as e:  # noqa: BLE001
            res.status = "ERROR"; res.notes.append(f"{type(e).__name__}: {e}"[:200])
        finally:
            self.on_status("safe", "LEDs off, fans back to 100 %"); self._safe()
        self.on_status("done", self.result.final_text())
        return res


def write_csv(res: FanSweepResult, path: str | Path) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    t0 = res.t0 or (res.samples[0].t if res.samples else 0.0)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# DVT-THM-004 LED temperature vs LED-cooling fan duty", f"status={res.status}", f"recommended_duty={res.recommended_duty()}"])
        w.writerow(["t_s", "fan_duty_pct", *[f"led_{p}_C" for p in PANELS], "tach_rpm"])
        for s in res.samples:
            w.writerow([f"{s.t - t0:.1f}", s.duty, *[("" if s.temps.get(p) is None else f"{s.temps[p]:.2f}") for p in PANELS], "" if s.tach is None else f"{s.tach:.0f}"])
        w.writerow([]); w.writerow(["# per duty", "status", "settled", "max_C", "hottest", "margin_C", "time_to_settle_min", *[f"{p}_C" for p in PANELS]])
        for r in res.rows:
            w.writerow([r.duty, r.status, r.settled, "" if r.max_settled_temp is None else f"{r.max_settled_temp:.2f}", r.hottest_panel or "",
                        "" if r.margin_to_working_limit is None else f"{r.margin_to_working_limit:.2f}", "" if r.time_to_settle is None else f"{r.time_to_settle:.1f}",
                        *[("" if r.temps.get(p) is None else f"{r.temps[p]:.2f}") for p in PANELS]])
    return p


def plot_png(res: FanSweepResult, path: str | Path, title: str = "DVT-THM-004 · LED temperature vs LED-cooling fan duty") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    t0 = res.t0 or (res.samples[0].t if res.samples else 0.0)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=120, gridspec_kw={"width_ratios": [3, 1.3]})
    colors = {"right": "#d62839", "left": "#2f6fdb", "back": "#e8760c", "door": "#1f9d61"}
    xs = [(s.t - t0) / 60.0 for s in res.samples]
    for pnl in PANELS:
        ys = [s.temps.get(pnl) for s in res.samples]
        ax.plot(xs, [y if y is not None else float("nan") for y in ys], color=colors[pnl], lw=1.5, label=f"{pnl} panel")
    lim = res.config.get("limit_c", 75.0); mg = res.config.get("margin_c", 5.0)
    ax.axhline(lim, color="#d62839", ls="--", lw=1.2, label=f"working limit {lim:.0f} C"); ax.axhline(lim - mg, color="#d68a0c", ls=":", lw=1, label=f"limit − margin {lim - mg:.0f} C")
    # duty bands
    cur, start = None, 0.0
    bands = []
    for s in res.samples:
        if s.duty != cur:
            if cur is not None: bands.append((cur, start, (s.t - t0) / 60.0))
            cur, start = s.duty, (s.t - t0) / 60.0
    if cur is not None and res.samples: bands.append((cur, start, (res.samples[-1].t - t0) / 60.0))
    for k, (duty, a, b) in enumerate(bands):
        ax.axvspan(a, b, color="#7c5cbf", alpha=0.05 + 0.05 * (k % 2)); ax.text((a + b) / 2, ax.get_ylim()[1] if False else lim + 1.5, f"fan {duty} %", ha="center", fontsize=9, color="#3d2a7a")
    ax.set_xlabel("time [min]"); ax.set_ylabel("LED back-face temperature [C]"); ax.grid(True, alpha=0.3); ax.legend(loc="lower right", fontsize=8)
    ax.set_title(f"{title} — {res.status}")
    # right: settled max per duty
    duties = [r.duty for r in res.rows]; maxes = [r.max_settled_temp if r.max_settled_temp is not None else 0 for r in res.rows]
    cols = ["#1f9d61" if (r.settled and r.max_settled_temp is not None and r.max_settled_temp <= lim - mg) else ("#d68a0c" if r.settled else "#d62839") for r in res.rows]
    ax2.bar([str(d) for d in duties], maxes, color=cols)
    for i, r in enumerate(res.rows):
        if r.max_settled_temp is not None:
            ax2.text(i, r.max_settled_temp / 2, f"{r.max_settled_temp:.1f} C\n{r.hottest_panel or ''}\n{'settled' if r.settled else r.status.lower()}", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    ax2.axhline(lim, color="#d62839", ls="--", lw=1.2); ax2.axhline(lim - mg, color="#d68a0c", ls=":", lw=1)
    ax2.set_xlabel("LED-cooling fan duty [%]"); ax2.set_ylabel("hottest panel, settled [C]"); ax2.set_ylim(0, max([lim + 10] + [m + 8 for m in maxes]))
    rec = res.recommended_duty()
    ax2.set_title(f"recommended: {rec} %" if rec is not None else "no duty with margin", fontsize=10, color="#1f9d61" if rec is not None else "#d62839")
    fig.tight_layout(); fig.savefig(p); plt.close(fig)
    return p
