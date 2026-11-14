"""UV-off timing, instrumented: UV irradiance against time while a protective
trigger fires. One runner, two catalog tests, selected by `UvOffConfig.trigger`:

    "door"            DVT-SAF-008  the door opens          uv_off_time  <= 1 s
    "led_thermistor"  DVT-SAF-004  an LED thermistor is    led_off_time <= 2 s
                                   disconnected (open circuit)

Sequence (`UvOffRunner.run`, blocking — call it from a worker thread):

    1. baseline      LEDs off, record the dark reading for `baseline_s`
    2. uv on         LEDs at `intensity` % (default 100 = maximum), `wavelength` nm
    3. plateau       wait until the reading is stable (peak-to-peak within
                     `plateau_tol` of the mean over `plateau_window_s`)
    4. trigger       "auto": the console fires it — door: POST /api/door/open
                     (the simulator opens the door; the real machine releases
                     the door magnet and the operator pulls the door);
                     thermistor: the simulator's fault injection (a real
                     thermistor can only be pulled by hand) — "operator": the
                     operator does it on the prompt and presses the marker.
                     t_trigger = the first DUT poll that reports the trigger
                     (door open / that thermistor reading gone), or the
                     operator's marker, or, failing both, the last sample at
                     plateau before the drop
    5. record        until the reading stays below `off_fraction` x plateau for
                     `settle_s`, or `timeout_after_trigger_s`
    6. safe          UV off / stop, read the machine's alarm, analyse

`analyze()` is a pure function over the sample list so it is unit-testable;
`write_csv()` and `plot_png()` produce the artefacts attached to the run —
the PNG is the "irradiance vs time" graph with the trigger and UV-off markers
and the measured uv_off_time against the test's limit.
"""

from __future__ import annotations

import csv
import statistics
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from ..alarms import normalise_alerts

LED_POSITIONS = ("right", "left", "back", "door")

# catalog step `tool:` key -> runner trigger
TOOL_TRIGGERS = {"uv_off_timing": "door", "led_off_timing": "led_thermistor"}

# What each trigger means for the operator, the artefacts and the verdict.
TRIGGERS = {
    "door": {
        "test_id": "DVT-SAF-008", "field": "uv_off_time", "limit_s": 1.0,
        "label": "door open", "prompt": "OPEN THE DOOR NOW",
        "auto_text": "opening the door (API)", "record_text": "door open — recording the UV decay",
        "sim_fault": None,
    },
    "led_thermistor": {
        "test_id": "DVT-SAF-004", "field": "led_off_time", "limit_s": 2.0,
        "label": "thermistor disconnected", "prompt": "DISCONNECT THE LED THERMISTOR NOW",
        "auto_text": "disconnecting the thermistor (simulator fault injection)", "record_text": "thermistor disconnected — recording the UV decay",
        "sim_fault": "led_thermistor_open",
    },
}


@dataclass
class UvOffConfig:
    trigger: str = "door"           # "door" (DVT-SAF-008) | "led_thermistor" (DVT-SAF-004)
    sensor_position: str = "right"  # led_thermistor only: which thermistor is pulled
    intensity: int = 100            # % — both tests run at maximum
    wavelength: int = 405
    sample_hz: float = 25.0
    baseline_s: float = 1.0
    plateau_window_s: float = 1.0
    plateau_tol: float = 0.05       # peak-to-peak / mean
    plateau_timeout_s: float = 20.0
    trigger_mode: str = "auto"      # "auto" | "operator"
    off_fraction: float = 0.10      # "UV removed" = below 10 % of plateau
    settle_s: float = 0.5           # must stay below for this long
    timeout_after_trigger_s: float = 15.0
    poll_s: float = 0.05            # DUT state poll while waiting for the trigger
    unit: str = "mW/cm2"
    limit_s: float | None = None    # pass limit; None = the trigger's catalog limit

    def __post_init__(self):
        if self.trigger not in TRIGGERS:
            raise ValueError(f"unknown trigger {self.trigger!r} (expected {' | '.join(TRIGGERS)})")
        if self.trigger == "led_thermistor" and self.sensor_position not in LED_POSITIONS:
            raise ValueError(f"unknown LED thermistor position {self.sensor_position!r} (expected {' | '.join(LED_POSITIONS)})")
        if self.limit_s is None:
            self.limit_s = TRIGGERS[self.trigger]["limit_s"]

    @property
    def spec(self) -> dict:
        return TRIGGERS[self.trigger]

    @property
    def prompt(self) -> str:
        if self.trigger == "led_thermistor":
            return f"DISCONNECT THE {self.sensor_position.upper()} LED THERMISTOR NOW"
        return self.spec["prompt"]


