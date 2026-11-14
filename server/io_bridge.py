#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
io_bridge.py - bridge between the Flask API (app.py) and the real CureBox
IO-board drivers in ../io_controller (Raspberry Pi CM5).

Architecture:
    React UI -> Flask API (app.py) -> IOBridge -> io_controller/
        SystemController        LED wavelength gating, heater safety, door interlock
        TemperatureController   PI(D) + delta-sigma heating (PWM_HEATER)
        CoolingController       fixed-fan cooling (damper + fans)

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

# UI cooling modes -> FIXED chamber-fan duty (%). The cooling loop holds the
# fan at this constant duty for the whole mode (no closed-loop rate control);
# components.json "cooling.mode_pwms" overrides these defaults.
COOLING_MODE_PWMS = {'fast': 100, 'medium': 60, 'slow': 30}

# FAST cooling boost: the four LED-cooling fans (FAN_LEFT/RIGHT/BACK/DOOR)
# join the chamber fan at this duty to move extra air through the chamber.
# components.json "cooling.fast_led_fan_pwm" overrides; 0 disables the boost.
# They are released (OFF) the moment cooling ends or the mode leaves 'fast'.
FAST_COOL_LED_FAN_PWM = 100

# Drying: the chamber intake/cooling fan (FAN_COOLING) runs at this duty for the
# WHOLE drying step - from the start of the ramp through the hold - so the
# chamber keeps a gentle airflow that carries moisture out. Turned off the
# moment any other step (heat / cure / cool / stop) takes over.
DRY_INTAKE_FAN_PWM = 30

# UV-only ventilation (cure/bleaching with NO chamber heating): damper OPEN +
# chamber intake fan pulling fresh outside air - the same airflow path cooling
# uses, but with no cooling loop/target; it runs for the whole UV exposure.
# components.json "ventilation.fan_pwm" overrides; 0 disables.
VENT_FAN_PWM = 60

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
    ('Left LED',  'TEMP_LEFT_UV'),
    ('Right LED', 'TEMP_RIGHT_UV'),
    ('Back LED',  'TEMP_BACK'),
    ('Door LED',  'TEMP_DOOR'),
]
LED_TEST_MAX_TEMP = 80.0
# Second thermistor on the Left / Right modules (U6 ch1 / ch3). Reported in
# /api/state ledTemps as left2 / right2 for telemetry only - NOT part of the
# LED start-up check or the sensor supervision (those use the ORIGIN sensors).
LED_SECOND_SENSORS = [('left2', 'TEMP_LEFT'), ('right2', 'TEMP_RIGHT')]

# Temperature-sensor supervision (policy defined with the user 2026-09-09):
# an NTC that reads open-circuit (at the 3.3 V pull-up rail -> no temperature)
# for SENSOR_OPEN_ALERT_SEC continuously raises a registry alert. The chamber
# and the Left / Right LED thermistors are REQUIRED: their alert is critical
# (9001) and no process may start while they are open (checked at start-up
# and again right before every process start). The Back / Door LED
# thermistors only raise a warning (9050) - processes run as usual.
SENSOR_OPEN_ALERT_SEC = 60.0
# Noise filter (2026-09-16, 10 s per the user): a sensor counts as a real problem only when it
# reads open CONTINUOUSLY for at least SENSOR_GLITCH_SEC. A shorter dropout
# (I2C / connector noise) is ignored everywhere - the immediate heater alert,
# the pre-start check and the start-up log line. Same window as the heater
# safety in io_controller (heater.thermistor_glitch_sec).
SENSOR_GLITCH_SEC = 10.0
CRITICAL_TEMP_SENSORS = {'TEMP_CHAMBER': 'chamber', 'TEMP_LEFT_UV': 'left',
                         'TEMP_RIGHT_UV': 'right'}
WARNING_TEMP_SENSORS = {'TEMP_BACK': 'back', 'TEMP_DOOR': 'door'}
ERR_TEMP_SENSOR_DISCONNECTED = 9001      # critical - errors.json
# The heater is controlled on the chamber NTC (io_controller heater.thermistor): it is never switched on while
# that sensor does not read (enable_heater pre-flight), and a running heater is switched off at once when it stops
# reading (heater_health_check). 9001 then carries this detail so the screen pops the heater fault.
HEATER_THERMISTOR = 'TEMP_CHAMBER'
HEATER_SENSOR_DETAIL = 'Heater temperature sensor (chamber NTC TEMP_CHAMBER) is not reading - the heater is off'
ERR_LED_TEMP_SENSOR_DISCONNECTED = 9050  # warning  - errors.json
SENSOR_VALID_C = (-20.0, 120.0)          # HSI valid range for every NTC

# Fan wear supervision (components.json "fan_health"): a fan running below its
# measured nominal RPM for a full minute -> 9051 warning (replace it) at
# warn_below_pct, or 9002 critical at critical_below_pct: every output is
# stopped, no process may start, the alert names the exact fan.
ERR_FAN_FAILURE = 9002                   # critical - errors.json
ERR_FAN_WEAR_WARNING = 9051              # warning  - errors.json
ERR_LED_FAN_STOPPED = 9003               # critical - errors.json: an LED cooling fan does not spin -> the job does not start
FAN_HEALTH_DEFAULTS = {'warn_below_pct': 10, 'critical_below_pct': 20,
                       'persist_sec': 60, 'settle_sec': 5, 'min_eval_duty': 30,
                       'stopped_persist_sec': 5,    # a fan reading ~0 RPM (disconnected / seized) trips after this, not after persist_sec
                       'led_fan_min_rpm': 100,      # pre-flight before the LEDs go on: every LED fan must spin at least this fast
                       'critical_below_pct_by_fan': {},   # per-fan override of critical_below_pct
                       'nominal_rpm_damper_open': {},     # nominal while the damper is OPEN (slower duct)
                       'nominal_rpm': {}}

# LED connection supervision (components.json "led_heating"): a lit LED
# module warms the thermistor sitting on it. A panel that is commanded ON at
# >= min_eval_intensity % system power but has NOT risen by min_rise_c after
# check_after_sec of accumulated light is not receiving current (open
# connector / driver output) -> 9004 critical "check the LED connection",
# the alert names the panel. Per the user (2026-09-14) the check uses the
# REGULAR Left / Right thermistors (TEMP_LEFT / TEMP_RIGHT, U6 ch3 / ch1),
# not the ORIGIN ones, so only the Left and Right panels are supervised
# (Back / Door carry an ORIGIN thermistor only). Bench 2026-09-14 (30 %,
# 405 nm, LED fans at 100 %): TEMP_LEFT / TEMP_RIGHT rose +1.3 / +1.2 C
# after 60 s, +1.8 / +1.7 C after 90 s, +2.4 / +2.2 C after 150 s (the ORIGIN
# ones about twice that) - hence 90 s and 1.0 C, a 1.7x margin.
# rest_sec keeps the thermal window: a panel re-lit within rest_sec of its
# last light continues the previous window (it is still warm, so a fresh
# baseline would see no rise) instead of starting a new one.
# led_heating.panels in components.json may override the panel -> sensor map.
# Mid-process drop (9005): once a lit panel has proved it heats, its peak
# temperature is tracked; a fall of drop_c below that peak - after taking off
# any fall of the chamber temperature over the same time - that persists for
# drop_persist_sec means the panel stopped receiving current mid-process
# (loose connector, driver output dropped) -> 9005 critical naming the panel.
# A power-level change or a re-light re-arms the peak after drop_settle_sec.
ERR_LED_NOT_HEATING = 9004               # critical - errors.json
ERR_LED_TEMP_DROP = 9005                 # critical - errors.json
LED_HEATING_DEFAULTS = {'min_eval_intensity': 30, 'check_after_sec': 90,
                        'min_rise_c': 1.0, 'rest_sec': 120,
                        'drop_c': 1.0, 'drop_persist_sec': 30, 'drop_settle_sec': 120}
LED_PANEL_LABELS = {'LED_LEFT': 'Left LED', 'LED_RIGHT': 'Right LED',
                    'LED_BACK': 'Back LED', 'LED_DOOR': 'Door LED'}
LED_PANEL_SENSORS = {'LED_LEFT': ('Left LED', 'TEMP_LEFT'),
                     'LED_RIGHT': ('Right LED', 'TEMP_RIGHT')}


