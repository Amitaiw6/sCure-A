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

# Automatic machine-status colors on the RGB strip (StatusLeds below):
# fault -> blink red, door open -> blink, all OK -> solid normal color.
# A manual /api/rgb override (bridge._rgb_state['on']) pauses the automatic
# colors while it is active; they repaint as soon as it turns off.
RGB_AUTO_STATUS = True

# LED diagnostic: the board thermistor sitting at each LED module
LED_TEST_SENSORS = [
    ('Left LED',  'TEMP_LEFT_ORIGIN'),
    ('Right LED', 'TEMP_RIGHT_ORIGIN'),
    ('Back LED',  'TEMP_BACK_ORIGIN'),
    ('Door LED',  'TEMP_DOOR_ORIGIN'),
]
LED_TEST_MAX_TEMP = 80.0


class StatusLeds(threading.Thread):
    """Machine status on the addressable RGB strip (components.json "rgb").

    Priority:  any active fault -> BLINKING fault color (red)
               door open        -> BLINKING door color
               process running  -> busy color (yellow) as a comet MOVING
                                   right-to-left (heating / cooling / UV —
                                   any active cure step)
               otherwise        -> solid normal color
    Colors / brightness / blink + chase rates come from "rgb"."status".
    Best-effort by design: any LED error is swallowed - the strip must never
    take down heating/cooling control.
    """

    def __init__(self, bridge, leds, rgb_cfg, parse_color):
        super().__init__(daemon=True, name='rgb-status')
        st = rgb_cfg.get('status', {})
        self.bridge = bridge
        self.leds = leds
        self.color_normal = parse_color(str(st.get('normal', 'green')))
        self.color_fault = parse_color(str(st.get('fault', 'red')))
        self.color_door = parse_color(str(st.get('door_open', 'ff7800')))
        self.color_busy = parse_color(str(st.get('busy', 'yellow')))
        self.brightness = float(st.get('brightness', 40))
        self.blink_sec = max(0.1, float(st.get('blink_sec', 0.5)))
        # chase_sec = time per one-LED step of the moving busy animation
        self.chase_sec = max(0.03, float(st.get('chase_sec', 0.12)))
        self.chase_tail = max(1, int(st.get('chase_tail', 5)))
        self.rtl = str(st.get('busy_direction', 'rtl')).lower() != 'ltr'
        self._stop_evt = threading.Event()
        self._last_frame = None
        self._warned = False              # first loop error is logged once

    def _mode(self):
        b = self.bridge
        try:
            cool = b.sys.cooling_status()
        except Exception:                 # noqa: BLE001
            cool = {}
        if b.temp.fault or b.sys.heater_fault or b.sys.led_fault or cool.get('fault'):
            return 'fault'
        if b.sys.door_open() is True:     # None (sensor unreadable) is not "open"
            return 'door'
        if b.temp.active or cool.get('active') or b._uv.get('on'):
            return 'busy'
        return 'normal'

    def _paint_chase(self, offset):
        """One frame of the busy animation: a comet with a fading tail that
        moves right-to-left across the strip (flip with busy_direction)."""
        px, n = self.leds.px, self.leds.count
        level = max(0.0, min(1.0, self.brightness / 100.0))
        r, g, b = self.color_busy
        head = (n - 1 - offset) % n if self.rtl else offset % n
        for i in range(n):
            # tail trails where the head came from
            d = (i - head) % n if self.rtl else (head - i) % n
            f = level * (1.0 - d / self.chase_tail) if d < self.chase_tail else 0.0
            px[i] = (int(r * f), int(g * f), int(b * f))
        px.show()

    def run(self):
        offset = 0
        while not self._stop_evt.wait(self.chase_sec):
            try:
                # Manual /api/rgb override active -> leave the strip alone;
                # force a repaint of the status color when it ends.
                if getattr(self.bridge, '_rgb_state', {}).get('on'):
                    self._last_frame = None
                    continue
                mode = self._mode()
                if mode == 'busy':
                    offset = (offset + 1) % self.leds.count
                    self._paint_chase(offset)
                    self._last_frame = ('busy', offset)
                    continue
                # blink phase derived from wall time (loop ticks at chase_sec)
                blink_on = int(time.time() / self.blink_sec) % 2 == 0
                if mode == 'fault':
                    frame = self.color_fault if blink_on else (0, 0, 0)
                elif mode == 'door':
                    frame = self.color_door if blink_on else (0, 0, 0)
                else:
                    frame = self.color_normal
                if frame != self._last_frame:
                    self.leds.fill(frame, self.brightness)
                    self._last_frame = frame
            except Exception as e:        # noqa: BLE001 - never kill the status loop
                if not self._warned:      # surface the first failure in the journal
                    self._warned = True
                    print(f'[API] RGB status loop error (strip writes failing): {e}')

    def stop(self):
        self._stop_evt.set()
        try:
            self.leds.off()
            self.leds.close()
        except Exception:                 # noqa: BLE001
            pass


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
        self._fan_duty = {name: 0 for name in FAN_GROUPS}   # last commanded %
        self._n2_on = False               # nitrogen valve state (GPIO13)
        self._bofa_on = False             # BOFA extraction (PCA ch 10)
        try:
            from io_controller import (SystemController, PCA_CHANNELS,
                                       PCA_FANS, GPIO_SIGNALS, set_gpio_level)
            from temperature_control import TemperatureController
            self.PCA_CHANNELS, self.PCA_FANS = PCA_CHANNELS, PCA_FANS
            self.GPIO_SIGNALS, self._set_gpio = GPIO_SIGNALS, set_gpio_level
            self.sys = SystemController()
            self.sys.startup_safe()       # known-OFF state before serving
            self.temp = TemperatureController(self.sys)
            self.available = True
            # RGB strip: manual ON/OFF via /api/rgb for now. The automatic
            # status colors (StatusLeds above) are ready but not enabled yet —
            # flip RGB_AUTO_STATUS to True to turn them on.
            self.status_leds = None
            self._rgb = None              # RGBLeds, created on first /api/rgb use
            self._rgb_state = {'on': False, 'color': None, 'brightness': None}
            if RGB_AUTO_STATUS:
                try:
                    from io_controller import (RGBLeds, parse_rgb_color,
                                               load_component_config)
                    rgb_cfg = load_component_config().get('rgb', {})
                    self.status_leds = StatusLeds(self, RGBLeds(), rgb_cfg,
                                                  parse_rgb_color)
                    self.status_leds.start()
                    print('[API] RGB status LEDs: AUTO (normal/fault/door colors)')
                except Exception as e:    # noqa: BLE001
                    print(f'[API] RGB status LEDs unavailable: {e}')
            # Damper (MG90S servo on GPIO8). Creating the servo claims the
            # pin as a driven PWM output; start from a known-CLOSED damper.
            # It re-opens only when cooling starts, or when a DRYING step
            # reaches its target temperature (_damper_watch below).
            self._drying = False
            ok_d, why_d = self.set_damper(False)
            print('[API] damper servo ready (GPIO8, closed)' if ok_d
                  else f'[API] damper servo unavailable: {why_d}')
            threading.Thread(target=self._damper_watch, daemon=True,
                             name='damper-watch').start()
        except FileNotFoundError as e:    # bad/missing components.json - NOT "no hardware"
            self.error = f'hardware config error: {e}'
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
        # fans = commanded duty % (same meaning as the simulation payload);
        # the measured tachometer readings go in fanRpm.
        fan_rpm = {}
        for ui_name, group in FAN_GROUPS.items():
            rpm = self.sys.read_rpm(group[0])
            fan_rpm[ui_name] = int(rpm) if rpm else 0
        led_temps = {}
        for name, sensor in LED_TEST_SENSORS:
            key = name.split()[0].lower()          # 'Left LED' -> 'left'
            try:
                with self.sys.lock:
                    led_temps[key] = round(self.sys.io.read_temp(sensor)['temp'], 1)
            except Exception:             # noqa: BLE001
                led_temps[key] = None
        target = None
        if self.temp.active:
            target = heat.get('target')
        elif cool.get('active'):
            target = cool.get('target')
        return {
            'chamberTemp': chamber if chamber is not None else heat.get('temp'),
            'targetTemp': target,
            # door_open(): True=open, False=closed, None=sensor unreadable.
            # Report null on unreadable so the UI keeps its last known state
            # instead of falsely flipping to "door open".
            'doorClosed': None if door_open is None else (door_open is False),
            'isHeating': bool(self.temp.active),
            'isCooling': bool(cool.get('active')),
            'coolingMode': self._cooling_mode,
            'uvOn': self._uv['on'],
            'uvIntensity': self._uv['intensity'],
            'uvWavelength': self._uv['wavelength'],
            'damperOpen': self._damper_open,
            'fans': dict(self._fan_duty),
            'fanRpm': fan_rpm,
            'ledTemps': led_temps,
            'nitrogenActive': self._n2_on,
            'n2LinePressure': None,       # no line-pressure sensor on this board
            'bofaOn': self._bofa_on,
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
            self._drying = False
            self.set_uv(False)
            self.sys.stop_cooling('user')
            self.set_damper(False)        # vent stays closed while heating
            return self.temp.start(target_c)

    def dry_to_target(self, target_c):
        """Drying = the same closed-loop heating, plus damper handling:
        CLOSED during the ramp, OPENED automatically the moment the chamber
        reaches the target temperature (_damper_watch) so the moisture can
        vent out."""
        with self._op:
            self._drying = False
            self.set_uv(False)
            self.sys.stop_cooling('user')
            self.set_damper(False)        # closed until the target is reached
            ok, why = self.temp.start(target_c)
            self._drying = bool(ok)       # arm the at-temperature damper open
            return ok, why

    def _damper_watch(self):
        """Open the damper when an armed DRYING step reaches its target
        temperature. One-shot per drying step; every other state keeps the
        damper closed (cooling mode owns it while cooling). Never dies."""
        while True:
            time.sleep(1.0)
            try:
                if (self._drying and self.temp.active
                        and self.temp.status().get('at_temp')):
                    self._drying = False          # fire once per drying step
                    ok, why = self.set_damper(True)
                    print('[API] drying at target temperature: damper OPEN'
                          if ok else f'[API] drying damper open failed: {why}')
            except Exception:             # noqa: BLE001 - watcher must survive
                pass

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
            self._drying = False
            self.sys.stop_cooling('user')
            self.set_damper(False)        # vent stays closed while curing
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
            self._drying = False          # cooling owns the damper from here
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

    def stop_all(self, immediate=False):
        """Stop every cure output (heater, UV, cooling, nitrogen).

        immediate=True (user abort): full heater shutdown right now, no
        10-minute fan run-on - matches the UI promise of an immediate stop.
        immediate=False (normal end-of-cure): heater off with the standard
        fan cooldown run-on."""
        with self._op:
            self._drying = False
            self.set_uv(False)
            self.set_nitrogen(False)
            self.sys.stop_cooling('user')
            if immediate:
                self.temp.shutdown('user')
            else:
                self.temp.stop('user')
            self.set_damper(False)        # idle state: vent closed
            self._damper_open = False
            return True, None

    # ------------------------------------------------------------------
    #  Nitrogen purge (solenoid valve on GPIO13) / BOFA extraction
    # ------------------------------------------------------------------
    def set_nitrogen(self, on):
        try:
            self._set_gpio(self.GPIO_SIGNALS['NITROGEN_VALVE'], bool(on))
        except Exception as e:            # noqa: BLE001 - pinctrl unavailable
            return False, f'nitrogen valve failed: {e}'
        self._n2_on = bool(on)
        return True, None

    def set_bofa(self, on):
        try:
            with self.sys.lock:
                self.sys.io.pca.set_duty(self.PCA_CHANNELS['BOFA'],
                                         100 if on else 0)
        except Exception as e:            # noqa: BLE001 - I2C write failed
            return False, f'BOFA control failed: {e}'
        self._bofa_on = bool(on)
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
        # The heating loop owns FAN_HEATER and the cooling loop owns
        # FAN_COOLING - a manual write would fight the control loop.
        if fan == 'chamber_heating' and (self.temp.active or self.sys.is_heater_on()):
            return False, 'heater fan is controlled by the heating loop while it is active'
        if fan == 'chamber_intake' and self.sys.cooling_status().get('active'):
            return False, 'intake fan is controlled by the cooling loop while it is active'
        try:
            with self.sys.lock:
                for name in names:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], percent)
        except Exception as e:            # noqa: BLE001 - I2C write failed
            return False, f'fan write failed: {e}'
        if fan in self._fan_duty:
            self._fan_duty[fan] = int(percent)
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
            try:
                self.sys.set_door_magnet(True)
                threading.Timer(DOOR_RELEASE_SEC,
                                lambda: self.sys.set_door_magnet(False)).start()
            except Exception as e:        # noqa: BLE001 - I2C write failed
                return False, f'door release failed: {e}'
            return True, None

    # ------------------------------------------------------------------
    #  Diagnostics
    # ------------------------------------------------------------------
    def run_fan_test(self, fan=None):
        """Spin the requested fan up (unless a control loop already owns it)
        and measure the real tachometer RPM. `fan` is a UI group name
        (led_cooling / chamber_intake / chamber_heating); default = heater fan."""
        group = FAN_GROUPS.get(fan or 'chamber_heating')
        if not group:
            return {'rpm': 0, 'status': 'FAIL', 'message': f'unknown fan: {fan}'}
        name = group[0]
        with self._op:
            if name == 'FAN_HEATER':
                fan_busy = self.sys.is_heater_on() or self.temp.active
            elif name == 'FAN_COOLING':
                fan_busy = bool(self.sys.cooling_status().get('active'))
            else:
                fan_busy = False
            if not fan_busy:
                with self.sys.lock:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], 100)
                time.sleep(2.0)           # spin-up
            rpm = self.sys.measure_rpm(name, window=1.0)
            if not fan_busy:
                with self.sys.lock:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], 0)
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
        for action in (lambda: self.status_leds and self.status_leds.stop(),
                       lambda: self.temp.shutdown('user'),
                       lambda: self.sys.stop_cooling('user'),
                       lambda: self.sys.all_leds_off(),
                       lambda: self.set_nitrogen(False)):
            try:
                action()
            except Exception:             # noqa: BLE001
                pass
