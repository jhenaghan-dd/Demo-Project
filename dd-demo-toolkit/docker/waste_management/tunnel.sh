#!/usr/bin/env bash
# Cloudflare quick tunnel for the WM fleet map, with a URL handoff for the
# dashboard embed.
#
# Writes the live https://<random>.trycloudflare.com URL to
# .secrets/wm_tunnel_url.txt so `deploy_dashboard.py create` (the UI's "Create
# dashboard" button) can pick it up and embed the live map iframe. Removes the
# file on exit, so a dead/stale tunnel never leaves a broken embed URL behind.
#
# Started by the UI process supervisor as `wm-tunnel` (long-running), or
# directly: `bash docker/waste_management/tunnel.sh`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"     # dd-demo-toolkit
PORT="${FLEET_MAP_PORT:-8088}"
URL_FILE="$ROOT/.secrets/wm_tunnel_url.txt"
mkdir -p "$ROOT/.secrets"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not installed. Install: brew install cloudflared" >&2
  exit 2
fi

cleanup() { rm -f "$URL_FILE"; }
trap cleanup EXIT
trap 'exit 0' INT TERM

TUNLOG="$(mktemp)"
cloudflared tunnel --url "http://localhost:${PORT}" > "$TUNLOG" 2>&1 &
CF_PID=$!

echo "starting Cloudflare tunnel for :${PORT} ..."
URL=""
for _ in $(seq 1 30); do
  # -a: cloudflared's banner has non-text bytes; without it grep reports
  # "Binary file matches" instead of the URL.
  URL=$(grep -aoE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUNLOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 2
done
if [ -z "$URL" ]; then
  echo "tunnel URL not found after 60s" >&2
  cat "$TUNLOG" >&2 || true
  kill "$CF_PID" 2>/dev/null || true
  exit 1
fi

echo "$URL" > "$URL_FILE"
echo "tunnel up: $URL"
echo "wrote $URL_FILE — now click 'Create dashboard' and the live map embeds."

# Stream cloudflared output to the supervisor log, and block on the tunnel so
# the supervisor tracks this as a running process (Stop → SIGINT → cleanup).
tail -f "$TUNLOG" &
wait "$CF_PID"
