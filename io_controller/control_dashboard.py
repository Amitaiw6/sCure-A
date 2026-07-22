#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
control_dashboard.py - engineering control & monitoring dashboard for the CureBox.

Dark, rounded-card UI (cyan accent) built on the unified io_controller. One
window, full control + live monitoring of every major component:

  Header   - system name, live Door + Chamber-temp status, connection.
  Fans     - independent PWM per fan, live RPM bar, temperature, by location.
  Temps    - all temperature sensors as live chips.
  LEDs     - independent intensity (0-100%) per channel.
  Heater   - ON/OFF toggle (read back from hardware) + chamber temperature.
  Cooling  - closed-loop cooling mode: rate setpoint (0-5 C/min) + target temp,
             live measured dT/dt; damper + fans driven by SystemController.
  Servo    - angle control (slider + presets) with a live dial.
  Nitrogen - open/close the solenoid valve + live status.
  Pressure - circular gauge with live value and units.

Run on the Pi:   python3 control_dashboard.py
Off-Pi it still imports and lays out (simulation banner). Slow I2C reads run on
a background thread; bus access is lock-serialized.
"""

import math
import threading
import time
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import tkinter.scrolledtext as scrolledtext

import io_controller as ioc
try:
    import system_log
except Exception:                      # noqa: BLE001 - logging optional
    system_log = None


# ===========================================================================
#  Layout configuration  (edit to match your wiring)
# ===========================================================================
SYSTEM_NAME = "CureBox"
FAN_LAYOUT = [
    ("FAN_LEFT",    "Left Side",  "TEMP_LEFT"),
    ("FAN_RIGHT",   "Right Side", "TEMP_RIGHT"),
    ("FAN_BACK",    "Rear",       "TEMP_BACK_ORIGIN"),
    ("FAN_DOOR",    "Door",       "TEMP_DOOR_ORIGIN"),
    ("FAN_HEATER",  "Heater",     "TEMP_CHAMBER"),
    ("FAN_COOLING", "Cooling",    "TEMP_CHAMBER"),
]
LED_LAYOUT = [
    ("LED_LEFT",  "Left Side"),
    ("LED_RIGHT", "Right Side"),
    ("LED_BACK",  "Rear"),
    ("LED_DOOR",  "Door"),
]
# LEDs reach full brightness already at this PWM duty (observed: ~60%), so the
# brightness slider (0-100%) is mapped onto 0..LED_MAX_DUTY. That way 100% on the
# slider = real max brightness and the percentage tracks actual output instead of
# saturating early. Tune to your hardware (use a dict here for per-channel values).
LED_MAX_DUTY = 60.0

# Fallback heater safety values (used only if components.json has no "heater" section).
HEATER_DEFAULTS = {
    "channel": "PWM_HEATER", "fan": "FAN_HEATER", "fan_pwm": 100,
    "thermistor": "TEMP_CHAMBER", "min_fan_rpm": 100,
    "temp_valid_min": -20, "temp_valid_max": 120, "health_check_sec": 10,
}
NITROGEN_SIGNAL = "NITROGEN_VALVE"
CHAMBER_TEMP = "TEMP_CHAMBER"

PRESSURE_CHANNEL = "SENSOR1_A1"      # TODO: confirm the pressure analog input + scaling
PRESSURE_UNITS = "kPa"
PRESSURE_MAX = 100.0


def volts_to_pressure(v):
    """TODO: replace with the real transfer function from the sensor datasheet."""
    return max(0.0, (v - 0.5) / 4.0 * 100.0)


RPM_MAX = 4000.0
SENSOR_REFRESH_SEC = 1.0
UI_REFRESH_MS = 400


# ===========================================================================
#  Design system - tokens
# ===========================================================================
COLORS = {
    "bg":      "#0a0b0d",
    "header":  "#0f1013",
    "card":    "#17181c",
    "card2":   "#202229",
    "border":  "#26282f",
    "track":   "#2a2d35",
    "text":    "#f2f4f7",
    "muted":   "#868c97",
    "accent":  "#2ea6ff",   # single cyan accent (mono-accent theme)
    "green":   "#22c55e",
    "red":     "#e5484d",
    "orange":  "#f59e0b",
}
# instruments reference these aliases; keep the theme mono-accent
COLORS["accent2"] = COLORS["accent"]
COLORS["accent3"] = COLORS["accent"]
COLORS["panel"] = COLORS["card"]

SANS_STACK = ("Segoe UI", "Inter", "DejaVu Sans", "Helvetica", "Arial")
MONO_STACK = ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "Courier New")


def _pick(root, stack):
    avail = set(tkfont.families(root))
    for fam in stack:
        if fam in avail:
            return fam
    return tkfont.nametofont("TkDefaultFont").actual("family")


def temp_color(t):
    if t is None:
        return COLORS["muted"]
    if t < 15:
        return COLORS["accent"]
    if t < 30:
        return COLORS["green"]
    if t < 45:
        return COLORS["orange"]
    return COLORS["red"]


def gauge_color(frac):
    if frac < 0.6:
        return COLORS["green"]
    if frac < 0.85:
        return COLORS["orange"]
    return COLORS["red"]


def round_points(x0, y0, x1, y1, r):
    """Control points for a rounded rectangle (use with create_polygon smooth=True)."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]


# ===========================================================================
#  Reusable rounded Canvas widgets
# ===========================================================================
class Card(tk.Canvas):
    """Rounded-rectangle card. Put content in `.body` (a Frame)."""
    def __init__(self, parent, *, parent_bg, fill=None, radius=14, padx=16, pady=14):
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0)
        self.fill = fill or COLORS["card"]
        self.r, self.px, self.py = radius, padx, pady
        self.body = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(padx, pady, anchor="nw", window=self.body)
        self._cw = self._ch = 0          # NOTE: not _w/_h - those are tkinter-internal
        self.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)

    def _on_canvas(self, e):
        if e.width != self._cw:
            self._cw = e.width
            self.itemconfigure(self._win, width=max(1, e.width - 2 * self.px))
        self._redraw()

    def _on_body(self, e):
        h = e.height + 2 * self.py
        if h != self._ch:
            self._ch = h
            self.config(height=h)
        self._redraw()

    def _redraw(self):
        w = self._cw or self.winfo_width()
        h = self._ch or self.winfo_height()
        if w <= 2 or h <= 2:
            return
        self.delete("card")
        self.create_polygon(round_points(1, 1, w - 1, h - 1, self.r), smooth=True,
                            fill=self.fill, outline=COLORS["border"], tags="card")
        self.tag_lower("card")


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, *, parent_bg, fill, fg,
                 hover=None, radius=9, padx=16, height=34, font):
        w = font.measure(text) + 2 * padx
        super().__init__(parent, width=w, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command = text, command
        self.fill, self.fg, self.hover = fill, fg, hover or fill
        self.r, self.font = radius, font
        self._cur = fill
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)
        self.bind("<Enter>", lambda e: self._set(self.hover))
        self.bind("<Leave>", lambda e: self._set(self.fill))

    def _set(self, c):
        self._cur = c
        self._draw()

    def set_text(self, text):
        self.text = text
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            return
        self.delete("all")
        self.create_polygon(round_points(1, 1, w - 1, h - 1, self.r), smooth=True,
                            fill=self._cur, outline=self._cur)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=self.font)


