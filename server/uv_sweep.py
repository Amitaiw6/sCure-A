"""DVT UV linearity sweep — irradiance against the commanded LED power, measured
by an Ophir StarBright plugged into the machine's own USB (DVT-OPT-001 405 nm,
DVT-OPT-002 450 nm).

Flask blueprint, mounted by app.py:

    GET  /api/dvt/meter                      is a StarBright present? identity, units,
                                             the wavelength it is SET to, one reading
    POST /api/dvt/meter/wavelength?nm=405    set the meter's wavelength
    POST /api/dvt/uv-sweep?wavelength=405&steps=30,40,50,60,70,80,90,100&dwell=15
                                             start (refused if a sweep is running, no
                                             meter, the meter is set to another wavelength
                                             — unless force=1 — or the door is open)
    GET  /api/dvt/uv-sweep                   live status + samples + per-step settled means
    POST /api/dvt/uv-sweep/abort             LEDs off, stop

The sweep: LEDs off for `baseline` s, then each step in turn — LEDs on at that
intensity for `dwell` s, the meter polled at `hz`; the step's value is the
mean of the last `settle` s. LEDs off at the end (and on abort, error, or
any exception). Every sample also carries the hottest LED thermistor from
the machine's own telemetry, so the drop in efficiency with junction
temperature can be seen next to the irradiance.
"""

from __future__ import annotations

import math
import statistics
import threading
import time

from flask import Blueprint, jsonify, request

bp = Blueprint("uv_sweep", __name__)
_hw = None
_lock = threading.Lock()
_state: dict = {"running": False, "phase": "idle", "samples": [], "steps": [], "error": None}
_abort = threading.Event()
DEFAULT_STEPS = (30, 40, 50, 60, 70, 80, 90, 100)


def configure(hw) -> None:
    """Give the blueprint the HardwareController (set_uv / get_state)."""
    global _hw
    _hw = hw


def _meter():
    from starbright_usb import StarBright
    return StarBright()


def _led_max():
    try:
        st = _hw.get_state() if _hw else {}
        temps = [v for v in (st.get("ledTemps") or {}).values() if isinstance(v, (int, float))]
        return (max(temps) if temps else None), st
    except Exception:  # noqa: BLE001
        return None, {}


def _door_open() -> bool | None:
    _, st = _led_max()
    if st.get("doorClosed") is not None:
        return not st["doorClosed"]
    if st.get("doorOpen") is not None:
        return bool(st["doorOpen"])
    return None


# ---------------------------------------------------------------- meter endpoints
@bp.route("/api/dvt/meter", methods=["GET"])
def meter_status():
    try:
        with _meter() as m:
            info = m.identify()
            info["reading_mw_cm2"] = m.power_mw_cm2()
            return jsonify({"ok": True, "present": True, **info})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "present": False, "message": str(e)})


@bp.route("/api/dvt/meter/wavelength", methods=["POST"])
def meter_set_wavelength():
    nm = int(request.args.get("nm", 0))
    if nm not in (405, 450):
        return jsonify({"ok": False, "message": f"wavelength must be 405 or 450 (got {nm})"})
    if _state["running"]:
        return jsonify({"ok": False, "message": "a sweep is running — the meter is busy"})
    try:
        with _meter() as m:
            m.set_wavelength(nm); now = m.wavelength_nm()
            return jsonify({"ok": now == nm, "wavelength_nm": now, "message": None if now == nm else f"meter reports {now} nm after setting {nm}"})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "message": str(e)})


# ---------------------------------------------------------------- the sweep
def _run(cfg: dict) -> None:
    s = _state
    t0 = time.monotonic()
    meter = None
    try:
        meter = _meter()
        s["meter"] = meter.identify()
        wl = cfg["wavelength"]

        def sample(phase, intensity, uv_on):
            v = meter.power_mw_cm2(); led, _ = _led_max()
            s["samples"].append([round(time.monotonic() - t0, 3), None if v is None else round(v, 4), intensity, phase, led, uv_on])
            s["reading"] = v; s["elapsed"] = round(time.monotonic() - t0, 1)

        def hold(seconds, phase, intensity, uv_on):
            period = 1.0 / cfg["hz"]; nxt = time.monotonic(); end = nxt + seconds
            while time.monotonic() < end and not _abort.is_set():
                sample(phase, intensity, uv_on)
                nxt += period; _abort.wait(max(0.0, nxt - time.monotonic()))

        s["phase"] = "baseline"; s["intensity"] = 0
        _hw.set_uv(False)
        hold(cfg["baseline"], "baseline", 0, False)
        dark = [x[1] for x in s["samples"] if x[3] == "baseline" and x[1] is not None]
        s["dark_mw_cm2"] = round(statistics.fmean(dark), 4) if dark else None
        for i, pct in enumerate(cfg["steps"]):
            if _abort.is_set():
                break
            s["phase"] = "step"; s["step_index"] = i; s["intensity"] = pct
            ok, why = _hw.set_uv(True, pct, wl)
            if not ok:
                s["error"] = f"UV refused at {pct} %: {why}"; break
            t_step = time.monotonic()
            hold(cfg["dwell"], "step", pct, True)
            tail = [x[1] for x in s["samples"] if x[3] == "step" and x[2] == pct and x[1] is not None and x[0] >= (time.monotonic() - t0) - cfg["settle"]]
            led_now, _ = _led_max()
            s["steps"].append({"intensity": pct, "mean_mw_cm2": round(statistics.fmean(tail), 4) if tail else None,
                               "sd_mw_cm2": round(statistics.pstdev(tail), 4) if len(tail) > 1 else 0.0 if tail else None,
                               "n": len(tail), "dwell_s": round(time.monotonic() - t_step, 1), "led_max_c": led_now})
        s["phase"] = "tail"; s["intensity"] = 0
        _hw.set_uv(False)
        hold(cfg["tail"], "tail", 0, False)
        s["aborted"] = _abort.is_set()
        s["status"] = "ABORTED" if s["aborted"] else ("ERROR" if s["error"] else ("OK" if len(s["steps"]) == len(cfg["steps"]) and all(st["mean_mw_cm2"] is not None for st in s["steps"]) else "INCOMPLETE"))
    except Exception as e:  # noqa: BLE001
        s["error"] = str(e)[:300]; s["status"] = "ERROR"
    finally:
        try:
            _hw.set_uv(False)
        except Exception:  # noqa: BLE001
            pass
        if meter is not None:
            try: meter.close()
            except Exception: pass  # noqa: BLE001
        s["phase"] = "done"; s["running"] = False; s["finished"] = time.time(); s["elapsed"] = round(time.monotonic() - t0, 1)


