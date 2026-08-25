#!/usr/bin/env python3
"""
sCure Hardware API Server (Python)
Runs on Raspberry Pi CM5.

Architecture:
    React UI (frontend) → Python Flask API → C++ hardware driver

Install:
    pip install flask flask-cors

Run:
    sudo python3 app.py
    (sudo needed for GPIO/reboot/shutdown)

The C++ driver is compiled as a shared library or called via subprocess.
"""

import os
import sys
import json
import subprocess
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# PostgreSQL data layer (print data, released materials, cure reports).
# Safe to import without a DB / driver — falls back to JSON files (see db.available()).
try:
    import db
except Exception as _e:  # pragma: no cover
    db = None
    print(f"[DB] data layer unavailable: {_e}")

# Try to import the C++ hardware driver
try:
    from hardware import hw_driver
    HW_AVAILABLE = True
except ImportError:
    HW_AVAILABLE = False
    print("[WARN] C++ hardware driver not found, running in simulation mode")

app = Flask(__name__)
CORS(app)


def run(cmd, timeout=15):
    """Run a shell command and return its stripped stdout ('' on failure)."""
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=timeout)
        return (out.stdout or '').strip()
    except Exception as e:  # noqa: BLE001 - diagnostics must never raise
        print(f"[SYS] command failed ({cmd}): {e}")
        return ''

# Real IO-board drivers (io_controller/ at the repo root), via the bridge.
# Off-Pi (no I2C / smbus2) the bridge reports unavailable and the simulation
# below keeps serving the UI.
io_bridge = None
try:
    from io_bridge import IOBridge
    _bridge = IOBridge()
    if _bridge.available:
        io_bridge = _bridge
        print("[API] IO board connected (io_controller bridge)")
    else:
        print(f"[API] IO board not available ({_bridge.error}) - simulation mode")
except Exception as _e:  # pragma: no cover
    print(f"[API] IO bridge failed to load: {_e} - simulation mode")

if io_bridge is not None:
    import atexit
    atexit.register(io_bridge.shutdown)   # everything OFF when the API exits

# ============================================================
# Hardware abstraction - calls C++ driver or simulates
# ============================================================

# Simulation thermal model (no IO board): the simulated chamber follows the
# commanded target the way the real PI loop does, so the UI always sees a
# chamber temperature that moves toward the target.
SIM_AMBIENT = 24.0
SIM_HEAT_RATE = 0.5                      # C/s while heating toward target
SIM_COOL_RATES = {'fast': 5.0 / 60, 'medium': 2.5 / 60, 'slow': 1.0 / 60}  # C/s
SIM_IDLE_RATE = 0.05                     # C/s drift back to ambient when idle
# UI cooling modes -> fixed chamber-fan duty % (mirrors io_bridge COOLING_MODE_PWMS)
COOLING_MODE_PWMS = {'fast': 100, 'medium': 60, 'slow': 30}


