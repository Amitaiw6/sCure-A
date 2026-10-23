#!/usr/bin/env bash
# Install the sCure DVT runner on a CureBox (run ON the machine, from the unpacked bundle folder):
#
#     sudo ./install-runner.sh --portal <web-app /exec URL> --key <DVT key> --machine CureBox-1 --unit UUT-01
#
# It runs the DVT tests requested from sCure Cloud's DVT tab - each one only after someone presses Start on this
# machine's screen (firmware 1.0.88+: /api/dvt/remote-confirm). Layout: /opt/scure-dvt-runner/{runner,web,VERSION},
# config /opt/scure-dvt-runner/runner/dvt-runner.json (mode 600), service scure-dvt-runner (user scure).
set -euo pipefail
PORTAL="" KEY="" MACHINE="" UNIT="" USER_NAME="scure"
while [ $# -gt 0 ]; do
  case "$1" in
    --portal) PORTAL="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --machine) MACHINE="$2"; shift 2 ;;
    --unit) UNIT="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 2; }
for v in PORTAL KEY MACHINE UNIT; do [ -n "${!v}" ] || { echo "--${v,,} is required" >&2; exit 2; }; done
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/scure-dvt-runner

# Node 18+ (fetch built in); Debian 13 ships 20
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  echo "== installing Node.js"
  apt-get update -qq && apt-get install -y -qq nodejs
fi
echo "== node $(node -v)"

# the firmware must offer the Start / Decline confirmation, or nothing could ever run
if ! curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/api/dvt/remote-confirm/probe | grep -q '^200$'; then
  echo "!! the firmware does not answer /api/dvt/remote-confirm - install sCureBox 1.0.88 or later first" >&2
  exit 3
fi

echo "== files -> $DEST"
mkdir -p "$DEST/runner" "$DEST/web"
install -m 644 "$HERE/runner/dvt-runner.cjs" "$DEST/runner/"
install -m 644 "$HERE/web/dvt-tool.html" "$HERE/web/dvt-catalog.js" "$HERE/web/dvt-criteria.js" "$HERE/web/dvt-auto.js" "$DEST/web/"
install -m 644 "$HERE/VERSION" "$DEST/VERSION"
umask 077
cat > "$DEST/runner/dvt-runner.json" <<EOF
{ "portalUrl": "$PORTAL", "key": "$KEY", "machine": "$MACHINE", "unit": "$UNIT",
  "machineApi": "http://127.0.0.1:3001", "pollSec": 10, "confirmTimeoutSec": 600, "promptTimeoutMin": 60,
  "resultsFile": "$DEST/runner/results.json" }
EOF
chown -R "$USER_NAME:$USER_NAME" "$DEST"
chmod 600 "$DEST/runner/dvt-runner.json"

echo "== service scure-dvt-runner"
cat > /etc/systemd/system/scure-dvt-runner.service <<EOF
[Unit]
Description=sCure DVT runner (runs DVT tests requested from sCure Cloud after Start on the machine screen)
After=network-online.target scurebox-ui.service
Wants=network-online.target

[Service]
User=$USER_NAME
ExecStart=$(command -v node) $DEST/runner/dvt-runner.cjs $DEST/runner/dvt-runner.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now scure-dvt-runner
sleep 3
systemctl --no-pager --lines=5 status scure-dvt-runner || true
echo "== done: the DVT tab of $MACHINE should show 'DVT runner online' within a minute"