@dataclass
class Sample:
    t: float
    value: float
    trigger_seen: bool | None = None   # the DUT reports the trigger (door open / thermistor reading gone)
    uv_on: bool | None = None


@dataclass
class UvOffResult:
    status: str = "NOT_RUN"          # OK | NO_PLATEAU | TIMEOUT | ABORTED | ERROR
    trigger: str = "door"
    test_id: str = "DVT-SAF-008"
    sensor_position: str | None = None
    limit_s: float = 1.0
    unit: str = ""
    samples: list[Sample] = field(default_factory=list)
    dark: float | None = None
    plateau: float | None = None
    t_uv_on: float | None = None
    t_trigger: float | None = None
    trigger_source: str = ""         # api | dut-poll | operator | trace
    t_uv_off: float | None = None    # first sample below off_fraction x plateau after the trigger
    uv_off_time: float | None = None
    t_1pct: float | None = None      # first sample below 1 % of plateau
    residual: float | None = None    # mean of the last settle_s after UV off
    residual_fraction: float | None = None
    alarm_code: str | None = None
    alarm_text: str | None = None
    alarm_identifies_sensor: bool | None = None   # led_thermistor: the alarm text names the position
    meter_info: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool | None:
        return None if self.uv_off_time is None else self.uv_off_time <= self.limit_s

    def summary(self) -> dict:
        d = asdict(self); d.pop("samples"); d["n_samples"] = len(self.samples); return d


# --------------------------------------------------------------------------
#  DUT helpers (work for DutClient and SimClient alike)
# --------------------------------------------------------------------------
def raw_state(dut) -> dict:
    if hasattr(dut, "sim"):
        return dut.sim.api_state()
    return dut._req("/api/state")


def door_is_open(s: dict) -> bool | None:
    if s.get("doorOpen") is not None:
        return bool(s["doorOpen"])
    if s.get("doorClosed") is not None:
        return not s["doorClosed"]
    return None


def thermistor_is_gone(s: dict, position: str) -> bool | None:
    """True when the machine reports no reading for that LED thermistor (open
    circuit): `ledTemps[position]` present but null. None when the machine does
    not report per-position LED temperatures at all."""
    led = s.get("ledTemps") or s.get("ledTemperatures")
    if not isinstance(led, dict):
        return None
    for key in (position, f"LED_{position.upper()}"):
        if key in led:
            return led[key] is None
    return None


def trigger_seen(s: dict, cfg: UvOffConfig) -> bool | None:
    if cfg.trigger == "led_thermistor":
        return thermistor_is_gone(s, cfg.sensor_position)
    return door_is_open(s)


def first_alert(s: dict) -> tuple[str | None, str | None]:
    # one reader for both shapes - the firmware's `alerts: [9011]` + `alertDetails` and the
    # simulator's dicts (alarms.normalise_alerts); before, a real machine's alarm came back
    # with its code but no text
    alerts = normalise_alerts(s)
    if alerts:
        return alerts[0].raw, alerts[0].text or None
    if s.get("doorAborted"):
        return "6016", "door abort"
    faults = s.get("faults") or {}
    if isinstance(faults, dict):
        for key in ("led", "heater", "cooling"):
            if faults.get(key) and not isinstance(faults[key], bool):
                return None, str(faults[key])      # the real machine: a fault message, no code
    return None, None


def alarm_names_position(text: str | None, position: str | None) -> bool | None:
    if text is None or not position:
        return None
    return position.lower() in text.lower()


class _DutPoller(threading.Thread):
    """Polls the DUT state fast while the trigger is awaited, so the trigger
    instant is known to within `poll_s`."""

    def __init__(self, dut, cfg: UvOffConfig):
        super().__init__(daemon=True, name="uvoff-dut-poll")
        self.dut, self.cfg, self.interval = dut, cfg, cfg.poll_s
        self.seen: bool | None = None; self.uv_on: bool | None = None
        self.t_trigger: float | None = None; self.last: dict = {}
        self._stop = threading.Event(); self.error: str | None = None

    def run(self):
        while not self._stop.is_set():
            try:
                s = raw_state(self.dut); self.last = s
                seen = trigger_seen(s, self.cfg); now = time.monotonic()
                if seen and not self.seen and self.t_trigger is None:
                    self.t_trigger = now
                self.seen = seen; self.uv_on = s.get("uvOn")
            except Exception as e:  # noqa: BLE001
                self.error = str(e)[:120]
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


