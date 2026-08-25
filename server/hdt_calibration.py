#!/usr/bin/env python3
"""
hdt_calibration.py - Material HDT calibration state machine (Developer Mode).

Determines the highest CALIBRATED SYSTEM LED POWER a material can take
without exceeding its HDT. The controller works exclusively at the
system-power level; the LED calibration layer (led_calibration.py, applied
inside hw.set_uv) translates each requested power into the four physical
Back/Door/Left/Right outputs — the four zones are never four separate test
powers.

Sequence: 10% → 90% in 10% steps. Per level: wait for thermal stabilization
(averaged CH1 temperature within STABILITY_BAND_C for STABILITY_TIME_MIN),
or NOT_CONVERGED after MAX_STABILIZATION_TIME_MIN. Reaching the material
HDT stops LED exposure and the whole sequence immediately.

Runs in its own daemon thread (the Flask UI thread only polls status()),
one temperature tick per SAMPLING_INTERVAL_SEC. Any loss of valid CH1
feedback (disconnect, NaN, stale, out-of-range), a user abort or an
internal error turns all LED zones OFF through the existing safe path
(hw.set_uv(False) → io_controller all_leds_off) and preserves all data
collected so far for partial reports.

State machine:
    IDLE → STARTING_CALIBRATION → [PREPARING_POWER_LEVEL →
    TESTING_POWER_LEVEL/WAITING_FOR_STABILITY]×9 →
    CALIBRATION_COMPLETE | HDT_LIMIT_REACHED | ABORTED | SENSOR_ERROR
"""

import csv
import io
import math
import threading
import time
from collections import deque
from datetime import datetime

import led_calibration
from dev_log import log_event

# --- configurable defaults (overridable per run via /api/dev/hdt/start) ----
SAMPLING_INTERVAL_SEC = 1.0
MOVING_AVERAGE_WINDOW_SEC = 10.0
STABILITY_BAND_C = 2.0
STABILITY_TIME_MIN = 5.0
# Second stability criterion: the averaged temperature's rate of change
# (linear-regression slope over the stability window) must not exceed this
# many degC per minute. 0 = disabled (band + time only).
STABILITY_MAX_RATE_C_PER_MIN = 0.5
MAX_STABILIZATION_TIME_MIN = 30.0
HDT_SAFETY_MARGIN_C = 2.0
# Thermal condition between levels: LEDs off, wait until the averaged
# temperature falls back to within this delta above the run baseline —
# or give up after COOLDOWN_MAX_WAIT_MIN and start the level anyway
# (its actual starting temperature is recorded either way).
NEXT_STEP_MAX_TEMP_DELTA_C = 8.0
COOLDOWN_MAX_WAIT_MIN = 15.0
POWER_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90]
HDT_WAVELENGTH = 405           # calibration runs on the 405 nm cure LEDs
# The chamber heater fan (FAN_HEATER) runs at this duty for the whole HDT
# run so the air around the model is mixed the same way as during a real
# cure; released back to 0% by _finish on every exit path.
HDT_HEATER_FAN_PWM = 100
# The heater-fan run-on that follows a heater OFF (temperature_control:
# 30% for cooldown_sec, then ALL fans OFF) must not override the HDT fan:
# the run-on is cancelled at start and the duty is re-commanded this often.
HEATER_FAN_REASSERT_SEC = 5.0

_OVERRIDE_KEYS = {
    'samplingIntervalSec': 'sampling_interval_sec',
    'movingAverageWindowSec': 'moving_average_window_sec',
    'stabilityBandC': 'stability_band_c',
    'stabilityTimeMin': 'stability_time_min',
    'stabilityMaxRateCPerMin': 'stability_max_rate_c_per_min',
    'maxStabilizationTimeMin': 'max_stabilization_time_min',
    'nextStepMaxTempDeltaC': 'next_step_max_temp_delta_c',
    'cooldownMaxWaitMin': 'cooldown_max_wait_min',
}


def _slope_c_per_min(window):
    """Least-squares slope (degC/min) of (monotonic_sec, avg) samples."""
    n = len(window)
    if n < 2:
        return None
    t0 = window[0][0]
    xs = [(t - t0) / 60.0 for t, _ in window]
    ys = [v for _, v in window]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


class _Abort(Exception): pass
class _SensorError(Exception): pass
class _HdtLimit(Exception): pass


