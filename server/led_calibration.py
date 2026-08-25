#!/usr/bin/env python3
"""
led_calibration.py - the LED calibration layer (Developer Mode).

One logical value drives the UV system:

    Requested System LED Power (0-100%)
              |
       calibration layer          <- this module
              |
    Back / Door / Left / Right physical outputs (0-100%, clamped)
              |
        hardware PWM (io_bridge -> io_controller)

Each zone has an independent calibration factor (default 1.0):

    physical_output = clamp(requested_power * factor, 0..100)

The factors are persisted in server/data/led_calibration.json (atomic
tmp+replace writes, same pattern as component_counters.json) and survive
application / system / Pi restarts. Every consumer — the cure process
(io_bridge.set_uv), the diagnostics /api/uv route and the HDT calibration —
goes through scaled_outputs()/scaled_output(), so the calibration logic
lives in exactly one place.
"""

import json
import os
import threading

ZONES = ('back', 'door', 'left', 'right')
DEFAULT_FACTORS = {z: 1.0 for z in ZONES}

# io_controller LED channel name -> calibration zone
LED_TO_ZONE = {
    'LED_BACK': 'back',
    'LED_DOOR': 'door',
    'LED_LEFT': 'left',
    'LED_RIGHT': 'right',
}

FACTOR_MIN, FACTOR_MAX = 0.0, 1.5      # physical output is clamped to 100% anyway

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'data', 'led_calibration.json')
_lock = threading.Lock()
_factors = None                        # loaded lazily


def _load():
    global _factors
    if _factors is not None:
        return
    factors = dict(DEFAULT_FACTORS)
    try:
        with open(_PATH, encoding='utf-8') as f:
            saved = json.load(f)
        for z in ZONES:
            v = float(saved.get(z, 1.0))
            factors[z] = min(FACTOR_MAX, max(FACTOR_MIN, v))
        print('[LED-CAL] loaded factors: ' +
              ', '.join(f'{z}={factors[z]:.2f}' for z in ZONES), flush=True)
    except FileNotFoundError:
        print('[LED-CAL] no saved calibration - all factors 1.0', flush=True)
    except Exception as e:  # noqa: BLE001 - corrupt file: fall back to defaults
        print(f'[LED-CAL] load failed ({e}) - all factors 1.0', flush=True)
    _factors = factors


def get_factors():
    """Current calibration factors {back, door, left, right}."""
    with _lock:
        _load()
        return dict(_factors)


def save_factors(new_factors):
    """Validate, persist and activate new factors. Returns the stored dict."""
    clean = {}
    for z in ZONES:
        v = float(new_factors[z])
        if not (FACTOR_MIN <= v <= FACTOR_MAX):
            raise ValueError(f'{z} factor {v} outside {FACTOR_MIN}-{FACTOR_MAX}')
        clean[z] = round(v, 4)
    with _lock:
        global _factors
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(clean, f, indent=2)
        os.replace(tmp, _PATH)
        _factors = dict(clean)
    print('[LED-CAL] saved factors: ' +
          ', '.join(f'{z}={clean[z]:.2f}' for z in ZONES), flush=True)
    return clean


def reset_factors():
    """Back to all-1.0 defaults (persisted)."""
    return save_factors(dict(DEFAULT_FACTORS))


def clamp_output(v):
    """Clamp a physical LED output to the valid hardware range (0-100%)."""
    return min(100.0, max(0.0, float(v)))


def scaled_output(requested_power, zone, factors=None):
    """Physical output for one zone at the requested system power."""
    f = (factors or get_factors()).get(zone, 1.0)
    return round(clamp_output(float(requested_power) * float(f)), 2)


def scaled_outputs(requested_power, factors=None):
    """Physical outputs for all four zones: {back, door, left, right}."""
    factors = factors or get_factors()
    return {z: scaled_output(requested_power, z, factors) for z in ZONES}


def zone_for_led(led_name):
    """Calibration zone for an io_controller LED channel (None if unmapped)."""
    return LED_TO_ZONE.get(led_name)
