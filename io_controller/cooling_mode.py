#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cooling_mode.py - closed-loop cooling-rate control for the CureBox chamber.

Separate logic module on top of io_controller: it owns NO hardware of its own.
Every component is driven ONLY through the existing verified IO activation
functions (PCA9685.set_duty_verified, Servo.goto) on the shared IOController,
serialized by the shared I2C lock.

Mode sequence (per the cooling requirement):
  1. Entry precondition: damper OPEN (servo) + heater fan fixed at 100% PWM
     for the whole mode.
  2. Chamber fan under PI control: the measured chamber dT/dt (C/min, from a
     sliding-window least-squares slope of TEMP_CHAMBER) tracks the user
     setpoint (0-5 C/min). The setpoint can be updated while running.
  3. End of process (target reached / stop / fault): ALL fans OFF, damper
     CLOSED (fans auto-driven by LEDs still on are left running).

All tuning lives in the "cooling" section of components.json (re-read on every
activation). Used via SystemController.start_cooling / set_cooling_rate /
stop_cooling / cooling_status, by the dashboard and the io_controller CLI.

Standalone run (blocking; Ctrl+C stops safely):
    python3 cooling_mode.py <rate C/min> [--target T]
    python3 cooling_mode.py 2 --target 30    # cool at 2 C/min down to 30 C
