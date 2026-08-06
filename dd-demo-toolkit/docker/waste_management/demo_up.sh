#!/usr/bin/env bash
# One-shot bring-up for the WasteManagement fleet-at-scale demo.
#
# Restores the whole live stack after a laptop sleep / reboot / new day:
#   1. fleet (emitter -> Datadog hosts + metrics, AND the map server on :8088)
#   2. a fresh Cloudflare quick tunnel (HTTPS -> :8088)
#   3. redeploys the Datadog dashboard with the *new* tunnel URL embedded
#
# Why step 3 every time: quick-tunnel URLs (*.trycloudflare.com) rotate on each
# restart, so the dashboard's iframe URL must be refreshed or the map panel goes
# blank. This script captures the new URL and redeploys automatically.
#
# Run it via `make wm-fleet-demo` (wraps this in `op run` so DD_API_KEY/DD_APP_KEY
# are injected). Processes are detached with nohup so they survive the terminal
# closing. Re-running is safe: an already-running fleet is reused, a stale tunnel
# is replaced.
set -euo pipefail

cd "$(dirname "$0")"                       # docker/waste_management
PY=../../.venv-ui/bin/python
PORT="${FLEET_MAP_PORT:-8088}"
LOG=/tmp/wm-fleet-live.log
TUNLOG=/tmp/wm-tunnel.log

# --- 1. Fleet (emitter + map) -------------------------------------------------
if curl -sf "localhost:${PORT}/healthz" >/dev/null 2>&1; then
  echo "✓ fleet already serving on :${PORT} — reusing"
else
  echo "→ starting fleet (emitter + map) ..."
  PYTHONUNBUFFERED=1 nohup "$PY" run.py >"$LOG" 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf "localhost:${PORT}/healthz" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf "localhost:${PORT}/healthz" >/dev/null 2>&1 \
    || { echo "✗ fleet failed to start — see $LOG"; exit 1; }
  echo "✓ fleet up on :${PORT}"
fi

# --- 2. Fresh Cloudflare quick tunnel ----------------------------------------
pkill -f "cloudflared tunnel --url http://localhost:${PORT}" 2>/dev/null || true
: > "$TUNLOG"
echo "→ starting Cloudflare tunnel ..."
nohup cloudflared tunnel --url "http://localhost:${PORT}" >"$TUNLOG" 2>&1 &
URL=""
for _ in $(seq 1 30); do
  # -a: cloudflared's banner has box-drawing bytes; without it grep reports
  # "Binary file ... matches" instead of the matched URL.
  URL=$(grep -aoE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUNLOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 2
done
[ -n "$URL" ] || { echo "✗ tunnel URL not found — see $TUNLOG"; exit 1; }
echo "✓ tunnel: $URL"

# --- 3. Redeploy dashboard with the new embed URL ----------------------------
echo "→ redeploying dashboard with embedded map ..."
"$PY" deploy_dashboard.py delete
WM_FLEET_MAP_URL="$URL" "$PY" deploy_dashboard.py create

echo ""
echo "✓ WasteManagement fleet demo is UP."
echo "  Map (local):  http://localhost:${PORT}"
echo "  Map (tunnel): $URL"
echo "  Stop with:    make wm-fleet-demo-down"