class HardwareController:
    def __init__(self, bridge=None):
        self.bridge = bridge              # IOBridge (real io_controller drivers) or None
        self.chamber_temp = SIM_AMBIENT
        self._sim_time = time.time()
        self.target_temp = None
        self.door_closed = True
        self.heating = False
        self.cooling = False
        self.cooling_mode = None       # 'fast' | 'medium' | 'slow'
        self.uv_on = False
        self.uv_intensity = 0
        self.uv_wavelength = None       # 405 (Cure) | 450 (Bleaching)
        self.uv_outputs = None          # per-zone physical % (calibration layer)
        self.damper_open = False
        self.nitrogen_on = False
        self.bofa_on = False
        self._door_reclose_at = None      # sim: door re-reads closed after release
        self.fans = {
            'led_cooling': 0,
            'chamber_intake': 0,
            'chamber_heating': 0,
        }

    def _sim_tick(self):
        """Advance the simulated chamber temperature toward the target."""
        if self._door_reclose_at and time.time() >= self._door_reclose_at:
            self.door_closed = True
            self._door_reclose_at = None
        now = time.time()
        dt = min(max(now - self._sim_time, 0.0), 10.0)
        self._sim_time = now
        if dt <= 0:
            return
        if self.heating and self.target_temp is not None:
            self.chamber_temp = min(float(self.target_temp),
                                    self.chamber_temp + SIM_HEAT_RATE * dt)
        elif self.cooling and self.target_temp is not None:
            rate = SIM_COOL_RATES.get(self.cooling_mode, SIM_COOL_RATES['medium'])
            self.chamber_temp = max(float(self.target_temp),
                                    self.chamber_temp - rate * dt)
        elif self.chamber_temp > SIM_AMBIENT:
            self.chamber_temp = max(SIM_AMBIENT,
                                    self.chamber_temp - SIM_IDLE_RATE * dt)
        self.chamber_temp = round(self.chamber_temp, 1)

    def get_state(self):
        if self.bridge:
            try:
                return self.bridge.get_state()
            except Exception as e:        # noqa: BLE001 - fall back to simulation
                print(f"[HW] state read failed: {e}")
        if HW_AVAILABLE:
            return hw_driver.get_state()
        self._sim_tick()
        base = self.chamber_temp
        return {
            'chamberTemp': self.chamber_temp,
            'targetTemp': self.target_temp,
            'doorClosed': self.door_closed,
            'isHeating': self.heating,
            'isCooling': self.cooling,
            'coolingMode': self.cooling_mode,
            'coolingFanPwm': (COOLING_MODE_PWMS.get(self.cooling_mode)
                              if self.cooling else None),
            'uvOn': self.uv_on,
            'uvIntensity': self.uv_intensity,          # logical system power %
            'uvWavelength': self.uv_wavelength,
            'uvOutputs': self.uv_outputs,              # per-zone physical %
            'damperOpen': self.damper_open,
            'fans': self.fans,
            'fanRpm': {k: (2850 if v > 0 else 0) for k, v in self.fans.items()},
            'ledTemps': {'left': round(base + 1.5, 1), 'right': round(base + 2.0, 1),
                         'door': round(base + 0.5, 1), 'back': round(base + 1.0, 1)},
            'nitrogenActive': self.nitrogen_on,
            'n2LinePressure': 6.0,        # simulated line pressure (no sensor off-Pi)
            'bofaOn': self.bofa_on,
            'faults': {'heater': None, 'cooling': None, 'led': None},
            'hwSource': 'simulation',
        }

    def set_target_temp(self, temp):
        self.target_temp = temp
        if self.bridge:
            ok, why = self.bridge.set_target_temp(temp)
            self.heating = ok
            return ok, why
        if HW_AVAILABLE:
            hw_driver.set_target_temperature(temp)
        self.heating = True               # simulation ramps toward the target
        return True, None

    def stop_heating(self):
        self.heating = False
        if self.bridge:
            return self.bridge.stop_heating()
        return True, None

    def set_fan_speed(self, fan, speed):
        self.fans[fan] = speed
        if self.bridge:
            return self.bridge.set_fan_speed(fan, speed)
        if HW_AVAILABLE:
            hw_driver.set_fan_speed(fan, speed)
        return True, None

    def set_damper(self, open_state):
        self.damper_open = open_state
        if self.bridge:
            return self.bridge.set_damper(open_state)
        if HW_AVAILABLE:
            hw_driver.set_damper(open_state)
        return True, None

    def open_door(self):
        if self.bridge:
            return self.bridge.open_door()
        if HW_AVAILABLE:
            hw_driver.open_door()
            return True, None
        # Simulation: the magnet releases and the operator shuts the door
        # again — mirror that so the door does not stay "open" forever.
        self.door_closed = False
        self._door_reclose_at = time.time() + 5.0
        return True, None

    def ack_door_abort(self):
        """User acknowledged the door-abort alert: strip returns to normal."""
        if self.bridge:
            return self.bridge.ack_door_abort()
        return True, None      # simulation: nothing to clear

    # ---- low-level output control (driver calls are optional/guarded) ----
    def set_heating(self, on):
        self.heating = bool(on)
        if on:
            self.cooling = False
        if HW_AVAILABLE and hasattr(hw_driver, 'set_heating'):
            hw_driver.set_heating(bool(on))

    def set_cooling(self, on, mode=None):
        self.cooling = bool(on)
        self.cooling_mode = mode if on else None
        if on:
            self.heating = False
        if HW_AVAILABLE and hasattr(hw_driver, 'set_cooling'):
            hw_driver.set_cooling(bool(on), mode)

    def set_uv(self, on, intensity=0, wavelength=None, factors=None):
        """`intensity` is the calibrated SYSTEM LED power; the per-zone
        factors are applied inside io_bridge.set_uv (real hardware) or
        mirrored here for the simulation state. `factors` overrides the
        saved calibration (Developer Mode live preview only)."""
        self.uv_on = bool(on)
        self.uv_intensity = int(intensity) if on else 0
        self.uv_wavelength = wavelength if on else None
        try:
            import led_calibration
            self.uv_outputs = (led_calibration.scaled_outputs(intensity, factors)
                               if on else None)
        except Exception:  # noqa: BLE001 - calibration must never block UV
            self.uv_outputs = None
        if self.bridge:
            return self.bridge.set_uv(bool(on), int(intensity) if on else 0,
                                      wavelength, factors)
        if HW_AVAILABLE and hasattr(hw_driver, 'set_uv'):
            hw_driver.set_uv(bool(on), int(intensity) if on else 0, wavelength)
        return True, None

    def set_nitrogen(self, on):
        """Open/close the N2 purge valve (GPIO13 on the IO board)."""
        if self.bridge:
            ok, why = self.bridge.set_nitrogen(on)
            self.nitrogen_on = ok and bool(on)
            return ok, why
        self.nitrogen_on = bool(on)
        return True, None

    def set_bofa(self, on):
        """BOFA fume-extraction control (PCA channel 10)."""
        if self.bridge:
            ok, why = self.bridge.set_bofa(on)
            self.bofa_on = ok and bool(on)
            return ok, why
        self.bofa_on = bool(on)
        return True, None

    # ---- high-level operation functions (one per recipe process) ----
    # Each function owns starting / controlling / stopping its hardware. The
    # process ends automatically per its own logic (target reached, etc.).
    def heat_to_target_temperature(self, target_c):
        """Heat the chamber to target_c. Ends when the target is reached."""
        self.target_temp = target_c
        if self.bridge:
            return self.bridge.heat_to_target(target_c)
        self.set_uv(False)
        self.set_cooling(False)
        self.heating = True
        return True, None

    def dry_to_target_temperature(self, target_c):
        """Run drying toward target_c; the process logic stops it automatically."""
        self.target_temp = target_c
        if self.bridge:
            return self.bridge.dry_to_target(target_c)
        self.set_uv(False)
        self.set_cooling(False)
        self.heating = True
        return True, None

    def cure_uv_405(self, target_c, intensity_pct):
        """Cure: heater to target_c + UV 405 nm at intensity_pct."""
        self.target_temp = target_c
        if self.bridge:
            return self.bridge.cure_uv(target_c, intensity_pct, 405)
        self.set_cooling(False)
        self.heating = True
        self.set_uv(True, intensity_pct, 405)
        return True, None

    def cure_uv_450(self, target_c, intensity_pct):
        """Bleaching: heater to target_c + UV 450 nm at intensity_pct."""
        self.target_temp = target_c
        if self.bridge:
            return self.bridge.cure_uv(target_c, intensity_pct, 450)
        self.set_cooling(False)
        self.heating = True
        self.set_uv(True, intensity_pct, 450)
        return True, None

    def cool_to_target_temperature(self, target_c, mode):
        """Cool the chamber to target_c in mode (fast/medium/slow). Ends when reached."""
        self.target_temp = target_c
        if self.bridge:
            return self.bridge.cool_to_target(target_c, mode)
        self.set_uv(False)
        self.set_heating(False)
        self.set_cooling(True, mode)
        # FAST cooling: the LED-cooling fans join the chamber fan (mirrors
        # the io_bridge behavior so the UI sees the same fans state off-Pi).
        self.fans['led_cooling'] = 100 if mode == 'fast' else 0
        self.fans['chamber_intake'] = COOLING_MODE_PWMS.get(mode, 60)
        return True, None

    def stop_all(self, immediate=False):
        """Stop every cure output (heater, UV, cooling, N2).
        immediate=True (abort): no heater-fan run-on."""
        self.nitrogen_on = False
        if self.bridge:
            return self.bridge.stop_all(immediate)
        self.set_uv(False)
        self.set_heating(False)
        self.set_cooling(False)
        self.fans['led_cooling'] = 0
        self.fans['chamber_intake'] = 0
        return True, None

    def run_fan_test(self, fan=None):
        if self.bridge:
            return self.bridge.run_fan_test(fan)
        if HW_AVAILABLE:
            return hw_driver.run_fan_test()
        return {'rpm': 2850, 'status': 'OK'}

    def run_led_test(self):
        if self.bridge:
            return self.bridge.run_led_test()
        if HW_AVAILABLE:
            return hw_driver.run_led_test()
        return {
            'results': [
                {'name': 'Font LED', 'temp': 62, 'status': 'OK'},
                {'name': 'Left LED', 'temp': 62, 'status': 'OK'},
                {'name': 'Door LED', 'temp': 62, 'status': 'OK'},
                {'name': 'Right LED', 'temp': 62, 'status': 'OK'},
            ]
        }


hw = HardwareController(io_bridge)

# ============================================================
# Developer Mode subsystems: LED calibration layer, PicoLog TC-08
# acquisition and the Material HDT calibration state machine.
# ============================================================
import led_calibration
import dev_log
from picolog_tc08 import Tc08Manager
from hdt_calibration import HdtCalibrationController

tc08 = Tc08Manager()
# Simulated TC-08 (SCURE_SIM_TC08=1): the model temperature follows the
# commanded system LED power, so the HDT flow can be tested off-hardware.
tc08.power_supplier = lambda: hw.uv_intensity if hw.uv_on else 0
hdt = HdtCalibrationController(hw, tc08)


# ============================================================
# Component runtime counters (real ON-hours, persisted)
# ============================================================
class ComponentCounters:
    """Accumulates the real ON-time of the wear components and persists it.

    Samples the authoritative hardware state every TICK seconds:
      led405 / led450 - UV on at that wavelength
      heater          - heater element actually energized (heaterOut: the
                        instantaneous delta-sigma ON/OFF output, not merely
                        "heating mode" - the PI controller streams the
                        element ON and OFF; fallback: heaterPwm > 0)
      heaterFan       - measured tach RPM (fallback: commanded duty)
      coolingFan      - measured tach RPM (fallback: commanded duty)

    Seconds are flushed atomically (tmp + os.replace) to a JSON file every
    FLUSH_SEC while something is running, and once more on process exit, so
    the totals survive reboots and power cuts (worst case: the last minute).
    """

    KEYS = ('led405', 'led450', 'coolingFan', 'heater', 'heaterFan')
    TICK = 2.0
    FLUSH_SEC = 60.0

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._dirty = False
        self.seconds = {k: 0.0 for k in self.KEYS}
        try:
            with open(self.path, encoding='utf-8') as f:
                saved = json.load(f)
            for k in self.KEYS:
                self.seconds[k] = max(0.0, float(saved.get(k, 0.0)))
            print(f"[COUNTERS] loaded: " +
                  ', '.join(f'{k}={v/3600:.1f}h' for k, v in self.seconds.items()))
        except FileNotFoundError:
            print("[COUNTERS] no saved counters - starting from zero")
        except Exception as e:  # noqa: BLE001 - corrupt file: keep zeros, will rewrite
            print(f"[COUNTERS] load failed ({e}) - starting from zero")
        threading.Thread(target=self._run, daemon=True,
                         name='component-counters').start()

    def hours(self):
        """Current totals in hours (1 decimal), for /api/state."""
        with self._lock:
            return {k: round(v / 3600.0, 1) for k, v in self.seconds.items()}

    def flush(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._lock:
            payload = {k: round(v, 1) for k, v in self.seconds.items()}
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        os.replace(tmp, self.path)

    def _sample(self):
        s = hw.get_state()
        rpm = s.get('fanRpm') or {}
        duty = s.get('fans') or {}
        heater_pwm = s.get('heaterPwm')
        heater_out = s.get('heaterOut')
        return {
            'led405': bool(s.get('uvOn')) and s.get('uvWavelength') == 405,
            'led450': bool(s.get('uvOn')) and s.get('uvWavelength') == 450,
            'heater': bool(heater_out) if heater_out is not None
                      else (heater_pwm > 0) if heater_pwm is not None
                      else bool(s.get('isHeating')),
            'heaterFan': rpm.get('chamber_heating', 0) > 0
                         or duty.get('chamber_heating', 0) > 0,
            'coolingFan': rpm.get('chamber_intake', 0) > 0
                          or duty.get('chamber_intake', 0) > 0,
        }

    def _run(self):
        last_flush = time.monotonic()
        while True:
            time.sleep(self.TICK)
            try:
                on = self._sample()
            except Exception:  # noqa: BLE001 - state read failed: skip the tick
                continue
            with self._lock:
                for k, active in on.items():
                    if active:
                        self.seconds[k] += self.TICK
                        self._dirty = True
            if self._dirty and time.monotonic() - last_flush >= self.FLUSH_SEC:
                try:
                    self.flush()
                    self._dirty = False
                    last_flush = time.monotonic()
                except Exception as e:  # noqa: BLE001 - disk hiccup: retry next round
                    print(f"[COUNTERS] flush failed: {e}")


counters = ComponentCounters(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'data', 'component_counters.json'))

