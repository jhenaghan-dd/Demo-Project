#!/usr/bin/env bash
# WM Operations Agent — agentic LLM Observability demo (standalone, agentless).
# No Docker, no Agent, no OTel collector — streams straight to Datadog.
#
#   export DD_API_KEY=<key>            # required
#   export DD_APP_KEY=<key>            # required for --experiments
#   export DD_SITE=datadoghq.com       # or us3/us5/eu/ap1/ddog-gov
#
#   ./run.sh                           # live agent TRACES (continuous; Ctrl-C to stop)
#   ./run.sh --count 25                # emit N trace conversations then exit
#   ./run.sh --experiments             # run the model-comparison EXPERIMENTS (scorecard)
#   ./run.sh --experiments --limit 2   # first 2 models only (quick smoke)
set -euo pipefail
cd "$(dirname "$0")"

SCRIPT="wm_ops_agent.py"
if [[ "${1:-}" == "--experiments" || "${1:-}" == "--exp" ]]; then
  SCRIPT="wm_ops_experiments.py"; shift
fi

if [[ -z "${DD_API_KEY:-}" ]]; then
  echo "DD_API_KEY is not set (required for agentless LLM Observability)." >&2
  exit 2
fi
export DD_SITE="${DD_SITE:-datadoghq.com}"

PY="${PYTHON:-python3}"
if ! "$PY" -c "import ddtrace" >/dev/null 2>&1; then
  echo "Installing ddtrace into a local venv (.venv-agentic)…"
  "$PY" -m venv .venv-agentic
  PY=".venv-agentic/bin/python"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r requirements.txt
fi

exec "$PY" "$SCRIPT" "$@"
