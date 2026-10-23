"""Built-in sCure machine simulator — lets the whole DVT flow be exercised
without hardware. Selected by using the DUT address `sim://scure`.

Physics (coarse, 1 s ticks, real time):
  chamber:  first-order towards ambient; heater adds up to +1.6 °C/min at
            230 V (scaled by (V/230)^2), circulation fan required; cooling
            modes fast/normal/slow remove heat at 3 / 2 / 1 °C/min above ambient
  LEDs:     back-face temperature rises with UV drive towards
            ambient + 0.55 °C per % (EVT figure), τ ≈ 40 s; degraded fans raise it
  fans:     RPM follows duty (6000 RPM at 100 %); injected faults zero it
  interlock: opening the door kills UV immediately and raises an alarm
  faults:   injectable from the DUT Control page — door open, heater sensor
            open/short, LED thermistor open, fan disconnected/blocked,
            circulation fan loss, mains dropout — each producing the alarm /
            protective action the catalog's SAF tests look for.

`SimClient` exposes the same interface as `DutClient` (state(), heat(),
cool(), stop(), uv(), door_open(), fan(), led_test(), fan_test()) plus
`inject(fault, on)` and `set_mains(v)`.
"""

from __future__ import annotations

import math
import random
import threading
import time

from .dut import DutState

FAULTS = {
    "door_open": "Door opened (interlock)",
    "heater_sensor_open": "Heater temperature sensor open circuit",
    "heater_sensor_short": "Heater temperature sensor shorted (reads low)",
    "led_thermistor_open": "LED thermistor open (right panel)",
    "led_fan_disconnected": "LED cooling fan disconnected (right)",
    "led_fan_blocked": "LED cooling fan blocked rotor (right)",
    "led_panel_open": "LED panel electrically disconnected (right)",
    "circulation_fan_loss": "Heater circulation fan loss",
    "chamber_fan_loss": "Chamber cooling fan loss",
    "mains_dropout": "Mains dropout",
    "thermal_cutout": "Independent thermal cutout tripped",
    "selector_open": "Voltage selector in the mid position (heater open circuit)",
}
ERROR_CODES = {
    "door_open": "1101", "heater_sensor_open": "2201", "heater_sensor_short": "2202", "led_thermistor_open": "2301", "led_panel_open": "2310",
    "led_fan_disconnected": "2401", "led_fan_blocked": "2402", "circulation_fan_loss": "2410", "chamber_fan_loss": "2411",
    "mains_dropout": "3001", "thermal_cutout": "2210", "heater_watchdog": "2220", "led_overtemp": "2320", "selector_open": "7004",
}