import atexit
atexit.register(lambda: counters.flush())

# ============================================================
# API Endpoints
# (Print data, released materials and cure data are managed in PostgreSQL — db.py.)
# ============================================================

@app.route('/api/state', methods=['GET'])
def get_state():
    """Get current hardware state - polled by frontend"""
    state = hw.get_state()
    state['counters'] = counters.hours()
    state['cloudSync'] = cloud_sync.status()
    return jsonify(state)


@app.route('/api/network/status', methods=['GET'])
def network_status():
    """Get network info - IP, MAC, gateway, interfaces"""
    info = {
        'connected': True,
        'ip': '0.0.0.0',
        'mac': '00:00:00:00:00:00',
        'gateway': '',
        'interfaces': [],
    }
    try:
        # LAN IP — eth0 ONLY. `hostname -I` must not be used here: it also
        # lists the WireGuard/VPN address, which stays assigned when the
        # cable is pulled and kept `connected` green forever.
        eth_ip = run("ip -4 -j addr show eth0 2>/dev/null")
        if eth_ip:
            import json as _json
            try:
                for iface in _json.loads(eth_ip):
                    for a in iface.get('addr_info', []):
                        if a.get('family') == 'inet' and a.get('local'):
                            info['ip'] = a['local']
                            break
            except Exception:            # noqa: BLE001 - unparsable ip output
                pass
        if info['ip'] == '0.0.0.0' and not run("ip link show eth0 2>/dev/null"):
            # no eth0 on this device (e.g. dev laptop): old generic behavior
            info['ip'] = run("hostname -I | awk '{print $1}'") or '0.0.0.0'

        # Physical link state: /sys carrier is 1 only when a cable is
        # actually plugged in and the link is up.
        carrier = run("cat /sys/class/net/eth0/carrier 2>/dev/null")

        # Get MAC
        result = run("cat /sys/class/net/eth0/address 2>/dev/null || echo '00:00:00:00:00:00'")
        info['mac'] = result

        # Get gateway
        result = run("ip route | grep default | awk '{print $3}'")
        info['gateway'] = result or ''

        # Get interfaces
        ifaces = run("ip -j addr show 2>/dev/null")
        if ifaces:
            import json as _json
            for iface in _json.loads(ifaces):
                addrs = [a.get('local', '') for a in iface.get('addr_info', []) if a.get('family') == 'inet']
                info['interfaces'].append({
                    'name': iface.get('ifname', ''),
                    'status': 'UP' if 'UP' in iface.get('flags', []) else 'DOWN',
                    'ip': addrs[0] if addrs else '',
                })

        # Connected = the wired link is physically up AND eth0 has an IPv4.
        # (carrier '' = no eth0 on this device: fall back to IP presence only)
        has_ip = info['ip'] != '0.0.0.0'
        info['connected'] = has_ip and (carrier == '1' or carrier == '')
    except Exception as e:
        info['connected'] = False
        info['code'] = 9084               # NETWORK_STATUS_UNAVAILABLE
        print(f"[NET] Error getting network status: {e}")

    # Live internet reachability from the automatic background watch
    # (io_bridge StatusLeds._net_watch). 'connected' above = LAN/IP level;
    # 'internet' = the machine actually reaches the outside world.
    if io_bridge is not None and getattr(io_bridge, 'status_leds', None):
        info['internet'] = bool(io_bridge.status_leds._internet_ok)
    else:
        info['internet'] = info['connected']   # simulation: mirror LAN state

    return jsonify(info)


@app.route('/api/network/diagnostics', methods=['POST'])
def network_diagnostics():
    """Run network diagnostic tool"""
    tool = request.json.get('tool', 'ping')
    address = request.json.get('address', '8.8.8.8')

    cmd_map = {
        'ping': f'ping -c 4 -W 3 {address}',
        'traceroute': f'traceroute -m 15 -w 3 {address}',
        'nslookup': f'nslookup {address}',
    }

    cmd = cmd_map.get(tool)
    if not cmd:
        return jsonify({'ok': False, 'code': 9080, 'result': 'Unknown tool'})

    try:
        result = run(cmd, timeout=45)
        return jsonify({'ok': True, 'result': result})
    except Exception as e:
        return jsonify({'ok': False, 'code': 9085, 'result': str(e)})


@app.route('/api/network/static', methods=['POST'])
def network_static():
    """Apply a static-IP (or DHCP) configuration to eth0 via NetworkManager."""
    d = request.get_json(silent=True) or {}
    use_dhcp = bool(d.get('dhcp'))
    ip, gateway = d.get('ip', ''), d.get('gateway', '')
    subnet, dns = d.get('subnet', '255.255.255.0'), d.get('dns', '')
    if not _on_device():
        return jsonify({'ok': True, 'message': 'Network config simulated (off-device)'})
    try:
        conn = run("nmcli -t -f NAME,DEVICE connection show --active | grep ':eth0' | cut -d: -f1") or 'eth0'
        if use_dhcp:
            run(f'nmcli connection modify "{conn}" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""')
        else:
            # subnet mask -> prefix length
            prefix = sum(bin(int(o)).count('1') for o in subnet.split('.')) if subnet else 24
            run(f'nmcli connection modify "{conn}" ipv4.method manual '
                f'ipv4.addresses {ip}/{prefix} ipv4.gateway {gateway}'
                + (f' ipv4.dns {dns}' if dns else ''))
        run(f'nmcli connection up "{conn}"', timeout=30)
        return jsonify({'ok': True, 'message': 'Network configuration applied'})
    except Exception as e:
        return jsonify({'ok': False, 'code': 9084, 'message': str(e)})


def _db_on():
    return db is not None and db.available()


def _require_db():
    return jsonify({'ok': False, 'message': 'Database not configured (set DATABASE_URL)'}), 503


# --- Persistent user-program store (JSON file on the SSD) ------------------
# When Postgres is NOT configured, user work programs are still saved to a file
# on disk so they SURVIVE A POWER-OFF. Browser localStorage alone is fragile
# (per-browser, cleared on profile reset) - this file is the durable store.
# It lives in server/data/ (gitignored, so `git pull` never deletes it) and is
# written atomically (temp file + fsync + rename) so a power cut mid-write
# cannot corrupt it.
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
_USER_MATERIALS_FILE = os.path.join(_DATA_DIR, 'user_materials.json')


