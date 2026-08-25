#!/usr/bin/env python3
"""
picolog_tc08.py - Pico Technology PicoLog TC-08 interface (Developer Mode).

Owns everything TC-08: detection, connection, CH1 configuration, 1 Hz
temperature acquisition, health/staleness tracking and safe reporting.
All driver calls happen in ONE background thread (the usbtc08 driver is
not thread-safe); Flask threads only read the latest snapshot under a lock.

Import-safe everywhere: without the picosdk / usbtc08 driver the manager
simply reports "Not Connected". While disconnected it retries the USB open
every RECONNECT_SEC, so plugging the unit in later just works.

Simulation (bench/dev work off the hardware): set SCURE_SIM_TC08=1 and the
manager produces a first-order thermal model that follows the LED power
reported by `power_supplier` (wired up by app.py) - so the whole HDT flow
can be exercised end-to-end without a TC-08.

Measurement channel: CH1 (channel 0 is the cold junction and stays enabled
for compensation). Thermocouple type: K.
"""

import math
import os
import threading
import time

SAMPLING_INTERVAL_SEC = 1.0    # one CH1 measurement per second
RECONNECT_SEC = 5.0            # retry cadence while no unit is found
STALE_SEC = 5.0                # no fresh sample for this long -> invalid
VALID_RANGE_C = (-25.0, 250.0) # readings outside are treated as sensor error
TC_TYPE = 'K'
MAINS_HZ = 50

SIMULATED = os.environ.get('SCURE_SIM_TC08', '') not in ('', '0', 'false')

# Simulated thermal model (SCURE_SIM_TC08=1): first-order lag toward
# ambient + GAIN * system LED power %.
SIM_AMBIENT_C = 24.0
SIM_GAIN_C_PER_PCT = 0.55
SIM_TAU_SEC = 40.0


def _add_pico_dll_dirs():
    """Help picosdk find usbtc08.dll on Windows (same as scripts/picolog_report.py)."""
    for d in (r'C:\Program Files\Pico Technology\PicoLog',
              r'C:\Program Files\Pico Technology\SDK\lib'):
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:  # noqa: BLE001 - non-Windows
                pass
            os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')


