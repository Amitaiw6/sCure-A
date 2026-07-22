#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
io_controller.py - single unified controller for every component on the
CureBox IO board (Raspberry Pi CM5).

Merges into one file all the drivers that used to live in separate modules:
  - PCA9685   (i2c-0, 0x55)  - 16-channel PWM: heater, fans, lights, motor EN, LEDs
  - TCA6424A  (i2c-0, 0x23)  - I/O expander: motor direction (H-bridge), valves,
                               fan ON/OFF, NFC reset
  - ADS1115   (analog)       - analog reads: light sensors and signals (0x48 on i2c-0/i2c-1)
  - ADS1115   (temperature)  - NTC thermistors -> temperature (beta equation, 0x49)
  - Servo     (GPIO8)        - SG90 via gpiozero
  - Direct GPIO (pinctrl)    - signals driven straight from a pin (nitrogen valve)

A single object - IOController - owns all components and drives/reads them together.
Unified CLI: python3 io_controller.py <component> <action> ...   (see --help)

Dependencies (imported lazily as needed): smbus2, gpiozero. The `pinctrl` system
tool is used for the direct-GPIO signals. Imports are guarded so the file still
loads off-Pi (for help/listing).
"""

import sys
import os
import json
import time
import math
import threading

try:
    from smbus2 import SMBus
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False

try:
    from system_log import log as LOG          # centralized system logger
except Exception:                              # noqa: BLE001 - logging is optional
    import logging as _logging
    LOG = _logging.getLogger("curebox")

# ===========================================================================
#  Unified configuration - every map and address in one place
# ===========================================================================

# --- PCA9685 ---------------------------------------------------------------
PCA_BUS, PCA_ADDR = 0, 0x55
PCA_MODE1, PCA_MODE2, PCA_PRESCALE, PCA_LED0_ON_L = 0x00, 0x01, 0xFE, 0x06
PCA_SLEEP, PCA_AI, PCA_RESTART = 0x10, 0x20, 0x80

PCA_CHANNELS = {
    "FAN_HEATER": 0, "FAN_DOOR": 1, "FAN_RIGHT": 2, "FAN_LEFT": 3, "FAN_BACK": 4, "FAN_COOLING": 5,
    "PWM_HEATER": 6, "LIGHT1": 7,
    "MOT1_EN": 8, "MOT2_EN": 9, "BOFA": 10,
    "LED_BACK": 11, "LED_DOOR": 12, "LED_RIGHT": 13, "LED_LEFT": 14,
    "LED_ANALOG5": 15,
}
# A fan = a PWM channel on the PCA9685 + a GPIO pin for the tachometer (RPM).
PCA_FANS = {
    "FAN_HEATER":  {"pwm": 0, "tach": 22},
    "FAN_DOOR":    {"pwm": 1, "tach": 23},
    "FAN_RIGHT":   {"pwm": 2, "tach": 24},
    "FAN_LEFT":    {"pwm": 3, "tach": 19},
    "FAN_BACK":    {"pwm": 4, "tach": 25},
    "FAN_COOLING": {"pwm": 5, "tach": 26},
}
PCA_PULSES_PER_REV = 2
PCA_RATED_RPM = {n: 3000 for n in PCA_FANS}
PCA_SOFT_START_SEC = 15
PCA_DROP_THRESHOLD = 0.20
# Channels behind an inverting driver (inverted in software). ON/OFF-only = DIGITAL.
PCA_INVERTED = {0, 1, 2, 3, 4, 5, 7, 8, 9}
PCA_DIGITAL = {6}

# --- TCA6424A --------------------------------------------------------------
TCA_BUS, TCA_ADDR = 0, 0x23
TCA_REG_INPUT, TCA_REG_OUTPUT, TCA_REG_CONFIG = 0x80, 0x84, 0x8C
TCA_PINS = {
    "NFC_RESET":  (0, 1), "LED_SWITCH": (0, 5),
    "FAN1_ONOFF": (1, 1), "FAN2_ONOFF": (1, 2), "FAN3_ONOFF": (1, 3),
    "FAN4_ONOFF": (1, 4), "FAN5_ONOFF": (1, 5), "FAN6_ONOFF": (1, 6),
    "MOT1_IN1":   (2, 5), "MOT1_IN2":   (2, 4),
    "MOT2_IN1":   (2, 2), "MOT2_IN2":   (2, 1),
    "VALVE_2_ON": (2, 6), "DOOR_MAGNET": (2, 6),   # P26 = valve 2 = door magnet
    "VALVE_1_ON": (2, 7),                          # (OUT2 -> J8_DOOR_MAGNET per schematic)
}
TCA_SAFE_HIGH = {"NFC_RESET"}
TCA_INVERTED = {"FAN1_ONOFF", "FAN2_ONOFF", "FAN3_ONOFF",
                "FAN4_ONOFF", "FAN5_ONOFF", "FAN6_ONOFF"}

# --- ADS1115 (shared) ------------------------------------------------------
ADS_REG_CONVERT, ADS_REG_CONFIG = 0x00, 0x01
ADS_FS_VOLTAGE = {0: 6.144, 1: 4.096, 2: 2.048, 3: 1.024, 4: 0.512, 5: 0.256}

# Analog reads (light sensors / signals) - PGA +/-6.144V
ANALOG_PGA = 0
ANALOG_SUPPLY = 5.0
ANALOG_ADCS = {
    "U10": {"bus": 1, "addr": 0x48},
    "U8":  {"bus": 0, "addr": 0x48},
}
ANALOG_SENSORS = {
    "LIGHT1": ("U10", 0), "LIGHT2": ("U10", 1),
    "AIN2": ("U10", 2), "AIN3": ("U10", 3),
    "SENSOR1_A1": ("U8", 0), "SENSOR1_A2": ("U8", 1),
    "SENSOR2_A1": ("U8", 2), "SENSOR2_A2": ("U8", 3),
}
ANALOG_DIVIDER = {"AIN2": 2.0, "AIN3": 2.0}

# Temperature (NTC) - PGA +/-4.096V, beta equation
TEMP_PGA = 1
TEMP_ADCS = {
    "U6": {"bus": 0, "addr": 0x49},
    "U7": {"bus": 1, "addr": 0x49},
}
TEMP_SENSORS = {
    "TEMP_RIGHT_ORIGIN": ("U6", 0), "TEMP_RIGHT": ("U6", 1),
    "TEMP_LEFT_ORIGIN":  ("U6", 2), "TEMP_LEFT":  ("U6", 3),
    "TEMP_BACK_ORIGIN":  ("U7", 0), "TEMP_DOOR_ORIGIN": ("U7", 1),
    "TEMP_CHAMBER":      ("U7", 2),   # NTC7 - chamber temperature
}
NTC_R0, NTC_BETA, NTC_T0 = 10000.0, 3934.0, 298.15
NTC_R_SERIES, NTC_VREF, NTC_DIVIDER = 10000.0, 3.3, "pullup"

# --- Servo (SG90 via gpiozero) --------------------------------------------
SERVO_PIN = 8
SERVO_MIN_PULSE, SERVO_MAX_PULSE = 0.0005, 0.0024
SERVO_MIN_ANGLE, SERVO_MAX_ANGLE = 0, 180
SERVO_INVERTED = True

# --- Direct GPIO (pinctrl) -------------------------------------------------
GPIO_SIGNALS = {
    "NITROGEN_VALVE": 13,   # nitrogen valve - GPIO13
    "RGB_LED": 12,          # RGB status LEDs (TM3909 driver, RGB_LV line) - GPIO12
    # GPIO16 (450nm SSR), GPIO20 (405nm SSR) and GPIO27 (voltage routing) are
    # driven by SystemController per the wavelength mode - see components.json
    # "led_power". They are not manual signals.
}
GPIO_INVERTED = set()

# Read-only GPIO inputs (sensors) - read via `pinctrl get`, never driven.
# GPIO27 = door open/closed sensor (door interlock). GPIO17 is the wavelength
# select output (in components.json led_power), not an input.
GPIO_INPUTS = {"DOOR_STATUS": 27}
GPIO_INPUT_OPEN_LEVEL = {"DOOR_STATUS": 0}   # GPIO27 HIGH = closed, LOW = open (bench-confirmed 2026-07-22)
DOOR_OPEN_MESSAGE = "Door is Open - Operation Disabled"


# ===========================================================================
#  Set-and-verify with retry (shared by every writable component)
# ===========================================================================
VERIFY_RETRIES = 3


class VerificationError(RuntimeError):
    """Raised when a component could not be confirmed in the commanded state."""


def set_and_verify(label, apply_fn, check_fn, retries=VERIFY_RETRIES):
    """Apply an action, read it back, and retry up to `retries` times.

    apply_fn(): performs the write.
    check_fn(): returns (ok: bool, observed) - reads back and compares.
    Returns (attempt, observed) on success; raises VerificationError if every
    attempt failed.
    """
    observed = None
    for attempt in range(1, retries + 1):
        apply_fn()
        ok, observed = check_fn()
        if ok:
            return attempt, observed
    raise VerificationError(
        f"{label}: not confirmed after {retries} attempts (last read back: {observed!r})")


def verify_each(actions):
    """Run every (label, callable) action, attempting all of them, then raise one
    aggregated VerificationError listing whatever failed. Used by the bulk paths
    (alloff / safe) so the whole system is still driven to its target state even
    if one component cannot be confirmed."""
    failures = []
    for label, act in actions:
        try:
            act()
        except Exception as e:  # noqa: BLE001 - collect, report all at the end
            failures.append(f"{label}: {e}")
    if failures:
        raise VerificationError(
            f"{len(failures)} component(s) not confirmed:\n  " + "\n  ".join(failures))


# ===========================================================================
#  PCA9685 - PWM controller
# ===========================================================================
class PCA9685:
    def __init__(self, bus=PCA_BUS, addr=PCA_ADDR):
        self.bus = SMBus(bus)
        self.addr = addr
        self.bus.write_byte_data(self.addr, PCA_MODE1, PCA_AI)
        self.bus.write_byte_data(self.addr, PCA_MODE2, 0x04)  # totem-pole, per-channel invert in SW
        time.sleep(0.001)

    def set_freq(self, hz):
        prescale = max(3, min(255, round(25_000_000 / (4096 * hz)) - 1))
        old = self.bus.read_byte_data(self.addr, PCA_MODE1)
        self.bus.write_byte_data(self.addr, PCA_MODE1, (old & 0x7F) | PCA_SLEEP)
        self.bus.write_byte_data(self.addr, PCA_PRESCALE, prescale)
        self.bus.write_byte_data(self.addr, PCA_MODE1, old)
        time.sleep(0.005)
        self.bus.write_byte_data(self.addr, PCA_MODE1, old | PCA_RESTART | PCA_AI)

    def set_pwm(self, ch, on, off):
        base = PCA_LED0_ON_L + 4 * ch
        self.bus.write_i2c_block_data(self.addr, base,
                                      [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

    def _write_full(self, ch, on_state):
        self.set_pwm(ch, 0x1000, 0) if on_state else self.set_pwm(ch, 0, 0x1000)

    def set_duty(self, ch, percent):
        """Logical duty 0-100%. Applies per-channel inversion; digital channel = switch."""
        percent = max(0.0, min(100.0, percent))
        if ch in PCA_DIGITAL:
            percent = 100.0 if percent > 0 else 0.0
        eff = (100.0 - percent) if ch in PCA_INVERTED else percent
        if eff <= 0:
            self._write_full(ch, False)
        elif eff >= 100:
            self._write_full(ch, True)
        else:
            self.set_pwm(ch, 0, int(eff / 100 * 4095))

    def on(self, ch):  self.set_duty(ch, 100)
    def off(self, ch): self.set_duty(ch, 0)
    def name(self, label, percent): self.set_duty(PCA_CHANNELS[label], percent)

    def read_state(self, ch):
        """Return a logical state string for a channel (honors inversion)."""
        base = PCA_LED0_ON_L + 4 * ch
        d = self.bus.read_i2c_block_data(self.addr, base, 4)
        on, off = d[0] | (d[1] << 8), d[2] | (d[3] << 8)
        inv = ch in PCA_INVERTED
        if on & 0x1000:
            return "OFF (full)" if inv else "ON (full)"
        if off & 0x1000:
            return "ON (full)" if inv else "OFF (full)"
        pct = off / 4095 * 100
        return f"{(100 - pct) if inv else pct:.0f}%"

    def _intended_regs(self, ch, percent):
        """The (on, off) register pair set_duty would write for this command."""
        percent = max(0.0, min(100.0, percent))
        if ch in PCA_DIGITAL:
            percent = 100.0 if percent > 0 else 0.0
        eff = (100.0 - percent) if ch in PCA_INVERTED else percent
        if eff <= 0:
            return (0, 0x1000)          # full-OFF
        if eff >= 100:
            return (0x1000, 0)          # full-ON
        return (0, int(eff / 100 * 4095))

    def set_duty_verified(self, ch, percent, retries=VERIFY_RETRIES):
        """Set duty, then read the channel registers back to confirm. Retries."""
        want = self._intended_regs(ch, percent)
        base = PCA_LED0_ON_L + 4 * ch

        def check():
            d = self.bus.read_i2c_block_data(self.addr, base, 4)
            got = (d[0] | (d[1] << 8), d[2] | (d[3] << 8))
            return got == want, self.read_state(ch)
        return set_and_verify(f"PCA channel {ch}",
                              lambda: self.set_duty(ch, percent), check, retries)

    def on_verified(self, ch, retries=VERIFY_RETRIES):
        return self.set_duty_verified(ch, 100, retries)

    def off_verified(self, ch, retries=VERIFY_RETRIES):
        return self.set_duty_verified(ch, 0, retries)

    def close(self):
        self.bus.close()


# ===========================================================================
#  TCA6424A - I/O expander (motors / valves / NFC)
# ===========================================================================
class TCA6424A:
    def __init__(self, bus=TCA_BUS, addr=TCA_ADDR):
        self.bus = SMBus(bus)
        self.addr = addr
        self.out = [0x00, 0x00, 0x00]   # shadow of the output registers
        self._safe_init()

    def _safe_init(self):
        for name in TCA_SAFE_HIGH | TCA_INVERTED:   # logical OFF / safe = physical high
            port, bit = TCA_PINS[name]
            self.out[port] |= (1 << bit)
        self.bus.write_i2c_block_data(self.addr, TCA_REG_OUTPUT, self.out)
        cfg = [0xFF, 0xFF, 0xFF]
        for port, bit in TCA_PINS.values():
            cfg[port] &= ~(1 << bit)                # mapped pin = output
        self.bus.write_i2c_block_data(self.addr, TCA_REG_CONFIG, cfg)

    def _commit(self):
        self.bus.write_i2c_block_data(self.addr, TCA_REG_OUTPUT, self.out)

    def _setbit(self, name, val):
        port, bit = TCA_PINS[name]
        if val:
            self.out[port] |= (1 << bit)
        else:
            self.out[port] &= ~(1 << bit)

    def set_pin(self, name, value):
        level = (0 if value else 1) if name in TCA_INVERTED else (1 if value else 0)
        self._setbit(name, level)
        self._commit()

    def get_pin(self, name):
        port, bit = TCA_PINS[name]
        data = self.bus.read_i2c_block_data(self.addr, TCA_REG_INPUT, 3)
        level = (data[port] >> bit) & 1
        return (1 - level) if name in TCA_INVERTED else level

    def motor(self, n, direction):
        in1, in2 = f"MOT{n}_IN1", f"MOT{n}_IN2"
        table = {"fwd": (1, 0), "rev": (0, 1), "brake": (1, 1), "stop": (0, 0)}
        if direction not in table:
            raise ValueError("direction: fwd/rev/stop/brake")
        a, b = table[direction]
        self._setbit(in1, a); self._setbit(in2, b)
        self._commit()

    def valve(self, n, on):     self.set_pin(f"VALVE_{n}_ON", 1 if on else 0)
    def fan_onoff(self, n, on): self.set_pin(f"FAN{n}_ONOFF", 1 if on else 0)

    def nfc_reset(self):
        self.set_pin("NFC_RESET", 0)
        time.sleep(0.01)
        self.set_pin_verified("NFC_RESET", 1)   # confirm it returns to idle (high)

    def all_safe(self):
        for n in (1, 2):
            self.motor(n, "stop")
            self.valve(n, False)

    # --- verified variants (set, read back, retry) ------------------------
    def set_pin_verified(self, name, value, retries=VERIFY_RETRIES):
        def check():
            v = self.get_pin(name)
            return v == value, v
        return set_and_verify(f"TCA pin {name}",
                              lambda: self.set_pin(name, value), check, retries)

    def valve_verified(self, n, on, retries=VERIFY_RETRIES):
        return self.set_pin_verified(f"VALVE_{n}_ON", 1 if on else 0, retries)

    def motor_verified(self, n, direction, retries=VERIFY_RETRIES):
        table = {"fwd": (1, 0), "rev": (0, 1), "brake": (1, 1), "stop": (0, 0)}
        if direction not in table:
            raise ValueError("direction: fwd/rev/stop/brake")
        in1, in2 = f"MOT{n}_IN1", f"MOT{n}_IN2"
        want = table[direction]

        def check():
            got = (self.get_pin(in1), self.get_pin(in2))
            return got == want, got
        return set_and_verify(f"TCA motor {n} ({direction})",
                              lambda: self.motor(n, direction), check, retries)

    def all_safe_verified(self, retries=VERIFY_RETRIES):
        """Stop both motors and close both valves, verifying each. Attempts all."""
        actions = []
        for n in (1, 2):
            actions.append((f"motor {n}", lambda n=n: self.motor_verified(n, "stop", retries)))
            actions.append((f"valve {n}", lambda n=n: self.valve_verified(n, False, retries)))
        verify_each(actions)

    def close(self):
        self.bus.close()


# ===========================================================================
#  ADS1115 - analog-to-digital converter (used for both analog and temperature)
# ===========================================================================
class ADS1115:
    def __init__(self, bus, addr, pga):
        self.bus, self.addr, self.pga = bus, addr, pga

    def read_raw(self, channel):
        mux = 0b100 + channel
        config = ((1 << 15) | (mux << 12) | (self.pga << 9) |
                  (1 << 8) | (0b100 << 5) | 0b00011)
        self.bus.write_i2c_block_data(self.addr, ADS_REG_CONFIG,
                                      [(config >> 8) & 0xFF, config & 0xFF])
        for _ in range(50):
            time.sleep(0.002)
            cfg = self.bus.read_i2c_block_data(self.addr, ADS_REG_CONFIG, 2)
            if cfg[0] & 0x80:
                break
        d = self.bus.read_i2c_block_data(self.addr, ADS_REG_CONVERT, 2)
        raw = (d[0] << 8) | d[1]
        return raw - 0x10000 if raw > 0x7FFF else raw

    def read_voltage(self, channel):
        return self.read_raw(channel) * ADS_FS_VOLTAGE[self.pga] / 32768.0


# ===========================================================================
#  NTC helpers (resistance / temperature)
# ===========================================================================
def ntc_voltage_to_resistance(v):
    if v <= 0 or v >= NTC_VREF:
        return None
    if NTC_DIVIDER == "pullup":
        return NTC_R_SERIES * v / (NTC_VREF - v)
    return NTC_R_SERIES * (NTC_VREF - v) / v


def ntc_resistance_to_temp(r):
    if r is None or r <= 0:
        return None
    inv_t = (1.0 / NTC_T0) + (1.0 / NTC_BETA) * math.log(r / NTC_R0)
    return (1.0 / inv_t) - 273.15


# ===========================================================================
#  Servo (SG90) and direct GPIO (pinctrl)
# ===========================================================================
class Servo:
    """SG90 via gpiozero (software PWM, lgpio backend on CM5)."""
    def __init__(self, pin=SERVO_PIN):
        from gpiozero import AngularServo
        self.dev = AngularServo(
            pin, min_angle=SERVO_MIN_ANGLE, max_angle=SERVO_MAX_ANGLE,
            min_pulse_width=SERVO_MIN_PULSE, max_pulse_width=SERVO_MAX_PULSE)

    def goto(self, angle):
        angle = max(SERVO_MIN_ANGLE, min(SERVO_MAX_ANGLE, angle))
        self.dev.angle = (SERVO_MAX_ANGLE + SERVO_MIN_ANGLE - angle) if SERVO_INVERTED else angle
        return angle

    def sweep(self, step=10, delay=0.05, cycles=2):
        for _ in range(cycles):
            for a in range(SERVO_MIN_ANGLE, SERVO_MAX_ANGLE + 1, step):
                self.goto(a); time.sleep(delay)
            for a in range(SERVO_MAX_ANGLE, SERVO_MIN_ANGLE - 1, -step):
                self.goto(a); time.sleep(delay)

    def close(self):
        self.dev.detach()
        self.dev.close()


class FanTach:
    """Read fan RPM by counting tachometer pulses (gpiozero, lgpio backend on CM5).

    Two usage modes:
      - read_rpm(window): blocking - counts pulses over `window` seconds.
      - .count property: non-blocking - a GUI/poller samples the running total and
        computes RPM from the delta over its own refresh interval.
    """
    def __init__(self, gpio, pulses_per_rev=PCA_PULSES_PER_REV):
        from gpiozero import DigitalInputDevice
        self.dev = DigitalInputDevice(gpio, pull_up=True)   # tach is open-collector
        self.ppr = pulses_per_rev
        self._count = 0
        self.dev.when_activated = self._tick

    def _tick(self):
        self._count += 1

    @property
    def count(self):
        return self._count

    def read_rpm(self, window=1.0):
        self._count = 0
        time.sleep(window)
        return (self._count / self.ppr) * (60.0 / window)

    def close(self):
        self.dev.close()


def _pinctrl(*args):
    import subprocess
    res = subprocess.run(["pinctrl", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"pinctrl failed: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def gpio_set_signal(name, on):
    if name not in GPIO_SIGNALS:
        raise ValueError(f"unknown signal: {name}")
    gpio = GPIO_SIGNALS[name]
    level = (not on) if name in GPIO_INVERTED else bool(on)
    _pinctrl("set", str(gpio), "op", "dh" if level else "dl")


def gpio_get_signal(name):
    if name not in GPIO_SIGNALS:
        raise ValueError(f"unknown signal: {name}")
    out = _pinctrl("get", str(GPIO_SIGNALS[name])).lower()
    phys = 1 if "hi" in out else (0 if "lo" in out else None)
    if phys is None:
        return None
    return (1 - phys) if name in GPIO_INVERTED else phys


def gpio_set_signal_verified(name, on, retries=VERIFY_RETRIES):
    """Drive a signal (pinctrl set), then read it back (pinctrl get). Retries.

    This is the generalized form of `pinctrl set <pin> op dh && pinctrl get <pin>`.
    """
    desired = 1 if on else 0

    def check():
        v = gpio_get_signal(name)
        return v == desired, v
    return set_and_verify(f"GPIO {name}",
                          lambda: gpio_set_signal(name, on), check, retries)


def read_gpio_level(pin):
    """Read any GPIO pin's level via `pinctrl get`. Returns 1, 0, or None."""
    try:
        out = _pinctrl("get", str(pin)).lower()
    except Exception:
        return None
    return 1 if "hi" in out else (0 if "lo" in out else None)