def _load_user_materials_file():
    try:
        with open(_USER_MATERIALS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001 - corrupt/unreadable: start empty, don't crash
        print(f"[DATA] user programs read failed: {e}")
        return []


def _save_user_materials_file(materials):
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _USER_MATERIALS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(materials, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())          # force the bytes to the SSD before rename
    os.replace(tmp, _USER_MATERIALS_FILE)   # atomic swap


@app.route('/api/materials/presets', methods=['GET'])
def get_preset_materials():
    """System-provided material programs (presets), from Postgres."""
    if not _db_on():
        return _require_db()          # UI falls back to its bundled presets
    return jsonify(db.get_materials(presets_only=True))


@app.route('/api/materials/user', methods=['GET'])
def get_user_materials():
    """User-created work programs. Postgres when configured, else the durable
    JSON file on disk (survives power-off)."""
    if _db_on():
        return jsonify(db.get_materials(presets_only=False))
    return jsonify(_load_user_materials_file())


@app.route('/api/materials/user', methods=['POST'])
def save_all_user_materials():
    """Save all user work programs (full replace). Postgres when configured,
    else persisted to the JSON file on disk."""
    materials = request.json or []
    if _db_on():
        db.replace_user_materials(materials)
    else:
        _save_user_materials_file(materials)
    return jsonify({'ok': True})


# --- Durable file store for histories (no-Postgres fallback) ---------------
# Same contract as the user-program file above: everything the UI records -
# received prints, cure runs (with telemetry) and generated cure reports -
# is persisted under server/data/ so it SURVIVES A POWER-OFF. Written
# atomically (temp + fsync + rename); a power cut mid-write cannot corrupt
# an existing file. When Postgres IS configured it stays authoritative and
# these files are not touched.
_PRINT_HISTORY_FILE = os.path.join(_DATA_DIR, 'print_history.json')
_CURE_HISTORY_FILE = os.path.join(_DATA_DIR, 'cure_history.json')
_CURE_REPORTS_FILE = os.path.join(_DATA_DIR, 'cure_reports.json')
_history_lock = threading.Lock()          # serializes read-modify-write cycles
_TELEMETRY_FLUSH_EVERY = 15               # samples between telemetry flushes


def _load_json_file(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except FileNotFoundError:
        return default
    except Exception as e:  # noqa: BLE001 - corrupt file: start empty, don't crash
        print(f"[DATA] read failed ({os.path.basename(path)}): {e}")
        return default


def _save_json_file(path, data):
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class _CureFileStore:
    """Cure runs + telemetry + reports in server/data/*.json.

    Start/finish/report writes flush immediately; telemetry (one sample per
    second during a run) flushes every _TELEMETRY_FLUSH_EVERY samples so the
    SSD is not rewritten every second - a power cut loses at most the last
    few seconds of the graph, never the run itself.
    """

    def __init__(self):
        with _history_lock:
            self.runs = _load_json_file(_CURE_HISTORY_FILE, [])
            self.reports = _load_json_file(_CURE_REPORTS_FILE, {})
            self._unflushed = 0
            # a run left 'running' by a power cut can never finish - mark it
            changed = False
            for r in self.runs:
                if r.get('status') == 'running':
                    r['status'] = 'error'
                    changed = True
            if changed:
                self._flush_runs()

    def _flush_runs(self):
        _save_json_file(_CURE_HISTORY_FILE, self.runs)

    def list(self):
        with _history_lock:
            return list(self.runs)

    def _find(self, ext_id):
        for r in self.runs:
            if r.get('id') == ext_id:
                return r
        return None

    def start(self, ext_id, d):
        with _history_lock:
            if self._find(ext_id) is None:
                self.runs.insert(0, {
                    'id': ext_id,
                    'materialName': d.get('materialName'),
                    'steps': d.get('steps'),
                    'stepsCompleted': 0,
                    'startedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'endedAt': None,
                    'duration': None,
                    'status': 'running',
                    'phases': d.get('phases') or [],
                    'targetTemp': d.get('targetTemp'),
                    'serialNumber': d.get('serialNumber'),
                    'telemetry': [],
                })
            self._flush_runs()

    def telemetry(self, ext_id, sample):
        with _history_lock:
            r = self._find(ext_id)
            if r is None:
                return False
            r.setdefault('telemetry', []).append(sample)
            self._unflushed += 1
            if self._unflushed >= _TELEMETRY_FLUSH_EVERY:
                self._flush_runs()
                self._unflushed = 0
            return True

    def finish(self, ext_id, status, steps_completed):
        with _history_lock:
            r = self._find(ext_id)
            if r is None:
                return False
            r['status'] = status
            r['endedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            if steps_completed is not None:
                r['stepsCompleted'] = steps_completed
            try:
                t0 = time.mktime(time.strptime(r['startedAt'], '%Y-%m-%dT%H:%M:%S'))
                r['duration'] = int(time.time() - t0)
            except Exception:  # noqa: BLE001 - unparsable start: leave duration
                pass
            self._flush_runs()
            return True

    def save_report(self, ext_id, d):
        with _history_lock:
            self.reports[ext_id] = {'content': d.get('content'),
                                    'summary': d.get('summary'),
                                    'format': d.get('format', 'html')}
            _save_json_file(_CURE_REPORTS_FILE, self.reports)
        return ext_id

    def get_report(self, ext_id):
        with _history_lock:
            return self.reports.get(ext_id)


_cure_files = _CureFileStore()


# ============================================================
# Cloud sync agent (sCure Cloud portal, cloud/portal.py)
# ============================================================
class CloudSync:
    """Connects the machine OUT to the sCure Cloud portal.

    Enabled by server/data/cloud.json:
        {"url": "https://portal.example.com", "key": "<machine secret>",
         "name": "CureBox-1", "interval": 10}
    Every `interval` seconds it POSTs a snapshot (state, counters, programs,
    prints, cure summaries) to /api/agent/sync and applies the returned
    DATA-ONLY commands:
        upsert_program / delete_program - work programs (work points)
        send_print                      - simulated received print
    There is deliberately no command that actuates hardware - heater/UV can
    only be started at the machine. Outbound-only: no inbound ports needed,
    works behind any NAT/firewall. Applied command ids are acked on the
    next sync so a command is never applied twice.
    """

    def __init__(self):
        self.enabled = False
        self.last_ok = None           # epoch of the last successful sync
        self.error = None
        self.cfg = {}
        try:
            with open(os.path.join(_DATA_DIR, 'cloud.json'), encoding='utf-8') as f:
                self.cfg = json.load(f)
        except FileNotFoundError:
            return                    # not configured - agent stays off
        except Exception as e:        # noqa: BLE001 - unreadable config
            self.error = f'bad cloud.json: {e}'
            return
        if not (self.cfg.get('url') and self.cfg.get('key')):
            self.error = 'cloud.json needs "url" and "key"'
            return
        self.enabled = True
        self._ack = []
        threading.Thread(target=self._run, daemon=True, name='cloud-sync').start()
        print(f"[CLOUD] sync agent ON -> {self.cfg['url']}")

    def status(self):
        return {'enabled': self.enabled, 'lastSyncOk': self.last_ok,
                'error': self.error}

    # -- data access through the same stores the API uses ------------------
    @staticmethod
    def _get_programs():
        return db.get_materials(presets_only=False) if _db_on() \
            else _load_user_materials_file()

    @staticmethod
    def _put_programs(mats):
        if _db_on():
            db.replace_user_materials(mats)
        else:
            _save_user_materials_file(mats)

    @staticmethod
    def _get_prints():
        if _db_on():
            return db.get_print_history()
        with _history_lock:
            return _load_json_file(_PRINT_HISTORY_FILE, [])

    @staticmethod
    def _put_prints(logs):
        if _db_on():
            db.replace_print_history(logs)
        else:
            with _history_lock:
                _save_json_file(_PRINT_HISTORY_FILE, logs)

    def _snapshot(self):
        try:
            s = hw.get_state()
            state = {k: s.get(k) for k in ('chamberTemp', 'doorClosed',
                                           'isHeating', 'isCooling', 'uvOn',
                                           'internetOk')}
            state['counters'] = counters.hours()
        except Exception:             # noqa: BLE001 - snapshot must never die
            state = {}
        cures = db.get_cure_history() if _db_on() else _cure_files.list()
        cures = [{k: v for k, v in c.items() if k != 'telemetry'}
                 for c in cures[:10]]
        return {'name': self.cfg.get('name', 'CureBox'), 'state': state,
                'programs': self._get_programs(),
                'prints': self._get_prints()[:20], 'cures': cures,
                'ackIds': self._ack}

    def _apply(self, cmd):
        ctype, p = cmd.get('type'), cmd.get('payload') or {}
        if ctype == 'upsert_program':
            mats = [m for m in self._get_programs() if m.get('id') != p.get('id')]
            self._put_programs(mats + [p])
            print(f"[CLOUD] program saved from portal: {p.get('name')}")
        elif ctype == 'delete_program':
            self._put_programs([m for m in self._get_programs()
                                if m.get('id') != p.get('id')])
            print(f"[CLOUD] program deleted from portal: {p.get('id')}")
        elif ctype == 'send_print':
            prog = next((m for m in self._get_programs()
                         if m.get('name') == p.get('materialName')), None)
            log = {'id': f'cloud-{int(time.time() * 1000)}',
                   'printName': p.get('printName') or 'Job',
                   'materialName': p.get('materialName') or '',
                   'printerName': p.get('printerName') or 'CLOUD',
                   'date': time.strftime('%Y-%m-%dT%H:%M:%S'),
                   'duration': int(p.get('duration')
                                   or (prog or {}).get('totalDuration') or 20),
                   'status': 'completed',
                   'steps': len((prog or {}).get('steps') or []) or int(p.get('steps') or 0),
                   'csvFile': p.get('csvFile') or ''}
            self._put_prints([log] + self._get_prints())
            print(f"[CLOUD] simulated print received: {log['printName']} "
                  f"({log['printerName']})")
        else:
            return False
        return True

    def _run(self):
        import urllib.request
        interval = max(3.0, float(self.cfg.get('interval', 10)))
        url = self.cfg['url'].rstrip('/') + '/api/agent/sync'
        while True:
            try:
                req = urllib.request.Request(
                    url, data=json.dumps(self._snapshot()).encode('utf-8'),
                    method='POST',
                    headers={'Content-Type': 'application/json',
                             'X-Machine-Key': self.cfg['key']})
                with urllib.request.urlopen(req, timeout=10) as r:
                    resp = json.load(r)
                self.last_ok = time.time()
                self.error = None
                acked = []
                for cmd in resp.get('commands') or []:
                    try:
                        if self._apply(cmd):
                            acked.append(cmd.get('id'))
                    except Exception as e:  # noqa: BLE001 - one bad command
                        print(f"[CLOUD] command {cmd.get('type')} failed: {e}")
                        acked.append(cmd.get('id'))   # ack anyway: don't loop
                self._ack = acked
            except Exception as e:    # noqa: BLE001 - portal unreachable
                self.error = str(e)
            time.sleep(interval)


cloud_sync = CloudSync()


@app.route('/api/cloud/config', methods=['POST'])
def cloud_config():
    """Write the cloud-portal sync config (server/data/cloud.json).

    The server runs as root, so this is the supported way to configure the
    agent (the data dir is not writable by the desktop user). If the agent
    is not yet running it starts immediately; if it was already running with
    an old config, a server restart applies the new one.
    """
    global cloud_sync
    d = request.get_json(silent=True) or {}
    if not (d.get('url') and d.get('key')):
        return jsonify({'ok': False, 'message': 'url and key required'}), 400
    os.makedirs(_DATA_DIR, exist_ok=True)
    cfg = {'url': d['url'], 'key': d['key'],
           'name': d.get('name', 'CureBox'),
           'interval': d.get('interval', 10)}
    with open(os.path.join(_DATA_DIR, 'cloud.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    if cloud_sync.enabled:
        return jsonify({'ok': True,
                        'message': 'Config saved - restart to apply (agent already running)'})
    cloud_sync = CloudSync()              # starts the agent with the new config
    return jsonify({'ok': True, 'message': 'Cloud sync agent started'})


@app.route('/api/print-history', methods=['GET'])
def get_print_history():
    """Print history: Postgres when configured, else the durable file."""
    if _db_on():
        return jsonify(db.get_print_history())
    with _history_lock:
        return jsonify(_load_json_file(_PRINT_HISTORY_FILE, []))


@app.route('/api/print-history', methods=['POST'])
def save_print_history():
    """Save print history (full replace), to Postgres or the durable file."""
    logs = request.json or []
    if _db_on():
        db.replace_print_history(logs)
    else:
        with _history_lock:
            _save_json_file(_PRINT_HISTORY_FILE, logs)
    return jsonify({'ok': True})


# ---- Cure runs, telemetry & the persisted cure report --------------------

@app.route('/api/cure-history', methods=['GET'])
def cure_history_list():
    """Cure History (§8): Postgres when configured, else the durable file."""
    if _db_on():
        return jsonify(db.get_cure_history())
    return jsonify(_cure_files.list())


@app.route('/api/cure-runs/<ext_id>/start', methods=['POST'])
def cure_run_start(ext_id):
    d = request.get_json(silent=True) or {}
    if _db_on():
        db.start_cure_run(ext_id, d.get('materialName'), d.get('steps'),
                          d.get('phases'), d.get('targetTemp'), d.get('serialNumber'))
    else:
        _cure_files.start(ext_id, d)
    return jsonify({'ok': True})


@app.route('/api/cure-runs/<ext_id>/telemetry', methods=['POST'])
def cure_run_telemetry(ext_id):
    sample = request.get_json(silent=True) or {}
    if _db_on():
        ok = db.record_telemetry(ext_id, sample)
    else:
        ok = _cure_files.telemetry(ext_id, sample)
    return jsonify({'ok': ok})


@app.route('/api/cure-runs/<ext_id>/finish', methods=['POST'])
def cure_run_finish(ext_id):
    d = request.get_json(silent=True) or {}
    if _db_on():
        ok = db.finish_cure_run(ext_id, d.get('status', 'completed'), d.get('stepsCompleted'))
    else:
        ok = _cure_files.finish(ext_id, d.get('status', 'completed'), d.get('stepsCompleted'))
    return jsonify({'ok': ok})


@app.route('/api/cure-runs/<ext_id>/report', methods=['POST'])
def cure_run_report_save(ext_id):
    """Persist a generated cure report for a run."""
    d = request.get_json(silent=True) or {}
    if _db_on():
        rid = db.save_report(ext_id, d.get('content'), d.get('summary'), d.get('format', 'html'))
    else:
        rid = _cure_files.save_report(ext_id, d)
    return jsonify({'ok': True, 'reportId': rid})


@app.route('/api/cure-runs/<ext_id>/report', methods=['GET'])
def cure_run_report_get(ext_id):
    rep = db.get_report(ext_id) if _db_on() else _cure_files.get_report(ext_id)
    if not rep:
        return jsonify({'ok': False, 'message': 'No report'}), 404
    return jsonify({'ok': True, **rep})


# ---- Real phase-timing analytics ------------------------------------------
# Every phase the UI completes reports its TRUE wall-clock duration here -
# including the ramp time the program's step list does not account for. The
# records accumulate in server/data/phase_timings.json (same durable folder
# as everything else) and are the raw data for estimating what each program
# REALLY takes: heating rate to each target, drying/cure holds, cooling time.
_PHASE_TIMINGS_FILE = os.path.join(_DATA_DIR, 'phase_timings.json')


@app.route('/api/phase-timings', methods=['GET'])
def phase_timings_list():
    """All collected phase timings (newest last)."""
    with _history_lock:
        return jsonify(_load_json_file(_PHASE_TIMINGS_FILE, []))


@app.route('/api/cure-runs/<ext_id>/phase', methods=['POST'])
def cure_run_phase(ext_id):
    """Record one finished phase's real timing (fire-and-forget from the UI)."""
    d = request.get_json(silent=True) or {}
    if not d.get('process') or d.get('seconds') is None:
        return jsonify({'ok': False, 'message': 'process and seconds required'}), 400
    rec = {
        'run': ext_id,
        'program': d.get('program'),
        'step': d.get('step'),
        'process': d.get('process'),
        'targetTemp': d.get('targetTemp'),
        'plannedMin': d.get('plannedMin'),      # what the program asked for
        'startedAt': d.get('startedAt'),
        'endedAt': d.get('endedAt'),
        'seconds': d.get('seconds'),            # what it REALLY took
        'rampSeconds': d.get('rampSeconds'),    # part of `seconds` spent ramping
        'tempStart': d.get('tempStart'),
        'tempEnd': d.get('tempEnd'),
    }
    with _history_lock:
        rows = _load_json_file(_PHASE_TIMINGS_FILE, [])
        rows.append(rec)
        _save_json_file(_PHASE_TIMINGS_FILE, rows)
    return jsonify({'ok': True, 'count': len(rows)})


def _on_device():
    """True when running on the machine itself (Pi / any Linux host)."""
    return sys.platform.startswith('linux')


@app.route('/api/system/reboot', methods=['POST'])
def reboot():
    print("[SYSTEM] Rebooting...")
    if not _on_device():
        return jsonify({'ok': True, 'message': 'Reboot simulated'})
    subprocess.Popen(['sudo', 'reboot'], stdout=subprocess.DEVNULL)
    return jsonify({'ok': True, 'message': 'Rebooting...'})


@app.route('/api/system/shutdown', methods=['POST'])
def shutdown():
    print("[SYSTEM] Shutting down...")
    if not _on_device():
        return jsonify({'ok': True, 'message': 'Shutdown simulated'})
    subprocess.Popen(['sudo', 'shutdown', '-h', 'now'], stdout=subprocess.DEVNULL)
    return jsonify({'ok': True, 'message': 'Shutting down...'})


@app.route('/api/door/open', methods=['POST'])
def door_open():
    hw.open_door()
    return jsonify({'ok': True, 'message': 'Door opened'})


@app.route('/api/door-abort/ack', methods=['POST'])
def door_abort_ack():
    """The user tapped 'Understood' on the Err 6016 alert - clear the abort
    flag so the RGB status strip returns from red to the normal color."""
    hw.ack_door_abort()
    return jsonify({'ok': True, 'message': 'Door abort acknowledged'})


@app.route('/api/chamber/temperature', methods=['POST'])
def set_temperature():
    # Same bounds as the driver (heating.target_min=30): anything below is
    # silently clamped up by the control loop, so reject it here instead.
    target = float(request.args.get('target', 25))
    if not (30 <= target <= 80):
        return jsonify({'ok': False, 'code': 7001,
                        'message': f'Invalid target {target} (30-80°C)'})
    ok, why = hw.set_target_temp(target)
    return jsonify({'ok': ok, 'message': why or f'Target set to {target}°C'})

@app.route('/api/chamber/stop', methods=['POST'])
def stop_heating():
    hw.stop_heating()
    return jsonify({'ok': True, 'message': 'Heating stopped'})


@app.route('/api/fans/<fan>', methods=['POST'])
def set_fan(fan):
    speed = int(request.args.get('speed', 0))
    hw.set_fan_speed(fan, speed)
    return jsonify({'ok': True, 'message': f'{fan} set to {speed}%'})


@app.route('/api/damper/<action>', methods=['POST'])
def damper(action):
    hw.set_damper(action == 'open')
    return jsonify({'ok': True, 'message': f'Damper {"opened" if action == "open" else "closed"}'})


# ============================================================
# Cure operation functions (one endpoint per recipe process)
# Each step is defined only by process + (target temp / UV intensity /
# UV wavelength / cooling mode). There is NO user-configured time — the
# function decides when its process is complete.
#
# Ranges mirror the REAL driver limits (io_controller/components.json):
#   heating.target_min = 30°C  → heat/dry/cure targets are 30-80°C
#   led_power.min_intensity = 10 → below 10% the LEDs stay dark
# Error codes come from the central registry (public/config/errors.json).
# ============================================================
HEAT_TARGET_MIN = 30    # io_controller heating.target_min — heater refuses below this
TEMP_MAX = 80
COOL_TARGET_MIN = 20
UV_INTENSITY_MIN = 10   # io_controller led_power.min_intensity — LEDs off below this

ERR_INVALID_TARGET_TEMP = 7001
ERR_INVALID_UV_INTENSITY = 7002
ERR_INVALID_COOLING_MODE = 7003
ERR_PRECURE_CHECK_FAILED = 6015


def _valid_heat_temp(t):
    return HEAT_TARGET_MIN <= t <= TEMP_MAX

def _valid_cool_temp(t):
    return COOL_TARGET_MIN <= t <= TEMP_MAX

def _valid_intensity(i):
    return UV_INTENSITY_MIN <= i <= 100

def _hw_result(ok, why, success_msg):
    """Uniform cure-route response; hardware refusals carry code 6015."""
    if ok:
        return jsonify({'ok': True, 'message': success_msg})
    return jsonify({'ok': False, 'code': ERR_PRECURE_CHECK_FAILED,
                    'message': why or 'Hardware refused the operation'})

@app.route('/api/cure/heat', methods=['POST'])
def cure_heat():
    target = float(request.args.get('target', 60))
    if not _valid_heat_temp(target):
        return jsonify({'ok': False, 'code': ERR_INVALID_TARGET_TEMP,
                        'message': f'Invalid target {target} ({HEAT_TARGET_MIN}-{TEMP_MAX}°C)'})
    ok, why = hw.heat_to_target_temperature(target)
    return _hw_result(ok, why, f'Heating to {target}°C')

@app.route('/api/cure/dry', methods=['POST'])
def cure_dry():
    target = float(request.args.get('target', 60))
    if not _valid_heat_temp(target):
        return jsonify({'ok': False, 'code': ERR_INVALID_TARGET_TEMP,
                        'message': f'Invalid target {target} ({HEAT_TARGET_MIN}-{TEMP_MAX}°C)'})
    ok, why = hw.dry_to_target_temperature(target)
    return _hw_result(ok, why, f'Drying to {target}°C')

@app.route('/api/cure/cure-405', methods=['POST'])
def cure_405():
    target = float(request.args.get('target', 60))
    intensity = int(request.args.get('intensity', 30))
    if not _valid_heat_temp(target):
        return jsonify({'ok': False, 'code': ERR_INVALID_TARGET_TEMP,
                        'message': f'Invalid target {target} ({HEAT_TARGET_MIN}-{TEMP_MAX}°C)'})
    if not _valid_intensity(intensity):
        return jsonify({'ok': False, 'code': ERR_INVALID_UV_INTENSITY,
                        'message': f'Invalid intensity {intensity} ({UV_INTENSITY_MIN}-100%)'})
    ok, why = hw.cure_uv_405(target, intensity)
    return _hw_result(ok, why, f'Cure UV 405nm @ {intensity}%, {target}°C')

@app.route('/api/cure/cure-450', methods=['POST'])
def cure_450():
    target = float(request.args.get('target', 60))
    intensity = int(request.args.get('intensity', 30))
    if not _valid_heat_temp(target):
        return jsonify({'ok': False, 'code': ERR_INVALID_TARGET_TEMP,
                        'message': f'Invalid target {target} ({HEAT_TARGET_MIN}-{TEMP_MAX}°C)'})
    if not _valid_intensity(intensity):
        return jsonify({'ok': False, 'code': ERR_INVALID_UV_INTENSITY,
                        'message': f'Invalid intensity {intensity} ({UV_INTENSITY_MIN}-100%)'})
    ok, why = hw.cure_uv_450(target, intensity)
    return _hw_result(ok, why, f'Bleaching UV 450nm @ {intensity}%, {target}°C')

@app.route('/api/cure/cool', methods=['POST'])
def cure_cool():
    target = float(request.args.get('target', 25))
    mode = request.args.get('mode', 'medium')
    if not _valid_cool_temp(target):
        return jsonify({'ok': False, 'code': ERR_INVALID_TARGET_TEMP,
                        'message': f'Invalid target {target} ({COOL_TARGET_MIN}-{TEMP_MAX}°C)'})
    if mode not in ('fast', 'medium', 'slow'):
        return jsonify({'ok': False, 'code': ERR_INVALID_COOLING_MODE,
                        'message': f'Invalid cooling mode {mode}'})
    ok, why = hw.cool_to_target_temperature(target, mode)
    return _hw_result(ok, why, f'Cooling ({mode}) to {target}°C')

@app.route('/api/cure/nitrogen', methods=['POST'])
def cure_nitrogen():
    """Open/close the N2 purge valve. ?on=1 opens, ?on=0 closes."""
    on = request.args.get('on', '1') not in ('0', 'false', 'off')
    ok, why = hw.set_nitrogen(on)
    return _hw_result(ok, why, f'Nitrogen valve {"opened" if on else "closed"}')

@app.route('/api/cure/stop', methods=['POST'])
def cure_stop():
    """Stop all cure outputs. The heater fan always runs its cooldown run-on
    after heating (30% / 10 min); only the door-open safety abort skips it.
    ?immediate=1 is kept for compatibility (same behavior)."""
    immediate = request.args.get('immediate', '0') not in ('0', 'false', '')
    hw.stop_all(immediate)
    return jsonify({'ok': True, 'message': 'All cure outputs stopped'
                    + (' immediately' if immediate else '')})


@app.route('/api/uv', methods=['POST'])
def set_uv_output():
    """Standalone UV control (diagnostics): ?on=1&intensity=30&wavelength=405."""
    on = request.args.get('on', '0') not in ('0', 'false', 'off')
    intensity = int(request.args.get('intensity', 30))
    wavelength = int(request.args.get('wavelength', 405))
    if on and not _valid_intensity(intensity):
        return jsonify({'ok': False, 'code': ERR_INVALID_UV_INTENSITY,
                        'message': f'Invalid intensity {intensity} ({UV_INTENSITY_MIN}-100%)'})
    if on and wavelength not in (405, 450):
        return jsonify({'ok': False, 'message': f'Invalid wavelength {wavelength} (405|450)'})
    ok, why = hw.set_uv(on, intensity, wavelength if on else None)
    return _hw_result(ok, why, f'UV {"on" if on else "off"}')


@app.route('/api/bofa', methods=['POST'])
def set_bofa():
    """BOFA fume-extraction on/off. ?on=1|0"""
    on = request.args.get('on', '1') not in ('0', 'false', 'off')
    ok, why = hw.set_bofa(on)
    return _hw_result(ok, why, f'BOFA {"on" if on else "off"}')


@app.route('/api/diagnostics/fan-test', methods=['POST'])
def fan_test():
    """Per-fan diagnostic: ?fan=led_cooling|chamber_intake|chamber_heating."""
    fan = request.args.get('fan')
    result = hw.run_fan_test(fan)
    return jsonify({'ok': True, **result})


@app.route('/api/diagnostics/led-test', methods=['POST'])
def led_test():
    result = hw.run_led_test()
    return jsonify({'ok': True, **result})


# ============================================================
# Developer Mode API (/api/dev/*)
#   - timestamped event log
#   - 4-zone LED calibration factors (persisted, server/data/)
#   - calibrated system LED power test drive
#   - PicoLog TC-08 status + Material HDT calibration state machine
# ============================================================

@app.route('/api/dev/log', methods=['POST'])
def dev_log_event():
    """Timestamped Developer Mode UI events (auth, navigation, edits)."""
    d = request.get_json(silent=True) or {}
    event = str(d.get('event', ''))[:200]
    if event:
        dev_log.log_event(event, d.get('detail') or {})
    return jsonify({'ok': True})


@app.route('/api/dev/led-calibration', methods=['GET', 'POST'])
def dev_led_calibration():
    if request.method == 'GET':
        return jsonify({'ok': True, 'factors': led_calibration.get_factors()})
    d = request.get_json(silent=True) or {}
    f = d.get('factors') or {}
    try:
        stored = led_calibration.save_factors(
            {z: f[z] for z in led_calibration.ZONES})
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({'ok': False, 'message': f'Invalid factors: {e}'}), 400
    dev_log.log_event('LED calibration saved', stored)
    return jsonify({'ok': True, 'factors': stored})


@app.route('/api/dev/led-calibration/reset', methods=['POST'])
def dev_led_calibration_reset():
    stored = led_calibration.reset_factors()
    dev_log.log_event('LED calibration reset')
    return jsonify({'ok': True, 'factors': stored})


@app.route('/api/dev/led-power', methods=['POST'])
def dev_led_power():
    """Drive the LEDs at one calibrated system power (LED calibration screen
    test drive). Optional unsaved preview factors ride along; power 0 = the
    safe OFF state. Refused while an HDT calibration owns the LEDs."""
    d = request.get_json(silent=True) or {}
    try:
        power = float(d.get('power', 0))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'Invalid power'}), 400
    if not (0 <= power <= 100):
        return jsonify({'ok': False, 'message': f'Invalid power {power} (0-100%)'}), 400
    if hdt.status()['running']:
        return jsonify({'ok': False,
                        'message': 'HDT calibration is running - abort it first'})
    preview = None
    if isinstance(d.get('factors'), dict):
        try:
            preview = {z: min(led_calibration.FACTOR_MAX,
                              max(led_calibration.FACTOR_MIN,
                                  float(d['factors'][z])))
                       for z in led_calibration.ZONES}
        except (KeyError, TypeError, ValueError):
            return jsonify({'ok': False, 'message': 'Invalid preview factors'}), 400
    if power <= 0:
        ok, why = hw.set_uv(False)
    else:
        ok, why = hw.set_uv(True, power, 405, preview)
    outputs = led_calibration.scaled_outputs(power, preview)
    dev_log.log_event('Physical LED outputs updated',
                      {'power': power, 'outputs': outputs,
                       'preview': preview is not None})
    return jsonify({'ok': bool(ok), 'message': why, 'outputs': outputs})


@app.route('/api/dev/picolog/status', methods=['GET'])
def dev_picolog_status():
    return jsonify(tc08.status())


@app.route('/api/dev/hdt/start', methods=['POST'])
def dev_hdt_start():
    d = request.get_json(silent=True) or {}
    ok, why = hdt.start(d.get('hdtC'), d.get('safetyMarginC'), overrides=d)
    return jsonify({'ok': ok, 'message': why})


@app.route('/api/dev/hdt/abort', methods=['POST'])
def dev_hdt_abort():
    hdt.abort()
    return jsonify({'ok': True, 'message': 'Abort requested - LEDs off'})


@app.route('/api/dev/hdt/reset', methods=['POST'])
def dev_hdt_reset():
    ok = hdt.reset()
    return jsonify({'ok': ok, 'message': None if ok else 'Calibration is running'})


@app.route('/api/dev/hdt/status', methods=['GET'])
def dev_hdt_status():
    samples_from = request.args.get('samplesFrom', type=int)
    return jsonify(hdt.status(samples_from=samples_from))


@app.route('/api/dev/hdt/report.csv', methods=['GET'])
def dev_hdt_report_csv():
    csv_text = hdt.csv_report()
    dev_log.log_event('Report exported', {'rows': csv_text.count('\n')})
    return app.response_class(csv_text, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename=hdt-calibration.csv'})


@app.route('/api/system/export-logs', methods=['POST'])
def export_logs():
    print("[SYSTEM] Exporting logs...")
    try:
        os.system('mkdir -p /media/usb && mount /dev/sda1 /media/usb 2>/dev/null')
        os.system('cp -r /var/log/scure /media/usb/scure-logs-$(date +%Y%m%d) 2>/dev/null')
        os.system('sync && umount /media/usb 2>/dev/null')
        return jsonify({'ok': True, 'message': 'Logs exported to USB'})
    except Exception as e:
        return jsonify({'ok': False, 'code': 9083, 'message': str(e)})


@app.route('/api/system/export-csv', methods=['POST'])
def export_csv_to_usb():
    """Write a generated cure-program CSV to the USB drive connected to the machine."""
    data = request.get_json(silent=True) or {}
    content = data.get('content', '')
    filename = os.path.basename(data.get('filename') or 'untitled.csv')
    if not filename.lower().endswith('.csv'):
        filename += '.csv'
    print(f"[SYSTEM] Exporting CSV '{filename}' to USB...")
    try:
        from updater import find_usb_mount
        usb = find_usb_mount()
        if not usb:
            return jsonify({'ok': False, 'code': 9081,
                            'message': 'No Disk-on-Key found. Please connect a Disk-on-Key (USB drive).'})
        dest = os.path.join(usb, filename)
        with open(dest, 'w', newline='') as f:
            f.write(content)
        os.system('sync')
        return jsonify({'ok': True, 'message': f'Saved {filename} to USB', 'path': dest})
    except Exception as e:
        return jsonify({'ok': False, 'code': 9082, 'message': str(e)})


@app.route('/api/system/export-report', methods=['POST'])
def export_report_to_usb():
    """Write a generated cure-report HTML to the USB drive connected to the machine."""
    data = request.get_json(silent=True) or {}
    content = data.get('content', '')
    filename = os.path.basename(data.get('filename') or 'cure-report.html')
    if not filename.lower().endswith('.html'):
        filename += '.html'
    print(f"[SYSTEM] Exporting report '{filename}' to USB...")
    try:
        from updater import find_usb_mount
        usb = find_usb_mount()
        if not usb:
            return jsonify({'ok': False, 'code': 9081,
                            'message': 'No Disk-on-Key found. Please connect a Disk-on-Key (USB drive).'})
        dest = os.path.join(usb, filename)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(content)
        os.system('sync')
        return jsonify({'ok': True, 'message': f'Saved {filename} to USB', 'path': dest})
    except Exception as e:
        return jsonify({'ok': False, 'code': 9082, 'message': str(e)})


@app.route('/api/system/version', methods=['GET'])
def system_version():
    """All live version/build info. The single source of truth for the app
    version is the VERSION file at the repo root (bumped per release, with a
    matching entry in public/config/versions.json); everything else is read
    from the machine at call time - nothing here is hardcoded."""
    repo = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..'))
    try:
        with open(os.path.join(repo, 'VERSION'), encoding='utf-8') as f:
            app_version = f.read().strip()
    except Exception:                     # noqa: BLE001 - file missing
        app_version = 'unknown'
    return jsonify({
        'appVersion': app_version,
        'gitCommit': run(f'git -C "{repo}" rev-parse --short HEAD') or None,
        'gitDate': run(f'git -C "{repo}" log -1 --format=%cs') or None,
        'lastBoot': run('uptime -s') or None,
        'os': run('. /etc/os-release && echo $PRETTY_NAME') or None,
        'kernel': run('uname -r') or None,
        'python': sys.version.split()[0],
    })


@app.route('/api/system/datetime', methods=['POST'])
def set_datetime():
    """Set the system clock: {date: 'YYYY-MM-DD', time: 'HH:MM'}."""
    d = request.get_json(silent=True) or {}
    date_s, time_s = d.get('date', ''), d.get('time', '')
    import re
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_s) or \
       not re.fullmatch(r'\d{2}:\d{2}(:\d{2})?', time_s):
        return jsonify({'ok': False, 'message': 'Invalid date/time format'})
    if not _on_device():
        return jsonify({'ok': True, 'message': f'Clock set simulated ({date_s} {time_s})'})
    try:
        run('sudo timedatectl set-ntp false')
        out = subprocess.run(['sudo', 'timedatectl', 'set-time', f'{date_s} {time_s}:00'
                              if len(time_s) == 5 else f'{date_s} {time_s}'],
                             capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return jsonify({'ok': False, 'message': out.stderr.strip() or 'set-time failed'})
        return jsonify({'ok': True, 'message': f'Clock set to {date_s} {time_s}'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


def _find_update_package():
    """Locate the newest .scu package on USB. Returns (path, error)."""
    try:
        from updater import find_usb_mount, find_update_package
        usb = find_usb_mount()
        if not usb:
            return None, ('No USB drive found', 9081)
        pkg = find_update_package(usb)
        if not pkg:
            return None, ('No .scu update file found on USB', 9087)
        return pkg, None
    except Exception as e:
        return None, (str(e), 9086)


@app.route('/api/system/update/manifest', methods=['GET'])
def update_manifest():
    """Version + SHA-256 of the update package, for UI-side integrity check."""
    pkg, err = _find_update_package()
    if not pkg:
        msg, code = err
        return jsonify({'ok': False, 'code': code, 'message': msg}), 404
    import hashlib
    h = hashlib.sha256()
    with open(pkg, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    version = os.path.basename(pkg)
    try:
        from updater import extract_and_verify, read_manifest
        update_dir, _msg = extract_and_verify(pkg)
        if update_dir:
            version = read_manifest(update_dir).get('version', version)
            import shutil as _sh
            _sh.rmtree(os.path.dirname(update_dir), ignore_errors=True)
    except Exception:  # pragma: no cover - version stays as filename
        pass
    return jsonify({'ok': True, 'version': version, 'sha256': h.hexdigest()})


@app.route('/api/system/update/package', methods=['GET'])
def update_package():
    """Raw update-package bytes (integrity-checked by the UI against the manifest)."""
    pkg, err = _find_update_package()
    if not pkg:
        msg, code = err
        return jsonify({'ok': False, 'code': code, 'message': msg}), 404
    return send_from_directory(os.path.dirname(pkg), os.path.basename(pkg),
                               as_attachment=True)


@app.route('/api/system/update', methods=['POST'])
def update_software():
    print("[SYSTEM] Starting update process...")
    try:
        from updater import run_update
        result = run_update()
        if not result.get('ok'):
            result.setdefault('code',
                              9087 if 'No .scu' in (result.get('message') or '')
                              else 9081 if 'USB' in (result.get('message') or '')
                              else 9086)
        return jsonify(result)
    except ImportError:
        return jsonify({'ok': True, 'message': 'Update simulated', 'steps': []})


# ============================================================
# Built UI (dist/) — served by Flask so one process runs everything.
# All /api/* rules above are static and win over this catch-all.
# ============================================================
DIST_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'dist'))


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_ui(path):
    if path and os.path.exists(os.path.join(DIST_DIR, path)):
        return send_from_directory(DIST_DIR, path)
    if os.path.exists(os.path.join(DIST_DIR, 'index.html')):
        return send_from_directory(DIST_DIR, 'index.html')
    return jsonify({'ok': False,
                    'message': 'UI not built — run `npm run build` in the repo root'}), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    print(f"[sCure API] Starting on port {port}")
    if io_bridge is not None:
        print("[sCure API] Hardware driver: IO BOARD (io_controller bridge)")
    else:
        print(f"[sCure API] Hardware driver: {'CONNECTED (C++)' if HW_AVAILABLE else 'SIMULATION'}")
    if db is not None and db.available():
        try:
            db.init_schema()
            print("[sCure API] Data store: POSTGRES (schema ensured)")
        except Exception as e:
            print(f"[sCure API] Data store: POSTGRES — schema init failed: {e}")
    else:
        print("[sCure API] Data store: JSON files (set DATABASE_URL to use PostgreSQL)")
    app.run(host='0.0.0.0', port=port, debug=False)
