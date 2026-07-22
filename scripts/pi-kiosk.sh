#!/bin/bash
# Open the sCure UI FULLSCREEN (Chromium kiosk) once the API is up.
# Used by the desktop autostart entry and by pi-start.sh.
URL="http://localhost:3001"

# Wait for the API (up to 60 s)
for _ in $(seq 1 60); do
  curl -s "$URL/api/state" >/dev/null 2>&1 && break
  sleep 1
done

BROWSER="$(command -v chromium-browser || command -v chromium)"
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars \
  --disable-session-crashed-bubble --check-for-update-interval=31536000 "$URL"