"""

import threading
import time

from io_controller import (LOG, PCA_CHANNELS, PCA_FANS, VerificationError,
                           load_component_config)

COOLING_DEFAULTS = {
    "damper_open_angle": 180, "damper_closed_angle": 0,
    "heater_fan": "FAN_HEATER", "heater_fan_pwm": 100,
    "chamber_fan": "FAN_COOLING",
    "thermistor": "TEMP_CHAMBER",
    "temp_valid_min": -20, "temp_valid_max": 120,
    "rate_min": 0.0, "rate_max": 5.0, "target_temp": 25.0,
    "sample_sec": 2.0, "window_sec": 30.0,
    "kp": 25.0, "ki": 2.0, "pwm_start": 50.0,
    "pwm_min": 0.0, "pwm_max": 100.0,
}


class CoolingController:
    """Closed-loop cooling mode. Drives the damper + fans exclusively through
    the SystemController's IOController verified activation functions."""

    def __init__(self, sysctl):
        self.sys = sysctl                # SystemController: io, lock, thermistor, heater state
        self.active = False
        self.fault = None
        self._state = {}                 # live loop status (setpoint/measured/pwm/...)
        self._stop = threading.Event()
        self._thread = None

    def cfg(self):
        """Re-read the cooling section fresh each call so config edits take effect."""
        c = dict(COOLING_DEFAULTS)
        try:
            file_cfg = load_component_config().get("cooling", {})
        except Exception:                # noqa: BLE001
            file_cfg = self.sys.config.get("cooling", {})
        c.update({k: v for k, v in file_cfg.items() if not k.startswith("_")})
        return c

    def _set_damper(self, open_, cfg=None):
        """Drive the damper (servo) to its configured open/closed angle."""
        cfg = cfg or self.cfg()
        angle = cfg["damper_open_angle"] if open_ else cfg["damper_closed_angle"]
        with self.sys.lock:
            self.sys.io.servo.goto(angle)
        LOG.info("damper -> %s (%g deg)", "OPEN" if open_ else "CLOSED", angle)

    def start(self, rate, target_temp=None):
        """Enter cooling mode. Precondition sequence first (damper OPEN, heater
        fan at heater_fan_pwm for the whole mode), then the chamber fan starts
        under closed-loop control toward `rate` (C/min, clamped to the config
        range). Returns (ok, reason)."""
        if self._thread and self._thread.is_alive():
            self.set_rate(rate)                   # already running: update setpoint
            if target_temp is not None:
                self._state["target"] = float(target_temp)
            return True, None
        self.fault = None
        cfg = self.cfg()
        if self.sys.heater_on:                    # never heat and cool together
            self.sys.disable_heater("user")
            LOG.info("cooling mode: heater forced OFF")
        ok_t, t, why = self.sys._thermistor_state(cfg)
        if not ok_t:                              # need a valid dT/dt source
            self.fault = why
            return False, why
        rate = max(cfg["rate_min"], min(cfg["rate_max"], float(rate)))
        target = float(cfg["target_temp"] if target_temp is None else target_temp)
        try:                                      # 1. open the damper
            self._set_damper(True, cfg)
        except Exception as e:                    # noqa: BLE001 - servo unavailable
            self.fault = f"damper open failed: {e}"
            return False, self.fault
        try:                                      # 2. heater fan fixed, 3. chamber fan starts
            with self.sys.lock:
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["heater_fan"]],
                                                  cfg["heater_fan_pwm"])
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["chamber_fan"]],
                                                  cfg["pwm_start"])
        except VerificationError as e:
            self.fault = str(e)
            self._exit_outputs(cfg)
            return False, self.fault
        self._state = {"rate_set": rate, "rate_meas": None,
                       "pwm": float(cfg["pwm_start"]), "target": target, "temp": t,
                       "limited": False, "chamber_fan": cfg["chamber_fan"],
                       "heater_fan": cfg["heater_fan"],
                       "heater_fan_pwm": cfg["heater_fan_pwm"]}
        self._stop.clear()
        self.active = True
        self._thread = threading.Thread(target=self._loop, args=(cfg,), daemon=True)
        self._thread.start()
        LOG.info("COOLING ON (rate=%.2f C/min, target=%.1f C, chamber=%.1f C, "
                 "%s fixed %g%%, %s PI-controlled)", rate, target, t,
                 cfg["heater_fan"], cfg["heater_fan_pwm"], cfg["chamber_fan"])
        return True, None

    def set_rate(self, rate):
        """Update the cooling-rate setpoint (C/min) while the mode is running."""
        cfg = self.cfg()
        rate = max(cfg["rate_min"], min(cfg["rate_max"], float(rate)))
        self._state["rate_set"] = rate
        LOG.info("cooling rate setpoint -> %.2f C/min", rate)
        return rate

    @staticmethod
    def _slope_c_per_min(samples):
        """Least-squares dT/dt over (monotonic_time, temp) samples.
        Returns the COOLING rate in C/min (positive while cooling), or None."""
        if len(samples) < 3 or samples[-1][0] - samples[0][0] < 10.0:
            return None                           # not enough data for a stable slope
        t0 = samples[0][0]
        xs = [s[0] - t0 for s in samples]
        ys = [s[1] for s in samples]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        den = sum((x - mx) ** 2 for x in xs)
        if den <= 0:
            return None
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den   # C/sec
        return -slope * 60.0

    def _loop(self, cfg):
        """PI loop: drive the chamber-fan PWM so measured dT/dt tracks the setpoint."""
        samples = []
        ki = cfg["ki"]
        integ = (cfg["pwm_start"] / ki) if ki > 0 else 0.0   # bumpless start at pwm_start
        last = time.monotonic()
        while not self._stop.wait(cfg["sample_sec"]):
            ok_t, t, why = self.sys._thermistor_state(cfg)
            if not ok_t:
                self._finish(why)
                return
            now = time.monotonic()
            dt, last = now - last, now
            self._state["temp"] = t
            if t <= self._state["target"]:        # reached target -> auto-terminate
                self._finish(None)
                return
            samples.append((now, t))
            while samples and now - samples[0][0] > cfg["window_sec"]:
                samples.pop(0)
            rate_meas = self._slope_c_per_min(samples)
            self._state["rate_meas"] = rate_meas
            if rate_meas is None:                 # window still filling up
                continue
            err = self._state["rate_set"] - rate_meas   # >0: cooling too slowly -> more fan
            integ += err * dt
            if ki > 0:                            # anti-windup: keep integral inside PWM range
                integ = max(cfg["pwm_min"] / ki, min(cfg["pwm_max"] / ki, integ))
            pwm = max(cfg["pwm_min"], min(cfg["pwm_max"], cfg["kp"] * err + ki * integ))
            self._state["pwm"] = pwm
            self._state["limited"] = pwm >= cfg["pwm_max"] - 1e-6 and err > 0.1
            try:
                with self.sys.lock:
                    self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["chamber_fan"]], pwm)
            except Exception as e:                # noqa: BLE001
                self._finish(f"chamber fan not confirmed: {e}")
                return

    def _exit_outputs(self, cfg):
        """End of process: ALL fans OFF (verified), damper CLOSED. Fans
        auto-driven by LEDs that are still on are left running (LED cooling)."""
        keep = set()
        try:
            for led in getattr(self.sys, "_leds_on", set()):
                fan = self.sys.leds.get(led, {}).get("fan")
                if fan:
                    keep.add(fan)
        except Exception:                # noqa: BLE001
            pass
        for fan in PCA_FANS:
            if fan in keep:
                continue
            try:
                with self.sys.lock:
                    self.sys.io.pca.set_duty_verified(PCA_CHANNELS[fan], 0)
            except Exception:            # noqa: BLE001 - keep going, close the rest
                pass
        try:
            self._set_damper(False, cfg)
        except Exception:                # noqa: BLE001 - servo unavailable
            pass
        LOG.info("end of cooling process: all fans OFF, damper CLOSED%s",
                 f" (kept LED fans: {', '.join(sorted(keep))})" if keep else "")

    def _finish(self, fault):
        """End the mode (from the loop or stop()): outputs safe + state."""
        self._stop.set()
        self._exit_outputs(self.cfg())
        was_on = self.active
        self.active = False
        if fault:
            self.fault = fault
            LOG.error("COOLING OFF - fault: %s", fault)
        elif was_on:
            t = self._state.get("temp")
            LOG.info("COOLING OFF (chamber %s C, target %s C)",
                     f"{t:.1f}" if t is not None else "?", self._state.get("target"))

    def stop(self, reason="user"):
        """Stop cooling mode: fans off, damper closed. Safe to call anytime."""
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=10)
        if self.active:                           # loop exited without finishing
            self._finish(None if reason == "user" else reason)

    def status(self):
        """Live status dict: active, rate_set/rate_meas (C/min), pwm, temp,
        target, limited (setpoint not physically achievable), fault."""
        s = dict(self._state)
        s["active"] = self.active
        s["fault"] = self.fault
        return s

    def close(self):
        self._stop.set()                          # end the loop; no hardware writes