class HdtCalibrationController:
    def __init__(self, hw, tc08):
        self.hw = hw               # HardwareController (real bridge or simulation)
        self.tc08 = tc08           # Tc08Manager
        self._lock = threading.Lock()
        self._thread = None
        self._abort_evt = threading.Event()
        self._reset_state()

    # ------------------------------------------------------------------
    #  Public API (called from Flask threads)
    # ------------------------------------------------------------------
    def start(self, hdt_c, safety_margin_c=None, overrides=None):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False, 'HDT calibration already running'
        try:
            hdt_c = float(hdt_c)
            if not (30.0 <= hdt_c <= 200.0):
                return False, f'Invalid material HDT {hdt_c} (30-200degC)'
        except (TypeError, ValueError):
            return False, 'Invalid material HDT'
        st = self.tc08.status()
        if not st['ch1Available']:
            return False, ('PicoLog TC-08 CH1 has no valid temperature - '
                           + (st['error'] or 'not connected'))
        try:
            hw_state = self.hw.get_state()
            if hw_state.get('uvOn') or hw_state.get('isHeating') or hw_state.get('isCooling'):
                return False, 'A cure process is active - stop it before HDT calibration'
        except Exception:  # noqa: BLE001 - state read is advisory here
            pass
        with self._lock:
            self._reset_state()
            self.hdt_c = hdt_c
            self.safety_margin_c = (float(safety_margin_c)
                                    if safety_margin_c is not None
                                    else HDT_SAFETY_MARGIN_C)
            for key, attr in _OVERRIDE_KEYS.items():
                if overrides and overrides.get(key) is not None:
                    setattr(self, attr, float(overrides[key]))
            self.state = 'STARTING_CALIBRATION'
            self.message = 'Starting calibration'
            self.started_at = datetime.now()
            self._abort_evt.clear()
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name='hdt-calibration')
            self._thread.start()
        log_event('HDT calibration started',
                  {'hdtC': hdt_c, 'safetyMarginC': self.safety_margin_c,
                   'factors': led_calibration.get_factors()})
        return True, None

    def abort(self):
        """User abort: LEDs off immediately, data preserved."""
        self._abort_evt.set()
        # The worker turns the LEDs off itself on the next tick (<1 s), but
        # for a hard guarantee force the safe state right away too.
        try:
            self.hw.set_uv(False)
        except Exception:  # noqa: BLE001
            pass
        return True

    def reset(self):
        """Clear a FINISHED run back to IDLE (refused while running)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._reset_state()
        return True

    def status(self, samples_from=None):
        with self._lock:
            now = time.monotonic()
            step_elapsed = (now - self._step_t0) if self._step_t0 else 0
            total_elapsed = ((now - self._t0) if self._t0 and self.running
                             else self._total_elapsed)
            out = {
                'state': self.state,
                'running': self.running,
                'finalStatus': self.final_status,
                'message': self.message,
                'hdtC': self.hdt_c,
                'safetyMarginC': self.safety_margin_c,
                'currentPower': self.current_power,
                'stepIndex': self.step_index,
                'totalSteps': len(POWER_LEVELS),
                'rawTemp': self._last_raw,
                'rateCPerMin': self._last_rate,
                'avgTemp': self._last_avg,
                'stepElapsedSec': round(step_elapsed, 1),
                'totalElapsedSec': round(total_elapsed, 1),
                'startedAt': self.started_at.isoformat() if self.started_at else None,
                'endedAt': self.ended_at.isoformat() if self.ended_at else None,
                'picolog': self.tc08.status(),
                'factors': led_calibration.get_factors(),
                'outputs': led_calibration.scaled_outputs(self.current_power or 0),
                'results': [dict(r) for r in self.results],
                'recommendedPower': self.recommended_power,
                'maxMeasuredTemp': self.max_measured_temp,
                'heaterFanPwm': self.heater_fan_pwm,
                'config': {
                    'samplingIntervalSec': self.sampling_interval_sec,
                    'movingAverageWindowSec': self.moving_average_window_sec,
                    'stabilityBandC': self.stability_band_c,
                    'stabilityTimeMin': self.stability_time_min,
                    'stabilityMaxRateCPerMin': self.stability_max_rate_c_per_min,
                    'maxStabilizationTimeMin': self.max_stabilization_time_min,
                    'hdtSafetyMarginC': self.safety_margin_c,
                    'nextStepMaxTempDeltaC': self.next_step_max_temp_delta_c,
                    'powerLevels': list(POWER_LEVELS),
                },
                'sampleCount': len(self.samples),
            }
            if samples_from is not None:
                out['samples'] = [
                    {k: s[k] for k in ('t', 'raw', 'avg', 'power', 'step')}
                    for s in self.samples[max(0, int(samples_from)):]
                ]
            return out

    # ------------------------------------------------------------------
    #  Internals
    # ------------------------------------------------------------------
    def _reset_state(self):
        self.state = 'IDLE'
        self.message = 'Idle'
        self.running = False
        self.heater_fan_pwm = 0
        self._last_rate = None
        self._fan_asserted_at = 0.0
        self.final_status = None
        self.hdt_c = None
        self.safety_margin_c = HDT_SAFETY_MARGIN_C
        self.sampling_interval_sec = SAMPLING_INTERVAL_SEC
        self.moving_average_window_sec = MOVING_AVERAGE_WINDOW_SEC
        self.stability_band_c = STABILITY_BAND_C
        self.stability_time_min = STABILITY_TIME_MIN
        self.stability_max_rate_c_per_min = STABILITY_MAX_RATE_C_PER_MIN
        self.max_stabilization_time_min = MAX_STABILIZATION_TIME_MIN
        self.next_step_max_temp_delta_c = NEXT_STEP_MAX_TEMP_DELTA_C
        self.cooldown_max_wait_min = COOLDOWN_MAX_WAIT_MIN
        self.current_power = None
        self.step_index = -1
        self.samples = []
        self.results = []
        self.recommended_power = None
        self.max_measured_temp = None
        self.started_at = None
        self.ended_at = None
        self.factors = None
        self._t0 = None
        self._step_t0 = None
        self._total_elapsed = 0.0
        self._last_raw = None
        self._last_avg = None
        self._avg_window = None
        self._baseline = None

    def _leds_off(self):
        """All four LED zones to the existing OFF/safe state."""
        try:
            self.hw.set_uv(False)
        except Exception as e:  # noqa: BLE001 - must never mask the stop reason
            print(f'[HDT] LED OFF command failed: {e}', flush=True)
        with self._lock:
            self.current_power = 0

    def _heater_fan(self, pwm, quiet=False):
        """Chamber heater fan (FAN_HEATER) duty for the HDT run. A non-zero
        duty first cancels any pending heater-fan run-on (whose end would
        switch every fan off under us) and is then (re)commanded."""
        try:
            if pwm > 0:
                cancel = getattr(self.hw, 'cancel_heater_fan_cooldown', None)
                if cancel:
                    cancel()                      # ends with all-fans-off: re-command below
            ok, why = self.hw.set_fan_speed('chamber_heating', pwm)
        except Exception as e:  # noqa: BLE001 - the fan must never stop a run/stop
            ok, why = False, str(e)
        with self._lock:
            self.heater_fan_pwm = pwm if ok else 0
            self._fan_asserted_at = time.monotonic()
        if not quiet or not ok:
            log_event('HDT heater fan', {'pwm': pwm, 'ok': bool(ok), 'why': why})
        if not ok:
            print(f'[HDT] heater fan {pwm}% refused: {why}', flush=True)

    def _reassert_heater_fan(self):
        """Keep FAN_HEATER at HDT_HEATER_FAN_PWM for the whole run even if
        something else (heater-off run-on, its all-fans-off) wrote the PCA."""
        if time.monotonic() - self._fan_asserted_at >= HEATER_FAN_REASSERT_SEC:
            self._heater_fan(HDT_HEATER_FAN_PWM, quiet=True)

    def _set_power(self, power):
        """One logical calibrated system power → four physical zones, via the
        central calibration layer inside hw.set_uv."""
        if power <= 0:
            self._leds_off()
            return
        ok, why = self.hw.set_uv(True, power, HDT_WAVELENGTH)
        if not ok:
            raise _SensorError(f'LED command refused: {why}')
        with self._lock:
            self.current_power = power
        log_event('Requested system LED power changed',
                  {'power': power,
                   'outputs': led_calibration.scaled_outputs(power, self.factors)})

    def _tick(self):
        """One sampling tick: sleep, read CH1, update the moving average,
        record the sample, and enforce abort / sensor validity / HDT limit."""
        if self._abort_evt.wait(self.sampling_interval_sec):
            raise _Abort()
        self._reassert_heater_fan()
        st = self.tc08.status()
        raw = st['temperature']
        if raw is None or not math.isfinite(raw):
            raise _SensorError(st['error'] or 'invalid CH1 temperature')
        self._avg_window.append(raw)
        avg = sum(self._avg_window) / len(self._avg_window)
        with self._lock:
            self._last_raw = round(raw, 2)
            self._last_avg = round(avg, 2)
            if self.max_measured_temp is None or raw > self.max_measured_temp:
                self.max_measured_temp = round(raw, 2)
            self.samples.append({
                't': round(time.monotonic() - self._t0, 1),
                'ts': datetime.now().isoformat(timespec='seconds'),
                'raw': round(raw, 2),
                'avg': round(avg, 2),
                'power': self.current_power or 0,
                'step': self.step_index,
                'state': self.state,
                'outputs': led_calibration.scaled_outputs(self.current_power or 0,
                                                          self.factors),
            })
        if avg >= self.hdt_c:
            raise _HdtLimit()
        return avg

    def _run(self):
        try:
            self._t0 = time.monotonic()
            self.factors = led_calibration.get_factors()
            n_avg = max(1, int(round(self.moving_average_window_sec
                                     / self.sampling_interval_sec)))
            self._avg_window = deque(maxlen=n_avg)
            with self._lock:
                self.running = True
            self._heater_fan(HDT_HEATER_FAN_PWM)
            with self._lock:
                self.results = [{
                    'power': p, 'status': 'NOT_TESTED',
                    'startTemp': None, 'stableTemp': None,
                    'minTemp': None, 'maxTemp': None,
                    'timeToStabilitySec': None, 'durationSec': None,
                    'rateCPerMin': None,
                    'startedAt': None, 'endedAt': None,
                    'outputs': led_calibration.scaled_outputs(p, self.factors),
                } for p in POWER_LEVELS]
            # a couple of ticks to seed the moving average / baseline
            for _ in range(3):
                baseline = self._tick()
            self._baseline = baseline
            for i, power in enumerate(POWER_LEVELS):
                with self._lock:
                    self.step_index = i
                self._prepare_level(i, power)
                self._test_level(i, power)
            self._finish('CALIBRATION_COMPLETE', None)
        except _Abort:
            self._leds_off()
            self._mark_current_step('ABORTED')
            self._finish('ABORTED', 'ABORTED_BY_USER')
            log_event('HDT calibration aborted')
        except _HdtLimit:
            self._leds_off()
            self._mark_current_step('HDT_LIMIT')
            self._finish('HDT_LIMIT_REACHED', 'HDT_LIMIT_REACHED')
            log_event('HDT threshold reached',
                      {'power': self.current_power, 'avgTemp': self._last_avg})
        except _SensorError as e:
            self._leds_off()
            self._mark_current_step('ABORTED')
            self._finish('SENSOR_ERROR', 'SENSOR_ERROR', str(e))
            log_event('Sensor error', {'reason': str(e)})
        except Exception as e:  # noqa: BLE001 - ANY internal error → safe stop
            self._leds_off()
            self._mark_current_step('ABORTED')
            self._finish('SENSOR_ERROR', 'SENSOR_ERROR', f'internal error: {e}')
            log_event('Sensor error', {'reason': f'internal error: {e}'})

    def _prepare_level(self, i, power):
        """Thermal condition between levels: LEDs off until the model has
        cooled back near the baseline (or the cooldown wait times out)."""
        if i == 0:
            return
        self._leds_off()
        limit = self._baseline + self.next_step_max_temp_delta_c
        deadline = time.monotonic() + self.cooldown_max_wait_min * 60
        with self._lock:
            self.state = 'PREPARING_POWER_LEVEL'
            self.message = (f'Cooling toward {limit:.1f}degC before the '
                            f'{power}% level')
            self._step_t0 = time.monotonic()
        while True:
            avg = self._tick()
            if avg <= limit:
                return
            if time.monotonic() >= deadline:
                log_event('HDT cooldown wait timed out',
                          {'nextPower': power, 'avgTemp': avg})
                return

    def _test_level(self, i, power):
        step_start_mono = time.monotonic()
        min_t = max_t = None
        with self._lock:
            r = self.results[i]
            r['status'] = 'RUNNING'
            r['startTemp'] = self._last_avg
            r['startedAt'] = datetime.now().isoformat(timespec='seconds')
            self.state = 'TESTING_POWER_LEVEL'
            self.message = f'Applying {power}% calibrated system power'
            self._step_t0 = step_start_mono
        log_event('HDT power level started',
                  {'power': power, 'startTemp': self._last_avg})
        try:
            self._set_power(power)
            with self._lock:
                self.state = 'WAITING_FOR_STABILITY'
                self._last_rate = None
                self.message = 'Waiting for thermal stabilization'
            window = deque()          # (mono_time, avg) inside the stability window
            need_sec = self.stability_time_min * 60
            max_sec = self.max_stabilization_time_min * 60
            while True:
                avg = self._tick()
                now = time.monotonic()
                window.append((now, avg))
                # keep one extra sample beyond the window so the oldest entry
                # can actually reach full need_sec coverage (ticks run at
                # sampling_interval + processing time, never exactly 1.0 s)
                while window and now - window[0][0] > need_sec + self.sampling_interval_sec:
                    window.popleft()
                if min_t is None or avg < min_t: min_t = avg
                if max_t is None or avg > max_t: max_t = avg
                covered = window and (now - window[0][0]) >= need_sec \
                    and (now - step_start_mono) >= need_sec
                rate = _slope_c_per_min(window)
                with self._lock:
                    self._last_rate = rate
                if covered:
                    vals = [v for _, v in window]
                    rate_ok = (self.stability_max_rate_c_per_min <= 0
                               or (rate is not None
                                   and abs(rate) <= self.stability_max_rate_c_per_min))
                    if max(vals) - min(vals) <= self.stability_band_c and rate_ok:
                        stable = sum(vals) / len(vals)
                        with self._lock:
                            r = self.results[i]
                            r['status'] = 'PASS'
                            r['stableTemp'] = round(stable, 2)
                            r['minTemp'] = round(min(vals), 2)
                            r['maxTemp'] = round(max(vals), 2)
                            r['timeToStabilitySec'] = round(now - step_start_mono, 1)
                            r['rateCPerMin'] = round(rate, 3) if rate is not None else None
                            r['durationSec'] = round(now - step_start_mono, 1)
                            r['endedAt'] = datetime.now().isoformat(timespec='seconds')
                            self.state = 'STABLE'
                            self.message = f'{power}% stable at {stable:.1f}degC'
                        log_event('Thermal stabilization detected',
                                  {'power': power, 'stableTemp': round(stable, 2),
                                   'timeToStabilitySec': round(now - step_start_mono, 1)})
                        return
                if now - step_start_mono >= max_sec:
                    with self._lock:
                        r = self.results[i]
                        r['status'] = 'NOT_CONVERGED'
                        r['minTemp'] = round(min_t, 2) if min_t is not None else None
                        r['maxTemp'] = round(max_t, 2) if max_t is not None else None
                        r['durationSec'] = round(now - step_start_mono, 1)
                        r['endedAt'] = datetime.now().isoformat(timespec='seconds')
                        self.state = 'NOT_CONVERGED'
                        self.message = (f'{power}% did not converge within '
                                        f'{self.max_stabilization_time_min:.0f} min')
                    log_event('Power level not converged',
                              {'power': power, 'lastAvg': self._last_avg,
                               'maxTemp': max_t})
                    return
        finally:
            # step bookkeeping that must survive aborts/errors mid-step
            with self._lock:
                r = self.results[i]
                if r['durationSec'] is None:
                    r['durationSec'] = round(time.monotonic() - step_start_mono, 1)
                if r['endedAt'] is None:
                    r['endedAt'] = datetime.now().isoformat(timespec='seconds')
                if r['maxTemp'] is None and max_t is not None:
                    r['maxTemp'] = round(max_t, 2)

    def _mark_current_step(self, status):
        with self._lock:
            if 0 <= self.step_index < len(self.results):
                r = self.results[self.step_index]
                if r['status'] in ('RUNNING', 'NOT_TESTED'):
                    r['status'] = status

    def _finish(self, state, final_status, message=None):
        self._leds_off()
        self._heater_fan(0)
        with self._lock:
            limit = (self.hdt_c - self.safety_margin_c) if self.hdt_c else None
            rec = None
            for r in self.results:
                if (r['status'] == 'PASS' and limit is not None
                        and r['stableTemp'] is not None
                        and r['stableTemp'] <= limit):
                    rec = r['power']
            self.recommended_power = rec
            if final_status is None:
                tested = [r for r in self.results if r['status'] != 'NOT_TESTED']
                final_status = ('NOT_CONVERGED'
                                if tested and all(r['status'] == 'NOT_CONVERGED'
                                                  for r in tested)
                                else 'COMPLETED')
            self.final_status = final_status
            self.state = state
            self.running = False
            self.ended_at = datetime.now()
            self._step_t0 = None
            self._total_elapsed = time.monotonic() - self._t0 if self._t0 else 0
            self.message = message or f'Calibration finished: {final_status}'
        log_event('HDT calibration completed',
                  {'status': final_status, 'recommendedPower': rec,
                   'maxMeasuredTemp': self.max_measured_temp})

    # ------------------------------------------------------------------
    #  CSV report (full or partial - all raw measurements)
    # ------------------------------------------------------------------
    def csv_report(self):
        with self._lock:
            samples = [dict(s) for s in self.samples]
            results = [dict(r) for r in self.results]
            factors = self.factors or led_calibration.get_factors()
            hdt_c, margin = self.hdt_c, self.safety_margin_c
            final = self.final_status or self.state
            meta = {
                'started': self.started_at.isoformat() if self.started_at else '',
                'ended': self.ended_at.isoformat() if self.ended_at else '',
                'recommendedPower': self.recommended_power,
                'maxMeasuredTemp': self.max_measured_temp,
                'device': (self.tc08.status().get('deviceInfo') or 'PicoLog TC-08'),
            }
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(['# sCure Material HDT Calibration Report'])
        w.writerow(['# Started', meta['started']])
        w.writerow(['# Ended', meta['ended']])
        w.writerow(['# Device', meta['device'], 'Channel', 'CH1'])
        w.writerow(['# Material HDT degC', hdt_c, 'Safety Margin degC', margin])
        w.writerow(['# Final Status', final])
        w.writerow(['# Recommended System LED Power %', meta['recommendedPower']])
        w.writerow(['# Max Measured Temp degC', meta['maxMeasuredTemp']])
        w.writerow([])
        w.writerow(['# Per-level results'])
        w.writerow(['System Power %', 'Status', 'Start Temp degC', 'Stable Temp degC',
                    'Min Temp degC', 'Max Temp degC', 'Time To Stability s',
                    'Duration s', 'Started', 'Ended',
                    'Back Output %', 'Door Output %', 'Left Output %', 'Right Output %'])
        for r in results:
            o = r.get('outputs') or {}
            w.writerow([r['power'], r['status'], r['startTemp'], r['stableTemp'],
                        r['minTemp'], r['maxTemp'], r['timeToStabilitySec'],
                        r['durationSec'], r['startedAt'], r['endedAt'],
                        o.get('back'), o.get('door'), o.get('left'), o.get('right')])
        w.writerow([])
        w.writerow(['Timestamp', 'Elapsed Time s', 'Test Step',
                    'Requested System LED Power %',
                    'Back LED Factor', 'Door LED Factor',
                    'Left LED Factor', 'Right LED Factor',
                    'Actual Back LED Output %', 'Actual Door LED Output %',
                    'Actual Left LED Output %', 'Actual Right LED Output %',
                    'Raw CH1 Temperature degC', 'Average Temperature degC',
                    'Material HDT degC', 'HDT Safety Margin degC',
                    'Stability Status', 'Test Status'])
        for s in samples:
            step = s.get('step', -1)
            test_status = (results[step]['status']
                           if 0 <= step < len(results) else '')
            o = s.get('outputs') or {}
            w.writerow([s.get('ts'), s['t'], step + 1 if step >= 0 else '',
                        s['power'],
                        factors['back'], factors['door'],
                        factors['left'], factors['right'],
                        o.get('back'), o.get('door'), o.get('left'), o.get('right'),
                        s['raw'], s['avg'], hdt_c, margin,
                        s.get('state', ''), test_status])
        return buf.getvalue()