def set_gpio_level(pin, on):
    """Drive any GPIO pin as an output high/low via `pinctrl`."""
    _pinctrl("set", str(pin), "op", "dh" if on else "dl")


def led_power_off(config=None):
    """Disconnect all LED drivers: drive the SSR + routing GPIOs OFF.
    Safe to call from any shutdown/fault path; ignores missing config/pinctrl."""
    try:
        lp = (config or load_component_config()).get("led_power", {})
    except Exception:
        return
    for key in ("ssr_450nm", "ssr_405nm", "routing"):
        pin = lp.get(key)
        if pin is not None:
            try:
                set_gpio_level(pin, False)
            except Exception:
                pass


_configured_inputs = set()


def ensure_gpio_input(pin):
    """Configure `pin` as a plain input with NO internal pull, once per process.
    After boot pinctrl shows unconfigured pins as 'no ... | --' (no function, no
    level) and may leave a default pull-down that loads the sensor line - the
    door line already has its own external pull-up (R46), so the internal pull
    must stay off."""
    if pin in _configured_inputs:
        return
    try:
        _pinctrl("set", str(pin), "ip", "pn")
        _configured_inputs.add(pin)
    except Exception:                 # noqa: BLE001 - off-Pi / no pinctrl
        pass


def gpio_read_input(name):
    """Read a read-only GPIO input via `pinctrl get`. Returns 1, 0, or None."""
    if name not in GPIO_INPUTS:
        raise ValueError(f"unknown input: {name}")
    ensure_gpio_input(GPIO_INPUTS[name])
    return read_gpio_level(GPIO_INPUTS[name])


