#!/bin/bash
# =============================================================
# sCure Box — one-time setup on the Raspberry Pi CM5
#
# Installs git + all dependencies, clones the repo, builds the
# UI, and installs autostart: on every boot the API server comes
# up and the UI opens FULLSCREEN (Chromium kiosk).
#
# Run on the Pi:
#   bash pi-setup.sh
# (or, if the repo is already on the Pi: bash scripts/pi-setup.sh)
# =============================================================
set -e

REPO_URL="https://github.com/Amitaiw6/sCure-A.git"

# If this script is already inside a clone of the repo, use that copy;
# otherwise clone to ~/sCure-A.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
  APP_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
else
  APP_DIR="$HOME/sCure-A"
fi

echo "== 1/6 System packages (git, python, node, chromium, i2c) =="
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-gpiozero python3-lgpio \
                    i2c-tools nodejs npm curl
sudo apt install -y chromium-browser 2>/dev/null || sudo apt install -y chromium

echo "== 2/6 Enable I2C =="
sudo raspi-config nonint do_i2c 0 2>/dev/null || true

echo "== 3/6 Get the code (git clone / pull) =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
chmod +x scripts/*.sh

echo "== 4/6 Python environment (Flask API + IO-board drivers) =="
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r server/requirements.txt

echo "== 5/6 Build the UI =="
npm install
npm run build

echo "== 6/6 Autostart: API service + fullscreen kiosk =="
sed "s|__APP_DIR__|$APP_DIR|g" scripts/scure.service \
  | sudo tee /etc/systemd/system/scure.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable scure.service

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/scure-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=sCure Kiosk
Exec=$APP_DIR/scripts/pi-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF

echo ""
echo "============================================================"
echo " Setup complete."
echo "   Start now:        bash scripts/pi-start.sh"
echo "   Or just reboot -- the server starts and the UI opens"
echo "   fullscreen automatically."
echo "============================================================"
