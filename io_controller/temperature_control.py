#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temperature_control.py - closed-loop chamber HEATING for the CureBox.

Separate logic module on top of io_controller (mirror of cooling_mode.py): it
owns NO hardware of its own. The heater element and its fan are driven ONLY
through the existing verified IO functions on the shared IOController,
serialized by the shared I2C lock, and behind the existing heater safety
layer in SystemController.

Mode sequence (heating):
  1. Entry: SystemController.enable_heater() runs the full pre-flight - door
     closed, cooling mode off, heater fan (FAN_HEATER) started at the
     configured PWM and verified to actually spin (tachometer RPM), and the
     chamber thermistor reading valid. The heater is enabled only if ALL pass.
  2. PI(D) loop: the heater element is a real PWM channel (PWM_HEATER on the
     PCA9685), so the controller output drives its duty directly (0-100%) -
     no on/off delta-sigma needed. TEMP_CHAMBER tracks the target
     temperature; the heater fan stays on for the whole mode.
  3. Ongoing safety: the standard heater health check (fan RPM + thermistor)
     re-runs every health_check_sec, and the door interlock can force the
     heater off at any time - either ends the mode with a fault.
  4. Exit: heater element OFF immediately; the heater fan keeps running for
     'cooldown_sec' (default 10 min) to carry residual heat off the element.
     At the END of the process (cooldown done or skipped) ALL fans are turned
     OFF and the damper is CLOSED (fans auto-driven by LEDs still on are left
     running). Restarting heating cancels a pending cooldown.

All tuning lives in the "heating" section of components.json (re-read on every
activation, like the "cooling" section).

Standalone run (blocking; Ctrl+C stops safely):
    python3 temperature_control.py <target C>
    python3 temperature_control.py 60        # heat the chamber to 60 C
