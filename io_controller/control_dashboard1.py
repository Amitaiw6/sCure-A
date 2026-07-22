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

import io_controller as ioc


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
# LED brightness calibration + minimum-intensity cutoff + SSR wavelength table
# all live in components.json (led_power.led_max_duty / min_intensity) and are
# applied by io_controller.SystemController.set_led_brightness - not here.
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
                 width=170, height=22, accent=None, track_h=6):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.lo, self.hi, self.value = lo, hi, value
        self.command, self.h = command, height
        self.accent = accent or COLORS["accent"]
        self.knob_r = height / 2 - 2
        self.track_h = track_h
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", lambda e: self._from_x(e.x))
        self.bind("<B1-Motion>", lambda e: self._from_x(e.x))

    def _frac(self):
        return (self.value - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def _bounds(self):
        m = self.knob_r + 2
        return m, self.winfo_width() - m

    def _draw(self):
        w = self.winfo_width()
        if w <= 2:
            return
        self.delete("all")
        x0, x1 = self._bounds()
        cy, th = self.h / 2, self.track_h
        self._pill(x0, x1, cy - th / 2, cy + th / 2, COLORS["track"])
        fx = x0 + (x1 - x0) * self._frac()
        self._pill(x0, fx, cy - th / 2, cy + th / 2, self.accent)
        r = self.knob_r
        self.create_oval(fx - r, cy - r, fx + r, cy + r, fill="white",
                         outline=self.accent, width=2)

    def _pill(self, x0, x1, y0, y1, color):
        r = (y1 - y0) / 2
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=color, outline=color)
        if x1 - x0 >= 2 * r:
            self.create_oval(x1 - 2 * r, y0, x1, y1, fill=color, outline=color)
            self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color)

    def _from_x(self, x):
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
        c, s = self.c, self.size
        pad = max(10, int(s * 0.11))          # proportional so the gauge scales cleanly
        lw = max(6, int(s * 0.085))
        c.delete("all")
        box = (pad, pad, s - pad, s - pad)
        c.create_arc(*box, start=225, extent=-270, style="arc", width=lw,
                     outline=COLORS["track"])
        if val is not None:
            frac = max(0.0, min(1.0, val / self.maxval))
            if frac > 0:
                c.create_arc(*box, start=225, extent=-270 * frac, style="arc",
                             width=lw, outline=gauge_color(frac))
        cx = cy = s / 2
        c.create_text(cx, cy - max(3, int(s * 0.033)),
                      text=(f"{val:.1f}" if val is not None else "--"),
                      fill=COLORS["text"], font=self.fonts["gauge"])
        c.create_text(cx, cy + max(12, int(s * 0.13)), text=self.units,
                      fill=COLORS["muted"], font=self.fonts["small"])


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
        c, w, h = self.c, self.w, self.h
        pad = max(9, int(w * 0.075))          # proportional so the dial scales cleanly
        lw = max(6, int(w * 0.05))
        tick = max(6, int(w * 0.05))
        c.delete("all")
        r = min(w / 2 - pad, h - pad)
        cx, cy = w / 2, h - 4
        box = (cx - r, cy - r, cx + r, cy + r)
        c.create_arc(*box, start=180, extent=-180, style="arc", width=lw,
                     outline=COLORS["track"])
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            a = math.radians(180 - 180 * frac)
            x0, y0 = cx + (r - tick) * math.cos(a), cy - (r - tick) * math.sin(a)
            x1, y1 = cx + r * math.cos(a), cy - r * math.sin(a)
            c.create_line(x0, y0, x1, y1, fill=COLORS["border"], width=2)
        if ang is not None:
            frac = max(0.0, min(1.0, (ang - self.lo) / (self.hi - self.lo)))
            c.create_arc(*box, start=180, extent=-180 * frac, style="arc",
                         width=lw, outline=COLORS["accent"])
            a = math.radians(180 - 180 * frac)
            ni = max(8, int(w * 0.067))
            nx, ny = cx + (r - ni) * math.cos(a), cy - (r - ni) * math.sin(a)
            c.create_line(cx, cy, nx, ny, fill=COLORS["accent"], width=max(3, int(w * 0.017)),
                          capstyle="round")
        hub = max(4, int(w * 0.025))
        c.create_oval(cx - hub, cy - hub, cx + hub, cy + hub, fill=COLORS["text"], outline="")
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
        self.lock = threading.Lock()
        self.box = None
        self.tachs = {}
        self.available = False
        self.error = None
        self._servo = None
        self.servo_ok = True
        try:
            self.box = ioc.IOController()
            self.available = True
        except Exception as e:        # noqa: BLE001
            self.error = str(e)
        if self.available:
            for fan, cfg in ioc.PCA_FANS.items():
                try:
                    self.tachs[fan] = ioc.FanTach(cfg["tach"])
                except Exception:     # noqa: BLE001
                    self.tachs[fan] = None
        self._rpm_last = {}
        # ALL LED system logic (min-intensity cutoff, SSR wavelength table for
        # GPIO16/20, brightness calibration, auto fans) lives in
        # io_controller.SystemController - the dashboard only delegates to it
        # and mirrors the result in the UI.
        try:
            cfg = ioc.load_component_config()
        except Exception:             # noqa: BLE001
            cfg = {}
        self.min_intensity = cfg.get("led_power", {}).get("min_intensity", 10)
        self.led_fans = {name: (c.get("fan"), c.get("fan_speed", 100))
                         for name, c in cfg.get("leds", {}).items()}
        self.sys = None
        if self.available and cfg:
            try:
                self.sys = ioc.SystemController(self.box, cfg, lock=self.lock)
            except Exception:         # noqa: BLE001
                self.sys = None

    def set_channel(self, name, percent):
        if not self.available:
            return
        with self.lock:
            self.box.pca.set_duty(ioc.PCA_CHANNELS[name], percent)

    def set_led(self, led, pct):
        """Delegate the whole LED logic (threshold, SSRs GPIO16/20, calibration,
        auto fan) to SystemController. True if applied, False if blocked."""
        if self.sys is None:
            return True               # simulation / no config
        try:
            return self.sys.set_led_brightness(led, pct)
        except Exception:             # noqa: BLE001
            return False

    def set_heater(self, on):
        if not self.available:
            return
        try:
            with self.lock:
                self.box.pca.set_duty_verified(ioc.PCA_CHANNELS["PWM_HEATER"], 100 if on else 0)
        except Exception:             # noqa: BLE001
            pass

    def get_heater(self):
        if not self.available:
            return None
        try:
            with self.lock:
                st = self.box.pca.read_state(ioc.PCA_CHANNELS["PWM_HEATER"])
            return st.startswith("ON")
        except Exception:             # noqa: BLE001
            return None

    def set_servo(self, angle):
        if not self.servo_ok:
            return
        try:
            with self.lock:
                if self._servo is None:
                    self._servo = ioc.Servo()
                self._servo.goto(angle)
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
        if not self.available:
            return None
        try:
            with self.lock:
                return ioc.door_is_open()
        except Exception:             # noqa: BLE001
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

    def read_rpm(self, fan):
        t = self.tachs.get(fan)
        if t is None:
            return None
        now = time.monotonic()
        cnt = t.count
        prev = self._rpm_last.get(fan)
        self._rpm_last[fan] = (cnt, now)
        if prev is None:
            return None
        dc, dt = cnt - prev[0], now - prev[1]
        return (dc / ioc.PCA_PULSES_PER_REV) * (60.0 / dt) if dt > 0 else None

    def close(self):
        if self._servo is not None:
            try: self._servo.close()
            except Exception: pass
        for t in self.tachs.values():
            if t is not None:
                try: t.close()
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

        # --- adaptive scaling: fit the whole UI on the current screen ------
        # The layout was designed for ~1200x1040 px of usable space; on smaller
        # screens every size (fonts, paddings, gauges) shrinks proportionally.
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        avail_w, avail_h = sw - 16, sh - 70          # taskbar + window chrome
        self.S = max(0.55, min(1.0, avail_h / 1040.0, avail_w / 1200.0))
        s = self.s
        self.root.minsize(s(1080), s(720))
        if self.S < 1.0:
            self.root.geometry(f"{avail_w}x{avail_h}+0+0")

        sans, mono = _pick(root, SANS_STACK), _pick(root, MONO_STACK)

        def fs(pt):
            return max(7, int(round(pt * self.S)))

        self.fonts = {
            "h1":       tkfont.Font(family=sans, size=fs(17), weight="bold"),
            "h2":       tkfont.Font(family=sans, size=fs(11), weight="bold"),
            "body":     tkfont.Font(family=sans, size=fs(10)),
            "small":    tkfont.Font(family=sans, size=fs(9)),
            "pill":     tkfont.Font(family=sans, size=fs(10), weight="bold"),
            "icon":     tkfont.Font(family=sans, size=fs(13)),
            "mono":     tkfont.Font(family=mono, size=fs(10)),
            "num":      tkfont.Font(family=mono, size=fs(14), weight="bold"),
            "mono_big": tkfont.Font(family=mono, size=fs(20), weight="bold"),
            "gauge":    tkfont.Font(family=mono, size=fs(26), weight="bold"),
        }
        self._init_styles()

        self.snapshot = {"temp": {}, "rpm": {}, "pressure": None,
                         "valve": None, "door": None, "heater": None}
        self._snap_lock = threading.Lock()
        self.fan_rpm, self.fan_temp, self.fan_pct, self.fan_bar = {}, {}, {}, {}
        self.fan_slider = {}
        self.led_pct, self.temp_chips = {}, {}
        self.valve_status = self.pressure_gauge = None
        self.servo_dial = self.servo_angle_lbl = None
        self.heater_toggle = self.heater_temp = None
        self.hdr_door = self.hdr_temp = None

        self._build_ui()
        self._stop = False
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)
        self._poller.start()
        self._schedule_ui_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- scaling ----------------------------------------------------------
    def s(self, v):
        """Scale a design-pixel value to the current screen."""
        return max(1, int(round(v * self.S)))

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
        return Card(parent, parent_bg=COLORS.get(parent_bg, parent_bg),
                    radius=self.s(14), padx=self.s(16), pady=self.s(14))

    def _section(self, parent, title):
        wrap = tk.Frame(parent, bg=COLORS["bg"])
        self._label(wrap, title, font="h2", fg="muted", bg="bg").pack(anchor="w", pady=(0, self.s(6)))
        card = self._card(wrap)
        card.pack(fill="x")
        return wrap, card.body

    # --- header -----------------------------------------------------------
    def _build_ui(self):
        s = self.s
        header = tk.Frame(self.root, bg=COLORS["header"])
        header.pack(fill="x")
        bar = tk.Frame(header, bg=COLORS["header"])
        bar.pack(fill="x", padx=s(18), pady=s(10))

        self._label(bar, "◆", font="h1", fg="accent", bg="header").pack(side="left")
        self._label(bar, f"  {SYSTEM_NAME}", font="h1", bg="header").pack(side="left")

        # right-side icon buttons
        for glyph, active in (("⚙", True), ("↻", False), ("N₂", False)):
            IconButton(bar, glyph, parent_bg=COLORS["header"], font=self.fonts["icon"],
                       active=active, d=s(38)).pack(side="right", padx=s(4))

        # live status: door + chamber temperature
        self.hdr_temp = self._statusbox(bar, "TEMP", "--")
        self.hdr_temp.pack(side="right", padx=(0, 14))
        self.hdr_door = self._statusbox(bar, "DOOR", "--")
        self.hdr_door.pack(side="right", padx=(0, 14))
        ok = self.hub.available
        tk.Label(bar, text=("● connected" if ok else "● simulation"),
                 font=self.fonts["small"], fg="white",
                 bg=COLORS["green"] if ok else COLORS["red"],
                 padx=s(10), pady=s(4)).pack(side="right", padx=(0, s(14)))

        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=s(18), pady=s(12))
        body.columnconfigure(0, weight=3, uniform="c")
        body.columnconfigure(1, weight=2, uniform="c")
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=COLORS["bg"])
        left.grid(row=0, column=0, sticky="nsew")
        self._build_fans(left)
        self._build_temps(left)
        self._build_leds(left)

        right = tk.Frame(body, bg=COLORS["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(s(16), 0))
        self._build_heater(right)
        self._build_pressure(right)
        self._build_servo(right)
        self._build_nitrogen(right)

    def _statusbox(self, parent, label, value):
        f = tk.Frame(parent, bg=COLORS["header"])
        self._label(f, label, font="small", fg="muted", bg="header").pack(side="left", padx=(0, 6))
        val = self._label(f, value, font="pill", bg="header")
        val.pack(side="left")
        f.value = val
        return f

    # --- sections ---------------------------------------------------------
    def _build_fans(self, parent):
        s = self.s
        wrap = tk.Frame(parent, bg=COLORS["bg"])
        wrap.pack(fill="both", expand=True)
        self._label(wrap, "FANS", font="h2", fg="muted", bg="bg").pack(anchor="w", pady=(0, s(6)))
        grid = tk.Frame(wrap, bg=COLORS["bg"])
        grid.pack(fill="both", expand=True)
        for i in range(2):
            grid.columnconfigure(i, weight=1, uniform="fan")

        for idx, (fan, location, temp_name) in enumerate(FAN_LAYOUT):
            r, c = divmod(idx, 2)
            card = self._card(grid)
            card.grid(row=r, column=c, sticky="nsew", padx=s(5), pady=s(5))
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
            rpm_row.grid(row=2, column=0, sticky="w", pady=(s(6), s(3)))
            rpm_lbl = self._label(rpm_row, "----", font="mono_big")
            rpm_lbl.pack(side="left")
            self._label(rpm_row, " rpm", font="small", fg="muted").pack(side="left", pady=(s(7), 0))
            self.fan_rpm[fan] = rpm_lbl

            bar = LinearBar(inner, width=s(220), height=max(3, s(6)),
                            maxval=RPM_MAX, color=COLORS["accent"])
            bar.grid(row=3, column=0, sticky="ew", pady=(0, s(6)))
            self.fan_bar[fan] = bar

            ctrl = tk.Frame(inner, bg=COLORS["card"])
            ctrl.grid(row=4, column=0, sticky="ew")
            ctrl.columnconfigure(1, weight=1)
            self._label(ctrl, "0%", font="small", fg="muted").grid(row=0, column=0, sticky="w")
            sl = Slider(ctrl, parent_bg=COLORS["card"], lo=0, hi=100, value=0, height=s(22),
                        track_h=max(3, s(6)),
                        command=lambda val, n=fan: self._on_fan_change(n, val))
            sl.grid(row=0, column=1, sticky="ew", padx=s(6))
            self.fan_slider[fan] = sl
            pct_lbl = self._label(ctrl, "0% PWM", font="small", fg="accent")
            pct_lbl.grid(row=0, column=2, sticky="e")
            self.fan_pct[fan] = pct_lbl

    @staticmethod
    def _short_temp(name):
        return name.replace("TEMP_", "").replace("_ORIGIN", " ORIG").replace("_", " ")

    def _build_temps(self, parent):
        s = self.s
        wrap, grid = self._section(parent, "TEMPERATURES")
        wrap.pack(fill="x", pady=(s(10), 0))
        cols = 4
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="temp")
        for idx, name in enumerate(ioc.TEMP_SENSORS):
            r, c = divmod(idx, cols)
            chip = tk.Frame(grid, bg=COLORS["card2"])
            chip.grid(row=r, column=c, sticky="nsew", padx=s(4), pady=s(4))
            cell = tk.Frame(chip, bg=COLORS["card2"])
            cell.pack(fill="both", padx=s(10), pady=s(6))
            self._label(cell, self._short_temp(name), font="small", fg="muted",
                        bg="card2").pack(anchor="w")
            val = self._label(cell, "--", font="num", fg="muted", bg="card2")
            val.pack(anchor="w")
            self.temp_chips[name] = val

    def _build_leds(self, parent):
        s = self.s
        wrap, grid = self._section(parent, "LEDS")
        wrap.pack(fill="x", pady=(s(10), 0))
        grid.columnconfigure(1, weight=1)
        for idx, (led, location) in enumerate(LED_LAYOUT):
            self._label(grid, location, font="body").grid(row=idx, column=0, sticky="w", pady=s(4))
            Slider(grid, parent_bg=COLORS["card"], lo=0, hi=100, value=0, height=s(22),
                   track_h=max(3, s(6)),
                   command=lambda val, n=led: self._on_led_change(n, val)
                   ).grid(row=idx, column=1, sticky="ew", padx=s(10))
            pct_lbl = self._label(grid, "0%", font="mono", fg="accent")
            pct_lbl.grid(row=idx, column=2, sticky="e")
            self.led_pct[led] = pct_lbl

    def _build_heater(self, parent):
        wrap, box = self._section(parent, "HEATER")
        wrap.pack(fill="x")
        row = tk.Frame(box, bg=COLORS["card"])
        row.pack(fill="x")
        row.columnconfigure(1, weight=1)
        self._label(row, "Chamber heater", font="body").grid(row=0, column=0, sticky="w")
        self.heater_toggle = Toggle(row, parent_bg=COLORS["card"],
                                    w=self.s(48), h=self.s(26),
                                    command=lambda on: self.hub.set_heater(on))
        self.heater_toggle.grid(row=0, column=2, sticky="e")
        self.heater_temp = self._label(box, "Chamber --", font="num", fg="muted")
        self.heater_temp.pack(anchor="w", pady=(self.s(8), 0))

    def _build_pressure(self, parent):
        s = self.s
        wrap, box = self._section(parent, "PRESSURE")
        wrap.pack(fill="x", pady=(s(14), 0))
        self.pressure_gauge = ArcGauge(box, self.fonts, size=s(180),
                                       maxval=PRESSURE_MAX, units=PRESSURE_UNITS)
        self.pressure_gauge.pack()
        self._label(box, f"{PRESSURE_UNITS}  ·  {PRESSURE_CHANNEL}",
                    font="small", fg="muted").pack(pady=(0, s(2)))

    def _build_servo(self, parent):
        s = self.s
        wrap, box = self._section(parent, "SERVO")
        wrap.pack(fill="x", pady=(s(14), 0))
        self.servo_dial = ServoDial(box, self.fonts, width=s(230),
                                    lo=ioc.SERVO_MIN_ANGLE, hi=ioc.SERVO_MAX_ANGLE)
        self.servo_dial.pack()
        ctrl = tk.Frame(box, bg=COLORS["card"])
        ctrl.pack(fill="x", pady=(s(4), s(6)))
        ctrl.columnconfigure(0, weight=1)
        self.servo_slider = Slider(ctrl, parent_bg=COLORS["card"], height=s(22),
                                   track_h=max(3, s(6)),
                                   lo=ioc.SERVO_MIN_ANGLE, hi=ioc.SERVO_MAX_ANGLE, value=90,
                                   command=lambda val: self._on_servo_change(val))
        self.servo_slider.grid(row=0, column=0, sticky="ew")
        self.servo_angle_lbl = self._label(ctrl, "90°", font="mono", fg="accent")
        self.servo_angle_lbl.grid(row=0, column=1, sticky="e", padx=(s(8), 0))
        presets = tk.Frame(box, bg=COLORS["card"])
        presets.pack(fill="x")
        for label, ang in (("0°", ioc.SERVO_MIN_ANGLE),
                           ("90°", (ioc.SERVO_MIN_ANGLE + ioc.SERVO_MAX_ANGLE) // 2),
                           ("180°", ioc.SERVO_MAX_ANGLE)):
            RoundedButton(presets, label, lambda a=ang: self._set_servo(a),
                          parent_bg=COLORS["card"], fill=COLORS["card2"],
                          fg=COLORS["text"], hover=COLORS["border"], font=self.fonts["pill"],
                          radius=s(9), padx=s(16), height=s(30)
                          ).pack(side="left", expand=True, fill="x", padx=s(3))
        self.servo_dial.set_angle(90)

    def _build_nitrogen(self, parent):
        s = self.s
        wrap, box = self._section(parent, "NITROGEN SYSTEM")
        wrap.pack(fill="x", pady=(s(14), 0))
        self.valve_status = tk.Label(box, text="UNKNOWN", font=self.fonts["pill"],
                                     fg="white", bg=COLORS["muted"], padx=s(12), pady=s(5))
        self.valve_status.pack(anchor="w", pady=(0, s(8)))
        btns = tk.Frame(box, bg=COLORS["card"])
        btns.pack(fill="x")
        RoundedButton(btns, "Open", lambda: self.hub.set_valve(True),
                      parent_bg=COLORS["card"], fill=COLORS["card2"], fg=COLORS["text"],
                      hover=COLORS["border"], font=self.fonts["pill"],
                      radius=s(9), padx=s(16), height=s(30)
                      ).pack(side="left", expand=True, fill="x", padx=(0, s(4)))
        RoundedButton(btns, "Close", lambda: self.hub.set_valve(False),
                      parent_bg=COLORS["card"], fill=COLORS["accent"], fg="white",
                      hover=self._shade(COLORS["accent"], 1.12), font=self.fonts["pill"],
                      radius=s(9), padx=s(16), height=s(30)
                      ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    @staticmethod
    def _shade(hexcolor, factor):
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
        r, g, b = (min(255, int(c * factor)) for c in (r, g, b))
        return f"#{r:02x}{g:02x}{b:02x}"

    # --- callbacks --------------------------------------------------------
    def _on_fan_change(self, fan, val):
        pct = round(val)
        self.fan_pct[fan].config(text=f"{pct}% PWM")
        self.hub.set_channel(fan, pct)

    def _on_led_change(self, led, val):
        pct = round(val)
        on = pct >= self.hub.min_intensity
        # the whole LED logic runs in io_controller.SystemController
        if not self.hub.set_led(led, pct):     # blocked: door open / routing fault
            on = False
        self.led_pct[led].config(text=f"{pct}%" if on else f"{pct}% (off)",
                                 fg=COLORS["accent"] if on else COLORS["muted"])
        # mirror the automatically-driven LED fan in the fan card UI
        fan, speed = self.hub.led_fans.get(led, (None, 100))
        if fan and fan in self.fan_slider:
            duty = speed if on else 0
            self.fan_slider[fan].set(duty)
            self.fan_pct[fan].config(text=f"{duty}% PWM")

    def _on_servo_change(self, val):
        ang = round(val)
        self.servo_angle_lbl.config(text=f"{ang}°")
        self.servo_dial.set_angle(ang)
        self.hub.set_servo(ang)

    def _set_servo(self, angle):
        self.servo_slider.set(angle)
        self._on_servo_change(angle)

    # --- polling + refresh ------------------------------------------------
    def _poll_loop(self):
        temp_names = list(ioc.TEMP_SENSORS)
        while not self._stop:
            temps = {name: self.hub.read_temp(name) for name in temp_names}
            rpms = {fan: self.hub.read_rpm(fan) for fan, _, _ in FAN_LAYOUT}
            with self._snap_lock:
                self.snapshot = {"temp": temps, "rpm": rpms,
                                 "pressure": self.hub.read_pressure(),
                                 "valve": self.hub.get_valve(),
                                 "door": self.hub.get_door(),
                                 "heater": self.hub.get_heater()}
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
            self.heater_toggle.set(heater)
        ct = snap["temp"].get(CHAMBER_TEMP)
        self.heater_temp.config(text=f"Chamber {ct:.1f} °C" if ct is not None else "Chamber --",
                                fg=temp_color(ct))
        self.hdr_temp.value.config(text=f"{ct:.1f}°C" if ct is not None else "--",
                                   fg=temp_color(ct) if ct is not None else COLORS["muted"])

        self.pressure_gauge.set_value(snap["pressure"])

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