class Toggle(tk.Canvas):
    def __init__(self, parent, *, parent_bg, on=False, command=None, w=48, h=26):
        super().__init__(parent, width=w, height=h, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h, self.on, self.command = w, h, on, command
        self.bind("<Button-1>", self._click)
        self._draw()

    def _click(self, _e):
        self.on = not self.on
        self._draw()
        if self.command:
            self.command(self.on)

    def set(self, on):
        if on != self.on:
            self.on = on
            self._draw()

    def _draw(self):
        self.delete("all")
        track = COLORS["accent"] if self.on else COLORS["track"]
        self.create_polygon(round_points(1, 1, self.w - 1, self.h - 1, self.h / 2 - 1),
                            smooth=True, fill=track, outline=track)
        d = self.h - 8
        x = self.w - self.h + 4 if self.on else 4
        self.create_oval(x, 4, x + d, 4 + d, fill="white", outline="white")


class Slider(tk.Canvas):
    """Fully rounded slider: pill track, rounded fill, round draggable knob."""
    def __init__(self, parent, *, parent_bg, lo=0, hi=100, value=0, command=None,
                 release=None, width=170, height=22, accent=None, track_h=6):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.lo, self.hi, self.value = lo, hi, value
        self.command, self.release, self.h = command, release, height
        self.accent = accent or COLORS["accent"]
        self.knob_r = height / 2 - 2
        self.track_h = track_h
        self.enabled = True
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", lambda e: self._from_x(e.x))
        self.bind("<B1-Motion>", lambda e: self._from_x(e.x))
        self.bind("<ButtonRelease-1>",
                  lambda e: self.release(self.value) if (self.enabled and self.release) else None)

    def set_enabled(self, flag):
        if flag != self.enabled:
            self.enabled = flag
            self.config(cursor="hand2" if flag else "arrow")
            self._draw()

    def _frac(self):
        return (self.value - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def _bounds(self):
        m = self.knob_r + 2
        return m, self.winfo_width() - m

    def _draw(self):
        w = self.winfo_width()
        if w <= 2:
            return
        accent = self.accent if self.enabled else COLORS["muted"]
        knob = "white" if self.enabled else COLORS["card2"]
        self.delete("all")
        x0, x1 = self._bounds()
        cy, th = self.h / 2, self.track_h
        self._pill(x0, x1, cy - th / 2, cy + th / 2, COLORS["track"])
        fx = x0 + (x1 - x0) * self._frac()
        self._pill(x0, fx, cy - th / 2, cy + th / 2, accent)
        r = self.knob_r
        self.create_oval(fx - r, cy - r, fx + r, cy + r, fill=knob,
                         outline=accent, width=2)

    def _pill(self, x0, x1, y0, y1, color):
        r = (y1 - y0) / 2
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=color, outline=color)
        if x1 - x0 >= 2 * r:
            self.create_oval(x1 - 2 * r, y0, x1, y1, fill=color, outline=color)
            self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color)

    def _from_x(self, x):
        if not self.enabled:
            return
        x0, x1 = self._bounds()
        frac = max(0.0, min(1.0, (x - x0) / (x1 - x0))) if x1 > x0 else 0.0
        self.value = self.lo + frac * (self.hi - self.lo)
        self._draw()
        if self.command:
            self.command(self.value)

    def set(self, value):
        self.value = max(self.lo, min(self.hi, value))
        self._draw()

    def get(self):
        return self.value


class IconButton(tk.Canvas):
    def __init__(self, parent, glyph, *, parent_bg, font, active=False, command=None, d=38):
        super().__init__(parent, width=d, height=d, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.d, self.glyph, self.font = d, glyph, font
        self.active, self.command = active, command
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)
        self._draw()

    def _draw(self):
        self.delete("all")
        ring = COLORS["accent"] if self.active else COLORS["border"]
        self.create_oval(2, 2, self.d - 2, self.d - 2, fill=COLORS["card"], outline=ring, width=2)
        self.create_text(self.d / 2, self.d / 2, text=self.glyph,
                         fill=COLORS["text"] if self.active else COLORS["muted"], font=self.font)


# ===========================================================================
#  Custom Canvas instruments
# ===========================================================================
class ArcGauge(tk.Frame):
    """270-degree circular gauge with a value/units readout in the centre."""
    def __init__(self, parent, fonts, *, size=190, maxval=100.0, units=""):
        super().__init__(parent, bg=COLORS["card"])
        self.size, self.maxval, self.units, self.fonts = size, maxval, units, fonts
        self.c = tk.Canvas(self, width=size, height=size, bg=COLORS["card"],
                           highlightthickness=0)
        self.c.pack()
        self.set_value(None)

    def set_value(self, val):
        c, s, pad = self.c, self.size, 20
        c.delete("all")
        box = (pad, pad, s - pad, s - pad)
        c.create_arc(*box, start=225, extent=-270, style="arc", width=16,
                     outline=COLORS["track"])
        if val is not None:
            frac = max(0.0, min(1.0, val / self.maxval))
            if frac > 0:
                c.create_arc(*box, start=225, extent=-270 * frac, style="arc",
                             width=16, outline=gauge_color(frac))
        cx = cy = s / 2
        c.create_text(cx, cy - 6, text=(f"{val:.1f}" if val is not None else "--"),
                      fill=COLORS["text"], font=self.fonts["gauge"])
        c.create_text(cx, cy + 24, text=self.units, fill=COLORS["muted"],
                      font=self.fonts["small"])


