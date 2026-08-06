#!/usr/bin/env bash
# One-shot bring-up for the MDES Apple Pay demo:
#   1. (re)deploy both dashboards
#   2. start the live synthetic log stream detached (survives terminal close)
#
# Run via `make mc-apple-demo` (wraps this in `op run` so DD_API_KEY / DD_SITE
# are injected). Re-running is safe: dashboards redeploy idempotently and an
# already-running stream is reused.
set -euo pipefail

cd "$(dirname "$0")"                        # docker/mc_apple_mdes
PY=../../.venv-ui/bin/python
LOG=/tmp/mc-apple-mdes.log

echo "Deploying MDES dashboards ..."
"$PY" deploy_dashboards.py create

if pgrep -f "run.py --tag mc-apple-mdes" >/dev/null 2>&1; then
  echo "MDES log stream already running - reusing (log: $LOG)"
else
  echo "Starting MDES log stream (detached) ..."
  PYTHONUNBUFFERED=1 nohup "$PY" run.py --tag mc-apple-mdes >"$LOG" 2>&1 &
  disown
  sleep 2
  pgrep -f "run.py --tag mc-apple-mdes" >/dev/null 2>&1 \
    && echo "✓ MDES log stream up (log: $LOG)" \
    || { echo "✗ log stream failed to start - see $LOG"; exit 1; }
fi
echo "Done. Give the dashboards ~1-2 min to fill on the 'Last 15 minutes' window."