# --------------------------------------------------------------------------
#  runner
# --------------------------------------------------------------------------
class UvOffRunner:
    def __init__(self, dut, meter, cfg: UvOffConfig | None = None,
                 on_status: Callable[[str, str], None] | None = None,
                 on_sample: Callable[[Sample], None] | None = None):
        self.dut, self.meter, self.cfg = dut, meter, cfg or UvOffConfig()
        self.on_status = on_status or (lambda phase, text: None)
        self.on_sample = on_sample or (lambda s: None)
        self._abort = threading.Event(); self._marked = threading.Event(); self._t_marked = None
        self._sim_fault_injected = False
        c = self.cfg
        self.result = UvOffResult(trigger=c.trigger, test_id=c.spec["test_id"], limit_s=c.limit_s, unit=c.unit, config=asdict(c),
                                  sensor_position=c.sensor_position if c.trigger == "led_thermistor" else None)

    # ---- operator hooks
    def abort(self):
        self._abort.set()

    def mark_trigger(self):
        """Operator pressed 'the door is open' / 'the thermistor is disconnected'
        (fallback when the DUT has no reading for the trigger)."""
        self._t_marked = time.monotonic(); self._marked.set()

    mark_door_open = mark_trigger      # DVT-SAF-008 name

    # ---- internals
    def _status(self, phase, text):
        self.on_status(phase, text)

    def _pump(self, poller: _DutPoller | None) -> list[Sample]:
        out = []
        for t, v in self.meter.read_all():
            s = Sample(t, v, poller.seen if poller else None, poller.uv_on if poller else None)
            self.result.samples.append(s); self.on_sample(s); out.append(s)
        return out

    def _sleep_tick(self):
        time.sleep(1.0 / self.cfg.sample_hz)

    def _uv_off(self):
        for fn in (lambda: self.dut.uv(False), lambda: self.dut.stop()):
            try: fn()
            except Exception: pass  # noqa: BLE001

    def _fire_trigger(self) -> float | None:
        """Auto mode: make the trigger happen. Returns the instant the API
        returned (the simulator applies it at once), or None if the console
        could not fire it and the operator has to."""
        cfg, res = self.cfg, self.result
        if cfg.trigger == "door":
            self._status("trigger", cfg.spec["auto_text"])
            self.dut.door_open(); return time.monotonic()
        fault = cfg.spec["sim_fault"]
        if hasattr(self.dut, "inject"):
            if cfg.sensor_position != "right":
                res.notes.append(f"simulator models the right thermistor only — {cfg.sensor_position} requested, right was disconnected")
            self._status("trigger", cfg.spec["auto_text"])
            self.dut.inject(fault, True); self._sim_fault_injected = True; return time.monotonic()
        res.notes.append("a real thermistor cannot be disconnected from the console — operator prompt used")
        self._status("trigger", cfg.prompt); return None

    def run(self) -> UvOffResult:
        cfg, res = self.cfg, self.result
        poller = None
        try:
            self._status("connect", f"connecting {getattr(self.meter, 'name', 'meter')}")
            res.meter_info = self.meter.connect() or {}
            res.unit = getattr(self.meter, "unit", cfg.unit) or cfg.unit
            poller = _DutPoller(self.dut, cfg); poller.start()
            # 1. baseline
            self._status("baseline", "LEDs off — recording the dark reading")
            t_end = time.monotonic() + cfg.baseline_s; base = []
            while time.monotonic() < t_end and not self._abort.is_set():
                base += [s.value for s in self._pump(poller)]; self._sleep_tick()
            res.dark = statistics.fmean(base) if base else 0.0
            if self._abort.is_set(): res.status = "ABORTED"; return res
            if poller.seen:
                res.notes.append("the trigger condition was already present at start (door open / thermistor reading missing) — fix it and rerun"); res.status = "ERROR"; return res
            # 2. UV on at maximum
            self._status("uv_on", f"LEDs on at {cfg.intensity} % / {cfg.wavelength} nm")
            r = self.dut.uv(True, cfg.intensity, cfg.wavelength)
            if isinstance(r, dict) and r.get("ok") is False:
                res.status = "ERROR"; res.notes.append(f"UV refused: {r.get('message')}"); return res
            res.t_uv_on = time.monotonic()
            # 3. plateau
            self._status("plateau", "waiting for a stable reading")
            window: list[Sample] = []; t_dead = res.t_uv_on + cfg.plateau_timeout_s; plateau = None
            while time.monotonic() < t_dead and not self._abort.is_set():
                window += self._pump(poller); self._sleep_tick()
                window = [s for s in window if s.t >= time.monotonic() - cfg.plateau_window_s]
                if len(window) >= 5 and (window[-1].t - window[0].t) >= cfg.plateau_window_s * 0.9:
                    vals = [s.value for s in window]; mean = statistics.fmean(vals)
                    if mean > (res.dark or 0) * 3 + 1e-9 and (max(vals) - min(vals)) <= cfg.plateau_tol * mean:
                        plateau = mean; break
            if self._abort.is_set(): self._uv_off(); res.status = "ABORTED"; return res
            if plateau is None:
                self._uv_off(); res.status = "NO_PLATEAU"; res.notes.append("reading never settled — check the sensor sees the LEDs and the meter range"); return res
            res.plateau = plateau
            # 4. trigger
            t_api = None
            if cfg.trigger_mode == "auto":
                try:
                    t_api = self._fire_trigger()
                except Exception as e:  # noqa: BLE001
                    res.notes.append(f"trigger API failed: {e}")
            else:
                self._status("trigger", cfg.prompt)
            t_wait = time.monotonic() + cfg.timeout_after_trigger_s
            while time.monotonic() < t_wait and not self._abort.is_set():
                self._pump(poller); self._sleep_tick()
                if poller.t_trigger is not None or self._marked.is_set():
                    break
            if self._abort.is_set(): self._uv_off(); res.status = "ABORTED"; return res
            if t_api is not None and hasattr(self.dut, "sim"):
                # the simulator applies the trigger the instant the API returns; the poll would add up to poll_s
                res.t_trigger, res.trigger_source = t_api, "api"
            elif poller.t_trigger is not None:
                res.t_trigger, res.trigger_source = poller.t_trigger, "dut-poll"
            elif self._marked.is_set():
                res.t_trigger, res.trigger_source = self._t_marked, "operator"
            # 5. record until UV is gone
            self._status("record", cfg.spec["record_text"])
            thresh = plateau * cfg.off_fraction; below_since = None
            t_dead = time.monotonic() + cfg.timeout_after_trigger_s
            while time.monotonic() < t_dead and not self._abort.is_set():
                for s in self._pump(poller):
                    if s.value <= thresh:
                        below_since = below_since or s.t
                    else:
                        below_since = None
                self._sleep_tick()
                if below_since is not None and time.monotonic() - below_since >= cfg.settle_s:
                    break
            res.status = "ABORTED" if self._abort.is_set() else ("OK" if below_since is not None else "TIMEOUT")
        except Exception as e:  # noqa: BLE001
            res.status = "ERROR"; res.notes.append(str(e)[:200])
        finally:
            self._uv_off()
            if poller is not None:
                poller.stop(); poller.join(timeout=1.0)
                try:
                    code, text = first_alert(poller.last or raw_state(self.dut)); res.alarm_code, res.alarm_text = code, text
                except Exception:  # noqa: BLE001
                    pass
            if self._sim_fault_injected:
                try: self.dut.inject(cfg.spec["sim_fault"], False); res.notes.append("simulated fault cleared after the run")
                except Exception: pass  # noqa: BLE001
            try: self.meter.close()
            except Exception: pass  # noqa: BLE001
        analyze(res, cfg)
        self._status("done", f"{res.status} — {cfg.spec['field']} {res.uv_off_time if res.uv_off_time is None else round(res.uv_off_time, 3)} s")
        return res


