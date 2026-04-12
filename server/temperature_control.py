#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Temperature control loop (PI controller) for the chamber."""

import time
import threading
from io_board import IOBoard


class TemperatureController:
    """Python version of your TS heat controller - simplified to work with IOBoard."""

    CTL_P = 0.08
    CTL_I = 0.00015
    CTL_D = 0.0

    INTEGRATOR_MAX = 0.85
    INTEGRATOR_MIN = 0.0
    # ------------------------------
    # Delta-Sigma DAC for Heater
    # ------------------------------
    def run_heater_dac(self, set_val: float):
        # clip to [0,1]
        v = max(0.0, min(1.0, set_val))

        # delta-sigma
        if self.heater_dac_last:
            delta = v - 1.0
        else:
            delta = v

        sig = self.heater_dac_accum + delta
        out = sig > 0.5

        self.heater_dac_last = out
        self.heater_dac_accum = sig

        if out:
            self.io.heater_on()
        else:
            self.io.heater_off()

    def __init__(self, io_board: IOBoard):
        self.io = io_board
        self.target_temp = 25.0
        self.integrate = 0.0
        self.prev_error = 0.0
        self.at_temp = False
        self.run = False
        self.thread: threading.Thread | None = None
        # Delta-Sigma heater DAC state
        self.heater_dac_accum = 0.0
        self.heater_dac_last = False
        # Callback for UI updates
        self._on_update = None

    # ------------------------------
    # UI callback - sends temp data to frontend
    # ------------------------------
    def set_update_callback(self, callback):
        """Set callback: callback(temp, target, at_temp, heating)"""
        self._on_update = callback

    def _notify_update(self, temp, heating):
        if self._on_update:
            try:
                self._on_update(temp, self.target_temp, self.at_temp, heating)
            except Exception:
                pass

    # ------------------------------
    # Set Target Temperature
    # ------------------------------
    def set_target(self, temp_c: float):
        self.target_temp = float(temp_c)

    # ------------------------------
    # Start Heating Process
    # ------------------------------
    def start(self, target_c: float | None = None):
        if target_c is not None:
            self.set_target(target_c)

        if self.run:
            return

        # Auto-start fan when heating begins
        try:
            print("[TempCtrl] Heating started — turning FAN ON")
            self.io.set_fan(100)
        except Exception as e:
            print(f"[TempCtrl] FAN start error: {e}")

        self.run = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # ------------------------------
    # Stop Heating + 10 min Fan
    # ------------------------------
    def stop(self):
        # Stop PI loop
        self.run = False

        # Immediately stop heater
        self.io.heater_off()
        print("[TempCtrl] Heating stopped — Heater OFF")

        # Notify UI
        self._notify_update(self.io.read_temp_c() or 0, False)

        # Keep fan running during cooldown
        try:
            print("[TempCtrl] Keeping FAN ON for 10 minutes...")
            self.io.set_fan(60)
        except Exception as e:
            print(f"[TempCtrl] FAN start error: {e}")

        # Delayed shutdown thread
        def delayed_fan_off():
            time.sleep(600)  # 10 minutes
            try:
                print("[TempCtrl] 10 minutes passed — Turning FAN OFF")
                self.io.set_fan(0)
            except Exception as e:
                print(f"[TempCtrl] FAN stop error (delayed): {e}")

        threading.Thread(target=delayed_fan_off, daemon=True).start()

    # ------------------------------
    # Main PI Loop
    # ------------------------------
    def _loop(self):
        print(f"[TempCtrl] Starting loop, target={self.target_temp}°C")

        while self.run:
            try:
                temp = self.io.read_temp_c()

                if temp is None:
                    print("[TempCtrl] No temperature reading, skipping cycle")
                    time.sleep(1)
                    continue

                error = self.target_temp - temp

                # Integrator
                self.integrate += self.CTL_I * error
                self.integrate = max(self.INTEGRATOR_MIN,
                                     min(self.integrate, self.INTEGRATOR_MAX))

                # Proportional + Derivative
                prop = self.CTL_P * error
                deriv = self.CTL_D * (error - self.prev_error)
                self.prev_error = error

                control = prop + self.integrate + deriv
                print(f"[PID] control={control:.2f} | P={prop:.2f} I={self.integrate:.2f} D={deriv:.2f}")

                # Heater ON/OFF
                power = max(0.0, min(1.0, control))
                self.run_heater_dac(power)

                self.at_temp = abs(error) < 1.5

                # Notify frontend
                self._notify_update(temp, power > 0)

                print(f"[TempCtrl] T={temp:.2f}C "
                      f"target={self.target_temp:.2f}C "
                      f"err={error:.2f} ctl={control:.3f} "
                      f"atTemp={self.at_temp}")

            except Exception as e:
                print(f"[TempCtrl] Error: {e}")

            time.sleep(0.05)


# ------------------------------
# Debug Standalone Mode
# ------------------------------
if __name__ == "__main__":
    board = IOBoard(debug=True)
    ctrl = TemperatureController(board)
    ctrl.start(60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[TempCtrl] Stopping by user")
        ctrl.stop()