# ===========================================================================
#  Standalone CLI - `python3 cooling_mode.py <rate> [--target T]`
#  (io_controller.py `cooling run` delegates here too)
# ===========================================================================
def run_cli(rate, target=None):
    """Blocking cooling run with a live status printout. Ctrl+C stops safely
    (fans off, damper closed)."""
    from io_controller import SystemController
    sysctl = SystemController(config=load_component_config())
    try:
        ok, why = sysctl.start_cooling(rate, target)
        if not ok:
            raise SystemExit(f"cooling blocked: {why}")
        s = sysctl.cooling_status()
        print(f"cooling mode ON: rate={s['rate_set']:.2f} C/min, "
              f"target={s['target']:.1f} C  (Ctrl+C to stop)\n")
        try:
            while sysctl.is_cooling_on():
                time.sleep(2.0)
                s = sysctl.cooling_status()
                meas = s.get("rate_meas")
                print(f"  chamber={s.get('temp'):.1f}C  "
                      f"rate={f'{meas:+.2f}' if meas is not None else '--'} C/min  "
                      f"(set {s['rate_set']:.2f})  fan={s.get('pwm', 0):.0f}%"
                      + ("  [rate not achievable]" if s.get("limited") else ""))
            fault = sysctl.cooling_status().get("fault")
            if fault:
                raise SystemExit(f"cooling fault: {fault}")
            print("\ntarget temperature reached - fans off, damper closed.")
        except KeyboardInterrupt:
            print("\nstopping cooling mode...")
    finally:
        sysctl.stop_cooling("user")
        sysctl.close()
        sysctl.io.close()


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        prog="cooling_mode.py",
        description="CureBox closed-loop cooling mode: damper open + heater fan "
                    "100%, chamber fan PI-controlled so the measured dT/dt "
                    "tracks the requested rate; auto-stops at the target "
                    "temperature (fans off, damper closed).")
    p.add_argument("rate", type=float, help="desired cooling rate in C/min (0-5)")
    p.add_argument("--target", type=float, default=None,
                   help="target temperature C (default from components.json)")
    args = p.parse_args(argv)
    run_cli(args.rate, args.target)


if __name__ == "__main__":
    main()