# --------------------------------------------------------------------------
#  analysis (pure)
# --------------------------------------------------------------------------
def analyze(res: UvOffResult, cfg: UvOffConfig) -> UvOffResult:
    """Fill t_uv_off / uv_off_time / t_1pct / residual from the samples.
    If no trigger instant is known, derive it from the trace (last sample still
    at >= 95 % of plateau before the final drop) and say so in trigger_source."""
    if res.trigger == "led_thermistor":
        res.alarm_identifies_sensor = alarm_names_position(res.alarm_text, res.sensor_position)
    if res.plateau is None or not res.samples:
        return res
    thr, thr1 = res.plateau * cfg.off_fraction, res.plateau * 0.01
    after = [s for s in res.samples if res.t_uv_on is None or s.t >= res.t_uv_on]
    # first sustained crossing below the threshold (after the plateau was reached)
    t_off = None
    for i, s in enumerate(after):
        if s.value <= thr and (res.t_trigger is None or s.t >= res.t_trigger - 0.001):
            tail = [x for x in after[i:] if x.t <= s.t + cfg.settle_s]
            if all(x.value <= thr for x in tail):
                t_off = s.t; break
    if t_off is None:
        return res
    res.t_uv_off = t_off
    if res.t_trigger is None:
        before = [s for s in after if s.t < t_off and s.value >= 0.95 * res.plateau]
        if before:
            res.t_trigger, res.trigger_source = before[-1].t, "trace"
            res.notes.append("trigger instant derived from the trace (no reading from the DUT, no operator marker) — the off time is a lower bound")
    if res.t_trigger is not None:
        res.uv_off_time = max(0.0, t_off - res.t_trigger)
    below1 = [s for s in after if s.t >= t_off and s.value <= thr1]
    res.t_1pct = below1[0].t if below1 else None
    tail = [s.value for s in after if s.t >= max(t_off, after[-1].t - cfg.settle_s)]
    if tail:
        res.residual = statistics.fmean(tail); res.residual_fraction = res.residual / res.plateau if res.plateau else None
    return res


