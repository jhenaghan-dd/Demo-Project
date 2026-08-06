#!/usr/bin/env bash
# Read the reproduction data back out of the org to prove queryability (not just flush).
# Requires DD_API_KEY, DD_APP_KEY, DD_SITE in the environment (export from op).
set -euo pipefail
: "${DD_API_KEY:?}"; : "${DD_APP_KEY:?}"; : "${DD_SITE:=datadoghq.com}"
API="https://api.${DD_SITE}"

distinct_resources() {
  local svc="$1"
  echo "### spans: distinct resource_name for service:$svc env:poc-repro"
  curl -s -X POST "$API/api/v2/spans/events/search" \
    -H "DD-API-KEY: $DD_API_KEY" -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"data\":{\"type\":\"search_request\",\"attributes\":{\"filter\":{\"query\":\"service:$svc env:poc-repro\",\"from\":\"now-40m\",\"to\":\"now\"},\"sort\":\"-timestamp\",\"page\":{\"limit\":200}}}}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); rs=sorted({(e.get('attributes',{}).get('resource_name') or e.get('attributes',{}).get('resource')) for e in d.get('data',[])}); print('  count events:', len(d.get('data',[]))); [print('   -', r) for r in rs if r]"
}

metric() {
  local q="$1"
  local now from; now=$(date +%s); from=$((now-2400))
  echo "### metric: $q"
  curl -s -G "$API/api/v1/query" \
    -H "DD-API-KEY: $DD_API_KEY" -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    --data-urlencode "from=$from" --data-urlencode "to=$now" --data-urlencode "query=$q" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('series') or [];
print('  series:', len(s));
[print('   points:', len(x.get('pointlist',[])), '| last:', (x.get('pointlist') or [[None,None]])[-1][1]) for x in s]"
}

distinct_resources identityproxy-baseline
distinct_resources identityproxy-mapped
metric "avg:jvm.heap_memory{service:identityproxy-mapped}"
metric "avg:jvm.gc.old_gen_size{service:identityproxy-mapped}"
metric "avg:trace.servlet.request.duration{service:identityproxy-mapped}"