class SimMachine:
    """The simulated unit. One instance per process (see `get_sim`)."""

    LED_WORKING_LIMIT = 75.0
    LED_SHUTDOWN = 82.0          # protective shutdown (catalog CONFIRM item)
    CHAMBER_CEILING = 95.0
    STALL_WATCHDOG_S = 60.0      # simulator-accelerated no-heating watchdog (real machine: 25 min)

    def __init__(self, ambient: float = 24.0, mains_v: float = 230.0):
        self.lock = threading.Lock()
        self.ambient = ambient; self.mains_v = mains_v
        self.chamber = ambient; self.heater_temp = ambient
        self.led = {k: ambient for k in ("right", "left", "back", "door")}
        self.target = None; self.mode = "IDLE"          # IDLE | HEAT | COOL | CURE
        self.cool_mode = "normal"
        self.uv_on = False; self.uv_pct = 0; self.uv_wavelength = 405
        self.door_open = False
        self.duty = {"chamber_heating": 0, "chamber_intake": 0, "led_cooling": 0}
        self.fan_override = {}          # operator-commanded fan duty (DVT-THM-005); cleared on stop
        self.faults: set[str] = set(); self._heat_t0 = None; self._heat_start = None
        self.alerts: list[dict] = []
        self.acked = True
        self.job_status = None
        self.version = "0.7.9-sim"
        self.meter_wavelength = 405        # the simulated StarBright's wavelength setting
        self.t0 = time.monotonic(); self._last = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sim-machine"); self._thread.start()

    # ---------------- physics loop ----------------
    def _loop(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                self._step(min(5.0, time.monotonic() - self._last)); self._last = time.monotonic()

    def _alarm(self, code_key: str, text: str, action: str | None = None):
        code = ERROR_CODES.get(code_key, "9999")
        if not any(a["code"] == code for a in self.alerts):
            self.alerts.append({"code": code, "message": text, "action": action or "Acknowledge to continue", "ts": time.time()})
            self.acked = False

    def _step(self, dt: float):
        f = self.faults
        heating = self.mode == "HEAT" or (self.mode == "CURE" and self.target is not None)
        # ---- protective logic (what the SAF tests verify) ----
        if "mains_dropout" in f:
            self.mode = "IDLE"; self.uv_on = False; self.duty = {k: 0 for k in self.duty}
            if self.job_status == "running": self.job_status = "aborted"
            self._alarm("mains_dropout", FAULTS["mains_dropout"], "Job aborted — restart manually")
            heating = False
        if self.door_open and self.uv_on:
            self.uv_on = False; self._alarm("door_open", FAULTS["door_open"], "Close the door and restart the job")
            if self.job_status == "running": self.job_status = "aborted"
        if heating and "circulation_fan_loss" in f:
            self.mode = "IDLE"; heating = False; self.duty["chamber_heating"] = 0
            self._alarm("circulation_fan_loss", FAULTS["circulation_fan_loss"] + " — heater disabled", "Check the heater circulation fan")
        if heating and "heater_sensor_open" in f:
            self.mode = "IDLE"; heating = False
            self._alarm("heater_sensor_open", FAULTS["heater_sensor_open"] + " — heater disabled", "Reconnect the heater sensor")
        if heating and "heater_sensor_short" in f:
            # a shorted NTC reads low: plausibility check catches it after the temp keeps climbing
            if self.chamber > self.ambient + 12:
                self.mode = "IDLE"; heating = False
                self._alarm("heater_sensor_short", FAULTS["heater_sensor_short"] + " — implausible reading, heater disabled", "Check the heater sensor")
        if "thermal_cutout" in f or self.chamber >= self.CHAMBER_CEILING:
            self.mode = "IDLE"; heating = False
            self._alarm("thermal_cutout", FAULTS["thermal_cutout"] + " — heater power removed", "Let the chamber cool; acknowledge")
        if self.uv_on and "led_thermistor_open" in f:
            self.uv_on = False; self._alarm("led_thermistor_open", FAULTS["led_thermistor_open"] + " — UV inhibited", "Reconnect the right LED thermistor")
        if self.uv_on and ("led_fan_disconnected" in f or "led_fan_blocked" in f):
            self.uv_on = False
            key = "led_fan_disconnected" if "led_fan_disconnected" in f else "led_fan_blocked"
            self._alarm(key, FAULTS[key] + " — UV inhibited", "Check the right LED cooling fan")
        if self.uv_on and "led_panel_open" in f:
            # dark panel detected at switch-on / mid-job: alarm names the panel, tells the operator to check the LED
            self.uv_on = False
            if self.job_status == "running": self.job_status = "aborted"
            self._alarm("led_panel_open", "LED panel not working (right) — UV inhibited", "Check the right LED panel and its driver connection")
        if self.uv_on and max(self.led.values()) >= self.LED_SHUTDOWN:
            self.uv_on = False; self._alarm("led_overtemp", f"LED back-face over {self.LED_SHUTDOWN:.0f} °C — UV inhibited", "Let the panels cool")
        # ---- heater / chamber ----
        gain = 0.0 if "selector_open" in f else (self.mains_v / 230.0) ** 2   # mid-position selector: heater branch open
        if heating and self.target is not None:
            self.duty["chamber_heating"] = 100
            # no-heating watchdog (the real machine's stall rule, Err 7004, is 5 x 5 min; the simulator uses 60 s)
            if self._heat_t0 is None: self._heat_t0, self._heat_start = time.monotonic(), self.chamber
            if time.monotonic() - self._heat_t0 >= self.STALL_WATCHDOG_S and self.chamber - self._heat_start < 1.0:
                self.mode = "IDLE"; heating = False
                if self.job_status == "running": self.job_status = "aborted"
                self._alarm("selector_open", "Chamber not heating — the heater receives no power", "Set the voltage selector to the position matching your mains (115 V or 230 V) — a mid position is an open circuit")
        else:
            self._heat_t0 = None
        if heating and self.target is not None:
            err = self.target - self.chamber
            drive = max(0.0, min(1.0, err / 4.0))                      # simple P control with a 4 °C band
            self.chamber += (1.6 / 60.0) * gain * drive * dt
            self.heater_temp = self.chamber + 25 * drive
        else:
            self.heater_temp += (self.chamber - self.heater_temp) * 0.05 * dt
        if self.mode == "COOL":
            rate = {"fast": 3.0, "normal": 2.0, "slow": 1.0}[self.cool_mode] / 60.0
            self.duty["chamber_intake"] = {"fast": 100, "normal": 60, "slow": 30}[self.cool_mode]; self.duty["chamber_heating"] = 100
            if "chamber_fan_loss" in f:
                self.duty["chamber_intake"] = 0; rate = 0.15 / 60
                self._alarm("chamber_fan_loss", FAULTS["chamber_fan_loss"] + " — cooling stopped", "Check the chamber cooling fan")
            self.chamber -= min(rate * dt, max(0.0, self.chamber - self.ambient))
            if self.target is not None and self.chamber <= self.target + 0.2:
                self.mode = "IDLE"; self.duty["chamber_intake"] = 0; self.duty["chamber_heating"] = 0; self.job_status = "complete"
        elif not heating:
            self.duty["chamber_heating"] = 0
        # passive loss to ambient
        self.chamber += (self.ambient - self.chamber) * (0.25 / 60.0) * dt
        # ---- LEDs ----
        led_duty = self.fan_override.get("led_cooling", 100)
        target_led = self.ambient + (0.55 * self.uv_pct if self.uv_on else 0) + max(0.0, (self.chamber - self.ambient) * 0.35)
        if self.uv_on: target_led += (100 - led_duty) * 0.3          # less cooling airflow -> hotter back face (~+9 C at 70 % duty)
        for k in self.led:
            t = target_led
            if k == "right" and self.uv_on and ("led_fan_disconnected" in f or "led_fan_blocked" in f): t += 25
            if k == "right" and "led_panel_open" in f: t = self.ambient + max(0.0, (self.chamber - self.ambient) * 0.35)   # dark panel: no self-heating
            self.led[k] += (t - self.led[k]) * (1 - math.exp(-dt / 40.0)) + random.uniform(-0.05, 0.05)
        self.duty["led_cooling"] = self.fan_override.get("led_cooling", 100 if self.uv_on else (40 if max(self.led.values()) > self.ambient + 5 else 0))
        if self.mode == "CURE" and self.uv_on and self.job_end and time.monotonic() >= self.job_end:
            self.uv_on = False; self.mode = "IDLE"; self.job_status = "complete"

    # ---------------- controls ----------------
    def heat(self, target):
        with self.lock:
            if self.door_open: self._alarm("door_open", "Door open — cannot start", "Close the door"); return {"ok": False, "message": "door open"}
            if not self.acked and self.alerts: return {"ok": False, "message": "acknowledge active alarm first"}
            self.target = float(target); self.mode = "HEAT"; self.job_status = "running"; return {"ok": True}

    def cool(self, target, mode="normal"):
        with self.lock:
            self.target = float(target); self.cool_mode = mode; self.mode = "COOL"; self.job_status = "running"; return {"ok": True}

    def stop(self):
        with self.lock:
            self.mode = "IDLE"; self.uv_on = False; self.target = None; self.duty = {k: 0 for k in self.duty}; self.fan_override.clear()
            if self.job_status == "running": self.job_status = "aborted"
            return {"ok": True}

    def uv(self, on, intensity=50, wavelength=405, seconds=None):
        with self.lock:
            if on and self.door_open: self._alarm("door_open", "Door open — UV inhibited", "Close the door"); return {"ok": False, "message": "door open"}
            if on and any(k in self.faults for k in ("led_thermistor_open", "led_fan_disconnected", "led_fan_blocked")):
                self._alarm(next(k for k in ("led_thermistor_open", "led_fan_disconnected", "led_fan_blocked") if k in self.faults), "Job start inhibited — LED protection", "Fix the fault")
                return {"ok": False, "message": "inhibited"}
            if on and "led_panel_open" in self.faults:
                self._alarm("led_panel_open", "LED panel not working (right) — job start inhibited", "Check the right LED panel and its driver connection")
                return {"ok": False, "message": "inhibited"}
            self.uv_on = bool(on); self.uv_pct = int(intensity); self.uv_wavelength = wavelength
            self.mode = "CURE" if on else ("HEAT" if self.target and self.mode == "CURE" else self.mode)
            self.job_end = (time.monotonic() + seconds) if (on and seconds) else None
            if on: self.job_status = "running"
            return {"ok": True}

    def door(self, open_):
        with self.lock:
            self.door_open = bool(open_)
            if self.door_open and self.uv_on:      # hardware interlock: UV is cut the instant the door opens (SAF-012)
                self.uv_on = False; self._alarm("door_open", FAULTS["door_open"], "Close the door and restart the job")
                if self.job_status == "running": self.job_status = "aborted"
            return {"ok": True, "doorOpen": self.door_open}

    def fan(self, name, speed):
        with self.lock:
            if name in self.duty: self.duty[name] = int(speed); self.fan_override[name] = int(speed)
            return {"ok": True}

    def ack(self):
        with self.lock:
            self.alerts.clear(); self.acked = True; return {"ok": True}

    def inject(self, fault, on=True):
        with self.lock:
            if fault == "door_open": self.door_open = bool(on)
            (self.faults.add if on else self.faults.discard)(fault)
            if not on and fault in ("thermal_cutout",): pass
            return {"ok": True, "faults": sorted(self.faults)}

    def set_mains(self, v):
        with self.lock: self.mains_v = float(v); return {"ok": True}

    def led_test(self):
        with self.lock: return {"ok": not any(k.startswith("led_") for k in self.faults), "panels": {k: round(v, 1) for k, v in self.led.items()}}

    def fan_test(self):
        with self.lock:
            return {"ok": not any(k.endswith("_loss") or k.startswith("led_fan") for k in self.faults), "rpm": self._rpm()}

    def _rpm(self):
        f = self.faults
        def rpm(duty): return 0 if duty <= 0 else max(0, round(60 * duty + random.uniform(-40, 40)))
        led = 0 if ("led_fan_disconnected" in f or "led_fan_blocked" in f) else rpm(self.duty["led_cooling"])
        return {"chamber_heating": 0 if "circulation_fan_loss" in f else rpm(self.duty["chamber_heating"]),
                "chamber_intake": 0 if "chamber_fan_loss" in f else rpm(self.duty["chamber_intake"]),
                "led_cooling": led}

    # ---------------- state as the real /api/state would report ----------------
    def api_state(self) -> dict:
        with self.lock:
            f = self.faults
            chamber_reading = None if "heater_sensor_open" in f else (self.ambient - 5 if "heater_sensor_short" in f else self.chamber)
            led = {k: (None if (k == "right" and "led_thermistor_open" in f) else round(v, 2)) for k, v in self.led.items()}
            return {"chamberTemp": None if chamber_reading is None else round(chamber_reading, 2), "chamberTempTrue": round(self.chamber, 2),
                    "ambientTemp": self.ambient, "heaterTemp": round(self.heater_temp, 1), "targetTemp": self.target,
                    "isHeating": self.mode == "HEAT", "isCooling": self.mode == "COOL", "uvOn": self.uv_on, "uvIntensity": self.uv_pct if self.uv_on else 0,
                    "uvWavelength": self.uv_wavelength, "doorOpen": self.door_open, "ledTemps": led,
                    "fanRpm": self._rpm(), "fans": dict(self.duty), "mainsVoltage": self.mains_v,
                    "alerts": list(self.alerts), "fault": bool(self.alerts), "jobStatus": self.job_status,
                    "faultsInjected": sorted(f), "version": self.version, "simulated": True,
                    "uptime": round(time.monotonic() - self.t0)}


class SimUvSweep:
    """In-process stand-in for server/uv_sweep.py: the same state document, the same refusals,
    a StarBright whose reading follows the simulated LEDs (bends over towards 100 %, like the bench)."""

    def __init__(self, sim: SimMachine):
        self.sim = sim; self.state = {"running": False, "status": "NOT_RUN", "phase": "idle", "samples": [], "steps": [], "error": None}
        self._abort = threading.Event(); self._lock = threading.Lock()

    def _read(self) -> float:
        s = self.sim
        with s.lock:
            on, pct, wl = s.uv_on, s.uv_pct, s.uv_wavelength
        base = 45.0 if wl == 405 else 34.0
        v = base * pct / 100.0 * (1 - 0.15 * max(0, pct - 30) / 70) if on else 0.002
        return max(0.0, v + random.gauss(0, 0.01))

    def meter(self) -> dict:
        return {"ok": True, "present": True, "transport": "sim", "firmware": "SIM1.00", "instrument": "STBR 000000 StarBright (simulated)", "head": "SI 000000 PD300RM-8W (sim)",
                "units": "w", "unit_name": "W/cm2", "wavelength_nm": self.sim.meter_wavelength, "reading_mw_cm2": round(self._read(), 4)}

    def set_wavelength(self, nm) -> dict:
        self.sim.meter_wavelength = int(nm); return {"ok": True, "wavelength_nm": int(nm)}

    def start(self, q: dict) -> dict:
        with self._lock:
            if self.state["running"]: return {"ok": False, "message": "a sweep is already running"}
            wl = int(q.get("wavelength", 405)); steps = [int(x) for x in str(q.get("steps", "30,40,50,60,70,80,90,100")).split(",") if str(x).strip()]
            cfg = {"wavelength": wl, "steps": steps, "dwell": float(q.get("dwell", 15)), "baseline": float(q.get("baseline", 5)), "settle": float(q.get("settle", 5)),
                   "tail": float(q.get("tail", 1)), "hz": float(q.get("hz", 5))}
            if self.sim.door_open: return {"ok": False, "message": "door open — close the door (the LEDs are interlocked)"}
            mwl = self.sim.meter_wavelength; force = str(q.get("force", 0)) not in ("0", "", "false")
            if mwl != wl and not force:
                return {"ok": False, "code": "METER_WAVELENGTH", "meter_wavelength_nm": mwl,
                        "message": f"the StarBright is set to {mwl} nm but this test is at {wl} nm — set the meter to {wl} nm first (or force=1 to record it as unverified)"}
            self._abort.clear()
            self.state = {"running": True, "status": "RUNNING", "phase": "starting", "config": cfg, "samples": [], "steps": [], "error": None, "aborted": False, "started": time.time(),
                          "finished": None, "elapsed": 0.0, "step_index": None, "intensity": 0, "reading": None, "meter": self.meter(), "meter_wavelength_nm": mwl, "meter_wavelength_verified": mwl == wl}
            threading.Thread(target=self._run, args=(cfg,), daemon=True, name="sim-uv-sweep").start()
            return {"ok": True, "message": "simulated sweep started", "meter_wavelength_nm": mwl, "meter_wavelength_verified": mwl == wl}

    def _run(self, cfg):
        s, t0 = self.state, time.monotonic()
        def led_max():
            with self.sim.lock: return round(max(self.sim.led.values()), 1)
        def hold(seconds, phase, pct, on):
            period = 1.0 / cfg["hz"]; nxt = time.monotonic(); end = nxt + seconds
            while time.monotonic() < end and not self._abort.is_set():
                v = self._read(); s["samples"].append([round(time.monotonic() - t0, 3), round(v, 4), pct, phase, led_max(), on]); s["reading"] = v
                nxt += period; self._abort.wait(max(0.0, nxt - time.monotonic()))
        try:
            s["phase"] = "baseline"; self.sim.uv(False); hold(cfg["baseline"], "baseline", 0, False)
            dark = [x[1] for x in s["samples"]]; s["dark_mw_cm2"] = round(sum(dark) / len(dark), 4) if dark else None
            for i, pct in enumerate(cfg["steps"]):
                if self._abort.is_set(): break
                s["phase"] = "step"; s["step_index"] = i; s["intensity"] = pct
                r = self.sim.uv(True, pct, cfg["wavelength"])
                if not r.get("ok"): s["error"] = f"UV refused at {pct} %: {r.get('message')}"; break
                hold(cfg["dwell"], "step", pct, True)
                tail = [x[1] for x in s["samples"] if x[3] == "step" and x[2] == pct and x[0] >= (time.monotonic() - t0) - cfg["settle"]]
                mean = sum(tail) / len(tail) if tail else None
                sd = (sum((v - mean) ** 2 for v in tail) / len(tail)) ** 0.5 if tail and mean is not None else None
                s["steps"].append({"intensity": pct, "mean_mw_cm2": None if mean is None else round(mean, 4), "sd_mw_cm2": None if sd is None else round(sd, 4), "n": len(tail), "led_max_c": led_max()})
            s["phase"] = "tail"; s["intensity"] = 0; self.sim.uv(False); hold(cfg["tail"], "tail", 0, False)
            s["aborted"] = self._abort.is_set()
            s["status"] = "ABORTED" if s["aborted"] else ("ERROR" if s["error"] else ("OK" if len(s["steps"]) == len(cfg["steps"]) else "INCOMPLETE"))
        finally:
            self.sim.uv(False); s["phase"] = "done"; s["running"] = False; s["finished"] = time.time(); s["elapsed"] = round(time.monotonic() - t0, 1)

    def status(self) -> dict:
        return {"ok": True, **dict(self.state)}

    def abort(self) -> dict:
        self._abort.set(); return {"ok": True, "message": "abort requested"}


_SIM: SimMachine | None = None
_SIM_SWEEP: SimUvSweep | None = None


def get_sim() -> SimMachine:
    global _SIM
    if _SIM is None:
        _SIM = SimMachine()
    return _SIM


class SimClient:
    """Drop-in for DutClient against the in-process simulator."""

    def __init__(self, url: str = "sim://scure", timeout: float = 0):
        self.url = url; self.sim = get_sim()

    def state(self) -> DutState:
        s = self.sim.api_state()
        led = {k: v for k, v in s["ledTemps"].items() if v is not None}
        alerts = s["alerts"]; first = alerts[0] if alerts else None
        metrics = {"chamberTemp": s["chamberTemp"], "ambientTemp": s["ambientTemp"], "heaterTemp": s["heaterTemp"],
                   "ledTempMax": max(led.values()) if led else None,
                   "ledTempRight": s["ledTemps"].get("right"), "ledTempLeft": s["ledTemps"].get("left"),
                   "ledTempBack": s["ledTemps"].get("back"), "ledTempDoor": s["ledTemps"].get("door"),
                   "heaterFanRpm": s["fanRpm"]["chamber_heating"], "ledFanRpm": s["fanRpm"]["led_cooling"], "intakeFanRpm": s["fanRpm"]["chamber_intake"],
                   "targetTemp": s["targetTemp"], "uvIntensity": s["uvIntensity"], "mainsVoltage": s["mainsVoltage"],
                   "errorCode": first["code"] if first else None, "alertText": first["message"] if first else None,
                   "jobStatus": s["jobStatus"], "faultsInjected": s["faultsInjected"]}
        flags = {"doorOpen": s["doorOpen"], "uvOn": s["uvOn"], "isHeating": s["isHeating"], "isCooling": s["isCooling"],
                 "fault": s["fault"], "simulated": True}
        return DutState(True, self.url, s["version"], metrics, flags)

    def heat(self, t): return self.sim.heat(t)
    def cool(self, t, mode="normal"): return self.sim.cool(t, mode)
    def stop(self): return self.sim.stop()
    def uv(self, on, intensity=50, wavelength=405): return self.sim.uv(on, intensity, wavelength)
    def door_open(self): return self.sim.door(True)
    def door_close(self): return self.sim.door(False)
    def fan(self, name, speed): return self.sim.fan(name, speed)
    def led_test(self): return self.sim.led_test()
    def fan_test(self): return self.sim.fan_test()
    def ack(self): return self.sim.ack()
    def inject(self, fault, on=True): return self.sim.inject(fault, on)
    def set_mains(self, v): return self.sim.set_mains(v)
    def version(self): return {"appVersion": self.sim.version, "simulated": True}
    # StarBright on the simulated machine + the UV linearity sweep (DVT-OPT-001/002)
    def _sweep(self) -> SimUvSweep:
        global _SIM_SWEEP
        if _SIM_SWEEP is None: _SIM_SWEEP = SimUvSweep(self.sim)
        return _SIM_SWEEP
    def meter(self): return self._sweep().meter()
    def meter_set_wavelength(self, nm): return self._sweep().set_wavelength(nm)
    def uv_sweep_start(self, q): return self._sweep().start(q)
    def uv_sweep_status(self): return self._sweep().status()
    def uv_sweep_abort(self): return self._sweep().abort()


def is_sim_url(url: str | None) -> bool:
    return bool(url) and url.startswith("sim://")
