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
from flask import Flask, request, jsonify
from flask_cors import CORS

# Try to import the C++ hardware driver
try:
    from hardware import hw_driver
    HW_AVAILABLE = True
except ImportError:
    HW_AVAILABLE = False
    print("[WARN] C++ hardware driver not found, running in simulation mode")

app = Flask(__name__)
CORS(app)

# Temperature controller
temp_controller = None
try:
    from temperature_control import TemperatureController
    from io_board import IOBoard
    io_board = IOBoard()
    temp_controller = TemperatureController(io_board)

    def on_temp_update(temp, target, at_temp, heating):
        hw.chamber_temp = temp
        hw.target_temp = target
        hw.heating = heating

    temp_controller.set_update_callback(on_temp_update)
    print("[API] Temperature controller connected")
except ImportError:
    print("[API] Temperature controller not available (simulation mode)")

# ============================================================
# Hardware abstraction - calls C++ driver or simulates
# ============================================================

class HardwareController:
    def __init__(self):
        self.chamber_temp = 24.0
        self.target_temp = None
        self.door_closed = True
        self.heating = False
        self.cooling = False
        self.uv_on = False
        self.uv_intensity = 0
        self.damper_open = False
        self.fans = {
            'led_cooling': 0,
            'chamber_intake': 0,
            'chamber_heating': 0,
        }

    def get_state(self):
        if HW_AVAILABLE:
            return hw_driver.get_state()
        return {
            'chamberTemp': self.chamber_temp,
            'targetTemp': self.target_temp,
            'doorClosed': self.door_closed,
            'isHeating': self.heating,
            'isCooling': self.cooling,
            'uvOn': self.uv_on,
            'uvIntensity': self.uv_intensity,
            'damperOpen': self.damper_open,
            'fans': self.fans,
        }

    def set_target_temp(self, temp):
        self.target_temp = temp
        if HW_AVAILABLE:
            hw_driver.set_target_temperature(temp)

    def set_fan_speed(self, fan, speed):
        self.fans[fan] = speed
        if HW_AVAILABLE:
            hw_driver.set_fan_speed(fan, speed)

    def set_damper(self, open_state):
        self.damper_open = open_state
        if HW_AVAILABLE:
            hw_driver.set_damper(open_state)

    def open_door(self):
        self.door_closed = False
        if HW_AVAILABLE:
            hw_driver.open_door()

    def run_fan_test(self):
        if HW_AVAILABLE:
            return hw_driver.run_fan_test()
        return {'rpm': 2850, 'status': 'OK'}

    def run_led_test(self):
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


hw = HardwareController()

# ============================================================
# Materials data path
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'materials')
USER_MATERIALS_FILE = os.path.join(DATA_DIR, 'user_materials.json')
PRINT_HISTORY_FILE = os.path.join(DATA_DIR, 'print_history.json')

def load_json_file(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

# ============================================================
# API Endpoints
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


@app.route('/api/materials/user', methods=['GET'])
def get_user_materials():
    """Get all user-created materials"""
    return jsonify(load_json_file(USER_MATERIALS_FILE))


@app.route('/api/materials/user', methods=['POST'])
def save_all_user_materials():
    """Save all user materials (full replace)"""
    save_json_file(USER_MATERIALS_FILE, request.json)
    return jsonify({'ok': True})


@app.route('/api/print-history', methods=['GET'])
def get_print_history():
    """Get print history"""
    return jsonify(load_json_file(PRINT_HISTORY_FILE))


@app.route('/api/print-history', methods=['POST'])
def save_print_history():
    """Save print history (full replace)"""
    save_json_file(PRINT_HISTORY_FILE, request.json)
    return jsonify({'ok': True})


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
    hw.set_target_temp(target)
    if temp_controller:
        temp_controller.start(target)
    return jsonify({'ok': True, 'message': f'Target set to {target}°C'})

@app.route('/api/chamber/stop', methods=['POST'])
def stop_heating():
    if temp_controller:
        temp_controller.stop()
    hw.heating = False
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


@app.route('/api/system/update', methods=['POST'])
def update_software():
    print("[SYSTEM] Starting update process...")
    try:
        from updater import run_update
        result = run_update()
        return jsonify(result)
    except ImportError:
        return jsonify({'ok': True, 'message': 'Update simulated', 'steps': []})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    print(f"[sCure API] Starting on port {port}")
    print(f"[sCure API] Hardware driver: {'CONNECTED' if HW_AVAILABLE else 'SIMULATION'}")
    app.run(host='0.0.0.0', port=port, debug=False)