def door_is_open():
    """True if the door is open, False if closed, None if unreadable/unconfigured."""
    if "DOOR_STATUS" not in GPIO_INPUTS:
        return None
    level = gpio_read_input("DOOR_STATUS")
    if level is None:
        return None
    return level == GPIO_INPUT_OPEN_LEVEL["DOOR_STATUS"]


# ===========================================================================
#  IOController - the master controller that unifies every component
# ===========================================================================
class IOController:
    """Owns every component. I2C devices open immediately; the servo is lazy."""

    def __init__(self):
        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus2 is not installed - required for all I2C components")
        self.pca = PCA9685()
        self.io = TCA6424A()
        self._buses = {}                      # bus_number -> SMBus (shared by the ADCs)
        self.analog = self._build_adcs(ANALOG_ADCS, ANALOG_PGA)
        self.temp = self._build_adcs(TEMP_ADCS, TEMP_PGA)
        self._servo = None

    def _bus(self, n):
        if n not in self._buses:
            self._buses[n] = SMBus(n)
        return self._buses[n]

    def _build_adcs(self, table, pga):
        return {chip: ADS1115(self._bus(cfg["bus"]), cfg["addr"], pga)
                for chip, cfg in table.items()}

    @property
    def servo(self):
        if self._servo is None:
            self._servo = Servo()
        return self._servo

    # --- sensor reads ------------------------------------------------------
    def read_temp(self, name):
        chip, ch = TEMP_SENSORS[name]
        v = self.temp[chip].read_voltage(ch)
        r = ntc_voltage_to_resistance(v)
        return {"voltage": v, "resistance": r, "temp": ntc_resistance_to_temp(r)}

    def read_analog(self, name):
        chip, ch = ANALOG_SENSORS[name]
        v = self.analog[chip].read_voltage(ch) * ANALOG_DIVIDER.get(name, 1.0)
        return {"voltage": v, "percent": max(0.0, min(100.0, v / ANALOG_SUPPLY * 100.0))}

    # --- whole-system safe state ------------------------------------------
    def all_safe(self, retries=VERIFY_RETRIES):
        """Drive every component to its safe state and verify each one.

        Turns off every PWM channel, stops both motors, closes both valves, and
        drops every direct-GPIO signal - reading each back, retrying, and raising
        an aggregated error for whatever could not be confirmed. Every component
        is still driven even if one fails to confirm."""
        actions = []
        for ch in range(16):
            actions.append((f"PCA ch{ch}", lambda c=ch: self.pca.off_verified(c, retries)))
        for n in (1, 2):
            actions.append((f"motor {n}", lambda n=n: self.io.motor_verified(n, "stop", retries)))
            actions.append((f"valve {n}", lambda n=n: self.io.valve_verified(n, False, retries)))
        for name in GPIO_SIGNALS:
            actions.append((name, lambda nm=name: gpio_set_signal_verified(nm, False, retries)))
        verify_each(actions)

    def snapshot(self):
        """Concurrent state snapshot of every component (dict)."""
        snap = {"pca": {}, "io": {}, "temp": {}, "analog": {}}
        names = {v: k for k, v in PCA_CHANNELS.items()}
        for ch in range(16):
            snap["pca"][names.get(ch, str(ch))] = self.pca.read_state(ch)
        for name in TCA_PINS:
            snap["io"][name] = self.io.get_pin(name)
        for name in TEMP_SENSORS:
            snap["temp"][name] = self.read_temp(name)["temp"]
        for name in ANALOG_SENSORS:
            snap["analog"][name] = self.read_analog(name)["voltage"]
        return snap

    def close(self):
        if self._servo is not None:
            try: self._servo.close()
            except Exception: pass
        try: self.pca.close()
        except Exception: pass
        try: self.io.close()
        except Exception: pass
        for b in self._buses.values():
            try: b.close()
            except Exception: pass