"""

import threading
import time

from io_controller import (LOG, PCA_CHANNELS, PCA_FANS, VerificationError,
                           load_component_config)

HEATING_DEFAULTS = {
    "target_temp": 60.0,
    "target_min": 30.0,  # lowest target temperature that can be entered (C)
    "sample_sec": 1.0,
    # Gains are in % duty (old 0-1 scale gains x100; old I was per-50ms cycle):
    "kp": 8.0,           # % duty per C of error          (was CTL_P = 0.08)
    "ki": 0.3,           # % duty per C*second of error   (was CTL_I = 0.00015)
    "kd": 0.0,           # % duty per C/second            (was CTL_D = 0.0)
    "integ_max": 85.0,   # cap on the integral term, % duty (was 0.85)
    "pwm_min": 0.0, "pwm_max": 100.0,
    "at_temp_band": 1.5,        # |error| below this -> "at temperature"
    "cooldown_sec": 600.0,      # fan run-on after heating stops (10 min)
    "cooldown_fan_pwm": 100,
}


class TemperatureController:
    """Closed-loop heating mode. Drives the heater element + heater fan
    exclusively through SystemController's safety layer and the IOController
    verified activation functions."""

    def __init__(self, sysctl):
        self.sys = sysctl                # SystemController: io, lock, heater safety
        self.active = False
        self.fault = None
        self._state = {}                 # live loop status (target/temp/pwm/...)
        self._stop = threading.Event()
        self._thread = None
        self._cooldown_cancel = threading.Event()
        self._cooldown_thread = None

    def cfg(self):
        """Re-read the heating section fresh each call so config edits take effect."""
        c = dict(HEATING_DEFAULTS)
        try:
            file_cfg = load_component_config().get("heating", {})
        except Exception:                # noqa: BLE001
            file_cfg = self.sys.config.get("heating", {})
        c.update({k: v for k, v in file_cfg.items() if not k.startswith("_")})
        return c

    # ------------------------------------------------------------------
    #  Start / setpoint
    # ------------------------------------------------------------------
    def start(self, target_temp=None):
        """Enter heating mode. enable_heater() runs the pre-flight (door, fan
        spin-up + RPM, thermistor) and turns the heater fan on; then the PI
        loop takes ownership of the heater PWM. Returns (ok, reason)."""
        if self._thread and self._thread.is_alive():
            if target_temp is not None:   # already running: update setpoint
                self.set_target(target_temp)
            return True, None
        self.fault = None
        cfg = self.cfg()
        hcfg = self.sys.heater_cfg()
        target = float(cfg["target_temp"] if target_temp is None else target_temp)
        if target < cfg["target_min"]:            # minimum enterable target temperature
            why = (f"target {target:.1f} C is below the minimum "
                   f"{cfg['target_min']:.0f} C")
            LOG.warning("HEATING blocked: %s", why)
            self.fault = why
            return False, why
        self._cancel_cooldown()                   # restarting during fan run-on
        ok, why = self.sys.enable_heater()        # full pre-flight + fan ON
        if not ok:
            self.fault = why
            return False, why
        try:                                      # PI owns the duty: ramp from 0
            with self.sys.lock:
                self.sys.io.pca.set_duty_verified(PCA_CHANNELS[hcfg["channel"]], 0)
        except VerificationError as e:
            self.fault = str(e)
            self.sys.disable_heater(self.fault)
            return False, self.fault
        self._state = {"target": target, "temp": None, "pwm": 0.0,
                       "at_temp": False, "fan": hcfg["fan"],
                       "fan_pwm": hcfg["fan_pwm"]}
        self._stop.clear()
        self.active = True
        self._thread = threading.Thread(target=self._loop, args=(cfg, hcfg),
                                        daemon=True)
        self._thread.start()
        LOG.info("HEATING ON (target=%.1f C, heater=%s PI-controlled, "
                 "fan %s fixed %g%%)", target, hcfg["channel"],
                 hcfg["fan"], hcfg["fan_pwm"])
        return True, None

    def set_target(self, temp_c):
        """Update the target temperature (C) while the mode is running.
        Values below the configured minimum (target_min) are clamped up."""
        lo = self.cfg()["target_min"]
        temp_c = float(temp_c)
        if temp_c < lo:
            LOG.warning("heating target %.1f C below minimum - clamped to %.0f C",
                        temp_c, lo)
            temp_c = lo
        self._state["target"] = temp_c
        LOG.info("heating target -> %.1f C", self._state["target"])
        return self._state["target"]

    # ------------------------------------------------------------------
    #  PI loop
    # ------------------------------------------------------------------
    def _loop(self, cfg, hcfg):
        """PI(D) loop: drive the heater PWM so TEMP_CHAMBER tracks the target.
        The heater fan is already on (enable_heater) and is re-verified by the
        periodic health check."""
        ki = cfg["ki"]
        integ = 0.0
        prev_err = None
        last = time.monotonic()
        health_period = max(1.0, float(hcfg.get("health_check_sec", 10)))
        next_health = last + health_period
        while not self._stop.wait(cfg["sample_sec"]):
            if not self.sys.heater_on:            # door interlock / external off
                self._finish(self.sys.heater_fault or "heater disabled externally")
                return
            now = time.monotonic()
            if now >= next_health:                # fan RPM + thermistor re-check
                next_health = now + health_period
                why = self.sys.heater_health_check()
                if why:
                    self._finish(why)
                    return
            ok_t, t, why = self.sys._thermistor_state(hcfg)
            if not ok_t:
                self._finish(why)
                return
            dt, last = now - last, now
            err = self._state["target"] - t
            integ += err * dt                     # anti-windup: 0..integ_max
            if ki > 0:
                integ = max(0.0, min(cfg["integ_max"] / ki, integ))
            deriv = (err - prev_err) / dt if (prev_err is not None and dt > 0) else 0.0
            prev_err = err
            pwm = max(cfg["pwm_min"], min(cfg["pwm_max"],
                      cfg["kp"] * err + ki * integ + cfg["kd"] * deriv))
            self._state.update(temp=t, pwm=pwm,
                               at_temp=abs(err) <= cfg["at_temp_band"])
            try:
                with self.sys.lock:
                    self.sys.io.pca.set_duty_verified(PCA_CHANNELS[hcfg["channel"]], pwm)
            except Exception as e:                # noqa: BLE001
                self._finish(f"heater not confirmed: {e}")
                return

    # ------------------------------------------------------------------
    #  Exit + fan cooldown
    # ------------------------------------------------------------------
    def _finish(self, fault):
        """End the mode (from the loop or stop()): heater off via the safety
        layer, then keep the fan running for the cooldown period."""
        self._stop.set()
        was_on = self.active
        self.active = False
        if self.sys.heater_on:                    # heater + fan off, state + log
            self.sys.disable_heater(fault)
        if fault:
            self.fault = fault
        if was_on:
            t = self._state.get("temp")
            LOG.info("HEATING OFF (chamber %s C, target %s C)",
                     f"{t:.1f}" if t is not None else "?",
                     self._state.get("target"))
            self._start_cooldown()

    def _close_fans_and_damper(self):
        """End of process: turn ALL fans OFF (verified) and CLOSE the damper.
        Fans auto-driven by LEDs that are still on are left running (LED
        cooling). Uses only the existing verified IO activation functions."""
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
            self.sys.cooling._set_damper(False)   # damper CLOSED (angles owned by cooling_mode)
        except Exception:                # noqa: BLE001 - servo unavailable
            pass
        LOG.info("end of heating process: all fans OFF, damper CLOSED%s",
                 f" (kept LED fans: {', '.join(sorted(keep))})" if keep else "")

    def _start_cooldown(self):
        """Heater fan run-on: keep it at cooldown_fan_pwm for cooldown_sec.
        When the cooldown ends (or is skipped), ALL fans are turned off and
        the damper is closed. Cancelled cleanly when heating restarts."""
        cfg = self.cfg()
        hcfg = self.sys.heater_cfg()
        secs = float(cfg["cooldown_sec"])
        if secs <= 0:                             # no run-on: end the process now
            self._close_fans_and_damper()
            return
        self._cooldown_cancel.clear()

        def run_on():
            try:
                with self.sys.lock:
                    self.sys.io.pca.set_duty_verified(
                        PCA_CHANNELS[hcfg["fan"]], cfg["cooldown_fan_pwm"])
                LOG.info("heater fan cooldown: %s @ %g%% for %.0f s",
                         hcfg["fan"], cfg["cooldown_fan_pwm"], secs)
                self._cooldown_cancel.wait(secs)
            finally:
                # Only shut down if heating did not take the fan back over.
                if not self.sys.heater_on:
                    self._close_fans_and_damper()   # end of process: all fans + damper

        self._cooldown_thread = threading.Thread(target=run_on, daemon=True)
        self._cooldown_thread.start()

    def _cancel_cooldown(self):
        """Abort a pending fan run-on (joined, so a restart's fan spin-up
        cannot race the cooldown's fan-off write)."""
        self._cooldown_cancel.set()
        t = self._cooldown_thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=10)
        self._cooldown_thread = None

    def stop(self, reason="user"):
        """Stop heating: heater off now, fan runs on for the cooldown period.
        Safe to call anytime."""
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=10)
        if self.active:                           # loop exited without finishing
            self._finish(None if reason == "user" else reason)

    def shutdown(self, reason="user"):
        """Immediate FULL OFF: heater element + heater fan right now, NO
        cooldown run-on. Ends the whole process at once - all fans OFF and
        damper CLOSED (LED-driven fans are left running). Safe to call
        anytime, including while a cooldown is in progress."""
        self._stop.set()                          # end the PI loop
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=10)
        was_on = self.active
        self.active = False
        if reason != "user":
            self.fault = reason
        if self.sys.heater_on:                    # heater + fan off, state + log
            self.sys.disable_heater(None if reason == "user" else reason)
        had_cooldown = bool(self._cooldown_thread and self._cooldown_thread.is_alive())
        self._cancel_cooldown()                   # its exit path closes fans + damper
        if not had_cooldown:                      # no run-on was active: close here
            self._close_fans_and_damper()
        if was_on or had_cooldown:
            LOG.info("HEATING SHUTDOWN (%s): heater + fan OFF immediately, "
                     "no cooldown", reason)

    def status(self):
        """Live status dict: active, target, temp, pwm (heater duty %),
        at_temp, fan / fan_pwm, cooldown (fan run-on in progress), fault."""
        s = dict(self._state)
        s["active"] = self.active
        s["cooldown"] = bool(self._cooldown_thread and self._cooldown_thread.is_alive())
        s["fault"] = self.fault
        return s

    def close(self):
        self._stop.set()                          # end the loop; no hardware writes
        self._cooldown_cancel.set()