class ServoDial(tk.Frame):
    """180-degree dial with tick marks and a needle showing the servo angle."""
    def __init__(self, parent, fonts, *, width=240, lo=0, hi=180):
        super().__init__(parent, bg=COLORS["card"])
        self.w, self.h, self.fonts = width, int(width * 0.60), fonts
        self.lo, self.hi = lo, hi
        self.c = tk.Canvas(self, width=self.w, height=self.h, bg=COLORS["card"],
                           highlightthickness=0)
        self.c.pack()
        self.set_angle(None)

    def set_angle(self, ang):
        c, w, h, pad = self.c, self.w, self.h, 18
        c.delete("all")
        r = min(w / 2 - pad, h - pad)
        cx, cy = w / 2, h - 4
        box = (cx - r, cy - r, cx + r, cy + r)
        c.create_arc(*box, start=180, extent=-180, style="arc", width=12,
                     outline=COLORS["track"])
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            a = math.radians(180 - 180 * frac)
            x0, y0 = cx + (r - 12) * math.cos(a), cy - (r - 12) * math.sin(a)
            x1, y1 = cx + r * math.cos(a), cy - r * math.sin(a)
            c.create_line(x0, y0, x1, y1, fill=COLORS["border"], width=2)
        if ang is not None:
            frac = max(0.0, min(1.0, (ang - self.lo) / (self.hi - self.lo)))
            c.create_arc(*box, start=180, extent=-180 * frac, style="arc",
                         width=12, outline=COLORS["accent"])
            a = math.radians(180 - 180 * frac)
            nx, ny = cx + (r - 16) * math.cos(a), cy - (r - 16) * math.sin(a)
            c.create_line(cx, cy, nx, ny, fill=COLORS["accent"], width=4, capstyle="round")
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=COLORS["text"], outline="")
        c.create_text(cx, cy - r / 2,
                      text=(f"{ang:.0f}°" if ang is not None else "--"),
                      fill=COLORS["text"], font=self.fonts["mono_big"])


class LinearBar(tk.Canvas):
    """Thin rounded progress bar (used for fan RPM)."""
    def __init__(self, parent, *, width, height, maxval, color):
        super().__init__(parent, width=width, height=height, bg=COLORS["card"],
                         highlightthickness=0)
        self.w, self.h, self.maxval, self.color = width, height, maxval, color
        self.set(None)

    def set(self, val):
        self.delete("all")
        r = self.h / 2
        self._pill(0, self.w, COLORS["track"], r)
        if val is not None and self.maxval > 0:
            frac = max(0.0, min(1.0, val / self.maxval))
            if frac > 0:
                self._pill(0, max(self.h, self.w * frac), self.color, r)

    def _pill(self, x0, x1, color, r):
        self.create_oval(x0, 0, x0 + 2 * r, self.h, fill=color, outline=color)
        self.create_oval(x1 - 2 * r, 0, x1, self.h, fill=color, outline=color)
        self.create_rectangle(x0 + r, 0, x1 - r, self.h, fill=color, outline=color)


# ===========================================================================
#  Hardware hub
# ===========================================================================
class HardwareHub:
    def __init__(self):
        self.lock = threading.Lock()   # shared with SystemController to serialize the I2C bus
        self.box = None
        self.available = False
        self.error = None
        self.config = self.sys = None
        self.config_error = None
        self.servo_ok = True
        self.mode_override = None
        self._heater_thread = None
        self._cooling_thread = None
        self._sim_heater = False       # heater state when running without hardware
        self._sim_cooling = False
        self._sim_fault = None

        try:
            self.box = ioc.IOController()
            self.available = True
        except Exception as e:        # noqa: BLE001
            self.error = str(e)
        try:
            self.config = ioc.load_component_config()
        except Exception as e:        # noqa: BLE001 - missing/invalid file
            self.config_error = str(e)
        # All control logic (gating, auto-fan, heater safety, tachs) lives here:
        if self.available and self.config:
            try:
                self.sys = ioc.SystemController(self.box, self.config, lock=self.lock)
            except Exception as e:    # noqa: BLE001
                self.config_error = self.config_error or str(e)

        # startup: everything OFF until the user activates it (0 fans, no heat, etc.)
        if self.sys:
            try:
                self.sys.startup_safe()
            except Exception:         # noqa: BLE001
                pass

    def set_channel(self, name, percent):
        if not self.available:
            return
        with self.lock:
            self.box.pca.set_duty(ioc.PCA_CHANNELS[name], percent)

    # --- LEDs + wavelength gating (config-driven) -------------------------
    def set_mode_override(self, mode):
        """Set the selected wavelength mode in software."""
        self.mode_override = mode
        if self.sys:
            self.sys.mode_override = mode

    def select_mode(self, mode):
        """Safe wavelength switch: all LEDs off, set GPIO17, verify. (ok, reason)."""
        self.mode_override = mode
        if self.sys:
            return self.sys.select_mode(mode)
        return True, None

    def door_interlock(self):
        """Safety: if the door is open, force all LEDs + heater OFF (called every poll)."""
        if self.sys:
            try:
                return self.sys.door_interlock()
            except Exception:         # noqa: BLE001
                return False
        return False

    def set_door_magnet(self, on):
        """Open/close the door via the door-magnet actuator (valve 2, TCA P26)."""
        if self.sys:
            try: self.sys.set_door_magnet(on)
            except Exception: pass    # noqa: BLE001
        elif self.available:
            try:
                with self.lock:
                    self.box.io.set_pin("DOOR_MAGNET", 1 if on else 0)
            except Exception: pass    # noqa: BLE001

    def wavelength_mode(self):
        if self.sys:
            try:
                return self.sys.wavelength_mode()   # honours sys.mode_override + GPIO27
            except Exception:         # noqa: BLE001
                pass
        if self.mode_override:
            return self.mode_override
        if self.config:
            return self.config.get("wavelength_switch", {}).get("default_mode", "405nm")
        return "405nm"

    def led_allowed_in_mode(self, led, mode):
        if not self.config:
            return True
        return mode in self.config["leds"].get(led, {}).get("modes", [])

    def led_fan(self, led):
        return self.config["leds"].get(led, {}).get("fan") if self.config else None

    def led_fan_speed(self, led):
        return self.config["leds"].get(led, {}).get("fan_speed", 0) if self.config else 0

    def set_led(self, led, duty):
        """Delegate to SystemController (gating + auto fan). True if applied, False if blocked."""
        if self.sys:
            try:
                return self.sys.set_led(led, duty)
            except Exception:         # noqa: BLE001
                return False
        # no SystemController: gate from config, write directly if hardware present
        if duty > 0 and not self.led_allowed_in_mode(led, self.wavelength_mode()):
            return False
        if not self.available:
            return True
        try:
            with self.lock:
                self.box.pca.set_duty(ioc.PCA_CHANNELS[led], duty)
                fan = self.led_fan(led)
                if fan:
                    self.box.pca.set_duty(ioc.PCA_CHANNELS[fan],
                                          self.led_fan_speed(led) if duty > 0 else 0)
            return True
        except Exception:             # noqa: BLE001
            return False

    def enforce_wavelength(self):
        if self.sys:
            try:
                self.sys.enforce_wavelength()
            except Exception:         # noqa: BLE001
                pass

    def read_rpm(self, fan):
        """Fan RPM (the tachometers are owned by SystemController)."""
        return self.sys.read_rpm(fan) if self.sys else None

    # --- heater safety (all logic in SystemController; these just delegate) -
    def request_heater(self, on):
        if on:
            if self._heater_thread and self._heater_thread.is_alive():
                return
            self._heater_thread = threading.Thread(target=self._enable_heater_seq, daemon=True)
            self._heater_thread.start()
        elif self.sys:
            self.sys.disable_heater("user")
        else:
            self._sim_heater = False

    def _enable_heater_seq(self):
        if self.sys:
            self.sys.enable_heater()              # pre-flight checks + enable, on the hardware side
        else:
            self._sim_heater, self._sim_fault = True, None

    def heater_health_check(self):
        if self.sys:
            self.sys.heater_health_check()

    @property
    def heater_fault(self):
        return self.sys.heater_fault if self.sys else self._sim_fault

    @property
    def led_fault(self):
        return self.sys.led_fault if self.sys else None

    def get_heater(self):
        if self.sys:
            return self.sys.is_heater_on()
        return self._sim_heater if not self.available else None

    def heater_fan_info(self):
        if self.sys:
            cfg = self.sys.heater_cfg()
        elif self.config:
            cfg = {**HEATER_DEFAULTS, **self.config.get("heater", {})}
        else:
            cfg = HEATER_DEFAULTS
        return cfg.get("fan", "FAN_HEATER"), cfg.get("fan_pwm", 100)

    def heater_health_sec(self):
        if self.sys:
            return self.sys.heater_cfg().get("health_check_sec", 10)
        if self.config:
            return self.config.get("heater", {}).get("health_check_sec", 10)
        return 10

    # --- cooling mode (all logic in SystemController; these just delegate) -
    def request_cooling(self, on, rate=None, target=None):
        if on:
            if self._cooling_thread and self._cooling_thread.is_alive():
                return
            self._cooling_thread = threading.Thread(
                target=self._enable_cooling_seq, args=(rate, target), daemon=True)
            self._cooling_thread.start()
        elif self.sys:
            self.sys.stop_cooling("user")
        else:
            self._sim_cooling = False

    def _enable_cooling_seq(self, rate, target):
        if self.sys:
            self.sys.start_cooling(rate, target)   # damper + fans + PI loop, hardware side
        else:
            self._sim_cooling = True

    def set_cooling_rate(self, rate):
        if self.sys and self.sys.is_cooling_on():
            self.sys.set_cooling_rate(rate)

    def cooling_status(self):
        if self.sys:
            return self.sys.cooling_status()
        return {"active": self._sim_cooling, "fault": None}

    def set_servo(self, angle):
        """Manual servo (damper) control - shares IOController's lazy servo
        instance so cooling mode and this card never open GPIO8 twice."""
        if not self.servo_ok or not self.available:
            return
        try:
            with self.lock:
                self.box.servo.goto(angle)
        except Exception:             # noqa: BLE001
            self.servo_ok = False

    def set_valve(self, on):
        if not self.available:
            return
        with self.lock:
            ioc.gpio_set_signal(NITROGEN_SIGNAL, on)

    def get_valve(self):
        if not self.available:
            return None
        try:
            with self.lock:
                return ioc.gpio_get_signal(NITROGEN_SIGNAL)
        except Exception:             # noqa: BLE001
            return None

    def get_door(self):
        """True = door open, False = closed, None = unknown (GPIO27)."""
        if self.sys:
            try:
                return self.sys.door_open()
            except Exception:         # noqa: BLE001
                return None
        return None

    def read_temp(self, name):
        if not self.available or name is None:
            return None
        try:
            with self.lock:
                return self.box.read_temp(name)["temp"]
        except Exception:             # noqa: BLE001
            return None

    def read_pressure(self):
        if not self.available:
            return None
        try:
            with self.lock:
                v = self.box.read_analog(PRESSURE_CHANNEL)["voltage"]
            return volts_to_pressure(v)
        except Exception:             # noqa: BLE001
            return None

    def close(self):
        if self.sys is not None:
            try: self.sys.stop_cooling("user")   # fans off, damper closed
            except Exception: pass
        if self.sys is not None:
            try: self.sys.close()         # closes the fan tachometers
            except Exception: pass
        if self.box is not None:
            try: self.box.close()
            except Exception: pass