# ===========================================================================
#  RGB status LEDs (TM3909 driver on GPIO12, WS2812-style serial protocol)
# ===========================================================================
RGB_GPIO_DEFAULT = 12
RGB_COUNT_DEFAULT = 16          # writing more pixels than fitted is harmless
RGB_ORDER_DEFAULT = "GRB"
RGB_COLORS = {
    "red":     (255, 0, 0),
    "green":   (0, 255, 0),
    "blue":    (0, 0, 255),
    "white":   (255, 255, 255),
    "yellow":  (255, 180, 0),
    "orange":  (255, 90, 0),
    "purple":  (170, 0, 255),
    "cyan":    (0, 200, 255),
    "pink":    (255, 40, 120),
    "off":     (0, 0, 0),
}


def parse_rgb_color(text):
    """'red', 'purple', ... or hex 'RRGGBB' / '#RRGGBB' -> (r, g, b)."""
    t = text.strip().lower().lstrip("#")
    if t in RGB_COLORS:
        return RGB_COLORS[t]
    if len(t) == 6 and all(c in "0123456789abcdef" for c in t):
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    raise ValueError(f"unknown color: {text} (named colors: {', '.join(RGB_COLORS)}, or hex RRGGBB)")


class RGBLeds:
    """Color control for the RGB status LEDs (single data line on GPIO12).
    Uses adafruit-blinka NeoPixel (RP1 PIO backend on CM5). Settings come from
    components.json "rgb" (gpio / count / order); install once with:
        sudo pip3 install adafruit-circuitpython-neopixel
    """
    def __init__(self, config=None):
        cfg = {}
        try:
            cfg = (config or load_component_config()).get("rgb", {})
        except Exception:            # noqa: BLE001 - config optional for RGB
            pass
        self.count = int(cfg.get("count", RGB_COUNT_DEFAULT))
        pin_num = int(cfg.get("gpio", RGB_GPIO_DEFAULT))
        order = cfg.get("order", RGB_ORDER_DEFAULT)
        import board                 # lazy: only needed for RGB use
        import neopixel
        self.px = neopixel.NeoPixel(getattr(board, f"D{pin_num}"), self.count,
                                    auto_write=False, pixel_order=order)

    def fill(self, rgb, brightness=100.0):
        f = max(0.0, min(1.0, brightness / 100.0))
        self.px.fill(tuple(int(c * f) for c in rgb))
        self.px.show()

    def off(self):
        self.fill((0, 0, 0))

    def close(self):
        try:
            self.px.deinit()
        except Exception:            # noqa: BLE001
            pass


# ===========================================================================
#  Component configuration file + high-level system logic
# ===========================================================================
DEFAULT_COMPONENT_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "components.json")


def load_component_config(path=None):
    """Load the component configuration file (LEDs, fans, wavelength gating).
    Looks next to this script and in the current directory."""
    candidates = [path] if path else [DEFAULT_COMPONENT_CONFIG,
                                      os.path.join(os.getcwd(), "components.json")]
    for p in candidates:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("components.json not found (looked in: "
                            + ", ".join(str(c) for c in candidates if c) + ")")


