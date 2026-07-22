#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
io_bridge.py - bridge between the Flask API (app.py) and the real CureBox
IO-board drivers in ../io_controller (Raspberry Pi CM5).

Architecture:
    React UI -> Flask API (app.py) -> IOBridge -> io_controller/
        SystemController        LED wavelength gating, heater safety, door interlock
        TemperatureController   closed-loop heating (PI on PWM_HEATER)
        CoolingController       closed-loop cooling (damper + fans)

The bridge is safe to import off-Pi: if the drivers cannot start (no smbus2 /
no I2C buses), `available` stays False and app.py keeps its simulation mode.
All safety logic (door interlock, heater fan spin-up + RPM verification,
thermistor validation, wavelength gating) lives in io_controller - the bridge
only composes the high-level operations the API exposes.
"""

import os
import sys
import threading
import time

# io_controller/ lives at the repo root, next to server/
IO_CONTROLLER_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'io_controller'))
if os.path.isdir(IO_CONTROLLER_DIR) and IO_CONTROLLER_DIR not in sys.path:
    sys.path.insert(0, IO_CONTROLLER_DIR)

# UI cooling modes -> cooling-rate setpoint (C/min, see components.json "cooling")
COOLING_MODE_RATES = {'fast': 5.0, 'medium': 2.5, 'slow': 1.0}

# UI fan names -> PCA9685 fan channels (io_controller PCA_CHANNELS)
FAN_GROUPS = {
    'led_cooling':     ['FAN_LEFT', 'FAN_RIGHT', 'FAN_BACK', 'FAN_DOOR'],
    'chamber_intake':  ['FAN_COOLING'],
    'chamber_heating': ['FAN_HEATER'],
}

DOOR_RELEASE_SEC = 2.0        # door-magnet energize time for /api/door/open

# LED diagnostic: the board thermistor sitting at each LED module
LED_TEST_SENSORS = [
    ('Left LED',  'TEMP_LEFT_ORIGIN'),
    ('Right LED', 'TEMP_RIGHT_ORIGIN'),
    ('Back LED',  'TEMP_BACK_ORIGIN'),
    ('Door LED',  'TEMP_DOOR_ORIGIN'),
]
LED_TEST_MAX_TEMP = 80.0


class IOBridge:
    """Owns the io_controller stack and exposes the API-level operations.

    Every operation returns (ok, reason-or-None) so endpoints can surface the
    safety-layer refusal (door open, fan not spinning, thermistor invalid...).
    """

    def __init__(self):
        self.available = False
        self.error = None
        self._op = threading.RLock()      # serializes compound operations
        self._damper_open = False
        self._cooling_mode = None         # UI mode name while cooling is active
        self._uv = {'on': False, 'intensity': 0, 'wavelength': None}
        try:
            from io_controller import SystemController, PCA_CHANNELS, PCA_FANS
            from temperature_control import TemperatureController
            self.PCA_CHANNELS, self.PCA_FANS = PCA_CHANNELS, PCA_FANS
            self.sys = SystemController()
            self.sys.startup_safe()       # known-OFF state before serving
            self.temp = TemperatureController(self.sys)
            self.available = True
        except Exception as e:            # noqa: BLE001 - off-Pi / no I2C
            self.error = str(e)

    # ------------------------------------------------------------------
    #  State (polled by the frontend via /api/state)
    # ------------------------------------------------------------------
    def get_state(self):
        heat = self.temp.status()
        cool = self.sys.cooling_status()
        if not cool.get('active') and self._cooling_mode:
            self._cooling_mode = None     # cooling auto-ended: damper was closed
            self._damper_open = False
        try:
            with self.sys.lock:
                chamber = self.sys.io.read_temp('TEMP_CHAMBER')['temp']
        except Exception:                 # noqa: BLE001
            chamber = None
        door_open = self.sys.door_open()
        fans = {}
        for ui_name, group in FAN_GROUPS.items():
            rpm = self.sys.read_rpm(group[0])
            fans[ui_name] = int(rpm) if rpm else 0
        target = None
        if self.temp.active:
            target = heat.get('target')
        elif cool.get('active'):
            target = cool.get('target')
        return {
            'chamberTemp': chamber if chamber is not None else heat.get('temp'),
            'targetTemp': target,
            'doorClosed': door_open is False,
            'isHeating': bool(self.temp.active),
            'isCooling': bool(cool.get('active')),
            'coolingMode': self._cooling_mode,
            'uvOn': self._uv['on'],
            'uvIntensity': self._uv['intensity'],
            'uvWavelength': self._uv['wavelength'],
            'damperOpen': self._damper_open,
            'fans': fans,
            'atTemp': bool(heat.get('at_temp')),
            'heaterPwm': heat.get('pwm'),
            'coolingRate': cool.get('rate_meas'),
            'faults': {
                'heater': self.temp.fault or self.sys.heater_fault,
                'cooling': cool.get('fault'),
                'led': self.sys.led_fault,
            },
            'hwSource': 'io_controller',
        }

    # ------------------------------------------------------------------
    #  UV LEDs (405nm cure / 450nm bleaching, via the wavelength gating)
    # ------------------------------------------------------------------
    def set_uv(self, on, intensity=0, wavelength=None):
        with self._op:
            if not on:
                self.sys.all_leds_off()
                self._uv = {'on': False, 'intensity': 0, 'wavelength': None}
                return True, None
            mode = '450nm' if wavelength == 450 else '405nm'
            ok, why = self.sys.select_mode(mode)   # all LEDs off, GPIO17 set + verified
            if not ok:
                return False, why
            lit = []
            for led in self.sys.allowed_leds(mode):
                if self.sys.set_led_brightness(led, intensity):
                    lit.append(led)
            if not lit:
                return False, self.sys.led_fault or 'no LED could be enabled'
            self._uv = {'on': True, 'intensity': int(intensity),
                        'wavelength': 450 if mode == '450nm' else 405}
            return True, None

    # ------------------------------------------------------------------
    #  Heating / drying (closed loop, heater safety pre-flight inside)
    # ------------------------------------------------------------------
    def heat_to_target(self, target_c):
        with self._op:
            self.set_uv(False)
            self.sys.stop_cooling('user')
            return self.temp.start(target_c)

    def dry_to_target(self, target_c):
        return self.heat_to_target(target_c)

    def set_target_temp(self, target_c):
        """Manual chamber setpoint: retarget the running loop, or start heating."""
        with self._op:
            if self.temp.active:
                self.temp.set_target(target_c)
                return True, None
            return self.temp.start(target_c)

    def stop_heating(self):
        self.temp.stop('user')            # heater off now; fan cooldown run-on continues
        return True, None

    # ------------------------------------------------------------------
    #  Cure / bleaching = heating + UV together
    # ------------------------------------------------------------------
    def cure_uv(self, target_c, intensity, wavelength):
        with self._op:
            self.sys.stop_cooling('user')
            ok_h, why_h = self.temp.start(target_c)
            ok_u, why_u = self.set_uv(True, intensity, wavelength)
            if ok_h and ok_u:
                return True, None
            problems = [p for p in (why_h, why_u) if p]
            return False, '; '.join(problems) or 'cure blocked'

    # ------------------------------------------------------------------
    #  Cooling (closed-loop rate control; damper + fans owned by the mode)
    # ------------------------------------------------------------------
    def cool_to_target(self, target_c, mode):
        with self._op:
            self.set_uv(False)
            # Immediate full heater OFF (no fan run-on): cooling owns the
            # heater fan for the whole mode and reopens the damper itself.
            self.temp.shutdown('user')
            rate = COOLING_MODE_RATES.get(mode, COOLING_MODE_RATES['medium'])
            ok, why = self.sys.start_cooling(rate, target_c)
            if ok:
                self._cooling_mode = mode
                self._damper_open = True
            return ok, why

    def stop_all(self):
        """Stop every cure output (heater, UV, cooling)."""
        with self._op:
            self.set_uv(False)
            self.sys.stop_cooling('user')
            self.temp.stop('user')
            self._damper_open = False
            return True, None

    # ------------------------------------------------------------------
    #  Fans / damper / door
    # ------------------------------------------------------------------
    def set_fan_speed(self, fan, percent):
        names = FAN_GROUPS.get(fan)
        if names is None and fan.upper() in self.PCA_FANS:
            names = [fan.upper()]
        if not names:
            return False, f'unknown fan: {fan}'
        with self.sys.lock:
            for name in names:
                self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], percent)
        return True, None

    def set_damper(self, open_state):
        try:
            self.sys.cooling._set_damper(bool(open_state))
        except Exception as e:            # noqa: BLE001 - servo unavailable
            return False, f'damper failed: {e}'
        self._damper_open = bool(open_state)
        return True, None

    def open_door(self):
        """Release the door magnet. Outputs are stopped first - opening the
        door mid-run would trip the interlock anyway; this makes it orderly."""
        with self._op:
            self.set_uv(False)
            self.temp.stop('user')
            self.sys.set_door_magnet(True)
            threading.Timer(DOOR_RELEASE_SEC,
                            lambda: self.sys.set_door_magnet(False)).start()
            return True, None

    # ------------------------------------------------------------------
    #  Diagnostics
    # ------------------------------------------------------------------
    def run_fan_test(self):
        """Spin the heater fan up (unless heating already owns it) and measure
        the real tachometer RPM."""
        fan = 'FAN_HEATER'
        with self._op:
            fan_busy = self.sys.is_heater_on() or self.temp.active
            if not fan_busy:
                with self.sys.lock:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[fan], 100)
                time.sleep(2.0)           # spin-up
            rpm = self.sys.measure_rpm(fan, window=1.0)
            if not fan_busy:
                with self.sys.lock:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[fan], 0)
        rpm = int(rpm or 0)
        min_rpm = self.sys.heater_cfg().get('min_fan_rpm', 100)
        return {'rpm': rpm, 'status': 'OK' if rpm >= min_rpm else 'FAIL'}

    def run_led_test(self):
        """Read the thermistor at each LED module and validate the reading."""
        results = []
        for name, sensor in LED_TEST_SENSORS:
            try:
                with self.sys.lock:
                    t = self.sys.io.read_temp(sensor)['temp']
            except Exception:             # noqa: BLE001
                t = None
            ok = t is not None and t < LED_TEST_MAX_TEMP
            results.append({'name': name,
                            'temp': round(t, 1) if t is not None else None,
                            'status': 'OK' if ok else 'FAIL'})
        return {'results': results}

    # ------------------------------------------------------------------
    #  Shutdown (atexit): everything OFF, no run-on
    # ------------------------------------------------------------------
    def shutdown(self):
        for action in (lambda: self.temp.shutdown('user'),
                       lambda: self.sys.stop_cooling('user'),
                       lambda: self.sys.all_leds_off()):
            try:
                action()
            except Exception:             # noqa: BLE001
                pass