# --------------------------------------------------------------------------
#  artefacts
# --------------------------------------------------------------------------
def _t0(res: UvOffResult) -> float:
    return res.t_trigger if res.t_trigger is not None else (res.t_uv_on or (res.samples[0].t if res.samples else 0.0))


def write_csv(res: UvOffResult, path: str | Path) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    t0 = _t0(res); spec = TRIGGERS[res.trigger]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([f"# {res.test_id} UV irradiance vs time", f"trigger={res.trigger}", f"sensor_position={res.sensor_position or ''}", f"unit={res.unit}",
                    f"status={res.status}", f"plateau={res.plateau}", f"t_trigger={res.t_trigger}", f"t_uv_off={res.t_uv_off}",
                    f"{spec['field']}={res.uv_off_time}", f"limit_s={res.limit_s}", f"trigger_source={res.trigger_source}"])
        w.writerow(["t_s_rel_trigger", f"irradiance_{res.unit}", "trigger_seen", "uv_on"])
        for s in res.samples:
            w.writerow([f"{s.t - t0:.4f}", f"{s.value:.6g}", "" if s.trigger_seen is None else int(bool(s.trigger_seen)), "" if s.uv_on is None else int(bool(s.uv_on))])
    return p


def plot_png(res: UvOffResult, path: str | Path, title: str | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    spec = TRIGGERS[res.trigger]; t0 = _t0(res)
    trig_label = spec["label"] + (f" ({res.sensor_position})" if res.sensor_position else "")
    title = title or f"{res.test_id} · UV irradiance vs time"
    xs = [s.t - t0 for s in res.samples]; ys = [s.value for s in res.samples]
    fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
    ax.plot(xs, ys, color="#7c5cbf", lw=1.6, label=f"irradiance [{res.unit}]")
    if res.plateau is not None:
        ax.axhline(res.plateau, color="#6b7a8c", ls=":", lw=1, label=f"plateau {res.plateau:.3g}")
        ax.axhline(res.plateau * res.config.get("off_fraction", 0.1), color="#d68a0c", ls=":", lw=1, label="UV-removed threshold (10 %)")
    if res.t_uv_on is not None:
        ax.axvline(res.t_uv_on - t0, color="#1f9d61", ls="--", lw=1.2, label="UV on")
    if res.t_trigger is not None:
        ax.axvline(0.0, color="#d62839", lw=1.6, label=f"{trig_label} ({res.trigger_source})")
    if res.t_uv_off is not None:
        ax.axvline(res.t_uv_off - t0, color="#2f6fdb", lw=1.6, label="UV off (< 10 %)")
        if res.uv_off_time is not None:
            ok = res.passed
            ax.annotate(f"{spec['field']} = {res.uv_off_time * 1000:.0f} ms  ({'PASS' if ok else 'FAIL'} vs {res.limit_s:g} s)",
                        xy=(res.t_uv_off - t0, (res.plateau or max(ys or [1])) * 0.55),
                        xytext=(12, 0), textcoords="offset points", fontsize=11, fontweight="bold", color="#1f9d61" if ok else "#d62839")
            ax.axvspan(0.0, res.t_uv_off - t0, color="#d62839", alpha=0.08)
    ax.set_xlabel(f"time relative to {trig_label} [s]"); ax.set_ylabel(f"irradiance [{res.unit}]")
    ax.set_title(f"{title} — {res.status}"); ax.grid(True, alpha=0.3); ax.legend(loc="upper right", fontsize=8)
    if xs:
        lo = min(xs); hi = max(xs)
        if res.t_trigger is not None:
            lo = max(lo, -3.0); hi = min(hi, max(3.0, (res.t_uv_off - t0 if res.t_uv_off else 0) + 2.0))
        ax.set_xlim(lo, hi)
    fig.tight_layout(); fig.savefig(p); plt.close(fig)
    return p
