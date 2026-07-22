#!/bin/bash
# Manual start: sCure API server + UI fullscreen (kiosk).
# (After pi-setup.sh a reboot does all of this automatically.)
set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! curl -s http://localhost:3001/api/state >/dev/null 2>&1; then
  if systemctl list-unit-files scure.service >/dev/null 2>&1; then
    sudo systemctl start scure.service
  else
    sudo "$APP_DIR/.venv/bin/python" "$APP_DIR/server/app.py" &
  fi
fi

"$APP_DIR/scripts/pi-kiosk.sh"
