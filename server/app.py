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

class HardwareController:
    def __init__(self, bridge=None):
        self.bridge = bridge              # IOBridge (real io_controller drivers) or None
        self.chamber_temp = 24.0
        self.target_temp = None
        self.door_closed = True
        self.heating = False
        self.cooling = False
        self.cooling_mode = None       # 'fast' | 'medium' | 'slow'
        self.uv_on = False
        self.uv_intensity = 0
        self.uv_wavelength = None       # 405 (Cure) | 450 (Bleaching)
        self.damper_open = False
        self.fans = {
            'led_cooling': 0,
            'chamber_intake': 0,
            'chamber_heating': 0,
        }

    def get_state(self):
        if self.bridge:
            try:
                return self.bridge.get_state()
            except Exception as e:        # noqa: BLE001 - fall back to simulation
                print(f"[HW] state read failed: {e}")
        if HW_AVAILABLE:
            return hw_driver.get_state()
        return {
            'chamberTemp': self.chamber_temp,
            'targetTemp': self.target_temp,
            'doorClosed': self.door_closed,
            'isHeating': self.heating,
            'isCooling': self.cooling,
            'coolingMode': self.cooling_mode,
            'uvOn': self.uv_on,
            'uvIntensity': self.uv_intensity,
            'uvWavelength': self.uv_wavelength,
            'damperOpen': self.damper_open,
            'fans': self.fans,
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
        self.door_closed = False
        if self.bridge:
            return self.bridge.open_door()
        if HW_AVAILABLE:
            hw_driver.open_door()
        return True, None

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

    def set_uv(self, on, intensity=0, wavelength=None):
        self.uv_on = bool(on)
        self.uv_intensity = int(intensity) if on else 0
        self.uv_wavelength = wavelength if on else None
        if HW_AVAILABLE and hasattr(hw_driver, 'set_uv'):
            hw_driver.set_uv(bool(on), int(intensity) if on else 0, wavelength)

    # ---- high-level operation functions (one per recipe process) ----
    # Each function owns starting / controlling / stopping its hardware. The
    # process ends automatically per its own logic (target reached, etc.).
    def heat_to_target_temperature(self, target_c):
        """Heat the chamber to target_c. Ends when the target is reached."""
        self.set_uv(False)
        self.set_cooling(False)
        self.target_temp = target_c
        self.heating = True
        if self.bridge:
            return self.bridge.heat_to_target(target_c)
        return True, None

    def dry_to_target_temperature(self, target_c):
        """Run drying toward target_c; the process logic stops it automatically."""
        self.set_uv(False)
        self.set_cooling(False)
        self.target_temp = target_c
        self.heating = True
        if self.bridge:
            return self.bridge.dry_to_target(target_c)
        return True, None

    def cure_uv_405(self, target_c, intensity_pct):
        """Cure: heater to target_c + UV 405 nm at intensity_pct."""
        self.set_cooling(False)
        self.target_temp = target_c
        self.heating = True
        self.set_uv(True, intensity_pct, 405)
        if self.bridge:
            return self.bridge.cure_uv(target_c, intensity_pct, 405)
        return True, None

    def cure_uv_450(self, target_c, intensity_pct):
        """Bleaching: heater to target_c + UV 450 nm at intensity_pct."""
        self.set_cooling(False)
        self.target_temp = target_c
        self.heating = True
        self.set_uv(True, intensity_pct, 450)
        if self.bridge:
            return self.bridge.cure_uv(target_c, intensity_pct, 450)
        return True, None

    def cool_to_target_temperature(self, target_c, mode):
        """Cool the chamber to target_c in mode (fast/medium/slow). Ends when reached."""
        self.set_uv(False)
        self.set_heating(False)
        self.target_temp = target_c
        self.set_cooling(True, mode)
        if self.bridge:
            return self.bridge.cool_to_target(target_c, mode)
        return True, None

    def stop_all(self):
        """Stop every cure output (heater, UV, cooling)."""
        self.set_uv(False)
        self.set_heating(False)
        self.set_cooling(False)
        if self.bridge:
            return self.bridge.stop_all()
        return True, None

    def run_fan_test(self):
        if self.bridge:
            return self.bridge.run_fan_test()
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
# API Endpoints
# (Print data, released materials and cure data are managed in PostgreSQL — db.py.)
# ============================================================

@app.route('/api/state', methods=['GET'])
def get_state():
    """Get current hardware state - polled by frontend"""
    return jsonify(hw.get_state())


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
        # Get IP
        result = run("hostname -I | awk '{print $1}'")
        info['ip'] = result or '0.0.0.0'

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

        info['connected'] = info['ip'] != '0.0.0.0'
    except Exception as e:
        info['connected'] = False
        print(f"[NET] Error getting network status: {e}")

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
        return jsonify({'ok': False, 'result': 'Unknown tool'})

    try:
        result = run(cmd)
        return jsonify({'ok': True, 'result': result})
    except Exception as e:
        return jsonify({'ok': False, 'result': str(e)})


def _db_on():
    return db is not None and db.available()


def _require_db():
    return jsonify({'ok': False, 'message': 'Database not configured (set DATABASE_URL)'}), 503


@app.route('/api/materials/presets', methods=['GET'])
def get_preset_materials():
    """System-provided material programs (presets), from Postgres."""
    if not _db_on():
        return _require_db()
    return jsonify(db.get_materials(presets_only=True))


@app.route('/api/materials/user', methods=['GET'])
def get_user_materials():
    """User-created material programs, from Postgres."""
    if not _db_on():
        return _require_db()
    return jsonify(db.get_materials(presets_only=False))


@app.route('/api/materials/user', methods=['POST'])
def save_all_user_materials():
    """Save all user materials (full replace)."""
    if not _db_on():
        return _require_db()
    db.replace_user_materials(request.json or [])
    return jsonify({'ok': True})


@app.route('/api/print-history', methods=['GET'])
def get_print_history():
    """Print history, from Postgres."""
    if not _db_on():
        return _require_db()
    return jsonify(db.get_print_history())


@app.route('/api/print-history', methods=['POST'])
def save_print_history():
    """Save print history (full replace)."""
    if not _db_on():
        return _require_db()
    db.replace_print_history(request.json or [])
    return jsonify({'ok': True})


# ---- Cure runs, telemetry & the persisted cure report --------------------

@app.route('/api/cure-history', methods=['GET'])
def cure_history_list():
    """Cure History (§8) — from Postgres."""
    if not _db_on():
        return _require_db()
    return jsonify(db.get_cure_history())


@app.route('/api/cure-runs/<ext_id>/start', methods=['POST'])
def cure_run_start(ext_id):
    if not _db_on():
        return jsonify({'ok': False, 'message': 'Database not configured'}), 503
    d = request.get_json(silent=True) or {}
    db.start_cure_run(ext_id, d.get('materialName'), d.get('steps'),
                      d.get('phases'), d.get('targetTemp'), d.get('serialNumber'))
    return jsonify({'ok': True})


@app.route('/api/cure-runs/<ext_id>/telemetry', methods=['POST'])
def cure_run_telemetry(ext_id):
    if not _db_on():
        return jsonify({'ok': False, 'message': 'Database not configured'}), 503
    ok = db.record_telemetry(ext_id, request.get_json(silent=True) or {})
    return jsonify({'ok': ok})


@app.route('/api/cure-runs/<ext_id>/finish', methods=['POST'])
def cure_run_finish(ext_id):
    if not _db_on():
        return jsonify({'ok': False, 'message': 'Database not configured'}), 503
    d = request.get_json(silent=True) or {}
    ok = db.finish_cure_run(ext_id, d.get('status', 'completed'), d.get('stepsCompleted'))
    return jsonify({'ok': ok})


@app.route('/api/cure-runs/<ext_id>/report', methods=['POST'])
def cure_run_report_save(ext_id):
    """Persist a generated cure report for a run."""
    if not _db_on():
        return jsonify({'ok': False, 'message': 'Database not configured'}), 503
    d = request.get_json(silent=True) or {}
    rid = db.save_report(ext_id, d.get('content'), d.get('summary'), d.get('format', 'html'))
    return jsonify({'ok': True, 'reportId': rid})


@app.route('/api/cure-runs/<ext_id>/report', methods=['GET'])
def cure_run_report_get(ext_id):
    if not _db_on():
        return jsonify({'ok': False, 'message': 'Database not configured'}), 503
    rep = db.get_report(ext_id)
    if not rep:
        return jsonify({'ok': False, 'message': 'No report'}), 404
    return jsonify({'ok': True, **rep})


@app.route('/api/system/reboot', methods=['POST'])
def reboot():
    print("[SYSTEM] Rebooting...")
    if not HW_AVAILABLE:
        return jsonify({'ok': True, 'message': 'Reboot simulated'})
    subprocess.Popen(['sudo', 'reboot'], stdout=subprocess.DEVNULL)
    return jsonify({'ok': True, 'message': 'Rebooting...'})


@app.route('/api/system/shutdown', methods=['POST'])
def shutdown():
    print("[SYSTEM] Shutting down...")
    if not HW_AVAILABLE:
        return jsonify({'ok': True, 'message': 'Shutdown simulated'})
    subprocess.Popen(['sudo', 'shutdown', '-h', 'now'], stdout=subprocess.DEVNULL)
    return jsonify({'ok': True, 'message': 'Shutting down...'})


@app.route('/api/door/open', methods=['POST'])
def door_open():
    hw.open_door()
    return jsonify({'ok': True, 'message': 'Door opened'})


@app.route('/api/chamber/temperature', methods=['POST'])
def set_temperature():
    target = float(request.args.get('target', 25))
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
# ============================================================
def _valid_temp(t):
    return 20 <= t <= 80

def _valid_intensity(i):
    return 5 <= i <= 100

@app.route('/api/cure/heat', methods=['POST'])
def cure_heat():
    target = float(request.args.get('target', 60))
    if not _valid_temp(target):
        return jsonify({'ok': False, 'message': f'Invalid target {target} (20-80°C)'})
    ok, why = hw.heat_to_target_temperature(target)
    return jsonify({'ok': ok, 'message': why or f'Heating to {target}°C'})

@app.route('/api/cure/dry', methods=['POST'])
def cure_dry():
    target = float(request.args.get('target', 60))
    if not _valid_temp(target):
        return jsonify({'ok': False, 'message': f'Invalid target {target} (20-80°C)'})
    ok, why = hw.dry_to_target_temperature(target)
    return jsonify({'ok': ok, 'message': why or f'Drying to {target}°C'})

@app.route('/api/cure/cure-405', methods=['POST'])
def cure_405():
    target = float(request.args.get('target', 60))
    intensity = int(request.args.get('intensity', 30))
    if not _valid_temp(target):
        return jsonify({'ok': False, 'message': f'Invalid target {target} (20-80°C)'})
    if not _valid_intensity(intensity):
        return jsonify({'ok': False, 'message': f'Invalid intensity {intensity} (5-100%)'})
    ok, why = hw.cure_uv_405(target, intensity)
    return jsonify({'ok': ok, 'message': why or f'Cure UV 405nm @ {intensity}%, {target}°C'})

@app.route('/api/cure/cure-450', methods=['POST'])
def cure_450():
    target = float(request.args.get('target', 60))
    intensity = int(request.args.get('intensity', 30))
    if not _valid_temp(target):
        return jsonify({'ok': False, 'message': f'Invalid target {target} (20-80°C)'})
    if not _valid_intensity(intensity):
        return jsonify({'ok': False, 'message': f'Invalid intensity {intensity} (5-100%)'})
    ok, why = hw.cure_uv_450(target, intensity)
    return jsonify({'ok': ok, 'message': why or f'Bleaching UV 450nm @ {intensity}%, {target}°C'})

@app.route('/api/cure/cool', methods=['POST'])
def cure_cool():
    target = float(request.args.get('target', 25))
    mode = request.args.get('mode', 'medium')
    if not _valid_temp(target):
        return jsonify({'ok': False, 'message': f'Invalid target {target} (20-80°C)'})
    if mode not in ('fast', 'medium', 'slow'):
        return jsonify({'ok': False, 'message': f'Invalid cooling mode {mode}'})
    ok, why = hw.cool_to_target_temperature(target, mode)
    return jsonify({'ok': ok, 'message': why or f'Cooling ({mode}) to {target}°C'})

@app.route('/api/cure/stop', methods=['POST'])
def cure_stop():
    hw.stop_all()
    return jsonify({'ok': True, 'message': 'All cure outputs stopped'})


@app.route('/api/diagnostics/fan-test', methods=['POST'])
def fan_test():
    result = hw.run_fan_test()
    return jsonify({'ok': True, **result})


@app.route('/api/diagnostics/led-test', methods=['POST'])
def led_test():
    result = hw.run_led_test()
    return jsonify({'ok': True, **result})


@app.route('/api/system/export-logs', methods=['POST'])
def export_logs():
    print("[SYSTEM] Exporting logs...")
    try:
        os.system('mkdir -p /media/usb && mount /dev/sda1 /media/usb 2>/dev/null')
        os.system('cp -r /var/log/scure /media/usb/scure-logs-$(date +%Y%m%d) 2>/dev/null')
        os.system('sync && umount /media/usb 2>/dev/null')
        return jsonify({'ok': True, 'message': 'Logs exported to USB'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


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
            return jsonify({'ok': False, 'message': 'No USB drive found. Please insert a USB stick.'})
        dest = os.path.join(usb, filename)
        with open(dest, 'w', newline='') as f:
            f.write(content)
        os.system('sync')
        return jsonify({'ok': True, 'message': f'Saved {filename} to USB', 'path': dest})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


@app.route('/api/system/update', methods=['POST'])
def update_software():
    print("[SYSTEM] Starting update process...")
    try:
        from updater import run_update
        result = run_update()
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