# ===========================================================================
#  Dashboard
# ===========================================================================
class Dashboard:
    def __init__(self, root, hub):
        self.root = root
        self.hub = hub
        self.root.title("CureBox Control")
        self.root.configure(bg=COLORS["bg"])
        self.root.minsize(1080, 720)

        sans, mono = _pick(root, SANS_STACK), _pick(root, MONO_STACK)
        self.fonts = {
            "h1":       tkfont.Font(family=sans, size=17, weight="bold"),
            "h2":       tkfont.Font(family=sans, size=11, weight="bold"),
            "body":     tkfont.Font(family=sans, size=10),
            "small":    tkfont.Font(family=sans, size=9),
            "pill":     tkfont.Font(family=sans, size=10, weight="bold"),
            "icon":     tkfont.Font(family=sans, size=13),
            "mono":     tkfont.Font(family=mono, size=10),
            "num":      tkfont.Font(family=mono, size=14, weight="bold"),
            "mono_big": tkfont.Font(family=mono, size=20, weight="bold"),
            "gauge":    tkfont.Font(family=mono, size=26, weight="bold"),
        }
        self._init_styles()

        self.snapshot = {"temp": {}, "rpm": {}, "pressure": None, "valve": None,
                         "door": None, "heater": None, "heater_fault": None,
                         "led_fault": None, "mode": None, "cooling": {}}
        self._snap_lock = threading.Lock()
        self.fan_rpm, self.fan_temp, self.fan_pct, self.fan_bar = {}, {}, {}, {}
        self.fan_slider, self.led_slider = {}, {}
        self.led_pct, self.temp_chips = {}, {}
        self.led_fault_lbl = None
        self.valve_status = self.pressure_gauge = None
        self.servo_dial = self.servo_angle_lbl = None
        self.heater_toggle = self.heater_temp = self.heater_fault_lbl = None
        self.cooling_toggle = self.cooling_rate_slider = self.cooling_rate_lbl = None
        self.cooling_target_entry = self.cooling_meas = self.cooling_fault_lbl = None
        self.hdr_door = self.hdr_temp = self.hdr_mode = None
        self.mode_btn = self.door_banner = self._body = self.log_text = None
        self._last_mode = None
        self._last_heater = None
        self._last_cooling = None
        self._banner_shown = False

        self._build_ui()
        self._stop = False
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)
        self._poller.start()
        self._schedule_ui_refresh()
        self._refresh_logs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- styling ----------------------------------------------------------
    def _init_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        for name in ("Fan.Horizontal.TScale", "Led.Horizontal.TScale",
                     "Servo.Horizontal.TScale"):
            st.configure(name, troughcolor=COLORS["track"], background=COLORS["accent"],
                         bordercolor=COLORS["track"], lightcolor=COLORS["accent"],
                         darkcolor=COLORS["accent"], gripcount=0)
            st.map(name, background=[("active", COLORS["accent"])])

    def _label(self, parent, text="", *, font="body", fg="text", bg="card"):
        return tk.Label(parent, text=text, font=self.fonts[font],
                        fg=COLORS.get(fg, fg), bg=COLORS.get(bg, bg))

    def _card(self, parent, parent_bg="bg"):
        return Card(parent, parent_bg=COLORS.get(parent_bg, parent_bg))

    def _section(self, parent, title):
        wrap = tk.Frame(parent, bg=COLORS["bg"])
        self._label(wrap, title, font="h2", fg="muted", bg="bg").pack(anchor="w", pady=(0, 6))
        card = self._card(wrap)
        card.pack(fill="x")
        return wrap, card.body

    # --- header -----------------------------------------------------------
    def _build_ui(self):
        header = tk.Frame(self.root, bg=COLORS["header"])
        header.pack(fill="x")
        bar = tk.Frame(header, bg=COLORS["header"])
        bar.pack(fill="x", padx=18, pady=12)

        self._label(bar, "◆", font="h1", fg="accent", bg="header").pack(side="left")
        self._label(bar, f"  {SYSTEM_NAME}", font="h1", bg="header").pack(side="left")

        # live status: wavelength mode + door + chamber temperature
        self.hdr_temp = self._statusbox(bar, "TEMP", "--")
        self.hdr_temp.pack(side="right", padx=(0, 14))
        self.hdr_door = self._statusbox(bar, "DOOR", "--")
        self.hdr_door.pack(side="right", padx=(0, 14))
        self.hdr_mode = self._statusbox(bar, "MODE", "--")
        self.hdr_mode.pack(side="right", padx=(0, 14))
        ok = self.hub.available
        tk.Label(bar, text=("● connected" if ok else "● simulation"),
                 font=self.fonts["small"], fg="white",
                 bg=COLORS["green"] if ok else COLORS["red"],
                 padx=10, pady=4).pack(side="right", padx=(0, 14))
        if self.hub.config_error:
            tk.Label(bar, text="⚠ components.json missing", font=self.fonts["small"],
                     fg="white", bg=COLORS["orange"], padx=10, pady=4
                     ).pack(side="right", padx=(0, 14))

        # door-interlock banner (shown only when the door is open)
        self.door_banner = tk.Label(self.root, text="  Door is Open - Operation Disabled  ",
                                    font=self.fonts["pill"], fg="white", bg=COLORS["red"],
                                    anchor="w", padx=12, pady=6)

        body = tk.Frame(self.root, bg=COLORS["bg"])
        self._body = body
        body.pack(fill="both", expand=True, padx=18, pady=16)
        body.columnconfigure(0, weight=3, uniform="c")
        body.columnconfigure(1, weight=2, uniform="c")
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=COLORS["bg"])
        left.grid(row=0, column=0, sticky="nsew")
        self._build_fans(left)
        self._build_temps(left)
        self._build_leds(left)

        right = tk.Frame(body, bg=COLORS["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self._build_wavelength(right)
        self._build_heater(right)
        self._build_cooling(right)
        self._build_pressure(right)
        self._build_servo(right)
        self._build_nitrogen(right)
        self._build_door(right)

        self._build_logs()

    def _statusbox(self, parent, label, value):
        f = tk.Frame(parent, bg=COLORS["header"])
        self._label(f, label, font="small", fg="muted", bg="header").pack(side="left", padx=(0, 6))
        val = self._label(f, value, font="pill", bg="header")
        val.pack(side="left")
        f.value = val
        return f

    # --- sections ---------------------------------------------------------
    def _build_fans(self, parent):
        wrap = tk.Frame(parent, bg=COLORS["bg"])
        wrap.pack(fill="both", expand=True)
        self._label(wrap, "FANS", font="h2", fg="muted", bg="bg").pack(anchor="w", pady=(0, 6))
        grid = tk.Frame(wrap, bg=COLORS["bg"])
        grid.pack(fill="both", expand=True)
        for i in range(2):
            grid.columnconfigure(i, weight=1, uniform="fan")

        for idx, (fan, location, temp_name) in enumerate(FAN_LAYOUT):
            r, c = divmod(idx, 2)
            card = self._card(grid)
            card.grid(row=r, column=c, sticky="nsew", padx=5, pady=5)
            inner = card.body
            inner.columnconfigure(0, weight=1)

            top = tk.Frame(inner, bg=COLORS["card"])
            top.grid(row=0, column=0, sticky="ew")
            top.columnconfigure(0, weight=1)
            self._label(top, location, font="h2").grid(row=0, column=0, sticky="w")
            temp_lbl = self._label(top, "--", font="body", fg="muted")
            temp_lbl.grid(row=0, column=1, sticky="e")
            self.fan_temp[fan] = (temp_lbl, temp_name)
            self._label(inner, fan, font="small", fg="muted").grid(row=1, column=0, sticky="w")

            rpm_row = tk.Frame(inner, bg=COLORS["card"])
            rpm_row.grid(row=2, column=0, sticky="w", pady=(8, 4))
            rpm_lbl = self._label(rpm_row, "----", font="mono_big")
            rpm_lbl.pack(side="left")
            self._label(rpm_row, " rpm", font="small", fg="muted").pack(side="left", pady=(7, 0))
            self.fan_rpm[fan] = rpm_lbl

            bar = LinearBar(inner, width=220, height=6, maxval=RPM_MAX, color=COLORS["accent"])
            bar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
            self.fan_bar[fan] = bar

            ctrl = tk.Frame(inner, bg=COLORS["card"])
            ctrl.grid(row=4, column=0, sticky="ew")
            ctrl.columnconfigure(1, weight=1)
            self._label(ctrl, "0%", font="small", fg="muted").grid(row=0, column=0, sticky="w")
            fs = Slider(ctrl, parent_bg=COLORS["card"], lo=0, hi=100, value=0,
                        command=lambda val, n=fan: self._on_fan_change(n, val),
                        release=lambda val, n=fan: self._log(f"fan {n} set to {round(val)}% PWM"))
            fs.grid(row=0, column=1, sticky="ew", padx=6)
            self.fan_slider[fan] = fs
            pct_lbl = self._label(ctrl, "0% PWM", font="small", fg="accent")
            pct_lbl.grid(row=0, column=2, sticky="e")
            self.fan_pct[fan] = pct_lbl

    @staticmethod
    def _short_temp(name):
        return name.replace("TEMP_", "").replace("_ORIGIN", " ORIG").replace("_", " ")

    def _build_temps(self, parent):
        wrap, grid = self._section(parent, "TEMPERATURES")
        wrap.pack(fill="x", pady=(10, 0))
        cols = 4
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="temp")
        for idx, name in enumerate(ioc.TEMP_SENSORS):
            r, c = divmod(idx, cols)
            chip = tk.Frame(grid, bg=COLORS["card2"])
            chip.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
            cell = tk.Frame(chip, bg=COLORS["card2"])
            cell.pack(fill="both", padx=10, pady=8)
            self._label(cell, self._short_temp(name), font="small", fg="muted",
                        bg="card2").pack(anchor="w")
            val = self._label(cell, "--", font="num", fg="muted", bg="card2")
            val.pack(anchor="w")
            self.temp_chips[name] = val

    def _build_leds(self, parent):
        wrap, grid = self._section(parent, "LEDS")
        wrap.pack(fill="x", pady=(10, 0))
        grid.columnconfigure(1, weight=1)
        for idx, (led, location) in enumerate(LED_LAYOUT):
            self._label(grid, location, font="body").grid(row=idx, column=0, sticky="w", pady=5)
            sl = Slider(grid, parent_bg=COLORS["card"], lo=0, hi=100, value=0,
                        command=lambda val, n=led: self._on_led_change(n, val),
                        release=lambda val, n=led: self._log(f"LED {n} brightness set to {round(val)}%"))
            sl.grid(row=idx, column=1, sticky="ew", padx=10)
            self.led_slider[led] = sl
            pct_lbl = self._label(grid, "0%", font="mono", fg="accent")
            pct_lbl.grid(row=idx, column=2, sticky="e")
            self.led_pct[led] = pct_lbl
        self.led_fault_lbl = self._label(grid, "", font="small", fg="red")
        self.led_fault_lbl.grid(row=len(LED_LAYOUT), column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_wavelength(self, parent):
        wrap, box = self._section(parent, "WAVELENGTH")
        wrap.pack(fill="x")
        row = tk.Frame(box, bg=COLORS["card"])
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        self._label(row, "Mode (tap to switch)", font="body").grid(row=0, column=0, sticky="w")
        self.mode_btn = RoundedButton(row, "405nm", self._toggle_mode,
                                      parent_bg=COLORS["card"], fill=COLORS["accent"], fg="white",
                                      hover=self._shade(COLORS["accent"], 1.12),
                                      font=self.fonts["pill"], padx=22)
        self.mode_btn.grid(row=0, column=1, sticky="e")

    def _build_heater(self, parent):
        wrap, box = self._section(parent, "HEATER")
        wrap.pack(fill="x")
        row = tk.Frame(box, bg=COLORS["card"])
        row.pack(fill="x")
        row.columnconfigure(1, weight=1)
        self._label(row, "Chamber heater", font="body").grid(row=0, column=0, sticky="w")
        self.heater_toggle = Toggle(row, parent_bg=COLORS["card"],
                                    command=lambda on: self.hub.request_heater(on))
        self.heater_toggle.grid(row=0, column=2, sticky="e")
        self.heater_temp = self._label(box, "Chamber --", font="num", fg="muted")
        self.heater_temp.pack(anchor="w", pady=(10, 0))
        self.heater_fault_lbl = self._label(box, "", font="small", fg="red")
        self.heater_fault_lbl.pack(anchor="w", pady=(4, 0))

    def _build_cooling(self, parent):
        wrap, box = self._section(parent, "COOLING MODE")
        wrap.pack(fill="x", pady=(14, 0))

        row = tk.Frame(box, bg=COLORS["card"])
        row.pack(fill="x")
        row.columnconfigure(1, weight=1)
        self._label(row, "Closed-loop cooling", font="body").grid(row=0, column=0, sticky="w")
        self.cooling_toggle = Toggle(row, parent_bg=COLORS["card"],
                                     command=self._on_cooling_toggle)
        self.cooling_toggle.grid(row=0, column=2, sticky="e")

        rate = tk.Frame(box, bg=COLORS["card"])
        rate.pack(fill="x", pady=(10, 0))
        rate.columnconfigure(1, weight=1)
        self._label(rate, "Rate", font="small", fg="muted").grid(row=0, column=0, sticky="w")
        self.cooling_rate_slider = Slider(
            rate, parent_bg=COLORS["card"], lo=0.0, hi=5.0, value=1.0,
            command=lambda v: self.cooling_rate_lbl.config(text=f"{v:.1f} °C/min"),
            release=self._on_cooling_rate_release)
        self.cooling_rate_slider.grid(row=0, column=1, sticky="ew", padx=8)
        self.cooling_rate_lbl = self._label(rate, "1.0 °C/min", font="mono", fg="accent")
        self.cooling_rate_lbl.grid(row=0, column=2, sticky="e")

        tgt = tk.Frame(box, bg=COLORS["card"])
        tgt.pack(fill="x", pady=(8, 0))
        self._label(tgt, "Target", font="small", fg="muted").pack(side="left")
        self.cooling_target_entry = tk.Entry(
            tgt, width=6, font=self.fonts["mono"], justify="center",
            bg=COLORS["card2"], fg=COLORS["text"], relief="flat",
            insertbackground=COLORS["text"], highlightthickness=1,
            highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"])
        self.cooling_target_entry.insert(0, "25.0")
        self.cooling_target_entry.pack(side="left", padx=8, ipady=3)
        self._label(tgt, "°C", font="small", fg="muted").pack(side="left")

        self.cooling_meas = self._label(box, "Measured --", font="num", fg="muted")
        self.cooling_meas.pack(anchor="w", pady=(10, 0))
        self.cooling_fault_lbl = self._label(box, "", font="small", fg="red")
        self.cooling_fault_lbl.pack(anchor="w", pady=(4, 0))

    def _cooling_target(self):
        try:
            return float(self.cooling_target_entry.get())
        except (TypeError, ValueError):
            return None                            # SystemController falls back to config

    def _on_cooling_toggle(self, on):
        if on:
            rate = self.cooling_rate_slider.get()
            self._log(f"cooling mode START (rate {rate:.1f} C/min, "
                      f"target {self.cooling_target_entry.get()} C)")
            self.hub.request_cooling(True, rate, self._cooling_target())
        else:
            self._log("cooling mode STOP (user)")
            self.hub.request_cooling(False)

    def _on_cooling_rate_release(self, val):
        self._log(f"cooling rate setpoint {val:.1f} C/min")
        self.hub.set_cooling_rate(val)             # live update while the mode runs

    def _build_pressure(self, parent):
        wrap, box = self._section(parent, "PRESSURE")
        wrap.pack(fill="x", pady=(14, 0))
        self.pressure_gauge = ArcGauge(box, self.fonts, size=180,
                                       maxval=PRESSURE_MAX, units=PRESSURE_UNITS)
        self.pressure_gauge.pack()
        self._label(box, f"{PRESSURE_UNITS}  ·  {PRESSURE_CHANNEL}",
                    font="small", fg="muted").pack(pady=(0, 2))

    def _build_servo(self, parent):
        wrap, box = self._section(parent, "SERVO")
        wrap.pack(fill="x", pady=(14, 0))
        self.servo_dial = ServoDial(box, self.fonts, width=230,
                                    lo=ioc.SERVO_MIN_ANGLE, hi=ioc.SERVO_MAX_ANGLE)
        self.servo_dial.pack()
        ctrl = tk.Frame(box, bg=COLORS["card"])
        ctrl.pack(fill="x", pady=(4, 6))
        ctrl.columnconfigure(0, weight=1)
        self.servo_slider = Slider(ctrl, parent_bg=COLORS["card"],
                                   lo=ioc.SERVO_MIN_ANGLE, hi=ioc.SERVO_MAX_ANGLE, value=90,
                                   command=lambda val: self._on_servo_change(val),
                                   release=lambda val: self._log(f"servo set to {round(val)} deg"))
        self.servo_slider.grid(row=0, column=0, sticky="ew")
        self.servo_angle_lbl = self._label(ctrl, "90°", font="mono", fg="accent")
        self.servo_angle_lbl.grid(row=0, column=1, sticky="e", padx=(8, 0))
        presets = tk.Frame(box, bg=COLORS["card"])
        presets.pack(fill="x")
        for label, ang in (("0°", ioc.SERVO_MIN_ANGLE),
                           ("90°", (ioc.SERVO_MIN_ANGLE + ioc.SERVO_MAX_ANGLE) // 2),
                           ("180°", ioc.SERVO_MAX_ANGLE)):
            RoundedButton(presets, label, lambda a=ang: self._set_servo(a),
                          parent_bg=COLORS["card"], fill=COLORS["card2"],
                          fg=COLORS["text"], hover=COLORS["border"], font=self.fonts["pill"]
                          ).pack(side="left", expand=True, fill="x", padx=3)
        self.servo_dial.set_angle(90)

    def _build_logs(self):
        frame = tk.Frame(self.root, bg=COLORS["bg"])
        frame.pack(fill="x", padx=18, pady=(0, 14))
        head = tk.Frame(frame, bg=COLORS["bg"])
        head.pack(fill="x")
        self._label(head, "SYSTEM LOG", font="h2", fg="muted", bg="bg").pack(side="left", pady=(0, 6))
        RoundedButton(head, "Export Logs", self._export_logs, parent_bg=COLORS["bg"],
                      fill=COLORS["card2"], fg=COLORS["text"], hover=COLORS["border"],
                      font=self.fonts["pill"]).pack(side="right")
        card = self._card(frame)
        card.pack(fill="x")
        self.log_text = scrolledtext.ScrolledText(
            card.body, height=8, bg=COLORS["card"], fg=COLORS["muted"],
            font=self.fonts["mono"], relief="flat", bd=0, highlightthickness=0,
            wrap="none", insertbackground=COLORS["text"])
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _export_logs(self):
        if system_log is None:
            return
        from tkinter import filedialog, messagebox
        dest = filedialog.askdirectory(title="Export system log to...")
        if not dest:
            return
        try:
            path = system_log.export(dest)
            system_log.log.info("system log exported to %s", path)
        except Exception as e:            # noqa: BLE001
            messagebox.showerror("Export failed", str(e))

    def _refresh_logs(self):
        if system_log is not None and self.log_text is not None:
            try:
                lines = system_log.recent(300)
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("end", "".join(lines))
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except Exception:             # noqa: BLE001
                pass
        if not self._stop:
            self.root.after(1500, self._refresh_logs)

    def _build_door(self, parent):
        wrap, box = self._section(parent, "DOOR")
        wrap.pack(fill="x", pady=(14, 0))
        btns = tk.Frame(box, bg=COLORS["card"])
        btns.pack(fill="x")
        RoundedButton(btns, "Open", lambda: self.hub.set_door_magnet(True),
                      parent_bg=COLORS["card"], fill=COLORS["card2"], fg=COLORS["text"],
                      hover=COLORS["border"], font=self.fonts["pill"]
                      ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        RoundedButton(btns, "Close", lambda: self.hub.set_door_magnet(False),
                      parent_bg=COLORS["card"], fill=COLORS["accent"], fg="white",
                      hover=self._shade(COLORS["accent"], 1.12), font=self.fonts["pill"]
                      ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _build_nitrogen(self, parent):
        wrap, box = self._section(parent, "NITROGEN SYSTEM")
        wrap.pack(fill="x", pady=(14, 0))
        self.valve_status = tk.Label(box, text="UNKNOWN", font=self.fonts["pill"],
                                     fg="white", bg=COLORS["muted"], padx=12, pady=6)
        self.valve_status.pack(anchor="w", pady=(0, 10))
        btns = tk.Frame(box, bg=COLORS["card"])
        btns.pack(fill="x")
        RoundedButton(btns, "Open", lambda: self._valve(True),
                      parent_bg=COLORS["card"], fill=COLORS["card2"], fg=COLORS["text"],
                      hover=COLORS["border"], font=self.fonts["pill"]
                      ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        RoundedButton(btns, "Close", lambda: self._valve(False),
                      parent_bg=COLORS["card"], fill=COLORS["accent"], fg="white",
                      hover=self._shade(COLORS["accent"], 1.12), font=self.fonts["pill"]
                      ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    @staticmethod
    def _shade(hexcolor, factor):
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
        r, g, b = (min(255, int(c * factor)) for c in (r, g, b))
        return f"#{r:02x}{g:02x}{b:02x}"

    # --- callbacks --------------------------------------------------------
    @staticmethod
    def _log(msg):
        if system_log is not None:
            try:
                system_log.log.info(msg)
            except Exception:             # noqa: BLE001
                pass

    def _valve(self, on):
        self._log(f"nitrogen valve {'OPEN' if on else 'CLOSE'}")
        self.hub.set_valve(on)

    def _on_fan_change(self, fan, val):
        pct = round(val)
        self.fan_pct[fan].config(text=f"{pct}% PWM")
        self.hub.set_channel(fan, pct)

    def _on_led_change(self, led, val):
        pct = round(val)
        duty = pct * LED_MAX_DUTY / 100.0          # brightness -> real duty (LED calibration)
        if not self.hub.set_led(led, duty):        # blocked by wavelength mode
            self.led_slider[led].set(0)
            pct = 0
        self.led_pct[led].config(text=f"{pct}%")
        # reflect the automatically-driven cooling fan in the fan UI
        fan = self.hub.led_fan(led)
        if fan and fan in self.fan_slider:
            speed = self.hub.led_fan_speed(led) if pct > 0 else 0
            self.fan_slider[fan].set(speed)
            self.fan_pct[fan].config(text=f"{speed}% PWM")

    def _on_servo_change(self, val):
        ang = round(val)
        self.servo_angle_lbl.config(text=f"{ang}°")
        self.servo_dial.set_angle(ang)
        self.hub.set_servo(ang)

    def _set_servo(self, angle):
        self.servo_slider.set(angle)
        self._on_servo_change(angle)

    def _toggle_mode(self):
        cur = self.hub.wavelength_mode()
        self._set_mode("450nm" if cur == "405nm" else "405nm")

    def _set_mode(self, mode):
        self.hub.select_mode(mode)             # all LEDs off first, set GPIO17, verify
        for led, _ in LED_LAYOUT:              # all LEDs are now off
            self.led_slider[led].set(0)
            self.led_pct[led].config(text="0%")
        with self._snap_lock:
            self.snapshot["mode"] = mode
        self._refresh_ui()

    # --- polling + refresh ------------------------------------------------
    def _poll_loop(self):
        temp_names = list(ioc.TEMP_SENSORS)
        count = 0
        health_period = max(1, round(self.hub.heater_health_sec() / SENSOR_REFRESH_SEC))
        while not self._stop:
            self.hub.door_interlock()             # safety: door open -> all LEDs + heater OFF
            temps = {name: self.hub.read_temp(name) for name in temp_names}
            rpms = {fan: self.hub.read_rpm(fan) for fan, _, _ in FAN_LAYOUT}
            with self._snap_lock:
                self.snapshot = {"temp": temps, "rpm": rpms,
                                 "pressure": self.hub.read_pressure(),
                                 "valve": self.hub.get_valve(),
                                 "door": self.hub.get_door(),
                                 "heater": self.hub.get_heater(),
                                 "heater_fault": self.hub.heater_fault,
                                 "led_fault": self.hub.led_fault,
                                 "mode": self.hub.wavelength_mode(),
                                 "cooling": self.hub.cooling_status()}
            count += 1
            if count % health_period == 0:        # background heater health check (~10s)
                self.hub.heater_health_check()
            time.sleep(SENSOR_REFRESH_SEC)

    def _schedule_ui_refresh(self):
        self._refresh_ui()
        if not self._stop:
            self.root.after(UI_REFRESH_MS, self._schedule_ui_refresh)

    def _refresh_ui(self):
        with self._snap_lock:
            snap = self.snapshot

        for fan, _, _ in FAN_LAYOUT:
            rpm = snap["rpm"].get(fan)
            self.fan_rpm[fan].config(text=f"{rpm:.0f}" if rpm is not None else "----")
            self.fan_bar[fan].set(rpm)
            lbl, temp_name = self.fan_temp[fan]
            if temp_name:
                t = snap["temp"].get(temp_name)
                lbl.config(text=f"{t:.1f} °C" if t is not None else "--", fg=temp_color(t))

        for name, lbl in self.temp_chips.items():
            t = snap["temp"].get(name)
            lbl.config(text=f"{t:.1f}°" if t is not None else "--", fg=temp_color(t))

        self.led_fault_lbl.config(text=snap.get("led_fault") or "")

        valve = snap["valve"]
        if valve is None:
            self.valve_status.config(text="UNKNOWN", bg=COLORS["muted"])
        else:
            self.valve_status.config(text="OPEN" if valve else "CLOSED",
                                     bg=COLORS["accent"] if valve else COLORS["muted"])

        door = snap.get("door")
        self.hdr_door.value.config(
            text=("Open" if door else "Closed") if door is not None else "--",
            fg=COLORS["orange"] if door else (COLORS["green"] if door is not None else COLORS["muted"]))

        heater = snap.get("heater")
        if heater is not None:
            self.heater_toggle.set(bool(heater))
        self.heater_fault_lbl.config(text=snap.get("heater_fault") or "")
        if heater != self._last_heater:        # reflect the auto-driven cooling fan
            self._last_heater = heater
            fan, pwm = self.hub.heater_fan_info()
            if fan in self.fan_slider:
                val = pwm if heater else 0
                self.fan_slider[fan].set(val)
                self.fan_pct[fan].config(text=f"{val}% PWM")
        # cooling mode: toggle + measured rate + auto-driven fan sliders
        cool = snap.get("cooling") or {}
        active = cool.get("active")
        if active is not None:
            self.cooling_toggle.set(bool(active))
        rm, pwm = cool.get("rate_meas"), cool.get("pwm")
        if active:
            txt = (f"Measured {rm:+.2f} °C/min" if rm is not None else "Measured --")
            if pwm is not None:
                txt += f"   fan {pwm:.0f}%"
            self.cooling_meas.config(text=txt, fg=COLORS["accent"])
        else:
            self.cooling_meas.config(text="Measured --", fg=COLORS["muted"])
        self.cooling_fault_lbl.config(
            text=cool.get("fault") or
            ("rate not achievable at current chamber temp" if cool.get("limited") else ""))
        if active or active != self._last_cooling:   # reflect the auto-driven fans
            self._last_cooling = active
            hfan, cfan = cool.get("heater_fan", "FAN_HEATER"), cool.get("chamber_fan", "FAN_COOLING")
            hpwm = cool.get("heater_fan_pwm", 100) if active else 0
            cpwm = (pwm if pwm is not None else 0) if active else 0
            for fan, val in ((hfan, hpwm), (cfan, cpwm)):
                if fan in self.fan_slider:
                    self.fan_slider[fan].set(val)
                    self.fan_pct[fan].config(text=f"{val:.0f}% PWM")

        ct = snap["temp"].get(CHAMBER_TEMP)
        self.heater_temp.config(text=f"Chamber {ct:.1f} °C" if ct is not None else "Chamber --",
                                fg=temp_color(ct))
        self.hdr_temp.value.config(text=f"{ct:.1f}°C" if ct is not None else "--",
                                   fg=temp_color(ct) if ct is not None else COLORS["muted"])

        self.pressure_gauge.set_value(snap["pressure"])

        mode = snap.get("mode")
        door_open = (snap.get("door") is True)
        if mode and self.hdr_mode:
            self.hdr_mode.value.config(
                text=mode, fg=COLORS["accent"] if mode == "405nm" else COLORS["orange"])
            if mode != self._last_mode:
                self._last_mode = mode
                if self.mode_btn:
                    self.mode_btn.set_text(mode)

        # door interlock banner (shown only when the door is open)
        if door_open != self._banner_shown:
            self._banner_shown = door_open
            if door_open:
                self.door_banner.pack(fill="x", padx=18, pady=(0, 6), before=self._body)
            else:
                self.door_banner.pack_forget()

        # LED sliders are usable only when the door is CLOSED and the LED is
        # allowed in the current wavelength mode; otherwise disabled and zeroed.
        for led, _ in LED_LAYOUT:
            sl = self.led_slider.get(led)
            if not sl:
                continue
            allowed = (not door_open) and (mode is not None) and \
                self.hub.led_allowed_in_mode(led, mode)
            sl.set_enabled(allowed)
            if not allowed and sl.get() != 0:
                sl.set(0)
                self.led_pct[led].config(text="0%")

    def _on_close(self):
        self._stop = True
        try:
            self.hub.close()
        except Exception:
            pass
        self.root.destroy()


def main():
    hub = HardwareHub()
    root = tk.Tk()
    Dashboard(root, hub)
    root.mainloop()


if __name__ == "__main__":
    main()