class SystemController:
    """High-level logic layer driven entirely by the component config file:

      - wavelength gating: GPIO switch (405nm/450nm) decides which LEDs may turn on
      - automatic fan control: turning an LED on starts its mapped fan at the
        configured speed; turning it off stops that fan.

    All LED<->fan mapping, speeds and mode rules live in components.json, so adding
    LEDs or changing assignments needs no source changes.
    """
    def __init__(self, controller=None, config=None, config_path=None, lock=None):
        self.io = controller or IOController()
        self.config = config or load_component_config(config_path)
        self.leds = self.config["leds"]
        self.lp = self.config.get("led_power", {})   # SSR + voltage-routing GPIOs
        self.mode_override = None        # the software-selected wavelength mode
        self._leds_on = set()            # which LEDs are currently on
        self.led_fault = None            # last LED-driver / routing fault message
        self.lock = lock or threading.Lock()   # serializes all I2C access (shared with the app)
        self.heater_on = False
        self.heater_fault = None
        self._cooling = None             # lazy CoolingController (cooling_mode.py)
        self.tachs = {}                  # fan tachometers for RPM-based heater checks
        self._rpm_last = {}
        for fan, c in PCA_FANS.items():
            try:
                self.tachs[fan] = FanTach(c["tach"])
            except Exception:            # noqa: BLE001 - gpiozero / tach unavailable
                self.tachs[fan] = None

    def wavelength_mode(self):
        """The software-selected wavelength mode ('405nm' / '450nm')."""
        return self.mode_override or self.lp.get("default_mode", "405nm")

    # --- LED-driver power: SSR + voltage routing (GPIO16/20/27) -----------
    def apply_led_power(self, mode=None):
        """Drive the SSR + routing GPIOs for `mode` per the config table, then
        read GPIO27 back to verify routing. Returns (ok, reason)."""
        mode = mode or self.wavelength_mode()
        states = self.lp.get("modes", {}).get(mode)
        if not states:
            return False, f"no led_power config for {mode}"
        for key, want in states.items():
            pin = self.lp.get(key)
            if pin is not None:
                set_gpio_level(pin, bool(want))
        rpin = self.lp.get("routing")            # verify the voltage-routing pin
        if rpin is not None:
            want = states.get("routing", 0)
            level = read_gpio_level(rpin)
            if level != want:
                return False, f"GPIO{rpin} routing not {want} (read {level})"
        return True, None

    def led_power_off(self):
        """Disconnect all LED drivers (SSR + routing OFF)."""
        led_power_off(self.config)

    def _refresh_led_power(self):
        """Reconfigure (or shut off) the LED-driver GPIOs for the current state."""
        if self._leds_on:
            ok, why = self.apply_led_power()
            if not ok:                            # routing could not be verified -> fault
                self.led_fault = why
                self._all_leds_pwm_off()
                self.led_power_off()
        else:
            self.led_power_off()

    def _set_routing(self, mode):
        """Drive the wavelength-select GPIO (GPIO17) for `mode` and verify it."""
        states = self.lp.get("modes", {}).get(mode, {})
        rpin = self.lp.get("routing")
        if rpin is None:
            return True, None
        want = states.get("routing", 0)
        set_gpio_level(rpin, bool(want))
        level = read_gpio_level(rpin)
        if level != want:
            return False, f"GPIO{rpin} wavelength-select not {want} (read {level})"
        return True, None

    def select_mode(self, mode):
        """Safe wavelength switch: turn ALL LEDs off first, set GPIO17, verify it,
        then the new mode is active and LEDs may be re-enabled. (ok, reason)."""
        self.all_leds_off()                       # never two modes active at once
        self.mode_override = mode
        ok, why = self._set_routing(mode)
        self.led_fault = None if ok else why
        LOG.info("wavelength mode -> %s (%s)", mode, "ok" if ok else why)
        return ok, why

    # --- door interlock (GPIO27) -----------------------------------------
    def door_open(self):
        """True if door open, False if closed, None if unreadable (from GPIO27)."""
        ds = self.config.get("door_sensor", {})
        pin = ds.get("gpio")
        if pin is None:
            return door_is_open()
        ensure_gpio_input(pin)
        level = read_gpio_level(pin)
        if level is None:
            return None
        return level == ds.get("open_level", 0)   # default matches bench polarity: HIGH = closed

    def set_door_magnet(self, on):
        """Drive the door magnet actuator (valve 2, TCA P26). Open = energize, Close = de-energize."""
        with self.lock:
            self.io.io.set_pin("DOOR_MAGNET", 1 if on else 0)
        LOG.info("door magnet -> %s", "OPEN" if on else "CLOSE")

    def door_interlock(self):
        """Continuous safety: if the door is OPEN, force all LEDs + heater OFF and
        block operation. Returns True if the door is open."""
        if self.door_open() is True:
            if self._leds_on or self.heater_on:
                LOG.warning("DOOR OPENED during operation - forcing all LEDs + heater OFF")
                self.all_leds_off()
                self.disable_heater(DOOR_OPEN_MESSAGE)
            self.led_fault = DOOR_OPEN_MESSAGE
            return True
        if self.led_fault == DOOR_OPEN_MESSAGE:   # door closed again -> clear the notice
            self.led_fault = None
            LOG.info("door closed - operation re-enabled")
        return False

    def led_allowed(self, led, mode=None):
        mode = mode or self.wavelength_mode()
        return mode in self.leds.get(led, {}).get("modes", [])

    def allowed_leds(self, mode=None):
        mode = mode or self.wavelength_mode()
        return [name for name in self.leds if self.led_allowed(name, mode)]

    def _drive_fan(self, led, on):
        fan = self.leds[led].get("fan")
        if fan:
            speed = self.leds[led].get("fan_speed", 100) if on else 0
            self.io.pca.set_duty(PCA_CHANNELS[fan], speed)

    def set_led(self, led, intensity):
        """Set LED duty (0-100) with wavelength gating, LED-driver SSR + routing
        control, and automatic fan control. Returns True if applied, False if
        blocked (wavelength mode or GPIO27 routing could not be verified)."""
        if led not in self.leds:
            raise ValueError(f"unknown LED: {led}")
        # Below the configured minimum intensity the LED counts as OFF: PWM is
        # zeroed and, once no LED remains on, the driver SSRs (GPIO16/20) are
        # disconnected via led_power_off(). min_intensity is a user-facing
        # brightness %; led_max_duty converts it to the duty scale callers use.
        min_duty = (self.lp.get("min_intensity", 0)
                    * self.lp.get("led_max_duty", 100) / 100.0)
        if 0 < intensity < min_duty:
            LOG.info("LED %s intensity %.1f below minimum (%.1f duty) -> OFF",
                     led, intensity, min_duty)
            intensity = 0
        if intensity > 0:
            if self.door_open() is not False:     # require door confirmed CLOSED
                self.led_fault = DOOR_OPEN_MESSAGE
                LOG.warning("LED %s blocked: %s", led, DOOR_OPEN_MESSAGE)
                return False
            if not self.led_allowed(led):
                LOG.warning("LED %s blocked: not allowed in %s mode", led, self.wavelength_mode())
                return False
            ok, why = self.apply_led_power()      # SSR + routing configured & GPIO17 verified
            if not ok:
                self.led_fault = why
                LOG.error("LED %s blocked: %s", led, why)
                return False
            self.led_fault = None
        with self.lock:
            self.io.pca.set_duty(PCA_CHANNELS[led], intensity)
            self._drive_fan(led, intensity > 0)
        if intensity > 0:
            if led not in self._leds_on:          # log only the OFF->ON transition
                LOG.info("LED %s ON (%s)", led, self.wavelength_mode())
            self._leds_on.add(led)
        else:
            if led in self._leds_on:
                LOG.info("LED %s OFF", led)
            self._leds_on.discard(led)
            if not self._leds_on:
                self.led_power_off()              # last LED off -> disconnect drivers
        return True

    def set_led_brightness(self, led, pct):
        """Single entry point for user-facing LED control (brightness 0-100%).
        ALL the LED system logic is applied here, driven by components.json:

          - below led_power.min_intensity the LED counts as OFF
          - brightness is calibrated to PWM duty via led_power.led_max_duty
          - the wavelength mode is inferred from the LEDs that end up on:
            any 405nm-only LED on -> 405nm (SSRs GPIO16 + GPIO20), otherwise
            450nm (GPIO16 only); the SSRs follow the config mode table
          - the LED's mapped fan starts at fan_speed when the LED turns on and
            stops when it turns off; last LED off -> SSRs disconnected.

        Returns True if applied, False if blocked (door open / routing fault)."""
        if led not in self.leds:
            raise ValueError(f"unknown LED: {led}")
        thr = self.lp.get("min_intensity", 0)
        on = pct > 0 and pct >= thr
        duty = pct * self.lp.get("led_max_duty", 100) / 100.0 if on else 0.0
        will_on = (set(self._leds_on) | {led}) if on else (set(self._leds_on) - {led})
        if will_on:
            needs_405 = any("450nm" not in self.leds[l].get("modes", ["405nm"])
                            for l in will_on)
            self.mode_override = "405nm" if needs_405 else "450nm"
        return self.set_led(led, duty)

    def set_led_off(self, led):
        if led not in self.leds:
            raise ValueError(f"unknown LED: {led}")
        with self.lock:
            self.io.pca.set_duty(PCA_CHANNELS[led], 0)
            self._drive_fan(led, False)
        self._leds_on.discard(led)
        if not self._leds_on:
            self.led_power_off()

    def enforce_wavelength(self):
        """Turn off LEDs not allowed in the current mode, then re-apply the
        LED-driver routing for whatever remains on (or shut the drivers off)."""
        mode = self.wavelength_mode()
        for led in self.leds:
            if not self.led_allowed(led, mode):
                self.set_led_off(led)
        self._refresh_led_power()

    def _all_leds_pwm_off(self):
        with self.lock:
            for led in self.leds:
                self.io.pca.set_duty(PCA_CHANNELS[led], 0)
                self._drive_fan(led, False)
        self._leds_on.clear()

    def all_leds_off(self):
        self._all_leds_pwm_off()
        self.led_power_off()

    # --- startup safe state ----------------------------------------------
    def startup_safe(self):
        """Bring everything to a known-OFF state at startup: all PWM off, motors
        stopped, valves closed, direct signals off. Nothing runs until activated."""
        with self.lock:
            for ch in range(16):
                self.io.pca.set_duty(ch, 0)
            self.io.io.all_safe()        # TCA6424A: motors stop, valves closed
        for name in GPIO_SIGNALS:
            try:
                gpio_set_signal(name, False)
            except Exception:            # noqa: BLE001
                pass
        self.led_power_off()             # SSR + routing GPIOs OFF (LED drivers disconnected)
        self._leds_on.clear()
        self.led_fault = None
        self.heater_on = False
        self.heater_fault = None
        LOG.info("startup: all components OFF (safe state)")

    # --- fan RPM (from tachometers) --------------------------------------
    def read_rpm(self, fan):
        """Non-blocking RPM from the tach pulse delta since the previous call."""
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
        return (dc / PCA_PULSES_PER_REV) * (60.0 / dt) if dt > 0 else None

    def measure_rpm(self, fan, window=1.0):
        """Blocking RPM measurement over `window` seconds (no I2C; tach only)."""
        t = self.tachs.get(fan)
        if t is None:
            return None
        c0 = t.count
        time.sleep(window)
        return (t.count - c0) / PCA_PULSES_PER_REV * (60.0 / window)

    # --- heater safety (fan + thermistor protected) ----------------------
    HEATER_DEFAULTS = {
        "channel": "PWM_HEATER", "fan": "FAN_HEATER", "fan_pwm": 100,
        "thermistor": "TEMP_CHAMBER", "min_fan_rpm": 100,
        "temp_valid_min": -20, "temp_valid_max": 120, "health_check_sec": 10,
    }

    def heater_cfg(self):
        """Re-read the heater section fresh each call so config edits take effect."""
        cfg = dict(self.HEATER_DEFAULTS)
        try:
            c = load_component_config().get("heater", {})
        except Exception:                # noqa: BLE001
            c = self.config.get("heater", {})
        cfg.update({k: v for k, v in c.items() if not k.startswith("_")})
        return cfg

    def _thermistor_state(self, cfg):
        """(ok, temp, reason): invalid = disconnected / out-of-range / comm error."""
        name = cfg["thermistor"]
        try:
            with self.lock:
                t = self.io.read_temp(name)["temp"]
        except Exception:                # noqa: BLE001
            return False, None, f"thermistor {name} communication error"
        if t is None:
            return False, None, f"thermistor {name} disconnected / invalid reading"
        if t < cfg["temp_valid_min"] or t > cfg["temp_valid_max"]:
            return False, t, f"thermistor {name} out of range ({t:.1f} C)"
        return True, t, None

    def enable_heater(self):
        """Pre-flight (cooling fan spinning + thermistor valid) then enable.
        Returns (ok, reason). The heater is enabled ONLY if both checks pass."""
        self.heater_fault = None
        if self.is_cooling_on():                  # heating and cooling are mutually exclusive
            self.heater_fault = "cooling mode active - stop cooling first"
            LOG.warning("HEATER blocked: %s", self.heater_fault)
            return False, self.heater_fault
        if self.door_open() is not False:         # door interlock: must be confirmed CLOSED
            self.heater_fault = DOOR_OPEN_MESSAGE
            LOG.warning("HEATER blocked: %s", DOOR_OPEN_MESSAGE)
            return False, self.heater_fault
        cfg = self.heater_cfg()
        with self.lock:                                  # start cooling fan at configured PWM
            self.io.pca.set_duty(PCA_CHANNELS[cfg["fan"]], cfg["fan_pwm"])
        ok_t, _t, why = self._thermistor_state(cfg)      # thermistor must be valid
        if not ok_t:
            self.disable_heater(why)
            return False, why
        time.sleep(2.0)                                  # fan spin-up (no I2C lock held)
        rpm = self.measure_rpm(cfg["fan"])               # fan must actually spin
        if rpm is None or rpm < cfg["min_fan_rpm"]:
            why = f"heater fan not spinning (RPM={'?' if rpm is None else int(rpm)})"
            self.disable_heater(why)
            return False, why
        with self.lock:
            self.io.pca.set_duty(PCA_CHANNELS[cfg["channel"]], 100)
        self.heater_on = True
        LOG.info("HEATER ON (fan %s @ %g%%, RPM=%d)", cfg["fan"], cfg["fan_pwm"], int(rpm))
        return True, None

    def disable_heater(self, reason=None):
        cfg = self.heater_cfg()
        try:
            with self.lock:
                self.io.pca.set_duty(PCA_CHANNELS[cfg["channel"]], 0)   # heater off
                self.io.pca.set_duty(PCA_CHANNELS[cfg["fan"]], 0)       # fan off
        except Exception:                # noqa: BLE001
            pass
        was_on = self.heater_on
        self.heater_on = False
        if reason and reason != "user":
            self.heater_fault = reason
            LOG.error("HEATER OFF - fault: %s", reason)
        elif was_on:
            LOG.info("HEATER OFF (%s)", reason or "manual")

    def heater_health_check(self):
        """Re-verify fan + thermistor while the heater runs. Returns a fault
        reason (and turns the heater OFF) on failure, else None."""
        if not self.heater_on:
            return None
        cfg = self.heater_cfg()
        rpm = self.read_rpm(cfg["fan"])
        if rpm is None or rpm < cfg["min_fan_rpm"]:
            why = f"heater fan failure (RPM={'?' if rpm is None else int(rpm)})"
            self.disable_heater(why)
            return why
        ok_t, _t, why = self._thermistor_state(cfg)
        if not ok_t:
            self.disable_heater(why)
            return why
        return None

    def is_heater_on(self):
        return self.heater_on

    # --- cooling mode (logic in cooling_mode.py; thin delegation only) ----
    # The separate CoolingController drives the damper + fans exclusively
    # through this controller's verified IO activation functions.
    @property
    def cooling(self):
        if self._cooling is None:
            from cooling_mode import CoolingController   # lazy: avoids import cycle
            self._cooling = CoolingController(self)
        return self._cooling

    def start_cooling(self, rate, target_temp=None):
        return self.cooling.start(rate, target_temp)

    def set_cooling_rate(self, rate):
        return self.cooling.set_rate(rate)

    def stop_cooling(self, reason="user"):
        if self._cooling is not None:
            self._cooling.stop(reason)

    def cooling_status(self):
        if self._cooling is None:
            return {"active": False, "fault": None}
        return self._cooling.status()

    def is_cooling_on(self):
        return self._cooling is not None and self._cooling.active

    def close(self):
        if self._cooling is not None:
            try: self._cooling.close()   # ends the cooling loop; no hardware writes
            except Exception: pass
        for t in self.tachs.values():
            if t is not None:
                try: t.close()
                except Exception: pass