class StatusLeds(threading.Thread):
    """Machine status on the addressable RGB strip (components.json "rgb").

    Priority:  any active fault -> BLINKING fault color (red)
               door open        -> BLINKING door color
               process running  -> busy color (yellow) as a comet MOVING
                                   right-to-left (heating / cooling / UV —
                                   any active cure step)
               no internet      -> SOLID no_internet color (blue), whether a
                                   process is running or not
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
        # Colors + brightness come from components.json rgb.status and are
        # re-read LIVE every status_sec (_reload_colors) - edit the file, the
        # strip follows within a second, no service restart needed.
        self._parse_color = parse_color
        self._status_cfg = dict(st)
        self._apply_colors(st)
        self.blink_sec = max(0.1, float(st.get('blink_sec', 0.5)))
        # chase_sec = time per one-LED step of the moving busy animation
        self.chase_sec = max(0.03, float(st.get('chase_sec', 0.12)))
        self.chase_tail = max(1, int(st.get('chase_tail', 5)))
        # busy_style 'comet' (default) = the busy color moves; 'solid' = steady. The no-internet-while-busy state is ALWAYS solid blue.
        self.busy_style = str(st.get('busy_style', 'comet')).lower()
        self.rtl = str(st.get('busy_direction', 'rtl')).lower() != 'ltr'
        # status_sec = how often the machine state is (re)classified AND the
        # door-open safety is enforced; animation keeps its own faster ticks.
        # HSI sampling-time rule: every reading is sampled at most every 1 s.
        self.status_sec = max(0.5, float(st.get('status_sec', 1.0)))
        # door grace: the process is aborted only if the door STAYS open this
        # long (components.json door_sensor.abort_after_sec, default 10 s)
        self.door_abort_sec = 10.0
        try:
            from io_controller import load_component_config
            self.door_abort_sec = float(load_component_config()
                                        .get('door_sensor', {})
                                        .get('abort_after_sec', 10))
        except Exception:                 # noqa: BLE001 - config optional
            pass
        self._door_open_since = None      # when door-open-with-outputs began
        # Internet reachability, refreshed in the background every
        # internet_check_sec (TCP 443 to real endpoints, 2 s timeout).
        self.net_check_sec = max(2.0, float(st.get('internet_check_sec', 5)))
        self._internet_ok = True          # optimistic until the first check
        self._stop_evt = threading.Event()
        self._last_frame = None
        self._warned = False              # first loop error is logged once

    def _apply_colors(self, st):
        """Parse the rgb.status colors (+ brightness) into the attributes
        the paint loop uses."""
        p = self._parse_color
        self.color_normal = p(str(st.get('normal', 'green')))
        self.color_fault = p(str(st.get('fault', 'red')))
        self.color_door = p(str(st.get('door_open', 'ff7800')))
        # busy = a running cure/bleaching program: purple comet (was yellow
        # until 2026-09-07 - the bench asked for the purple back).
        self.color_busy = p(str(st.get('busy', 'purple')))
        self.color_no_net = p(str(st.get('no_internet', 'blue')))
        # Manual chamber heating (Settings slider) gets its own SOLID color -
        # steady orange, no comet / no blink - so it is visually distinct from
        # a running cure program (moving comet) and from door-open (blinking).
        self.color_manual = p(str(st.get('manual_heat', 'ff8c00')))
        self.color_warn = p(str(st.get('warning', 'yellow')))      # a warning on the Alerts screen: pulsing yellow
        self.brightness = float(st.get('brightness', 40))

    def _reload_colors(self):
        """Re-read rgb.status from components.json (called from _evaluate,
        i.e. every status_sec). A changed table is applied at once and the
        strip repaints; any read/parse problem keeps the last good colors."""
        try:
            from io_controller import load_component_config
            st = load_component_config().get('rgb', {}).get('status', {})
            if st != self._status_cfg:
                self._apply_colors(st)
                self._status_cfg = dict(st)
                self._last_frame = None       # force a repaint in the new colors
                print('[API] RGB status colors reloaded from components.json',
                      flush=True)
        except Exception:                 # noqa: BLE001 - keep the last good table
            pass

    def _net_watch(self):
        """Background flag refresher: does the machine actually reach the
        internet? Runs in its own thread so a dead network (2 s timeouts)
        never stalls the LED animation or the door watchdog."""
        import socket
        # HTTPS endpoints, not DNS port 53: some routers intercept and answer
        # DNS locally even with the uplink dead, which would fake "online".
        targets = (('www.google.com', 443), ('1.1.1.1', 443))
        while True:
            ok = False
            for host, port in targets:
                try:
                    socket.create_connection((host, port), timeout=2).close()
                    ok = True
                    break
                except OSError:
                    pass
            if ok != self._internet_ok:
                print(f'[API] Internet {"back online" if ok else "UNREACHABLE"}'
                      ' - status strip updated', flush=True)
            self._internet_ok = ok
            if self._stop_evt.wait(self.net_check_sec):
                return

    def _mode(self):
        b = self.bridge
        try:
            cool = b.sys.cooling_status()
        except Exception:                 # noqa: BLE001
            cool = {}
        if b.temp.fault or b.sys.heater_fault or b.sys.led_fault or cool.get('fault'):
            return 'fault'
        # The notifications on the machine's screen drive the strip: any undismissed CRITICAL alert -> pulsing
        # red, any WARNING -> pulsing yellow (below), all cleared -> the normal solid green. The UI reports its
        # counts (POST /api/rgb/alerts) on every change and every 30 s; a report older than 90 s is ignored.
        ui = getattr(b, '_ui_alerts', None)
        ui_fresh = bool(ui) and time.time() - ui.get('at', 0) < 90
        if ui_fresh and ui.get('critical', 0) > 0:
            return 'fault'
        # A door abort stays RED until the user acknowledges the Err 6016
        # alert in the UI (POST /api/door-abort/ack) or starts a new process.
        if b._door_abort_ts:
            return 'fault'
        if b.sys.door_open() is True:     # None (sensor unreadable) is not "open"
            return 'door'
        if ui_fresh and ui.get('warning', 0) > 0:
            return 'warn'
        # Manual chamber heating (Settings slider, /api/chamber/temperature):
        # its own steady color, checked BEFORE the generic busy animation.
        if (b.temp.active and getattr(b, '_manual_heat', False)
                and not cool.get('active') and not b._uv.get('on')):
            return 'manual_heat'
        if b.temp.active or cool.get('active') or b._uv.get('on'):
            # A process without internet runs the comet in the no-internet
            # color, so the strip shows BOTH facts at once.
            return 'busy' if self._internet_ok else 'busy_no_net'
        if not self._internet_ok:         # idle + offline -> no-internet color
            return 'no_net'
        return 'normal'

    def _evaluate(self):
        """Runs every status_sec (default 1 s): classify the machine state for
        the strip AND enforce the door safety. The door opening mid-process
        gets a grace period (door_abort_sec, default 10 s) to be closed;
        only if it STAYS open that long is the process aborted and every
        output forced off. The check is independent of the displayed mode,
        so it fires even when a fault has priority on the strip."""
        b = self.bridge
        self._reload_colors()
        try:
            b._sensor_tick()              # NTC open-circuit supervision (60 s rule)
        except Exception:                 # noqa: BLE001 - never disturb the door safety
            pass
        try:
            b._fan_tick()                 # fan wear supervision (60 s rule)
        except Exception:                 # noqa: BLE001
            pass
        try:
            b._led_heat_tick()            # LED connection supervision (thermistor rise)
        except Exception:                 # noqa: BLE001
            pass
        try:
            outputs_on = False
            if b.sys.door_open() is True:
                outputs_on = (b.temp.active or b.sys.cooling_status().get('active')
                              or b._uv.get('on') or b._n2_on or b._bofa_on
                              or any(d > 0 for d in b._fan_duty.values()))
            if outputs_on:
                now = time.time()
                if self._door_open_since is None:
                    self._door_open_since = now
                    print(f'[SAFETY] Door opened mid-process - aborting in '
                          f'{self.door_abort_sec:.0f}s unless it closes',
                          flush=True)
                elif now - self._door_open_since >= self.door_abort_sec:
                    self._door_open_since = None
                    b.door_abort()
            else:
                if self._door_open_since is not None:
                    print('[SAFETY] Door closed in time - process continues',
                          flush=True)
                self._door_open_since = None
        except Exception:                 # noqa: BLE001 - best-effort here; the
            pass                          # io_controller interlock still backs it up
        return self._mode()

    def _paint_chase(self, offset, color=None):
        """One frame of the busy animation: a comet with a fading tail that
        moves right-to-left across the strip (flip with busy_direction).
        color overrides the comet color (no-internet runs it in blue)."""
        px, n = self.leds.px, self.leds.count
        level = max(0.0, min(1.0, self.brightness / 100.0))
        r, g, b = color or self.color_busy
        head = (n - 1 - offset) % n if self.rtl else offset % n
        for i in range(n):
            # tail trails where the head came from
            d = (i - head) % n if self.rtl else (head - i) % n
            f = level * (1.0 - d / self.chase_tail) if d < self.chase_tail else 0.0
            px[i] = (int(r * f), int(g * f), int(b * f))
        px.show()

    def run(self):
        offset = 0
        mode = 'normal'
        last_eval = 0.0
        threading.Thread(target=self._net_watch, daemon=True,
                         name='rgb-net-watch').start()
        while not self._stop_evt.wait(self.chase_sec):
            try:
                # State (+ door safety) every status_sec; the strip animates
                # between evaluations with the last classified mode.
                now = time.time()
                if now - last_eval >= self.status_sec:
                    last_eval = now
                    mode = self._evaluate()
                    self.mode = mode                      # exposed in /api/state as stripMode
                # Manual /api/rgb override active -> leave the strip alone;
                # force a repaint of the status color when it ends.
                if getattr(self.bridge, '_rgb_state', {}).get('on'):
                    self._last_frame = None
                    continue
                if mode == 'busy_no_net' or (mode == 'busy' and self.busy_style == 'solid'):
                    # process running with no internet: SOLID blue (a moving blue comet read as a warning);
                    # busy_style 'solid' makes the busy color steady as well
                    frame = self.color_no_net if mode == 'busy_no_net' else self.color_busy
                    if frame != self._last_frame:
                        self.leds.fill(frame, self.brightness)
                        self._last_frame = frame
                    continue
                if mode == 'busy':
                    offset = (offset + 1) % self.leds.count
                    self._paint_chase(offset)
                    self._last_frame = (mode, offset)
                    continue
                # blink phase derived from wall time (loop ticks at chase_sec)
                blink_on = int(time.time() / self.blink_sec) % 2 == 0
                if mode == 'fault':
                    frame = self.color_fault if blink_on else (0, 0, 0)
                elif mode == 'door':
                    frame = self.color_door if blink_on else (0, 0, 0)
                elif mode == 'warn':          # a warning on the Alerts screen: pulsing yellow
                    frame = self.color_warn if blink_on else (0, 0, 0)
                elif mode == 'manual_heat':   # Settings-slider heating: solid orange
                    frame = self.color_manual
                elif mode == 'no_net':    # idle + no internet: solid blue
                    frame = self.color_no_net
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
        self._damper_open = None          # None = never driven; set on first command
        self._dry_fan_on = False          # chamber intake fan held at 30% while drying
        self._cooling_mode = None         # UI mode name while cooling is active
        self._cool_led_fans = False       # LED fans boosting a FAST cool
        self._uv = {'on': False, 'intensity': 0, 'wavelength': None}
        self._vent_on = False             # fresh-air vent during a no-heat UV step
        self._fan_duty = {name: 0 for name in FAN_GROUPS}   # last commanded %
        self._n2_on = False               # nitrogen valve state (GPIO13)
        self._bofa_on = False             # BOFA extraction (PCA ch 10)
        self._door_abort_ts = None        # when the door-open safety last fired
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
            # temperature-sensor supervision (see SENSOR_OPEN_ALERT_SEC)
            self._sensor_open_since = {}  # sensor name -> time.time() it went open
            self._sensor_open_logged = set()  # open past SENSOR_GLITCH_SEC and logged once
            self._sensor_alerts = set()   # active registry codes (9001 / 9050)
            self._sensor_details = {}     # code -> which sensor (alertDetails)
            self._sensor_check(startup=True)
            # fan wear supervision (see FAN_HEALTH_DEFAULTS / components.json)
            self._fan_health = {}         # fan -> {duty, rpm, expected, deficitPct, status, since}
            self._fan_duty_seen = {}      # fan -> (duty, time it was last changed)
            self._fan_below_since = {}    # fan -> (level, time.time() first below)
            self._fan_alerts = {}         # code -> detail text (active)
            self._fan_critical = set()    # fans latched critical (block processes)
            self._fan_override = set()    # fans the operator chose to run WITHOUT ("continue anyway"): reported, never acted on
            # LED connection supervision (see LED_HEATING_DEFAULTS)
            self._led_heat = {}           # led -> thermal window {base, lit_sec, lit_at, last_lit, verdict}
            self._led_health = {}         # led -> {lit, intensity, baseline, rise, litSec, status}
            self._led_failed = {}         # led -> detail text (latched until it heats again)
            self._led_dropped = {}        # led -> detail text (fell mid-process, latched until it recovers)
            self._led_alerts = {}         # code -> detail text (active)
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
            self._manual_heat = False     # True only for Settings-slider heating
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
            self._set_cool_led_fans(False)  # release the FAST-cool LED-fan boost
        try:
            with self.sys.lock:
                chamber = self.sys.io.read_temp('TEMP_CHAMBER')['temp']
        except Exception:                 # noqa: BLE001
            chamber = None
        door_open = self.sys.door_open()
        # fans = commanded duty % (same meaning as the simulation payload);
        # the measured tachometer readings go in fanRpm.
        fan_rpm, fan_rpm_each = {}, {}
        for ui_name, group in FAN_GROUPS.items():
            vals = []
            for name in group:
                r = self.sys.read_rpm(name)
                fan_rpm_each[name] = int(r) if r else 0
                if r is not None:
                    vals.append(int(r))
            fan_rpm[ui_name] = min(vals) if vals else 0    # the WORST fan of the group: a stopped LED fan shows as 0, not hidden behind its neighbours
        led_temps = {}
        for name, sensor in LED_TEST_SENSORS:
            key = name.split()[0].lower()          # 'Left LED' -> 'left'
            try:
                with self.sys.lock:
                    led_temps[key] = round(self.sys.io.read_temp(sensor)['temp'], 1)
            except Exception:             # noqa: BLE001
                led_temps[key] = None
        for key, sensor in LED_SECOND_SENSORS:
            try:
                with self.sys.lock:
                    led_temps[key] = round(self.sys.io.read_temp(sensor)['temp'], 1)
            except Exception:             # noqa: BLE001
                led_temps[key] = None
        n2p = self._read_pressure()
        target = None
        if self.temp.active:
            target = heat.get('target')
        elif cool.get('active'):
            target = cool.get('target')
        return {
            'chamberTemp': chamber if chamber is not None else heat.get('temp'),
            'targetTemp': target,
            # Automatic internet watch (StatusLeds._net_watch): True/False,
            # or null when the status thread is not running.
            'internetOk': (bool(self.status_leds._internet_ok)
                           if self.status_leds else None),
            # door_open(): True=open, False=closed, None=sensor unreadable.
            # Report null on unreadable so the UI keeps its last known state
            # instead of falsely flipping to "door open".
            'doorClosed': None if door_open is None else (door_open is False),
            # True from the door-open abort until the user acknowledges the
            # alert (or starts a new process) - the strip stays red meanwhile
            'doorAborted': bool(self._door_abort_ts),
            # Internet reachability (StatusLeds background check, ~5s cadence)
            'internetOk': (self.status_leds._internet_ok
                           if self.status_leds else True),
            'isHeating': bool(self.temp.active),
            'isCooling': bool(cool.get('active')),
            'coolingMode': self._cooling_mode,
            'uvOn': self._uv['on'],
            'uvIntensity': self._uv['intensity'],          # logical system power %
            'uvWavelength': self._uv['wavelength'],
            'uvOutputs': self._uv.get('outputs'),          # per-zone physical %
            'ventOn': self._vent_on,                       # no-heat UV fresh-air vent

            'damperOpen': self._damper_open,
            'damperDriver': self._damper_driver(),         # 'pio' (hardware-timed) / 'lgpio' (software PWM)
            'fans': dict(self._fan_duty),
            'fanRpm': fan_rpm,
            'fanRpmEach': fan_rpm_each,                    # every tachometer fan by name
            'fanOverride': sorted(self._fan_override),     # fans the operator chose to continue without
            'stripMode': getattr(self.status_leds, 'mode', None) if self.status_leds else None,   # what the RGB strip shows right now
            'uiAlerts': dict(getattr(self, '_ui_alerts', {}) or {}),
            'ledTemps': led_temps,
            'nitrogenActive': self._n2_on,
            # SMC ISE20 analog pressure sensor on U7 AIN3 (components.json
            # pressure_sensor): {volts, mpa, bar, on, saturated, mode, setPointMPa}
            # or null when the ADC read fails; n2LinePressure (bar) feeds the
            # Settings 6 bar guard and is null while the reading is not usable
            'n2Pressure': n2p,
            'n2LinePressure': (n2p or {}).get('bar'),
            'bofaOn': self._bofa_on,
            'atTemp': bool(heat.get('at_temp')),
            'heaterPwm': heat.get('pwm'),         # commanded average power %
            'heaterOut': heat.get('heater_out'),  # element ON right now (delta-sigma)
            'coolingRate': cool.get('rate_meas'),
            'coolingFanPwm': cool.get('pwm') if cool.get('active') else None,
            'faults': {
                'heater': self.temp.fault or self.sys.heater_fault,
                'cooling': cool.get('fault'),
                'led': self.sys.led_fault,
            },
            'sensors': self.sensors_state(),       # per-NTC ok / open seconds
            'fanHealth': dict(self._fan_health),   # per-fan rpm vs nominal
            'ledHealth': dict(self._led_health),   # per-panel thermistor rise while lit
            'alerts': sorted(self._sensor_alerts | set(self._fan_alerts)
                             | set(self._led_alerts)),  # active registry codes
            'alertDetails': {**self._sensor_details, **self._fan_alerts, **self._led_alerts},  # code -> which sensor / fan / panel
            'hwSource': 'io_controller',
        }

    # ------------------------------------------------------------------
    #  UV LEDs (405nm cure / 450nm bleaching, via the wavelength gating)
    # ------------------------------------------------------------------
    def set_uv(self, on, intensity=0, wavelength=None, factors=None):
        """`intensity` is the CALIBRATED SYSTEM LED POWER (0-100%). This is
        the single calibration choke point: each zone is driven at
        clamp(intensity x its Developer-Mode factor) — led_calibration.py —
        so 100% system power means 100% of the calibrated system, not raw
        PWM. Zones keep reporting the logical system power upstream.
        `factors` overrides the saved factors (Developer Mode preview only)."""
        with self._op:
            if not on:
                self.sys.all_leds_off()
                self._uv = {'on': False, 'intensity': 0, 'wavelength': None,
                            'outputs': None}
                return True, None
            mode = '450nm' if wavelength == 450 else '405nm'
            ok, why = self.sys.select_mode(mode)   # all LEDs off, GPIO17 set + verified
            if not ok:
                return False, why
            try:
                import led_calibration
                factors = factors or led_calibration.get_factors()
                zone_for = led_calibration.zone_for_led
            except Exception as e:        # noqa: BLE001 - never block UV on this
                print(f'[HW] LED calibration unavailable ({e}) - factors 1.0',
                      flush=True)
                factors, zone_for = factors or {}, lambda _led: None
            ok, why = self._led_fan_preflight(mode)   # every LED cooling fan must spin before an LED goes on
            if not ok:
                return False, why
            lit, outputs = [], {}
            for led in self.sys.allowed_leds(mode):
                zone = zone_for(led)
                factor = factors.get(zone, 1.0) if zone else 1.0
                out = min(100.0, max(0.0, float(intensity) * factor))
                if self.sys.set_led_brightness(led, out):
                    lit.append(led)
                    if zone:
                        outputs[zone] = round(out, 2)
            if not lit:
                return False, self.sys.led_fault or 'no LED could be enabled'
            self._uv = {'on': True, 'intensity': int(intensity),
                        'wavelength': 450 if mode == '450nm' else 405,
                        'outputs': outputs}
            return True, None

    def set_ui_alerts(self, critical, warning):
        """The UI's undismissed notification counts (Alerts screen): they drive the RGB strip — critical -> pulsing
        red, warning -> pulsing yellow, none -> solid green. Reported on every change and as a 30 s heartbeat."""
        self._ui_alerts = {'critical': max(0, int(critical)), 'warning': max(0, int(warning)), 'at': time.time()}
        return True, None

    def set_fan_override(self, fan, on=True):
        """The operator chose to continue WITHOUT this fan (UI dialog "Continue anyway"): the fan keeps being
        measured and reported, but it no longer stops outputs, blocks a start or fails the LED pre-flight.
        Cleared by the UI when the process ends. Logged."""
        if fan == 'all':
            fans = [f for g in FAN_GROUPS.values() for f in g]
        elif fan in FAN_GROUPS:
            fans = list(FAN_GROUPS[fan])
        elif fan in self.PCA_CHANNELS:
            fans = [fan]
        else:
            return False, f'unknown fan: {fan}'
        for f in fans:
            if on:
                self._fan_override.add(f); self._fan_critical.discard(f)
            else:
                self._fan_override.discard(f)
        if not self._fan_critical - self._fan_override:
            self._fan_alerts.pop(ERR_FAN_FAILURE, None)
        if on:
            self._fan_alerts.pop(ERR_LED_FAN_STOPPED, None)
        print(f"[FAN] override {'ON' if on else 'off'} for {', '.join(fans)} (operator: continue anyway)", flush=True)
        return True, None

    def _led_fan_preflight(self, mode):
        """Before the LEDs go on: spin the cooling fan of every LED about to be
        lit, measure each tachometer and refuse — code 9003, the fan named — if
        one does not turn. An LED never runs without its fan. Skipped while the
        LEDs are already on and for 30 s after a pass (the same command is
        often re-sent)."""
        now = time.time()
        if self._uv.get('on') or now - getattr(self, '_led_fan_ok_at', 0) < 30:
            return True, None
        fans = []
        for led in self.sys.allowed_leds(mode):
            fan = (getattr(self.sys, 'leds', {}).get(led) or {}).get('fan')
            if fan and fan in self.PCA_CHANNELS and fan not in fans:
                fans.append(fan)
        if not fans:
            return True, None
        min_rpm = float(self._fan_cfg().get('led_fan_min_rpm', 100))
        with self.sys.lock:
            for fan in fans:
                self.sys.io.pca.set_duty(self.PCA_CHANNELS[fan], 100)
        time.sleep(1.5)                                    # spin-up
        stopped = []
        for fan in fans:
            rpm = self.sys.measure_rpm(fan, window=0.5)
            if fan in self._fan_override:
                continue                                   # "continue anyway" chosen for this fan
            if rpm is None or rpm < min_rpm:
                stopped.append(f"{fan} ({'?' if rpm is None else int(rpm)} RPM)")
        if stopped:
            with self.sys.lock:
                for fan in fans:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[fan], 0)
            why = f"[{ERR_LED_FAN_STOPPED}] LED cooling fan not spinning: {', '.join(stopped)} - job start refused"
            self._fan_alerts[ERR_LED_FAN_STOPPED] = why
            print(f'[FAN] {why}', flush=True)
            return False, why
        self._fan_alerts.pop(ERR_LED_FAN_STOPPED, None)
        self._led_fan_ok_at = now
        return True, None

    # ------------------------------------------------------------------
    #  UV-only ventilation (no-heat cure): damper + intake fan together
    # ------------------------------------------------------------------
    def set_ventilation(self, on):
        """Fresh-air ventilation for a UV-only (no chamber heating) step:
        damper OPEN + chamber intake fan at VENT_FAN_PWM, pulling outside air
        like cooling's airflow. Refused while the cooling loop owns the fan."""
        want = bool(on)
        if want == self._vent_on:
            return True, None
        if want and self.sys.cooling_status().get('active'):
            return False, 'cooling owns the airflow while it is active'
        pwm = self.sys.config.get('ventilation', {}).get('fan_pwm', VENT_FAN_PWM)
        try:
            pwm = max(0, min(100, float(pwm)))
        except (TypeError, ValueError):
            pwm = VENT_FAN_PWM
        if want:
            if pwm <= 0:
                return False, 'ventilation disabled (ventilation.fan_pwm = 0)'
            ok, why = self.set_damper(True)
            if not ok:
                return False, why
            ok, why = self.set_fan_speed('chamber_intake', pwm)
            if not ok:
                self.set_damper(False)
                return False, why
        else:
            self.set_fan_speed('chamber_intake', 0)
            self.set_damper(False)
        self._vent_on = want
        state = f'ON (damper open, intake {pwm:.0f}%)' if want else 'OFF'
        print(f'[API] UV ventilation -> {state}', flush=True)
        return True, None

    # ------------------------------------------------------------------
    #  Heating / drying (closed loop, heater safety pre-flight inside)
    # ------------------------------------------------------------------
    def _start_dry_fan(self):
        """Chamber intake/cooling fan ON at DRY_INTAKE_FAN_PWM for the drying step."""
        self._dry_fan_on = True
        ok, why = self.set_fan_speed('chamber_intake', DRY_INTAKE_FAN_PWM)
        print(f'[API] drying intake fan -> {DRY_INTAKE_FAN_PWM}% '
              f'({"ok" if ok else "FAILED: " + str(why)})', flush=True)

    def _stop_dry_fan(self):
        """Turn the drying intake fan off when leaving the drying step."""
        if self._dry_fan_on:
            self._dry_fan_on = False
            self.set_fan_speed('chamber_intake', 0)
            print('[API] drying intake fan -> 0% (step ended)', flush=True)

    def heat_to_target(self, target_c):
        ok, why = self.sensor_preflight()   # required NTCs must read (9001)
        if not ok:
            return False, why
        with self._op:
            self._drying = False
            self._stop_dry_fan()          # not drying anymore
            self._manual_heat = False     # program heating, not the manual slider
            self._door_abort_ts = None    # new process: clear the door abort
            self.set_uv(False)
            self.sys.stop_cooling('user')
            self.set_ventilation(False)   # release a UV-only vent (fan + damper)
            self.set_damper(False)        # vent stays closed while heating
            return self.temp.start(target_c)

    def dry_to_target(self, target_c):
        """Drying = the same closed-loop heating, plus, the moment the chamber
        reaches the target temperature (_damper_watch): the damper OPENS and
        the chamber intake/cooling fan turns on at DRY_INTAKE_FAN_PWM (30%)
        together - venting the moisture. Both stay on for the rest of the step
        and turn off when any other step takes over. During the ramp the damper
        is closed and the intake fan is off, so heating is not slowed."""
        ok, why = self.sensor_preflight()   # required NTCs must read (9001)
        if not ok:
            return False, why
        with self._op:
            self._drying = False
            self._manual_heat = False     # program heating, not the manual slider
            self._door_abort_ts = None    # new process: clear the door abort
            self.set_uv(False)
            self.sys.stop_cooling('user')
            self.set_ventilation(False)   # release a UV-only vent (fan + damper)
            self.set_damper(False)        # closed until the target is reached
            ok, why = self.temp.start(target_c)
            self._drying = bool(ok)       # arm the at-temperature damper + fan
            return ok, why

    def _damper_watch(self):
        """When an armed DRYING step reaches its target temperature: open the
        damper AND turn the chamber intake fan on at 30% together, to vent the
        moisture. One-shot per drying step; every other state keeps the damper
        closed and the fan off (cooling mode owns them while cooling). Never
        dies."""
        while True:
            time.sleep(1.0)
            try:
                if (self._drying and self.temp.active
                        and self.temp.status().get('at_temp')):
                    self._drying = False          # fire once per drying step
                    ok, why = self.set_damper(True)
                    if ok:
                        self._start_dry_fan()     # fan comes on WITH the damper
                    print('[API] drying at target: damper OPEN + intake fan 30%'
                          if ok else f'[API] drying damper open failed: {why}')
            except Exception:             # noqa: BLE001 - watcher must survive
                pass

    def set_target_temp(self, target_c):
        """Manual chamber setpoint: retarget the running loop, or start heating.
        Flags the heat as MANUAL so the RGB strip shows its dedicated solid
        color instead of the cure-program animation."""
        with self._op:
            if self.temp.active:
                self.temp.set_target(target_c)
                self._manual_heat = True
                return True, None
            ok, why = self.temp.start(target_c)
            self._manual_heat = bool(ok)
            return ok, why

    def stop_heating(self):
        self._manual_heat = False
        self.temp.stop('user')            # heater off now; fan cooldown run-on continues
        return True, None

    # ------------------------------------------------------------------
    #  Cure / bleaching = heating + UV together
    # ------------------------------------------------------------------
    def cure_uv(self, target_c, intensity, wavelength):
        ok, why = self.sensor_preflight()   # required NTCs must read (9001)
        if not ok:
            return False, why
        with self._op:
            self._drying = False
            self._stop_dry_fan()          # not drying anymore
            self._manual_heat = False     # program heating, not the manual slider
            self._door_abort_ts = None    # new process: clear the door abort
            self.sys.stop_cooling('user')
            self.set_ventilation(False)   # release a UV-only vent (fan + damper)
            self.set_damper(False)        # vent stays closed while curing
            ok_h, why_h = self.temp.start(target_c)
            ok_u, why_u = self.set_uv(True, intensity, wavelength)
            if ok_h and ok_u:
                return True, None
            problems = [p for p in (why_h, why_u) if p]
            return False, '; '.join(problems) or 'cure blocked'

    def cure_uv_only(self, intensity, wavelength, vent=False):
        """UV exposure with NO chamber heating. The heater is stopped; only
        the LEDs run (through the calibration layer in set_uv), plus, when
        `vent` is requested, the fresh-air ventilation: damper open + chamber
        intake fan — outside air flowing through the chamber like cooling's
        airflow, without a cooling loop. A ventilation failure never blocks
        the UV step itself (it is airflow comfort, not a safety interlock)."""
        ok, why = self.sensor_preflight()   # required NTCs must read (9001)
        if not ok:
            return False, why
        with self._op:
            self._drying = False
            self._stop_dry_fan()          # not drying anymore
            self._manual_heat = False
            self._door_abort_ts = None    # new process: clear the door abort
            self.sys.stop_cooling('user')
            self.temp.stop('user')        # heater off; fan cooldown run-on continues
            ok, why = self.set_uv(True, intensity, wavelength)
            if not ok:
                return False, why
            ok_v, why_v = self.set_ventilation(bool(vent))
            if vent and not ok_v:
                print(f'[API] UV-only ventilation unavailable: {why_v}', flush=True)
            return True, None

    # ------------------------------------------------------------------
    #  Cooling (fixed chamber-fan duty per mode; damper + fans owned by it)
    # ------------------------------------------------------------------
    def _set_cool_led_fans(self, on):
        """FAST-cool boost: run/release the four LED-cooling fans together
        with the chamber fan. Best-effort - a fan write error must never
        block the cooling mode itself. No-op when nothing changes, and the
        fans are never touched while any LED is lit (their fans then belong
        to the LED-cooling logic)."""
        if bool(on) == self._cool_led_fans:
            return
        if getattr(self.sys, '_leds_on', None):
            return                        # LED logic owns these fans right now
        pwm = self.sys.config.get('cooling', {}).get('fast_led_fan_pwm',
                                                     FAST_COOL_LED_FAN_PWM)
        try:
            pwm = max(0, min(100, float(pwm)))
        except (TypeError, ValueError):
            pwm = FAST_COOL_LED_FAN_PWM
        if on and pwm <= 0:
            return                        # boost disabled in components.json
        try:
            with self.sys.lock:
                for name in FAN_GROUPS['led_cooling']:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[name],
                                             pwm if on else 0)
        except Exception as e:            # noqa: BLE001 - I2C write failed
            print(f'[HW] FAST-cool LED-fan boost failed: {e}', flush=True)
            return
        self._cool_led_fans = bool(on)
        self._fan_duty['led_cooling'] = int(pwm) if on else 0

    def cool_to_target(self, target_c, mode):
        ok, why = self.sensor_preflight()   # required NTCs must read (9001)
        if not ok:
            return False, why
        with self._op:
            self._drying = False          # cooling owns the damper from here
            self._dry_fan_on = False      # cooling takes over FAN_COOLING itself
            self._manual_heat = False
            self._door_abort_ts = None    # new process: clear the door abort
            self.set_ventilation(False)   # cooling takes over damper + intake fan
            pwms = dict(COOLING_MODE_PWMS)
            pwms.update(self.sys.config.get('cooling', {}).get('mode_pwms', {}))
            pwm = pwms.get(mode, pwms['medium'])
            try:
                already_cooling = bool(self.sys.cooling_status().get('active'))
            except Exception:             # noqa: BLE001
                already_cooling = False
            # Only tear the heater down on a FRESH entry into cooling. Doing it
            # while cooling is already running (a mode change) runs the heater's
            # end-of-process routine, which CLOSES the damper and kills the
            # cooling fans - and start_cooling's already-running path would only
            # update the fan duty, never reopening the damper. So when already
            # cooling we just retarget/re-rate: the damper stays open.
            if not already_cooling:
                self.set_uv(False)
                # Immediate full heater OFF (no fan run-on): cooling owns the
                # heater fan for the whole mode and reopens the damper itself.
                self.temp.shutdown('user')
            ok, why = self.sys.start_cooling(pwm, target_c)
            if ok:
                self._cooling_mode = mode
                self._damper_open = True
                # FAST mode: the LED-cooling fans join in; any other mode
                # (including a fast->medium/slow change) releases them.
                self._set_cool_led_fans(mode == 'fast')
            return ok, why

    def set_rgb(self, on, color=None, brightness=None):
        """Manual RGB strip override (/api/rgb): a solid color while on; the
        automatic status colors pause meanwhile and repaint as soon as the
        override is released (StatusLeds watches bridge._rgb_state)."""
        leds = self.status_leds
        if not leds:
            return False, 'RGB strip unavailable'
        if not on:
            self._rgb_state = {'on': False, 'color': None, 'brightness': None}
            leds._last_frame = None       # status loop repaints on its next tick
            return True, None
        try:
            from io_controller import parse_rgb_color
            rgb = parse_rgb_color(color or 'white')
        except Exception as e:            # noqa: BLE001 - bad color name/hex
            return False, str(e)
        br = leds.brightness if brightness is None else max(0.0, min(100.0, float(brightness)))
        self._rgb_state = {'on': True, 'color': color or 'white', 'brightness': br}
        try:
            leds.leds.fill(rgb, br)
        except Exception as e:            # noqa: BLE001 - strip write failed
            self._rgb_state = {'on': False, 'color': None, 'brightness': None}
            return False, f'strip write failed: {e}'
        return True, None

    def _read_pressure(self):
        """One reading of the N2 line pressure sensor for /api/state."""
        try:
            with self.sys.lock:
                r = self.sys.io.read_pressure(self.sys.config)
        except Exception:                 # noqa: BLE001 - ADC / config problem
            return None
        return {'volts': round(r['voltage'], 3),
                'mpa': round(r['mpa'], 3) if r['mpa'] is not None else None,
                'bar': round(r['bar'], 2) if r['bar'] is not None else None,
                'on': bool(r['on']), 'saturated': bool(r['saturated']),
                'mode': r['mode'], 'setPointMPa': r['set_point_mpa']}

    def door_abort(self):
        """SAFETY: the door opened while outputs were live. Kill EVERY output
        immediately - heater, UV, cooling, fans, nitrogen, BOFA, damper - and
        flag the abort so the UI stops the running program (doorAborted in
        /api/state). Fired by the StatusLeds status watchdog (every 1 s).
        This is the ONLY stop path with no heater-fan run-on."""
        with self._op:
            self.temp.shutdown('door open')   # heater + fan OFF now, no run-on
            self.stop_all()
            for fan in list(self._fan_duty):    # manual fan writes too
                self.set_fan_speed(fan, 0)
            self.set_bofa(False)
            self._door_abort_ts = time.time()
        print('[SAFETY] Door opened mid-process - ALL outputs forced OFF',
              flush=True)

    def ack_door_abort(self):
        """The user acknowledged the door-abort alert (Err 6016) in the UI -
        clear the flag so the status strip returns from red to normal."""
        self._door_abort_ts = None
        return True, None

    def stop_all(self, immediate=False):
        """Stop every cure output (heater, UV, cooling, nitrogen).

        The heater ELEMENT turns off right away in both cases; after heating,
        the heater fan always keeps running its cooldown run-on
        (cooldown_fan_pwm % for cooldown_sec, default 30% / 15 min) to carry
        residual heat off the element - including on a user abort. The only
        full-kill paths with NO run-on are door_abort() (safety) and
        shutdown() (process exit). `immediate` is kept for API compatibility;
        both values now behave the same."""
        with self._op:
            self._drying = False
            self._stop_dry_fan()
            self._manual_heat = False
            self.set_uv(False)
            self.set_nitrogen(False)
            self.sys.stop_cooling('user')
            self._set_cool_led_fans(False)  # release the FAST-cool LED-fan boost
            self.set_ventilation(False)   # release a UV-only vent (fan + damper)
            self.temp.stop('user')        # heater off now; fan run-on continues
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
        if on:
            # Opening the purge valve starts a process step, exactly like
            # heating / cure / cooling do: a door abort latched by an EARLIER
            # run must not kill a program whose first step is the N2 purge.
            self._door_abort_ts = None
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
    def cancel_heater_fan_cooldown(self):
        """Abort the heater-fan run-on that temperature_control starts when
        the heater goes off (30% then ALL fans OFF after cooldown_sec). The
        cancel itself ends with the all-fans-off write, so the caller must
        re-command its own fan duty afterwards. Refused while heating."""
        if self.temp.active or self.sys.is_heater_on():
            return False, 'heating is active'
        try:
            self.temp._cancel_cooldown()
        except Exception as e:            # noqa: BLE001
            return False, f'cancel failed: {e}'
        return True, None

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
        if fan == 'led_cooling' and self._cool_led_fans:
            return False, 'LED fans are boosting the fast cooling while it is active'
        try:
            with self.sys.lock:
                for name in names:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], percent)
        except Exception as e:            # noqa: BLE001 - I2C write failed
            return False, f'fan write failed: {e}'
        if fan in self._fan_duty:
            self._fan_duty[fan] = int(percent)
        return True, None

    def _damper_driver(self):
        """Which pulse generator drives the damper servo: 'pio' (RP1 PIO,
        hardware-timed) or 'lgpio' (software PWM fallback); None until the
        servo has been created."""
        try:
            s = self.sys.io._servo
            return s.driver if s is not None else None
        except Exception:            # noqa: BLE001
            return None

    def set_damper(self, open_state):
        # Command the servo only when the position actually changes. Many code
        # paths re-assert "damper closed" (every heat/dry/cure/stop) - without
        # this guard each one re-drives the servo and it buzzes. The first call
        # (self._damper_open is None) always goes through to set a known state.
        want = bool(open_state)
        if self._damper_open is want:
            return True, None
        try:
            self.sys.cooling._set_damper(want)
        except Exception as e:            # noqa: BLE001 - servo unavailable
            return False, f'damper failed: {e}'
        self._damper_open = want
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
    def _fan_nominal_points(self, fan, cfg):
        """The measured duty->RPM points this fan is judged against: the
        damper-OPEN table while the damper is open (an open duct slows the
        intake fan), otherwise the regular nominal_rpm table."""
        if self._damper_open:
            open_pts = (cfg.get('nominal_rpm_damper_open') or {}).get(fan)
            if open_pts:
                return open_pts
        return (cfg.get('nominal_rpm') or {}).get(fan)

    def _fan_verdict(self, cfg, fan, rpm, duty, min_rpm):
        """OK / WARN / FAIL for one measured fan, on the SAME policy as the wear
        supervision (_fan_tick): the reading is compared with the nominal RPM at
        the duty the fan was measured at. Before 0.9.93 the test only asked
        "is it turning at all" (>= min_fan_rpm), so a fan at a third of its
        nominal speed - the very wear 9051/9002 exist for - still said OK."""
        expected = self._fan_expected_rpm(self._fan_nominal_points(fan, cfg), duty)
        entry = {'rpm': rpm, 'duty': int(round(duty)),
                 'expected': int(expected) if expected else None,
                 'deficitPct': None, 'status': 'OK'}
        if rpm < min_rpm:                      # not turning at all (disconnected, seized)
            entry['status'] = 'FAIL'
            return entry
        if not expected:
            return entry                       # no measured nominal for this fan: only the floor applies
        deficit = round((1 - rpm / expected) * 100, 1)
        crit = float((cfg.get('critical_below_pct_by_fan') or {}).get(fan, cfg['critical_below_pct']))
        entry['deficitPct'] = deficit
        entry['status'] = ('FAIL' if deficit >= crit
                           else 'WARN' if deficit >= float(cfg['warn_below_pct']) else 'OK')
        return entry

    @staticmethod
    def _fan_test_message(fans, names, min_rpm):
        """One line per fan that is not OK: what it read against what it owes."""
        parts = []
        for name in names:
            f = fans[name]
            if f['rpm'] < min_rpm or not f['expected']:
                parts.append(f"{name}: {f['rpm']} RPM — not spinning")
            else:
                parts.append(f"{name}: {f['rpm']} RPM, {f['expected']} RPM expected at "
                             f"{f['duty']} % duty ({f['deficitPct']:.0f} % below nominal)")
        return ', '.join(parts) or None

    def run_fan_test(self, fan=None):
        """Spin every fan of the requested group up (unless a control loop
        already owns it) and measure the real tachometer RPM of EACH fan.
        `fan` is a UI group name (led_cooling / chamber_intake / chamber_heating);
        default = heater fan. The group fails if any one of its fans fails, and
        the failing fans are named — an LED cooling fan hidden behind three
        healthy neighbours used to pass this test.
        Each reading is judged against the fan's nominal RPM at the duty it was
        measured at (fan_health): FAIL below critical_below_pct (or not turning
        at all), WARN below warn_below_pct, otherwise OK — the same thresholds
        the wear supervision raises 9002 / 9051 on."""
        group = [f for g in FAN_GROUPS.values() for f in g] if fan == 'all' else FAN_GROUPS.get(fan or 'chamber_heating')
        if not group:
            return {'rpm': 0, 'status': 'FAIL', 'message': f'unknown fan: {fan}'}
        min_rpm = self.sys.heater_cfg().get('min_fan_rpm', 100)
        cfg = self._fan_cfg()
        try:
            heat = self.temp.status()
        except Exception:                 # noqa: BLE001
            heat = {}
        try:
            cool = self.sys.cooling_status()
        except Exception:                 # noqa: BLE001
            cool = {}
        with self._op:
            busy, duty_at = {}, {}
            for name in group:
                # a fan already being driven (heating, cooling, a heater-fan cooldown run-on, lit LEDs) is measured as it
                # runs and left alone — the test must never switch off a fan that a process relies on
                prev = self._pca_duty(name)
                if prev is not None:
                    busy[name] = prev > 0
                elif name == 'FAN_HEATER':
                    busy[name] = self.sys.is_heater_on() or self.temp.active
                elif name == 'FAN_COOLING':
                    busy[name] = bool(self.sys.cooling_status().get('active'))
                else:
                    busy[name] = False
                # the duty the reading is judged at: its own while a process drives it
                # (a cooldown run-on at 30 % must not be measured against the 100 % nominal),
                # 100 % for every fan the test drives itself
                duty_at[name] = (prev if prev is not None
                                 else self._fan_commanded_duty(name, heat, cool)) if busy[name] else 100.0
            with self.sys.lock:
                for name in group:
                    if not busy[name]:
                        self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], 100)
            time.sleep(2.0)           # spin-up
            # read every tachometer at the same time (each has its own pulse counter): 1 s for the whole group, not 1 s per fan
            measured = {}
            def _measure(name):
                measured[name] = self.sys.measure_rpm(name, window=1.0)
            workers = [threading.Thread(target=_measure, args=(name,), daemon=True) for name in group]
            for w in workers: w.start()
            for w in workers: w.join(timeout=5.0)
            fans = {}
            for name in group:
                rpm = int(measured.get(name) or 0)
                fans[name] = self._fan_verdict(cfg, name, rpm, duty_at[name], min_rpm)
            with self.sys.lock:
                for name in group:
                    if not busy[name]:
                        self.sys.io.pca.set_duty(self.PCA_CHANNELS[name], 0)
        failed = [n for n, f in fans.items() if f['status'] == 'FAIL']
        warned = [n for n, f in fans.items() if f['status'] == 'WARN']
        worst = min(f['rpm'] for f in fans.values())
        return {'rpm': worst, 'status': 'FAIL' if failed else 'WARN' if warned else 'OK', 'fans': fans,
                'message': self._fan_test_message(fans, failed + warned, min_rpm)}

    def run_led_test(self, seconds=15.0, intensity=100, wavelength=405, min_rise_c=0.8, precool_above_c=30.0, precool_s=20.0):
        """Settings > LED Test, in three stages:
          1. every LED thermistor must give a valid reading (and be under the max);
          2. ALL panels on at `intensity` % for `seconds` (15 s: a panel rises ~0.2 C/s at 100 %);
          3. every thermistor must have RISEN by at least `min_rise_c` — a panel whose
             sensor does not warm is not emitting (or its sensor is not on the module).
        LEDs off at the end whatever happens. Refused while a process runs.
        The answer names the sensors that did not read / did not heat up."""
        def read_all():
            out = {}
            for name, sensor in LED_TEST_SENSORS:
                try:
                    with self.sys.lock:
                        out[name] = self.sys.io.read_temp(sensor)['temp']
                except Exception:         # noqa: BLE001
                    out[name] = None
            return out
        if self._uv.get('on') or self.temp.active or self.sys.cooling_status().get('active'):
            return {'ok': False, 'status': 'FAIL', 'stage': 'busy', 'results': [],
                    'message': 'a process is running - run the LED test when the machine is idle'}
        start = read_all()
        # panels still warm from a previous run (>= precool_above_c) cool faster than a small heat input warms them, so
        # a lit panel could look cold: wait precool_s with the LEDs off, then take the real starting point
        precooled = False
        if any(v is not None and v >= precool_above_c for v in start.values()):
            # the four LED cooling fans at full speed for the cool-down (they are off while the LEDs are off), then back
            led_fans = FAN_GROUPS.get('led_cooling', [])
            prev = {f: (self._pca_duty(f) or 0.0) for f in led_fans}
            with self.sys.lock:
                for f in led_fans:
                    self.sys.io.pca.set_duty(self.PCA_CHANNELS[f], 100)
            try:
                time.sleep(float(precool_s))
            finally:
                with self.sys.lock:
                    for f in led_fans:
                        self.sys.io.pca.set_duty(self.PCA_CHANNELS[f], prev[f])
            start = read_all(); precooled = True
        results = [{'name': n, 'temp': round(t, 1) if t is not None else None,
                    'status': 'OK' if (t is not None and t < LED_TEST_MAX_TEMP) else 'FAIL'} for n, t in start.items()]
        bad = [r['name'] for r in results if r['status'] == 'FAIL']
        if bad:
            return {'ok': True, 'status': 'FAIL', 'stage': 'sensors', 'results': results,
                    'message': 'no valid temperature reading: ' + ', '.join(bad)}
        ok, why = self.set_uv(True, intensity, wavelength)     # door interlock + LED-fan pre-flight apply
        if not ok:
            return {'ok': True, 'status': 'FAIL', 'stage': 'uv', 'results': results,
                    'message': f'LEDs could not be switched on: {why}'}
        try:
            time.sleep(float(seconds))
            end = read_all()
        finally:
            self.set_uv(False)
        # at 450 nm the door panel's string leaves too little heat at its sensor to judge (+0.5 C in 30 s from cold on
        # the test unit, against +1.7 … +2.3 C on the other panels): its rise is reported, not judged
        not_judged = {'Door LED'} if int(wavelength) == 450 else set()
        results = []
        for name, _sensor in LED_TEST_SENSORS:
            t0, t1 = start.get(name), end.get(name)
            rise = None if (t0 is None or t1 is None) else round(t1 - t0, 1)
            status = 'INFO' if name in not_judged else ('OK' if (rise is not None and rise >= min_rise_c) else 'FAIL')
            results.append({'name': name, 'start': round(t0, 1) if t0 is not None else None,
                            'temp': round(t1, 1) if t1 is not None else None, 'rise': rise, 'status': status})
        cold = [r for r in results if r['status'] == 'FAIL']
        note = ', '.join(f"{r['name']} not judged at {int(wavelength)} nm ({'?' if r['rise'] is None else f'{r['rise']:+.1f}'} C)" for r in results if r['status'] == 'INFO')
        return {'ok': True, 'status': 'FAIL' if cold else 'OK', 'stage': 'heating', 'seconds': seconds, 'wavelength': int(wavelength), 'precooled': precooled,
                'intensity': intensity, 'min_rise_c': min_rise_c, 'results': results,
                'message': ('did not heat up: ' + ', '.join(f"{r['name']} ({'?' if r['rise'] is None else f'{r['rise']:+.1f}'} C in {int(seconds)} s)" for r in cold) + (f'; {note}' if note else '')) if cold else (note or None)}

    # ------------------------------------------------------------------
    #  Temperature-sensor supervision (open-circuit NTC detection)
    # ------------------------------------------------------------------
    def _sensor_read_ok(self, name):
        """True when the NTC reads a plausible temperature; False when it is
        open (pull-up rail -> no temperature) or outside the valid range."""
        try:
            with self.sys.lock:
                t = self.sys.io.read_temp(name)['temp']
        except Exception:                 # noqa: BLE001 - I2C / math error = not ok
            return False
        return t is not None and SENSOR_VALID_C[0] <= t <= SENSOR_VALID_C[1]

    def _heating_wanted(self):
        """Heating is active, commanded, or was just refused / switched off by the heater safety."""
        try:
            return bool(self.temp.active or self.sys.is_heater_on() or self.sys.heater_fault or self.temp.fault)
        except Exception:                 # noqa: BLE001
            return False

    def _sensor_check(self, startup=False):
        """One supervision pass over all NTCs. Tracks how long each has been
        open and raises / clears the registry alert after SENSOR_OPEN_ALERT_SEC.
        Returns the set of sensor names currently open."""
        now = time.time()
        open_now = set()
        for name in list(CRITICAL_TEMP_SENSORS) + list(WARNING_TEMP_SENSORS):
            is_critical = name in CRITICAL_TEMP_SENSORS
            code = ERR_TEMP_SENSOR_DISCONNECTED if is_critical else ERR_LED_TEMP_SENSOR_DISCONNECTED
            if self._sensor_read_ok(name):
                if name in self._sensor_open_since:
                    if name in self._sensor_open_logged:
                        print(f'[SENSOR] {name} reads again', flush=True)
                    del self._sensor_open_since[name]
                self._sensor_open_logged.discard(name)
                continue
            since = self._sensor_open_since.setdefault(name, now)
            if now - since < SENSOR_GLITCH_SEC:
                continue                  # dropout shorter than the noise filter: not (yet) a problem
            open_now.add(name)
            # The heater's own thermistor (TEMP_CHAMBER) open while heating is active or commanded: the
            # heater safety has already switched the element off - raise 9001 right after the noise
            # filter so the screen pops the fault now, not a minute later
            if name == HEATER_THERMISTOR and code not in self._sensor_alerts and self._heating_wanted():
                self._sensor_alerts.add(code)
                self._sensor_details[str(code)] = HEATER_SENSOR_DETAIL
                print(f'[SENSOR] {name} open while heating -> heater OFF, Err {code} at once', flush=True)
            if startup or name not in self._sensor_open_logged:
                self._sensor_open_logged.add(name)
                kind = 'REQUIRED, processes blocked' if is_critical else 'LED sensor, warning only'
                print(f'[SENSOR] {"start-up check: " if startup else ""}{name} OPEN for {int(now - since)} s - {kind}', flush=True)
            if now - since >= SENSOR_OPEN_ALERT_SEC and code not in self._sensor_alerts:
                self._sensor_alerts.add(code)
                self._sensor_details[str(code)] = (HEATER_SENSOR_DETAIL if name == HEATER_THERMISTOR
                                                   else f'Temperature sensor disconnected: {name}')
                sev = 'critical' if is_critical else 'warning'
                print(f'[SENSOR] {name} open for {SENSOR_OPEN_ALERT_SEC:.0f}s -> Err {code} ({sev})', flush=True)
        # clear an alert only when every sensor of its class reads again
        for code, group in ((ERR_TEMP_SENSOR_DISCONNECTED, CRITICAL_TEMP_SENSORS),
                            (ERR_LED_TEMP_SENSOR_DISCONNECTED, WARNING_TEMP_SENSORS)):
            if code in self._sensor_alerts and not (open_now & set(group)):
                self._sensor_alerts.discard(code)
                self._sensor_details.pop(str(code), None)
                print(f'[SENSOR] Err {code} cleared - sensors read again', flush=True)
        return open_now

    def _sensor_tick(self):
        """Called every status_sec by the status loop."""
        self._sensor_check()

    # ------------------------------------------------------------------
    #  Fan wear supervision (tachometer RPM vs measured nominal)
    # ------------------------------------------------------------------
    def _fan_cfg(self):
        cfg = dict(FAN_HEALTH_DEFAULTS)
        try:
            from io_controller import load_component_config   # not a module global here
            c = load_component_config().get('fan_health', {})
            cfg.update({k: v for k, v in c.items() if not k.startswith('_')})
        except Exception:                 # noqa: BLE001 - keep defaults
            pass
        return cfg

    def _pca_duty(self, fan):
        """The duty last written to the fan's PCA channel, or None if the driver does not keep it."""
        cache = getattr(getattr(self.sys.io, 'pca', None), 'last_duty', None)
        ch = self.PCA_CHANNELS.get(fan)
        if cache is None or ch is None or ch not in cache:
            return None
        return float(cache[ch])

    def _fan_commanded_duty(self, fan, heat, cool):
        """What the fan is being driven at right now (0-100), from whichever
        loop owns it: heater fan by the heating loop (or its run-on), the
        intake fan by the cooling loop, LED fans by their lit LED; otherwise
        the last manual / group write."""
        real = self._pca_duty(fan)
        if real is not None:
            return real                   # what the channel is really driven at — a fan someone switched off is not "expected" to spin
        if fan == 'FAN_HEATER':
            if self.temp.active or self.sys.is_heater_on():
                return float(heat.get('fan_pwm') or 0)
            if heat.get('cooldown'):
                try:
                    return float(getattr(self.temp, 'cfg', {}).get('cooldown_fan_pwm', 30))
                except Exception:         # noqa: BLE001
                    return 30.0
            return float(self._fan_duty.get('chamber_heating', 0))
        if fan == 'FAN_COOLING':
            if cool.get('active'):
                return float(cool.get('pwm') or 0)
            return float(self._fan_duty.get('chamber_intake', 0))
        led = {'FAN_LEFT': 'LED_LEFT', 'FAN_RIGHT': 'LED_RIGHT',
               'FAN_BACK': 'LED_BACK', 'FAN_DOOR': 'LED_DOOR'}.get(fan)
        if led and led in getattr(self.sys, '_leds_on', set()):
            return float(self.sys.leds.get(led, {}).get('fan_speed', 100))
        return float(self._fan_duty.get('led_cooling', 0))

    @staticmethod
    def _fan_expected_rpm(points, duty):
        """Nominal RPM at `duty` from the measured duty->rpm points (linear
        interpolation; proportional below the lowest point)."""
        pts = sorted((float(k), float(v)) for k, v in (points or {}).items())
        if not pts:
            return None
        if duty <= pts[0][0]:
            return pts[0][1] * duty / pts[0][0]
        for (d0, r0), (d1, r1) in zip(pts, pts[1:]):
            if d0 <= duty <= d1:
                return r0 + (r1 - r0) * (duty - d0) / (d1 - d0)
        return pts[-1][1] * duty / pts[-1][0]

    def _fan_tick(self):
        """Once per status_sec: compare every tach fan to its nominal RPM at
        the commanded duty. Below nominal by warn_below_pct for persist_sec
        -> 9051 (replace fan); by critical_below_pct for persist_sec -> 9002:
        all outputs off, processes blocked, the fan named in the alert."""
        cfg = self._fan_cfg()
        warn = float(cfg['warn_below_pct'])
        by_fan = cfg.get('critical_below_pct_by_fan') or {}   # the heater fan stops at its own limit (user 2026-10-08)
        persist, settle = float(cfg['persist_sec']), float(cfg['settle_sec'])
        min_duty = float(cfg['min_eval_duty'])
        now = time.time()
        try:
            heat = self.temp.status()
        except Exception:                 # noqa: BLE001
            heat = {}
        try:
            cool = self.sys.cooling_status()
        except Exception:                 # noqa: BLE001
            cool = {}
        health = {}
        for fan in self.PCA_FANS:
            duty = self._fan_commanded_duty(fan, heat, cool)
            prev = self._fan_duty_seen.get(fan)
            if prev is None or abs(prev[0] - duty) > 0.5:
                self._fan_duty_seen[fan] = (duty, now)
            changed_at = self._fan_duty_seen[fan][1]
            rpm = self.sys.read_rpm(fan)
            rpm = int(rpm) if rpm is not None else None
            expected = self._fan_expected_rpm(self._fan_nominal_points(fan, cfg), duty) if duty > 0 else None
            entry = {'duty': duty, 'rpm': rpm, 'expected': int(expected) if expected else None,
                     'deficitPct': None, 'status': 'idle', 'since': None}
            evaluate = (duty >= min_duty and expected and rpm is not None
                        and now - changed_at >= settle)
            if evaluate:
                deficit = round((1 - rpm / expected) * 100, 1)
                # a fan that is not turning at all (disconnected, seized) is not wear: it trips after stopped_persist_sec, not persist_sec
                p_this = float(cfg.get('stopped_persist_sec', 5)) if rpm <= 0.05 * expected else persist
                entry['deficitPct'] = deficit
                crit = float(by_fan.get(fan, cfg['critical_below_pct']))
                level = 'critical' if deficit >= crit else 'warn' if deficit >= warn else 'ok'
                if level == 'ok':
                    self._fan_below_since.pop(fan, None)
                    entry['status'] = 'ok'
                else:
                    lvl0, since = self._fan_below_since.get(fan, (level, now))
                    # a deeper deficit keeps the earlier start; a shallower one restarts
                    if lvl0 == 'critical' and level == 'warn':
                        since = now
                    self._fan_below_since[fan] = (level, since)
                    entry['since'] = int(now - since)
                    entry['status'] = level if now - since >= p_this else f'{level}-pending'
                    if now - since >= p_this:
                        detail = (f'{fan}: {rpm} RPM measured, {int(expected)} RPM expected at '
                                  f'{duty:.0f} % duty ({deficit:.0f} % below nominal for '
                                  f'{int(now - since)} s)')
                        if fan in self._fan_override:
                            entry['status'] = 'overridden'      # the operator chose to continue without this fan: shown, not acted on
                        elif level == 'critical':
                            self._fan_alerts[ERR_FAN_FAILURE] = detail
                            if fan not in self._fan_critical:
                                self._fan_critical.add(fan)
                                print(f'[FAN] CRITICAL {detail} -> Err {ERR_FAN_FAILURE}: '
                                      f'stopping every output', flush=True)
                                try:
                                    self.stop_all(True)
                                except Exception as e:  # noqa: BLE001
                                    print(f'[FAN] stop_all failed: {e}', flush=True)
                        elif ERR_FAN_WEAR_WARNING not in self._fan_alerts \
                                or fan in self._fan_alerts[ERR_FAN_WEAR_WARNING]:
                            if ERR_FAN_WEAR_WARNING not in self._fan_alerts:
                                print(f'[FAN] WARNING {detail} -> Err {ERR_FAN_WEAR_WARNING}: '
                                      f'replace the fan', flush=True)
                            self._fan_alerts[ERR_FAN_WEAR_WARNING] = detail
            else:
                self._fan_below_since.pop(fan, None)
            health[fan] = entry
        self._fan_health = health
        # release the critical latch only after the fan has read OK for persist_sec
        for fan in list(self._fan_critical):
            e = health.get(fan, {})
            ok_for = self._fan_ok_since.get(fan) if hasattr(self, '_fan_ok_since') else None
            if e.get('status') == 'ok':
                if not hasattr(self, '_fan_ok_since'):
                    self._fan_ok_since = {}
                self._fan_ok_since.setdefault(fan, now)
                if now - self._fan_ok_since[fan] >= persist:
                    self._fan_critical.discard(fan)
                    self._fan_ok_since.pop(fan, None)
                    print(f'[FAN] {fan} back to nominal - critical latch released', flush=True)
            elif hasattr(self, '_fan_ok_since'):
                self._fan_ok_since.pop(fan, None)
        if not self._fan_critical and ERR_FAN_FAILURE in self._fan_alerts:
            self._fan_alerts.pop(ERR_FAN_FAILURE, None)
            print(f'[FAN] Err {ERR_FAN_FAILURE} cleared', flush=True)
        if ERR_FAN_WEAR_WARNING in self._fan_alerts and not any(
                e.get('status') in ('warn', 'critical') for e in health.values()):
            self._fan_alerts.pop(ERR_FAN_WEAR_WARNING, None)
            print(f'[FAN] Err {ERR_FAN_WEAR_WARNING} cleared', flush=True)

    def fan_issues_now(self):
        """Fans currently flagged (for the cure-history indication)."""
        return [{'fan': f, 'deficitPct': e.get('deficitPct'), 'critical': e.get('status') == 'critical'}
                for f, e in self._fan_health.items() if e.get('status') in ('warn', 'critical')]

    # ------------------------------------------------------------------
    #  LED connection supervision (thermistor rise while the panel is lit)
    # ------------------------------------------------------------------
    def _led_heat_cfg(self):
        cfg = dict(LED_HEATING_DEFAULTS)
        cfg['panels'] = dict(LED_PANEL_SENSORS)
        try:
            from io_controller import load_component_config
            c = load_component_config().get('led_heating', {})
            for k in LED_HEATING_DEFAULTS:
                if k in c:
                    cfg[k] = float(c[k])
            panels = c.get('panels')
            if isinstance(panels, dict) and panels:
                cfg['panels'] = {led: (LED_PANEL_LABELS.get(led, led), str(sensor))
                                 for led, sensor in panels.items()
                                 if led in LED_PANEL_LABELS and sensor}
        except Exception:                 # noqa: BLE001 - keep defaults
            pass
        return cfg

    def _led_heat_tick(self):
        """Once per status_sec: every supervised LED panel (Left / Right by
        default, via their regular thermistors) that is lit must warm that
        thermistor. Baseline = the panel temperature when its light started
        (a re-light within rest_sec continues the same window); after
        check_after_sec of accumulated light at >= min_eval_intensity % the
        rise must be >= min_rise_c, otherwise the panel is not being powered
        -> 9004 critical, the alert names the panel and says to check its
        connection. A panel latched failed clears as soon as it heats again.
        Once a panel has proved it heats, its peak is tracked: a fall of
        drop_c below the peak (chamber cooling taken off) for drop_persist_sec
        while still lit -> 9005 critical "panel fault", cleared when the
        panel climbs back to within drop_c/2 of its peak."""
        cfg = self._led_heat_cfg()
        min_int, check_after = cfg['min_eval_intensity'], cfg['check_after_sec']
        min_rise, rest = cfg['min_rise_c'], cfg['rest_sec']
        drop_c, drop_persist = cfg['drop_c'], cfg['drop_persist_sec']
        drop_settle = cfg['drop_settle_sec']
        now = time.time()
        uv = self._uv
        lit = set(getattr(self.sys, '_leds_on', set())) if uv.get('on') else set()
        intensity = float(uv.get('intensity') or 0) if uv.get('on') else 0.0
        chamber = None
        if lit:
            try:
                with self.sys.lock:
                    chamber = self.sys.io.read_temp('TEMP_CHAMBER')['temp']
            except Exception:             # noqa: BLE001
                chamber = None
        health = {}
        panels = cfg['panels']
        for led, (label, sensor) in panels.items():
            st = self._led_heat.get(led)
            is_lit = led in lit
            entry = {'lit': is_lit, 'intensity': intensity if is_lit else 0,
                     'baseline': None, 'rise': None, 'litSec': None, 'status': 'off'}
            if is_lit and intensity >= min_int:
                try:
                    with self.sys.lock:
                        t = self.sys.io.read_temp(sensor)['temp']
                except Exception:         # noqa: BLE001
                    t = None
                if t is None or not (SENSOR_VALID_C[0] <= t <= SENSOR_VALID_C[1]):
                    entry['status'] = 'no-sensor'   # open / invalid thermistor: not judged
                    health[led] = entry
                    continue
                if st is None or (st['lit_at'] is None and now - st['last_lit'] > rest):
                    st = {'base': t, 'lit_sec': 0.0, 'lit_at': now, 'last_lit': now,
                          'verdict': None, 'fail_at': check_after,
                          'peak': None, 'peak_chamber': None, 'int_seen': None,
                          'settle_until': 0.0, 'drop_since': None}
                elif st['lit_at'] is None:
                    # re-lit while still warm: same window (baseline kept), but
                    # the panel cooled during the gap - give it check_after_sec
                    # of light again before a 'not heating' verdict, and let it
                    # climb back before the peak is tracked again
                    st['lit_at'] = now
                    st['fail_at'] = st['lit_sec'] + check_after
                    # re-judge: the rise rule again (it must climb back), then
                    # the peak restarts from the re-light temperature at once -
                    # a panel that lost power during the gap only cools from here
                    st.update({'verdict': None, 'peak': None, 'drop_since': None,
                               'int_seen': None, 'settle_until': now})
                else:
                    st['lit_sec'] += now - st['lit_at']
                    st['lit_at'] = now
                st['last_lit'] = now
                rise = t - st['base']
                entry.update({'baseline': round(st['base'], 1), 'rise': round(rise, 2),
                              'litSec': int(st['lit_sec'])})
                dropped = led in self._led_dropped
                if st['verdict'] == 'ok' or rise >= min_rise:
                    # proved heating in this window: the rise rule is done with
                    # it - a later fall belongs to the drop rule below
                    entry['status'] = 'ok'
                    if st['verdict'] != 'ok':
                        st['verdict'] = 'ok'
                    if led in self._led_failed and rise >= min_rise:
                        self._led_failed.pop(led, None)
                        print(f'[LED] {label} heats again (+{rise:.1f} C) - Err '
                              f'{ERR_LED_NOT_HEATING} latch released', flush=True)
                elif st['lit_sec'] >= st['fail_at'] and not dropped:
                    entry['status'] = 'fail'
                    detail = (f'{label}: +{rise:.1f} C after {int(st["lit_sec"])} s at '
                              f'{intensity:.0f} % (at least {min_rise:.1f} C expected) - '
                              f'check that the {label} connector is plugged in')
                    if st['verdict'] != 'fail':
                        st['verdict'] = 'fail'
                        print(f'[LED] {detail} -> Err {ERR_LED_NOT_HEATING}', flush=True)
                    self._led_failed[led] = detail
                else:
                    entry['status'] = 'warming'
                # --- mid-process drop: armed once the panel has proved it heats
                if st['verdict'] == 'ok':
                    if st['int_seen'] is None:
                        st['int_seen'] = intensity            # first arm: track at once
                    elif abs(intensity - st['int_seen']) > 0.5:
                        # new power level: the panel settles to a new temperature
                        st.update({'int_seen': intensity, 'peak': None, 'drop_since': None,
                                   'settle_until': now + drop_settle})
                    if now >= st['settle_until']:
                        if st['peak'] is None or t > st['peak']:
                            st['peak'], st['peak_chamber'] = t, chamber
                        comp = 0.0                            # the chamber cooled too?
                        if chamber is not None and st['peak_chamber'] is not None:
                            comp = max(0.0, st['peak_chamber'] - chamber)
                        drop = (st['peak'] - t) - comp
                        entry.update({'peak': round(st['peak'], 1), 'drop': round(drop, 2)})
                        if drop >= drop_c:
                            st['drop_since'] = st['drop_since'] or now
                            if now - st['drop_since'] >= drop_persist:
                                detail = (f'{label}: fell {drop:.1f} C below its {st["peak"]:.1f} C '
                                          f'peak while lit at {intensity:.0f} % (chamber cooling '
                                          f'taken off) for {int(now - st["drop_since"])} s - the '
                                          f'panel stopped heating mid-process, check the {label} '
                                          f'connector and driver output')
                                if not dropped:
                                    print(f'[LED] {detail} -> Err {ERR_LED_TEMP_DROP}', flush=True)
                                self._led_dropped[led] = detail
                        else:
                            st['drop_since'] = None
                            if dropped and drop <= drop_c / 2:
                                self._led_dropped.pop(led, None)
                                print(f'[LED] {label} back near its peak - Err '
                                      f'{ERR_LED_TEMP_DROP} latch released', flush=True)
                if led in self._led_dropped:
                    entry['status'] = 'drop'
            else:
                if st is not None and st['lit_at'] is not None:
                    # light stopped somewhere since the last lit tick: count
                    # only the light seen between lit ticks, not the gap
                    st['last_lit'] = st['lit_at']
                    st['lit_at'] = None
                if is_lit:
                    entry['status'] = 'low'   # below min_eval_intensity: not judged
                if led in self._led_failed:
                    entry['status'] = 'fail'  # latched until it heats again
                if led in self._led_dropped:
                    entry['status'] = 'drop'  # latched until it climbs back while lit
            if st is not None:
                self._led_heat[led] = st
            health[led] = entry
        self._led_health = health
        if self._led_failed:
            self._led_alerts[ERR_LED_NOT_HEATING] = '; '.join(
                self._led_failed[led] for led in LED_PANEL_LABELS if led in self._led_failed)
        elif ERR_LED_NOT_HEATING in self._led_alerts:
            self._led_alerts.pop(ERR_LED_NOT_HEATING, None)
            print(f'[LED] Err {ERR_LED_NOT_HEATING} cleared - every panel heats', flush=True)
        if self._led_dropped:
            self._led_alerts[ERR_LED_TEMP_DROP] = '; '.join(
                self._led_dropped[led] for led in LED_PANEL_LABELS if led in self._led_dropped)
        elif ERR_LED_TEMP_DROP in self._led_alerts:
            self._led_alerts.pop(ERR_LED_TEMP_DROP, None)
            print(f'[LED] Err {ERR_LED_TEMP_DROP} cleared - no panel below its peak', flush=True)

    def led_issues_now(self):
        """Panels currently latched (not heating / dropped) for the cure-history indication."""
        return ([{'led': led, 'code': ERR_LED_NOT_HEATING, 'detail': d} for led, d in self._led_failed.items()]
                + [{'led': led, 'code': ERR_LED_TEMP_DROP, 'detail': d} for led, d in self._led_dropped.items()])

    def sensor_preflight(self):
        """Right before a process starts: a fan latched critical (9002) blocks
        the start, then the REQUIRED NTCs (chamber, Left, Right) must read.
        Re-read every 0.5 s for SENSOR_GLITCH_SEC: a single valid read passes,
        so only a sensor that stays open for the whole window refuses the
        start with the critical code (carried to the UI)."""
        if self._fan_critical - self._fan_override:
            fans = ', '.join(sorted(self._fan_critical - self._fan_override))
            return False, (f'[{ERR_FAN_FAILURE}] Fan below minimum speed: {fans} - '
                           f'the system cannot run until the fan is replaced')
        pending = set(CRITICAL_TEMP_SENSORS)
        deadline = time.time() + SENSOR_GLITCH_SEC
        while True:
            pending = {n for n in pending if not self._sensor_read_ok(n)}
            if not pending or time.time() >= deadline:
                break
            time.sleep(0.5)
        bad = [n for n in CRITICAL_TEMP_SENSORS if n in pending]
        if not bad:
            return True, None
        names = ', '.join(f'{n} ({CRITICAL_TEMP_SENSORS[n]})' for n in bad)
        self._sensor_alerts.add(ERR_TEMP_SENSOR_DISCONNECTED)
        self._sensor_details[str(ERR_TEMP_SENSOR_DISCONNECTED)] = (
            HEATER_SENSOR_DETAIL if HEATER_THERMISTOR in bad else f'Temperature sensor disconnected: {names}')
        for n in bad:
            self._sensor_open_since.setdefault(n, time.time())
        print(f'[SENSOR] process refused: {names} open -> Err {ERR_TEMP_SENSOR_DISCONNECTED}', flush=True)
        return False, (f'[{ERR_TEMP_SENSOR_DISCONNECTED}] Temperature sensor disconnected: '
                       f'{names} - reconnect the sensor before starting a process')

    def sensors_state(self):
        """Per-NTC supervision snapshot for /api/state (and the cure-history
        sensorIssues). A dropout shorter than SENSOR_GLITCH_SEC still reads ok."""
        now = time.time()
        out = {}
        for name, key in list(CRITICAL_TEMP_SENSORS.items()) + list(WARNING_TEMP_SENSORS.items()):
            since = self._sensor_open_since.get(name)
            if since is not None and now - since < SENSOR_GLITCH_SEC:
                since = None
            out[key] = {'sensor': name, 'ok': since is None,
                        'openSec': int(now - since) if since else None,
                        'critical': name in CRITICAL_TEMP_SENSORS}
        return out

    # ------------------------------------------------------------------
    #  Shutdown (atexit): everything OFF, no run-on
    # ------------------------------------------------------------------
    def shutdown(self):
        for action in (lambda: self.status_leds and self.status_leds.stop(),
                       lambda: self.temp.shutdown('user'),
                       lambda: self.sys.stop_cooling('user'),
                       lambda: self.sys.all_leds_off(),
                       lambda: self.set_nitrogen(False),
                       # rest state for the LED path: SSR + switch GPIOs LOW and
                       # the LED_SWITCH relay (TCA P05 -> K4) at 0
                       lambda: self.sys.led_power_off(),
                       lambda: self.sys.io.io.set_pin("LED_SWITCH", 0)):
            try:
                action()
            except Exception:             # noqa: BLE001
                pass
