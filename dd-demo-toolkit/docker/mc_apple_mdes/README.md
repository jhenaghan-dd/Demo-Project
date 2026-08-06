# MDES Apple Pay Provisioning - Datadog recreation (Mastercard)

Recreates two Mastercard Splunk dashboards for the **MDES Apple Pay
provisioning** flow in a Datadog sandbox, on top of a **100% synthetic** log
stream:

1. **MDES Apple Pay Provisioning - Operational Dashboard** (from the screenshot)
2. **Apple Trouble Shooting - Logs (MDES)** (from `MC_Apple_Log.txt`)

Like `docker/waste_management/`, this is a **standalone** asset - not a
`verticals/` vertical - so it deploys via its own thin scripts that reuse the
toolkit's `DatadogAPIClient` (auth/site/retry) and secret handling (`op run`).

---

## ⚠️ Everything here is synthetic - and why

**Mastercard shared no log data.** The file we received, `MC_Apple_Log.txt`, is
a **Splunk dashboard definition** (the "Apple Trouble Shooting - Logs" board) -
JSON with SPL queries, **zero log records**. So there was nothing to "import."

What we *did* have was the **field schema** embedded in that dashboard's SPL and
the panels in the operational-dashboard screenshot. `event_model.py`
reconstructs a faithful log stream from that schema. Every value below is
fabricated:

| Panel / field | Source | Synthetic? | How it's made faithful |
|---|---|---|---|
| All log records | - | **100% synthetic** | No customer data was provided |
| Field names (`msg.operation`, `gwrequesturi`, …) | SPL in `MC_Apple_Log.txt` | Real (schema only) | Names copied verbatim so queries read like Splunk |
| Operation mix (getStatus, networkCheckCard, …) | screenshot legends | synthetic weights | Weighted to look like the screenshot |
| **Exception table rows + counts** | screenshot | synthetic weights | The `(operation, statuscode, netsub, statusmessage, mdeserrorcode)` tuples and their weights ARE the counts visible in the screenshot, so the table ranks the same |
| STL DOWN / KSC UP status split | screenshot | synthetic | PCF-app + standalone heartbeats reproduce the red/green grid |
| p90 response times | screenshot | synthetic per-event `@response_time_ms` | See "p90" below |
| Correlation/Conversation/SEID IDs | SPL tokens | synthetic per-transaction | One transaction = one correlated bundle so drill-downs line up |

**Call this out in the demo:** the numbers are illustrative, not Mastercard
production data.

### p90 without the usual breakage

The Splunk panels compute p90 over log events. We emit each request as a log
carrying a numeric `@response_time_ms`, and the dashboard uses the **log-based**
`pc90` aggregation over that measure. That is a *true* percentile at query time
- unlike metric-percentile widgets (STYLE_GUIDE §1.1), which need distribution
metrics and often show no data. This is the reliable way to honor the p90
panels.

---

## Schema mapping (Splunk to Datadog)

```
index=app_pcf  sourcetype=cf:logmessage   to  service:mdes-mntbwltorc-wallet-api  ddsource:pcf   (tag dd_index:app_pcf)
index=app_apigw json:apigw:accesslog      to  service:apigw                       ddsource:nginx (tag dd_index:app_apigw)
index=ept_web                             to  service:ept-web                     ddsource:ept   (tag dd_index:ept_web)

msg.operation / msg.statuscode / msg.correlationid / msg.conversationId
msg.mdeserrorcode / msg.networksubstatuscode / msg.statusmessage / msg.xception
msg.TUR_01 / msg.srcTokenUniqueReference / msg.TokenResolutionSource / msg.bin
gwrequesturi / uri / gwhttpstatus / gwdestinationtype / correlationid / device_id
```

All field names are preserved so the recreated queries read like the originals
(`@msg.operation`, `@gwhttpstatus`, …).

---

## Run it

Everything is wrapped in `op run` (1Password must be unlocked) so
`DD_API_KEY` / `DD_SITE` are injected - no plain secrets on disk.

```bash
# 1. Deploy both dashboards (idempotent - safe to re-run)
make mc-apple-dashboards

# 2. Start the live synthetic log stream (foreground; Ctrl-C to stop)
make mc-apple-logs

# One-shot before a demo: deploy dashboards + start the stream detached
make mc-apple-demo

# Teardown
make mc-apple-dashboards-delete        # or: dd-demo teardown --all-verticals
make mc-apple-demo-down                # stop the detached log stream
```

Tunables (env): `MC_TX_PER_CYCLE` (default 60), `MC_CYCLE_SEC` (10),
`MC_ERROR_RATE` (0.10).

Both dashboards carry the `[dd-demo-toolkit:payments]` description marker, so
`dd-demo teardown --all-verticals` removes them like any other toolkit asset.

---

## Files

| File | Purpose |
|---|---|
| `event_model.py` | Synthetic event model - weighted tables mapped to the SPL schema |
| `dd_log_emitter.py` | POST logs to the Datadog v2 logs intake |
| `run.py` | Live-stream loop |
| `build_dashboards.py` | Generate the two dashboard JSONs (log-based widgets) |
| `deploy_dashboards.py` | Create/delete both dashboards (idempotent, teardown marker) |
| `dashboards/*.json` | Generated dashboard definitions |
| `demo_up.sh` | One-shot: deploy + start the stream detached |