# ===========================================================================
#  Unified CLI
# ===========================================================================
def _resolve_pca_channel(token):
    if token.upper() in PCA_CHANNELS:
        return PCA_CHANNELS[token.upper()]
    if token.isdigit() and 0 <= int(token) <= 15:
        return int(token)
    raise SystemExit(f"unknown PCA channel: {token}")


def build_parser():
    import argparse
    p = argparse.ArgumentParser(
        prog="io_controller.py",
        description="Unified controller for every component on the CureBox IO board "
                    "(PCA9685 / TCA6424A / ADS1115 / Servo / GPIO).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 io_controller.py pca set PWM_HEATER 25 # heater element to 25%%
  python3 io_controller.py pca on FAN_RIGHT      # right fan full
  python3 io_controller.py io  motor 1 fwd       # motor 1 forward
  python3 io_controller.py io  valve 1 on        # open valve 1
  python3 io_controller.py temp read TEMP_RIGHT  # right temperature
  python3 io_controller.py analog read LIGHT1    # read a light sensor
  python3 io_controller.py servo angle 90        # SG90 to center
  python3 io_controller.py gpio on NITROGEN_VALVE
  python3 io_controller.py cooling run 2 --target 30   # cool at 2 C/min down to 30 C
  python3 io_controller.py status                # snapshot of *all* components at once
  python3 io_controller.py safe                  # return the whole system to a safe state
""")
    sub = p.add_subparsers(dest="comp", required=True)

    # --- pca ---
    pca = sub.add_parser("pca", help="PCA9685 - PWM").add_subparsers(dest="cmd", required=True)
    a = pca.add_parser("set");  a.add_argument("channel"); a.add_argument("percent", type=float)
    pca.add_parser("on").add_argument("channel")
    pca.add_parser("off").add_argument("channel")
    pca.add_parser("freq").add_argument("hz", type=float)
    pca.add_parser("alloff"); pca.add_parser("status"); pca.add_parser("list")

    # --- io (TCA6424A) ---
    io = sub.add_parser("io", help="TCA6424A - motors/valves/NFC").add_subparsers(dest="cmd", required=True)
    m = io.add_parser("motor"); m.add_argument("n", type=int, choices=[1, 2])
    m.add_argument("direction", choices=["fwd", "rev", "stop", "brake"])
    v = io.add_parser("valve"); v.add_argument("n", type=int, choices=[1, 2]); v.add_argument("state", choices=["on", "off"])
    pn = io.add_parser("pin"); pn.add_argument("name"); pn.add_argument("value", type=int, choices=[0, 1])
    io.add_parser("nfc-reset"); io.add_parser("safe"); io.add_parser("status"); io.add_parser("list")

    # --- temp ---
    tp = sub.add_parser("temp", help="temperature (NTC)").add_subparsers(dest="cmd", required=True)
    tp.add_parser("read").add_argument("sensor", nargs="?", default="all")
    tp.add_parser("raw"); tp.add_parser("list")
    tm = tp.add_parser("monitor"); tm.add_argument("--interval", type=float, default=1.0)

    # --- analog ---
    an = sub.add_parser("analog", help="analog reads").add_subparsers(dest="cmd", required=True)
    an.add_parser("read").add_argument("channel", nargs="?", default="all")
    an.add_parser("raw"); an.add_parser("list")
    am = an.add_parser("monitor"); am.add_argument("--interval", type=float, default=1.0)

    # --- servo ---
    sv = sub.add_parser("servo", help="SG90 servo").add_subparsers(dest="cmd", required=True)
    sv.add_parser("angle").add_argument("deg", type=float)
    sv.add_parser("min"); sv.add_parser("max"); sv.add_parser("center")
    sw = sv.add_parser("sweep")
    sw.add_argument("--step", type=int, default=10); sw.add_argument("--delay", type=float, default=0.05)
    sw.add_argument("--cycles", type=int, default=2)

    # --- direct gpio ---
    gp = sub.add_parser("gpio", help="direct GPIO (pinctrl)").add_subparsers(dest="cmd", required=True)
    gp.add_parser("on").add_argument("name")
    gp.add_parser("off").add_argument("name")
    gp.add_parser("status").add_argument("name", nargs="?", default="all")
    gp.add_parser("list")

    # --- rgb status LEDs (TM3909 on GPIO12, colors) ---
    rgb = sub.add_parser("rgb", help="RGB status LEDs - colors (GPIO12)").add_subparsers(dest="cmd", required=True)
    rs = rgb.add_parser("set"); rs.add_argument("color", help="name (red/green/...) or hex RRGGBB")
    rs.add_argument("brightness", nargs="?", type=float, default=100.0, help="0-100%% (default 100)")
    rgb.add_parser("off"); rgb.add_parser("list")

    # --- leds (config-driven: wavelength gating + automatic fan control) ---
    led = sub.add_parser("led", help="LED control with wavelength gating + auto fan").add_subparsers(dest="cmd", required=True)
    ls = led.add_parser("set"); ls.add_argument("led"); ls.add_argument("intensity", type=float)
    led.add_parser("on").add_argument("led")
    led.add_parser("off").add_argument("led")
    led.add_parser("list")

    # --- cooling mode (closed-loop cooling-rate control) ---
    cl = sub.add_parser("cooling", help="closed-loop cooling mode (damper + fans)"
                        ).add_subparsers(dest="cmd", required=True)
    cr = cl.add_parser("run", help="run cooling mode (blocking; Ctrl+C stops)")
    cr.add_argument("rate", type=float, help="desired cooling rate in C/min (0-5)")
    cr.add_argument("--target", type=float, default=None,
                    help="target temperature C (default from components.json)")

    # --- wavelength mode ---
    sub.add_parser("mode", help="show wavelength mode (405nm/450nm) from the switch GPIO")

    # --- unified ---
    sub.add_parser("status", help="snapshot of all components at once")
    sub.add_parser("safe", help="return the whole system to a safe state")
    return p


def cmd_pca(args):
    if args.cmd == "list":
        for name, ch in PCA_CHANNELS.items():
            print(f"  {ch:>2}  {name}")
        return
    pca = PCA9685()
    try:
        if args.cmd == "set":
            ch = _resolve_pca_channel(args.channel)
            attempt, _ = pca.set_duty_verified(ch, args.percent)
            print(f"channel {ch} ({args.channel}) -> {args.percent}% "
                  f"(verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "on":
            ch = _resolve_pca_channel(args.channel)
            attempt, _ = pca.on_verified(ch)
            print(f"channel {ch} -> ON (verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "off":
            ch = _resolve_pca_channel(args.channel)
            attempt, _ = pca.off_verified(ch)
            print(f"channel {ch} -> OFF (verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "freq":
            pca.set_freq(args.hz); print(f"PWM frequency -> {args.hz} Hz")
        elif args.cmd == "alloff":
            verify_each([(f"ch{ch}", lambda c=ch: pca.off_verified(c)) for ch in range(16)])
            print(f"all channels off (each verified up to {VERIFY_RETRIES} attempts)")
        elif args.cmd == "status":
            names = {v: k for k, v in PCA_CHANNELS.items()}
            for ch in range(16):
                tag = " (inv)" if ch in PCA_INVERTED else ""
                print(f"  {ch:>2} {names.get(ch, ''):<13} {pca.read_state(ch)}{tag}")
    finally:
        pca.close()


def cmd_io(args):
    if args.cmd == "list":
        for name, (port, bit) in TCA_PINS.items():
            print(f"  {name:<12} P{port}{bit}")
        return
    io = TCA6424A()
    try:
        if args.cmd == "motor":
            attempt, _ = io.motor_verified(args.n, args.direction)
            print(f"motor {args.n} -> {args.direction} (verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "valve":
            attempt, _ = io.valve_verified(args.n, args.state == "on")
            print(f"valve {args.n} -> {args.state} (verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "pin":
            attempt, _ = io.set_pin_verified(args.name.upper(), args.value)
            print(f"{args.name.upper()} -> {args.value} (verified, attempt {attempt}/{VERIFY_RETRIES})")
        elif args.cmd == "nfc-reset":
            io.nfc_reset(); print("NFC reset pulse done")
        elif args.cmd == "safe":
            io.all_safe_verified()
            print(f"all components returned to a safe state (verified up to {VERIFY_RETRIES} attempts)")
        elif args.cmd == "status":
            for name in TCA_PINS:
                print(f"  {name:<12} {io.get_pin(name)}")
    finally:
        io.close()


def _open_adcs(table, pga):
    buses = {}
    for cfg in table.values():
        buses.setdefault(cfg["bus"], None)
    for n in buses:
        buses[n] = SMBus(n)
    adcs = {chip: ADS1115(buses[cfg["bus"]], cfg["addr"], pga) for chip, cfg in table.items()}
    return adcs, buses


def cmd_temp(args):
    if args.cmd == "list":
        for name, (chip, ch) in TEMP_SENSORS.items():
            cfg = TEMP_ADCS[chip]
            print(f"  {name}  ->  {chip} (i2c-{cfg['bus']}, 0x{cfg['addr']:02X}), AIN{ch}")
        return
    adcs, buses = _open_adcs(TEMP_ADCS, TEMP_PGA)

    def read(name):
        chip, ch = TEMP_SENSORS[name]
        v = adcs[chip].read_voltage(ch)
        r = ntc_voltage_to_resistance(v)
        return v, r, ntc_resistance_to_temp(r)
    try:
        if args.cmd == "raw":
            for name in TEMP_SENSORS:
                chip, ch = TEMP_SENSORS[name]
                print(f"  {name}: {adcs[chip].read_voltage(ch):.4f} V")
        elif args.cmd == "read":
            names = list(TEMP_SENSORS) if args.sensor == "all" else [args.sensor.upper()]
            for name in names:
                if name not in TEMP_SENSORS: raise SystemExit(f"unknown sensor: {name}")
                v, r, t = read(name)
                print(f"  {name}: {f'{t:.1f} C' if t is not None else '-'}   ({v:.3f} V)")
        elif args.cmd == "monitor":
            print("continuous monitor (Ctrl+C to quit)\n")
            try:
                while True:
                    line = []
                    for name in TEMP_SENSORS:
                        _, _, t = read(name)
                        line.append(f"{name}={f'{t:.1f}' if t is not None else '-'}C")
                    print("  " + "  ".join(line))
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nmonitor stopped.")
    finally:
        for b in buses.values(): b.close()


def cmd_analog(args):
    if args.cmd == "list":
        for name, (chip, ch) in ANALOG_SENSORS.items():
            cfg = ANALOG_ADCS[chip]; scale = ANALOG_DIVIDER.get(name)
            extra = f"  (divider x{scale:g})" if scale else ""
            print(f"  {name:<11} ->  {chip} (i2c-{cfg['bus']}, 0x{cfg['addr']:02X}), AIN{ch}{extra}")
        return
    adcs, buses = _open_adcs(ANALOG_ADCS, ANALOG_PGA)

    def read(name):
        chip, ch = ANALOG_SENSORS[name]
        v = adcs[chip].read_voltage(ch) * ANALOG_DIVIDER.get(name, 1.0)
        return v, max(0.0, min(100.0, v / ANALOG_SUPPLY * 100.0))
    try:
        if args.cmd == "raw":
            for name, (chip, ch) in ANALOG_SENSORS.items():
                print(f"  {name}: {adcs[chip].read_voltage(ch):.4f} V")
        elif args.cmd == "read":
            names = list(ANALOG_SENSORS) if args.channel == "all" else [args.channel.upper()]
            for name in names:
                if name not in ANALOG_SENSORS: raise SystemExit(f"unknown channel: {name}")
                v, pct = read(name)
                print(f"  {name:<11} {v:.3f} V   ({pct:.0f}%)")
        elif args.cmd == "monitor":
            print("continuous monitor (Ctrl+C to quit)\n")
            try:
                while True:
                    print("  " + "  ".join(f"{name}={read(name)[0]:.2f}V" for name in ANALOG_SENSORS))
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nmonitor stopped.")
    finally:
        for b in buses.values(): b.close()


def cmd_servo(args):
    s = Servo()
    try:
        if args.cmd == "angle":
            print(f"angle -> {s.goto(args.deg)} deg"); time.sleep(1.0)
        elif args.cmd == "min":
            print(f"angle -> {s.goto(SERVO_MIN_ANGLE)} deg"); time.sleep(1.0)
        elif args.cmd == "max":
            print(f"angle -> {s.goto(SERVO_MAX_ANGLE)} deg"); time.sleep(1.0)
        elif args.cmd == "center":
            print(f"angle -> {s.goto((SERVO_MIN_ANGLE + SERVO_MAX_ANGLE) / 2)} deg"); time.sleep(1.0)
        elif args.cmd == "sweep":
            s.sweep(step=args.step, delay=args.delay, cycles=args.cycles); print("sweep complete")
    finally:
        s.close()


def _door_label(level):
    """Human OPEN/CLOSED for the DOOR_STATUS level (honors the open-level config)."""
    if level is None:
        return "?"
    return "OPEN" if level == GPIO_INPUT_OPEN_LEVEL["DOOR_STATUS"] else "CLOSED"


def cmd_rgb(args):
    if args.cmd == "list":
        for name, (r, g, b) in RGB_COLORS.items():
            print(f"  {name:<8} #{r:02X}{g:02X}{b:02X}")
        return
    leds = RGBLeds()
    try:
        if args.cmd == "off":
            leds.off()
            print("RGB -> off")
        elif args.cmd == "set":
            rgb = parse_rgb_color(args.color)
            leds.fill(rgb, args.brightness)
            print(f"RGB -> {args.color} #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} "
                  f"@ {args.brightness:.0f}%")
    finally:
        leds.close()


def cmd_gpio(args):
    if args.cmd == "list":
        for name, gpio in GPIO_SIGNALS.items():
            inv = "  (inverted)" if name in GPIO_INVERTED else ""
            print(f"  {name:<16} GPIO{gpio}{inv}  [output]")
        for name, gpio in GPIO_INPUTS.items():
            print(f"  {name:<16} GPIO{gpio}  [input, read-only]")
    elif args.cmd == "on":
        attempt, _ = gpio_set_signal_verified(args.name.upper(), True)
        print(f"{args.name.upper()} -> ON (verified, attempt {attempt}/{VERIFY_RETRIES})")
    elif args.cmd == "off":
        attempt, _ = gpio_set_signal_verified(args.name.upper(), False)
        print(f"{args.name.upper()} -> OFF (verified, attempt {attempt}/{VERIFY_RETRIES})")
    elif args.cmd == "status":
        if args.name == "all":
            names = list(GPIO_SIGNALS) + list(GPIO_INPUTS)
        else:
            names = [args.name.upper()]
        for name in names:
            if name in GPIO_SIGNALS:
                v = gpio_get_signal(name)
                print(f"  {name:<16} {v if v is not None else '?'}")
            elif name in GPIO_INPUTS:
                v = gpio_read_input(name)
                extra = f"  ({_door_label(v)})" if name == "DOOR_STATUS" else ""
                print(f"  {name:<16} {v if v is not None else '?'}{extra}")
            else:
                raise SystemExit(f"unknown signal: {name}")


def _load_config_or_exit():
    try:
        return load_component_config()
    except FileNotFoundError:
        raise SystemExit(f"component config not found: {DEFAULT_COMPONENT_CONFIG}")


def cmd_mode(_args):
    cfg = _load_config_or_exit()
    lp = cfg.get("led_power", {})
    mode = lp.get("default_mode", "405nm")
    allowed = [n for n, c in cfg["leds"].items() if mode in c.get("modes", [])]
    print(f"default wavelength mode: {mode}")
    print(f"allowed LEDs:           {', '.join(allowed) or '(none)'}")
    print("LED-driver GPIO states (SSR450 / SSR405 / routing) per mode:")
    for m, st in lp.get("modes", {}).items():
        print(f"  {m}:  GPIO{lp.get('ssr_450nm')}={st.get('ssr_450nm')}  "
              f"GPIO{lp.get('ssr_405nm')}={st.get('ssr_405nm')}  "
              f"GPIO{lp.get('routing')}={st.get('routing')}")


def cmd_led(args):
    cfg = _load_config_or_exit()
    if args.cmd == "list":
        for name, c in cfg["leds"].items():
            print(f"  {name:<10} fan={c.get('fan',''):<10} speed={c.get('fan_speed')}%  "
                  f"intensity={c.get('intensity')}  modes={','.join(c.get('modes', []))}")
        return
    sysctl = SystemController(config=cfg)
    try:
        led = args.led.upper()
        if led not in cfg["leds"]:
            raise SystemExit(f"unknown LED: {led}")
        if args.cmd == "off":
            sysctl.set_led_off(led)
            print(f"{led} -> OFF; fan {cfg['leds'][led].get('fan')} stopped")
            return
        intensity = args.intensity if args.cmd == "set" else cfg["leds"][led].get("intensity", 100)
        if not sysctl.set_led(led, intensity):
            raise SystemExit(f"{led} blocked: not allowed in {sysctl.wavelength_mode()} mode")
        fan = cfg["leds"][led].get("fan")
        print(f"{led} -> {intensity:g}%; fan {fan} auto-started at "
              f"{cfg['leds'][led].get('fan_speed')}% ({sysctl.wavelength_mode()} mode)")
    finally:
        sysctl.io.close()


def cmd_cooling(args):
    """Delegates to cooling_mode.py - the module responsible for cooling."""
    _load_config_or_exit()                 # fail early with a clear message
    from cooling_mode import run_cli
    run_cli(args.rate, args.target)


def cmd_status(_args):
    box = IOController()
    try:
        snap = box.snapshot()
        print("=== PCA9685 (PWM) ===")
        for name, st in snap["pca"].items():
            print(f"  {name:<13} {st}")
        print("\n=== TCA6424A (I/O) ===")
        for name, val in snap["io"].items():
            print(f"  {name:<12} {val}")
        print("\n=== temperature (NTC) ===")
        for name, t in snap["temp"].items():
            print(f"  {name}: {f'{t:.1f} C' if t is not None else '-'}")
        print("\n=== analog ===")
        for name, v in snap["analog"].items():
            print(f"  {name:<11} {v:.3f} V")
    finally:
        box.close()


def cmd_safe(_args):
    box = IOController()
    try:
        box.all_safe()
        led_power_off()        # disconnect LED drivers: SSR + routing GPIOs OFF
        print(f"whole system verified safe (PWM off, motors stopped, valves closed, "
              f"LED drivers disconnected) - each component read back, up to {VERIFY_RETRIES} attempts.")
    finally:
        box.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    dispatch = {
        "pca": cmd_pca, "io": cmd_io, "temp": cmd_temp, "analog": cmd_analog,
        "servo": cmd_servo, "gpio": cmd_gpio, "rgb": cmd_rgb, "led": cmd_led, "mode": cmd_mode,
        "cooling": cmd_cooling, "status": cmd_status, "safe": cmd_safe,
    }
    needs_i2c = args.comp in ("pca", "io", "temp", "analog", "led", "cooling", "status", "safe")
    is_list = getattr(args, "cmd", None) == "list"   # list prints config only - no hardware needed
    if not SMBUS_AVAILABLE and needs_i2c and not is_list:
        raise SystemExit("smbus2 is not installed - required for I2C components. Install: pip install smbus2")
    try:
        dispatch[args.comp](args)
    except VerificationError as e:
        raise SystemExit(f"error: {e}")


if __name__ == "__main__":
    main()