class Tc08Manager:
    """Background TC-08 acquisition with a thread-safe status snapshot."""

    def __init__(self):
        self._lock = threading.Lock()
        self._connected = False
        self._device_info = None
        self._error = 'starting'
        self._last_temp = None         # last VALID CH1 temperature (degC)
        self._last_ts = 0.0            # monotonic time of the last valid sample
        self._was_connected = False    # for connect/disconnect event logging
        # Simulation: callable returning the current system LED power % (0-100)
        self.power_supplier = None
        self._sim_temp = SIM_AMBIENT_C
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True, name='tc08').start()

    # ------------------------------------------------------------------
    #  Public snapshot (safe from any thread)
    # ------------------------------------------------------------------
    def status(self):
        """PicoLog status for the UI / HDT controller."""
        with self._lock:
            fresh = (time.monotonic() - self._last_ts) <= STALE_SEC
            valid = self._connected and fresh and self._last_temp is not None
            return {
                'connected': self._connected,
                'ch1Available': valid,
                'temperature': round(self._last_temp, 2) if valid else None,
                'deviceInfo': self._device_info,
                'error': None if valid else (self._error or
                                             ('stale data' if self._connected else None)),
            }

    def read_valid(self):
        """Latest valid CH1 temperature, or None (disconnected/stale/invalid)."""
        s = self.status()
        return s['temperature'] if s['ch1Available'] else None

    # ------------------------------------------------------------------
    #  Acquisition thread
    # ------------------------------------------------------------------
    def _set(self, connected=None, temp=None, error=None, info=None):
        from dev_log import log_event
        with self._lock:
            if connected is not None:
                if connected and not self._was_connected:
                    log_event('PicoLog TC-08 connected',
                              {'device': info or self._device_info})
                elif not connected and self._was_connected:
                    log_event('PicoLog TC-08 disconnected', {'reason': error})
                self._was_connected = connected
                self._connected = connected
            if info is not None:
                self._device_info = info
            self._error = error
            if temp is not None:
                self._last_temp = temp
                self._last_ts = time.monotonic()

    def _run(self):
        if SIMULATED:
            self._run_simulated()
            return
        handle = None
        lib = None
        import ctypes
        temp_buf = (ctypes.c_float * 9)()
        overflow = ctypes.c_int16(0)
        while not self._stop.is_set():
            if handle is None:
                handle, lib, info, err = self._open()
                if handle is None:
                    self._set(connected=False, error=err)
                    if self._stop.wait(RECONNECT_SEC):
                        return
                    continue
                self._set(connected=True, error=None, info=info)
            try:
                units = lib.USBTC08_UNITS['USBTC08_UNITS_CENTIGRADE']
                ok = lib.usb_tc08_get_single(
                    handle, ctypes.byref(temp_buf), ctypes.byref(overflow), units)
                if not ok:
                    raise IOError('usb_tc08_get_single failed')
                t = float(temp_buf[1])                     # CH1
                if not math.isfinite(t):
                    self._set(connected=True, error='CH1 reading is NaN '
                              '(thermocouple disconnected?)')
                elif not (VALID_RANGE_C[0] <= t <= VALID_RANGE_C[1]):
                    self._set(connected=True,
                              error=f'CH1 reading {t:.1f}degC out of range')
                else:
                    self._set(connected=True, temp=t, error=None)
            except Exception as e:  # noqa: BLE001 - unit unplugged / USB error
                self._set(connected=False, error=f'communication lost: {e}')
                try:
                    lib.usb_tc08_close_unit(handle)
                except Exception:  # noqa: BLE001
                    pass
                handle = None
                continue
            if self._stop.wait(SAMPLING_INTERVAL_SEC):
                return

    def _open(self):
        """Try to open the TC-08 and configure CH1. Returns (handle, lib, info, err)."""
        try:
            _add_pico_dll_dirs()
            from picosdk.usbtc08 import usbtc08 as tc08
        except Exception as e:  # noqa: BLE001 - driver/SDK not installed
            return None, None, None, f'usbtc08 driver unavailable: {e}'
        try:
            handle = tc08.usb_tc08_open_unit()
            if handle == 0:
                return None, None, None, 'no TC-08 found (unplugged, or in use by PicoLog?)'
            if handle < 0:
                return None, None, None, 'TC-08 open failed - replug the USB'
            tc08.usb_tc08_set_mains(handle, MAINS_HZ)
            # channel 0 = cold junction, must stay enabled for compensation;
            # CH1 = the model thermocouple; 2-8 disabled.
            tc08.usb_tc08_set_channel(handle, 0, ord('C'))
            tc08.usb_tc08_set_channel(handle, 1, ord(TC_TYPE))
            for c in range(2, 9):
                tc08.usb_tc08_set_channel(handle, c, 0)
            info = 'PicoLog TC-08'
            try:
                import ctypes
                buf = ctypes.create_string_buffer(256)
                # line 4 = batch and serial
                if tc08.usb_tc08_get_unit_info2(handle, buf, 256, 4) > 0:
                    info = f'PicoLog TC-08 S/N {buf.value.decode(errors="ignore")}'
            except Exception:  # noqa: BLE001 - info is optional
                pass
            return handle, tc08, info, None
        except Exception as e:  # noqa: BLE001
            return None, None, None, f'TC-08 open error: {e}'

    def _run_simulated(self):
        self._set(connected=True, error=None,
                  info='PicoLog TC-08 (SIMULATED - SCURE_SIM_TC08)')
        last = time.monotonic()
        while not self._stop.wait(SAMPLING_INTERVAL_SEC):
            now = time.monotonic()
            dt = min(now - last, 10.0)
            last = now
            power = 0.0
            try:
                power = float(self.power_supplier()) if self.power_supplier else 0.0
            except Exception:  # noqa: BLE001
                pass
            target = SIM_AMBIENT_C + SIM_GAIN_C_PER_PCT * power
            self._sim_temp += (target - self._sim_temp) * (dt / SIM_TAU_SEC)
            import random
            self._set(connected=True, temp=self._sim_temp + random.uniform(-0.15, 0.15),
                      error=None)

    def stop(self):
        self._stop.set()