@bp.route("/api/dvt/uv-sweep", methods=["POST"])
def sweep_start():
    global _state
    if _hw is None:
        return jsonify({"ok": False, "message": "hardware controller not configured"})
    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "message": "a sweep is already running"})
        try:
            wl = int(request.args.get("wavelength", 405))
            steps = [int(x) for x in (request.args.get("steps") or ",".join(map(str, DEFAULT_STEPS))).split(",") if x.strip()]
            cfg = {"wavelength": wl, "steps": steps, "dwell": float(request.args.get("dwell", 10)), "baseline": float(request.args.get("baseline", 5)),
                   "settle": float(request.args.get("settle", 5)), "tail": float(request.args.get("tail", 3)), "hz": max(0.5, min(10.0, float(request.args.get("hz", 5))))}
        except ValueError as e:
            return jsonify({"ok": False, "message": f"bad parameter: {e}"})
        if wl not in (405, 450):
            return jsonify({"ok": False, "message": f"wavelength must be 405 or 450 (got {wl})"})
        if not steps or any(not 10 <= p <= 100 for p in steps):
            return jsonify({"ok": False, "message": "steps must be percentages between 10 and 100"})
        if cfg["settle"] > cfg["dwell"]:
            cfg["settle"] = cfg["dwell"]
        if _door_open():
            return jsonify({"ok": False, "message": "door open — close the door (the LEDs are interlocked)"})
        try:
            with _meter() as m:
                meter_wl = m.wavelength_nm(); ident = m.identify()
        except Exception as e:  # noqa: BLE001
            return jsonify({"ok": False, "message": f"StarBright not reachable: {e}"})
        force = request.args.get("force", "0") not in ("0", "false", "")
        if meter_wl != wl and not force:
            return jsonify({"ok": False, "code": "METER_WAVELENGTH", "meter_wavelength_nm": meter_wl,
                            "message": f"the StarBright is set to {meter_wl} nm but this test is at {wl} nm — set the meter to {wl} nm first (or force=1 to record it as unverified)"})
        _abort.clear()
        _state = {"running": True, "status": "RUNNING", "phase": "starting", "config": cfg, "samples": [], "steps": [], "error": None, "aborted": False,
                  "started": time.time(), "finished": None, "elapsed": 0.0, "step_index": None, "intensity": 0, "reading": None,
                  "meter": ident, "meter_wavelength_nm": meter_wl, "meter_wavelength_verified": meter_wl == wl}
        threading.Thread(target=_run, args=(cfg,), daemon=True, name="dvt-uv-sweep").start()
        return jsonify({"ok": True, "message": f"UV sweep started at {wl} nm: {steps} x {cfg['dwell']:g} s", "meter_wavelength_nm": meter_wl,
                        "meter_wavelength_verified": meter_wl == wl})


@bp.route("/api/dvt/uv-sweep", methods=["GET"])
def sweep_status():
    s = dict(_state)
    if request.args.get("samples", "1") in ("0", "false"):
        s["samples"] = []; s["n_samples"] = len(_state["samples"])
    return jsonify({"ok": True, **s})


@bp.route("/api/dvt/uv-sweep/abort", methods=["POST"])
def sweep_abort():
    if not _state["running"]:
        try:
            if _hw: _hw.set_uv(False)
        except Exception:  # noqa: BLE001
            pass
        return jsonify({"ok": True, "message": "no sweep running — LEDs off"})
    _abort.set()
    return jsonify({"ok": True, "message": "abort requested — LEDs go off"})


def linear_fit(points):
    """(slope, intercept, r2) of y over x — kept here so the sweep JSON can carry a first fit."""
    pts = [(x, y) for x, y in points if y is not None and not (isinstance(y, float) and math.isnan(y))]
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
