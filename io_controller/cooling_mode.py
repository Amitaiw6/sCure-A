#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cooling_mode.py - fixed-fan cooling mode for the CureBox chamber.

Separate logic module on top of io_controller: it owns NO hardware of its own.
Every component is driven ONLY through the existing verified IO activation
functions (PCA9685.set_duty_verified, Servo.goto) on the shared IOController,
serialized by the shared I2C lock.

Mode sequence (per the cooling requirement):
  1. Entry precondition: damper OPEN (servo) + heater fan fixed at 100% PWM
     for the whole mode.
  2. Chamber fan at a FIXED duty for the whole mode. The UI cooling modes map
     to duties in server/io_bridge.py (components.json "cooling.mode_pwms"):
     fast=100%, medium=60%, slow=30%. The measured chamber dT/dt (C/min,
     sliding-window least-squares slope of TEMP_CHAMBER) is still computed,
     but only for status/telemetry - it never drives the fan.
  3. End of process (target reached / stop / fault): ALL fans OFF, damper
     CLOSED (fans auto-driven by LEDs still on are left running).

All tuning lives in the "cooling" section of components.json (re-read on every
activation). Used via SystemController.start_cooling / set_cooling_pwm /
stop_cooling / cooling_status, by the dashboard and the io_controller CLI.

Standalone run (blocking; Ctrl+C stops safely):
    python3 cooling_mode.py <fan %> [--target T]
    python3 cooling_mode.py 60 --target 30    # fan at 60% down to 30 C
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
    "target_temp": 25.0,
    "sample_sec": 1.0, "window_sec": 30.0,
    "pwm_min": 0.0, "pwm_max": 100.0,
}


class CoolingController:
    """Fixed-fan cooling mode. Drives the damper + fans exclusively through
    the SystemController's IOController verified activation functions."""

    def __init__(self, sysctl):
        self.sys = sysctl                # SystemController: io, lock, thermistor, heater state
        self.active = False
        self.fault = None
        self._state = {}                 # live loop status (pwm/measured/temp/...)
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

    def start(self, pwm, target_temp=None):
        """Enter cooling mode. Precondition sequence first (damper OPEN, heater
        fan at heater_fan_pwm for the whole mode), then the chamber fan runs at
        the FIXED duty `pwm` (%, clamped to [pwm_min, pwm_max]) until the
        chamber reaches the target temperature. Returns (ok, reason)."""
        if self._thread and self._thread.is_alive():
            ok, why = self.set_pwm(pwm)           # already running: update duty
            if ok and target_temp is not None:
                self._state["target"] = float(target_temp)
            return ok, why
        self.fault = None
        cfg = self.cfg()
        if self.sys.heater_on:                    # never heat and cool together
            self.sys.disable_heater("user")
            LOG.info("cooling mode: heater forced OFF")
        ok_t, t, why = self.sys._thermistor_state(cfg)
        if not ok_t:                              # need a valid temp for the auto-stop
            self.fault = why
            return False, why
        pwm = max(cfg["pwm_min"], min(cfg["pwm_max"], float(pwm)))
        target = float(cfg["target_temp"] if target_temp is None else target_temp)
        try:                                      # 1. open the damper
            self._set_damper(True, cfg)
        except Exception as e:                    # noqa: BLE001 - servo unavailable
            self.fault = f"damper open failed: {e}"
            return False, self.fault
        try:                                      # 2. heater fan fixed, 3. chamber fan fixed
            with self.sys.lock:
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["heater_fan"]],
                                                  cfg["heater_fan_pwm"])
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["chamber_fan"]],
                                                  pwm)
        except VerificationError as e:
            self.fault = str(e)
            self._exit_outputs(cfg)
            return False, self.fault
        self._state = {"pwm": float(pwm), "rate_meas": None,
                       "target": target, "temp": t,
                       "chamber_fan": cfg["chamber_fan"],
                       "heater_fan": cfg["heater_fan"],
                       "heater_fan_pwm": cfg["heater_fan_pwm"]}
        self._stop.clear()
        self.active = True
        self._thread = threading.Thread(target=self._loop, args=(cfg,), daemon=True)
        self._thread.start()
        LOG.info("COOLING ON (%s fixed %g%%, target=%.1f C, chamber=%.1f C, "
                 "%s fixed %g%%)", cfg["chamber_fan"], pwm, target, t,
                 cfg["heater_fan"], cfg["heater_fan_pwm"])
        return True, None

    def set_pwm(self, pwm):
        """Update the fixed chamber-fan duty (%) while the mode is running."""
        cfg = self.cfg()
        pwm = max(cfg["pwm_min"], min(cfg["pwm_max"], float(pwm)))
        try:
            with self.sys.lock:
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[cfg["chamber_fan"]], pwm)
        except Exception as e:                    # noqa: BLE001
            return False, f"chamber fan not confirmed: {e}"
        self._state["pwm"] = pwm
        LOG.info("cooling fan duty -> %g%%", pwm)
        return True, None

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
        """Monitor loop: sample the chamber temperature, keep the measured
        dT/dt for status/telemetry, auto-stop at the target temperature.
        The chamber-fan duty is FIXED - nothing in here drives it."""
        samples = []
        while not self._stop.wait(cfg["sample_sec"]):
            ok_t, t, why = self.sys._thermistor_state(cfg)
            if not ok_t:
                self._finish(why)
                return
            now = time.monotonic()
            self._state["temp"] = t
            if t <= self._state["target"]:        # reached target -> auto-terminate
                self._finish(None)
                return
            samples.append((now, t))
            while samples and now - samples[0][0] > cfg["window_sec"]:
                samples.pop(0)
            self._state["rate_meas"] = self._slope_c_per_min(samples)

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
        """Live status dict: active, pwm (fixed chamber-fan duty %),
        rate_meas (measured C/min, telemetry only), temp, target, fault."""
        s = dict(self._state)
        s["active"] = self.active
        s["fault"] = self.fault
        return s

    def close(self):
        self._stop.set()                          # end the loop; no hardware writes


# ===========================================================================
#  Standalone CLI - `python3 cooling_mode.py <fan %> [--target T]`
#  (io_controller.py `cooling run` delegates here too)
# ===========================================================================
def run_cli(pwm, target=None):
    """Blocking cooling run with a live status printout. Ctrl+C stops safely
    (fans off, damper closed)."""
    from io_controller import SystemController
    sysctl = SystemController(config=load_component_config())
    try:
        ok, why = sysctl.start_cooling(pwm, target)
        if not ok:
            raise SystemExit(f"cooling blocked: {why}")
        s = sysctl.cooling_status()
        print(f"cooling mode ON: fan={s['pwm']:.0f}%, "
              f"target={s['target']:.1f} C  (Ctrl+C to stop)\n")
        try:
            while sysctl.is_cooling_on():
                time.sleep(2.0)
                s = sysctl.cooling_status()
                meas = s.get("rate_meas")
                print(f"  chamber={s.get('temp'):.1f}C  "
                      f"rate={f'{meas:+.2f}' if meas is not None else '--'} C/min  "
                      f"fan={s.get('pwm', 0):.0f}%")
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
        description="CureBox cooling mode: damper open + heater fan 100%, "
                    "chamber fan at a FIXED duty for the whole mode; "
                    "auto-stops at the target temperature (fans off, damper "
                    "closed).")
    p.add_argument("pwm", type=float, help="chamber-fan duty in %% (0-100)")
    p.add_argument("--target", type=float, default=None,
                   help="target temperature C (default from components.json)")
    args = p.parse_args(argv)
    run_cli(args.pwm, args.target)


if __name__ == "__main__":
    main()