# ===========================================================================
#  Standalone CLI - `python3 temperature_control.py <target C>`
# ===========================================================================
def run_off():
    """Immediate full OFF (heater + fans, damper closed), then exit. For use
    after an interrupted run or as a manual kill switch:
        python3 temperature_control.py --off"""
    from io_controller import SystemController
    sysctl = SystemController(config=load_component_config())
    try:
        TemperatureController(sysctl).shutdown("user")
        print("heater OFF, fans OFF, damper closed.")
    finally:
        sysctl.close()
        sysctl.io.close()


def run_cli(target):
    """Blocking heating run with a live status printout. Ctrl+C stops safely
    (heater off; fan cooldown keeps running - second Ctrl+C skips it)."""
    from io_controller import SystemController
    sysctl = SystemController(config=load_component_config())
    ctrl = TemperatureController(sysctl)
    try:
        ok, why = ctrl.start(target)
        if not ok:
            raise SystemExit(f"heating blocked: {why}")
        s = ctrl.status()
        print(f"heating ON: target={s['target']:.1f} C, fan {s['fan']} @ "
              f"{s['fan_pwm']}%  (Ctrl+C to stop)\n")
        try:
            while ctrl.active:
                time.sleep(2.0)
                s = ctrl.status()
                t = s.get("temp")
                print(f"  chamber={f'{t:.1f}' if t is not None else '--'}C  "
                      f"target={s['target']:.1f}C  heater={s.get('pwm', 0):.0f}%"
                      + ("  [at temp]" if s.get("at_temp") else ""))
            if ctrl.fault:
                raise SystemExit(f"heating fault: {ctrl.fault}")
        except KeyboardInterrupt:
            print("\nstopping heating...")
            ctrl.stop("user")
        # fan run-on: keep the process alive so the daemon thread can finish
        if ctrl.status()["cooldown"]:
            print("heater fan cooldown running (Ctrl+C again to skip)...")
            try:
                while ctrl.status()["cooldown"]:
                    time.sleep(5.0)
                print("cooldown done - all fans off, damper closed.")
            except KeyboardInterrupt:
                ctrl.shutdown("user")
                print("skipping cooldown - heater + fans off, damper closed.")
    finally:
        ctrl.stop("user")
        ctrl.close()
        sysctl.close()
        sysctl.io.close()


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        prog="temperature_control.py",
        description="CureBox closed-loop heating: heater fan verified + fixed "
                    "on, heater element PWM under PI control toward the target "
                    "chamber temperature; on stop the fan runs on for the "
                    "configured cooldown before turning off.")
    p.add_argument("target", type=float, nargs="?", default=None,
                   help="target chamber temperature C, minimum 30 "
                        "(default from components.json)")
    p.add_argument("--off", action="store_true",
                   help="turn the heater + fans OFF immediately (no cooldown) and exit")
    args = p.parse_args(argv)
    if args.off:
        run_off()
    else:
        run_cli(args.target)


if __name__ == "__main__":
    main()
