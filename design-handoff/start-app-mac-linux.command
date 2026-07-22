#!/bin/sh
# Launches the sCure UI build locally so the designer can click through every screen.
# Requires Node.js (https://nodejs.org). The browser opens automatically once ready.
# On macOS you can double-click this file (you may need: chmod +x start-app-mac-linux.command).
cd "$(dirname "$0")"

# Find Node: first on PATH, then common install locations (a double-clicked
# launcher sometimes runs without Node on PATH even when it is installed).
NODE_EXE=""
if command -v node >/dev/null 2>&1; then
  NODE_EXE="node"
else
  for p in /usr/local/bin/node /opt/homebrew/bin/node /usr/bin/node \
           "$HOME/.volta/bin/node" "$HOME/.nvm/current/bin/node" \
           "$HOME/.local/bin/node"; do
    [ -x "$p" ] && NODE_EXE="$p" && break
  done
  # nvm / fnm versioned installs (pick the newest if present)
  if [ -z "$NODE_EXE" ]; then
    for p in "$HOME"/.nvm/versions/node/*/bin/node "$HOME"/.local/state/fnm_multishells/*/bin/node; do
      [ -x "$p" ] && NODE_EXE="$p"
    done
  fi
fi

if [ -z "$NODE_EXE" ]; then
  echo ""
  echo "  Node.js was not found. Install it once from https://nodejs.org then run this again."
  echo ""
  exit 1
fi

"$NODE_EXE" "$(dirname "$0")/server.mjs"
