#!/usr/bin/env bash
# identityProxy APM reproduction driver.
# All traffic is driven container-to-container (Colima — no host-port publish).
set -euo pipefail

NET=idproxy-net
AGENT=idproxy-agent
IMG=idproxy-app:1.64.2
CURL_IMG=curlimages/curl:latest
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMON_OPTS="-Ddd.env=poc-repro -Ddd.version=1.0 -Ddd.runtime.metrics.enabled=true \
-Ddd.profiling.enabled=true -Ddd.tags=purpose:poc-repro,synthetic:true \
-Ddd.trace.sample.rate=1 -Xmx512m"

require_creds() { : "${DD_API_KEY:?set DD_API_KEY from op}"; : "${DD_SITE:=datadoghq.com}"; }
now_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# All HTTP calls go through the Docker network via this helper.
# Usage: net_curl <container-target> <curl-args...>
net_curl() {
  local target="$1"; shift
  docker run --rm --network "$NET" "$CURL_IMG" -s "$@" "http://${target}:8080$1" 2>/dev/null
}
# More flexible: pass full URL after container base
ncurl() {
  docker run --rm --network "$NET" "$CURL_IMG" "$@" 2>/dev/null
}

up() {
  require_creds
  docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
  echo "[*] starting Datadog Agent (APM)…"
  docker rm -f "$AGENT" >/dev/null 2>&1 || true
  docker run -d --name "$AGENT" --network "$NET" \
    -e DD_API_KEY -e DD_SITE \
    -e DD_APM_ENABLED=true -e DD_APM_NON_LOCAL_TRAFFIC=true \
    -e DD_HOSTNAME=identity-proxy-repro \
    -e DD_TAGS="purpose:poc-repro synthetic:true" \
    gcr.io/datadoghq/agent:7 >/dev/null
  echo "[*] waiting for APM intake to connect…"
  for i in $(seq 1 45); do
    if docker exec "$AGENT" agent status 2>/dev/null | grep -qiE "Trace Agent|APM"; then
      docker exec "$AGENT" sh -c 'agent status 2>/dev/null | grep -iA2 "Trace Agent" || true'
      break
    fi
    sleep 3
  done
  echo "[*] building app image (Spring + dd-java-agent 1.64.2)…"
  docker build -q -t "$IMG" "$DIR/app" >/dev/null
  docker pull -q "$CURL_IMG" >/dev/null 2>&1 || true
  echo "[+] up. image=$IMG"
}

start_app() {
  local name="$1" svc="$2" extra="${3:-}"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network "$NET" \
    -e DD_AGENT_HOST="$AGENT" -e DD_TRACE_AGENT_PORT=8126 \
    -e JAVA_OPTS="-Ddd.service=$svc $extra $COMMON_OPTS" \
    "$IMG" >/dev/null
  echo "[*] $name ($svc) starting; waiting for readiness…"
  for i in $(seq 1 45); do
    ncurl -sf -X POST "http://${name}:8080/identity-v1/acctNumCheck" >/dev/null 2>&1 && { echo "[+] ready"; return 0; }
    sleep 2
  done
  echo "[!] app did not become ready"; docker logs --tail 40 "$name"; return 1
}

traffic() {
  local name="$1" n="${2:-220}"
  local ops=(acctNumCheck balanceInquiry addressUpdate)
  for i in $(seq 1 "$n"); do
    local op="${ops[$((i % 3))]}"
    ncurl -s -o /dev/null -X POST "http://${name}:8080/identity-v1/$op" || true
    if (( i % 40 == 0 )); then ncurl -s -o /dev/null "http://${name}:8080/admin/fault" || true; fi
  done
  echo "[+] sent $n requests to $name across ${ops[*]}"
}

runA() {
  start_app idproxy-a identityproxy-baseline ""
  traffic idproxy-a 240
  echo "[+] Run A complete (baseline, no mapping)."
  docker rm -f idproxy-a >/dev/null 2>&1 || true
}

runB() {
  start_app idproxy-b identityproxy-mapped \
    "-Ddd.trace.http.server.path-resource-name-mapping=/identity-v1/**:*"
  traffic idproxy-b 240
  echo "[+] Run B baseline traffic complete (mapped). Container idproxy-b left UP for leak phase."
}

leak() {
  echo "=== LEAK TIMELINE (UTC) ==="
  local t_start; t_start="$(now_utc)"
  ncurl -s "http://idproxy-b:8080/admin/fault?leak=on" >/dev/null || true
  echo "fault_start        $t_start"
  local sat="" latdeg="" firsterr=""
  local endc=$(( SECONDS + 660 ))
  while (( SECONDS < endc )); do
    local out; out="$(ncurl -s -o /dev/null -w '%{http_code} %{time_total}' -X POST "http://idproxy-b:8080/identity-v1/balanceInquiry" || echo '000 0')"
    local code="${out%% *}" tt="${out##* }"
    local fill; fill="$(ncurl -s "http://idproxy-b:8080/admin/fault" | grep -o '"heapFillPct":[0-9]*' | grep -o '[0-9]*' || echo 0)"
    if [[ -z "$sat" && "${fill:-0}" -ge 80 ]]; then sat="$(now_utc)"; echo "heap_saturation    $sat  (heapFillPct=$fill)"; fi
    if [[ -z "$latdeg" ]] && awk "BEGIN{exit !($tt > 0.30)}"; then latdeg="$(now_utc)"; echo "first_latency_deg  $latdeg  (time_total=${tt}s)"; fi
    if [[ -z "$firsterr" && "$code" =~ ^5 ]]; then firsterr="$(now_utc)"; echo "first_error        $firsterr  (http=$code)"; fi
    for j in 1 2 3; do ncurl -s -o /dev/null -X POST "http://idproxy-b:8080/identity-v1/acctNumCheck" || true; done
    sleep 1
  done
  echo "leak_window_end    $(now_utc)"
  echo "=== end timeline ==="
}

down() { docker rm -f idproxy-a idproxy-b "$AGENT" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; echo "[+] torn down"; }

cmd="${1:-}"; shift || true
case "$cmd" in
  up) up ;;
  runA) runA ;;
  runB) runB ;;
  leak) leak ;;
  down) down ;;
  *) echo "usage: $0 {up|runA|runB|leak|down}"; exit 2 ;;
esac
