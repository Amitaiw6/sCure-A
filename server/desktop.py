"""sCure Box desktop app — the software's own fullscreen window (no browser).

Runs the Flask API server in-process and shows the built UI in a native
window (WebView2 on Windows). Launched by scripts/win-start.bat.
The Raspberry Pi keeps using the Chromium kiosk (scripts/pi-kiosk.sh).
"""
import os
import sys
import threading
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

# Under pythonw.exe there is no console: stdout/stderr are None and any
# server logging would crash. Send everything to a log file instead.
if sys.stdout is None or sys.stderr is None:
    _log = open(os.path.join(APP_DIR, '..', 'scure-desktop.log'),
                'a', buffering=1, encoding='utf-8', errors='replace')
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import webview  # pywebview — native window; not needed on the Pi

import app as scure

PORT = int(os.environ.get('PORT', 3001))
URL = f'http://127.0.0.1:{PORT}'


def api_up():
    try:
        with urllib.request.urlopen(f'{URL}/api/state', timeout=2):
            return True
    except Exception:
        return False


def start_server():
    # Same startup as `python server/app.py` (see app.py __main__).
    if scure.db is not None and scure.db.available():
        try:
            scure.db.init_schema()
        except Exception as e:
            print(f"[sCure] Postgres schema init failed: {e}")
    scure.app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    # Reuse an already-running server (e.g. a dev session); else start one.
    if not api_up():
        threading.Thread(target=start_server, daemon=True).start()
        for _ in range(60):
            if api_up():
                break
            time.sleep(1)
    webview.create_window('sCure Box', URL, fullscreen=True)
    webview.start()