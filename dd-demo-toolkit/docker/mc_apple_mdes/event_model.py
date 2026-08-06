"""MDES Apple Pay provisioning - synthetic log event model.

EVERYTHING here is synthetic. Mastercard shared NO log records - the file we
were given (`MC_Apple_Log.txt`) is a Splunk *dashboard definition* (the "Apple
Trouble Shooting - Logs" board), not data. This module reconstructs a faithful
log stream purely from the field schema embedded in that dashboard's SPL and
from the panels visible in the operational-dashboard screenshot.

Field-name fidelity (so the recreated dashboards read like the originals):

  Splunk / SPL field            to  Datadog attribute
  ---------------------------------------------------------------
  msg.operation                 to  @msg.operation
  msg.statuscode                to  @msg.statuscode
  msg.correlationid             to  @msg.correlationid
  msg.conversationId            to  @msg.conversationId
  msg.mdeserrorcode             to  @msg.mdeserrorcode
  msg.networksubstatuscode      to  @msg.networksubstatuscode
  msg.statusmessage             to  @msg.statusmessage
  msg.message                   to  @msg.message
  msg.level / log.level         to  @msg.level / status
  msg.xception                  to  @msg.xception
  msg.TUR_01 / srcTokenUnique.. to  @msg.TUR_01 / @msg.srcTokenUniqueReference
  gwrequesturi / uri / host     to  @gwrequesturi / @uri / @host
  gwhttpstatus / gwdestination. to  @gwhttpstatus / @gwdestinationtype
  correlationid / device_id     to  @correlationid / @device_id  (APIGW nginx)

  Splunk index/sourcetype       to  service + ddsource + dd_index tag
  ---------------------------------------------------------------
  index=app_pcf cf:logmessage   to  service:mdes-mntbwltorc-wallet-api ddsource:pcf
  index=app_apigw json:accesslog to   service:apigw                     ddsource:nginx
  index=ept_web                 to  service:ept-web                   ddsource:ept

A "transaction" emits a *correlated* set of logs that all share one
correlationid + conversationId + device_id (SEID). That is what makes the
troubleshooting dashboard's call-trail drill-downs (by corr_id / convid) line
up across the APIGW, PCF, EPT and token-resolution panels - exactly like the
Splunk board that pivots on `$corr_id$` / `$convid$`.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Dict, List

# --------------------------------------------------------------------------
# Topology - two active sites, mirroring the STL / KSC split on every panel.
# KSC runs hotter in the screenshot (STL app tier is largely degraded, see the
# PCF status table below), so KSC carries more inbound volume.
# --------------------------------------------------------------------------
SITES = {
    "stl": {"weight": 0.42, "apigw_host": "apigw-stl-01", "gw_prefix": "stl"},
    "ksc": {"weight": 0.58, "apigw_host": "apigw-ksc-01", "gw_prefix": "ksc"},
}

APP = "mdes-mntbwltorc-wallet-api"
SPACE = "prod"

# --------------------------------------------------------------------------
# Inbound provisioning operations (API-gateway + application tiers).
# Names come straight off the operational dashboard legends. baseline_ms is a
# rough per-op gateway response time; a real per-event value is emitted so the
# p90 panels compute a TRUE percentile over the measure (not a fabricated
# metric percentile).
# --------------------------------------------------------------------------
INBOUND_OPS = [
    {"op": "getADPPRProvisionRequest", "weight": 20, "baseline_ms": 240, "endpoint": "adppr", "uri": "/api/auth/adppr"},
    {"op": "getStatus",                "weight": 26, "baseline_ms": 90,  "endpoint": "status", "uri": "/api/status"},
    {"op": "checkDeviceCard",          "weight": 14, "baseline_ms": 180, "endpoint": "checkDeviceCard", "uri": "/api/auth/checkDeviceCard"},
    {"op": "notifyProvisionResult",    "weight": 10, "baseline_ms": 150, "endpoint": "notify", "uri": "/api/notify"},
    {"op": "postControl_mercReads",    "weight": 8,  "baseline_ms": 120, "endpoint": "control", "uri": "/api/control"},
    {"op": "resume",                   "weight": 6,  "baseline_ms": 200, "endpoint": "resume", "uri": "/api/auth/resume"},
    {"op": "sendOTP",                  "weight": 5,  "baseline_ms": 260, "endpoint": "sendOTP", "uri": "/api/auth/sendOTP"},
    {"op": "createToken",              "weight": 7,  "baseline_ms": 320, "endpoint": "createToken", "uri": "/api/auth/createToken"},
    {"op": "getFundingAccountInfo",    "weight": 4,  "baseline_ms": 140, "endpoint": "fundingAccount", "uri": "/api/fundingAccount"},
]

# Operations that show up in the exceptions tables also need to exist as ops.
_EXTRA_OPS = {
    "networkCheckCard": {"baseline_ms": 210, "endpoint": "networkCheckCard", "uri": "/api/auth/networkCheckCard"},
    "linkAndProvision": {"baseline_ms": 300, "endpoint": "linkAndProvision", "uri": "/api/auth/linkAndProvision"},
}

# Outbound operations at the API gateway (OUTBOUND traffic panels).
OUTBOUND_OPS = [
    {"op": "doStandIn",           "weight": 8,  "baseline_ms": 180},
    {"op": "put_pending_commands", "weight": 14, "baseline_ms": 260},
    {"op": "submitCommand",       "weight": 20, "baseline_ms": 210},
]

# --------------------------------------------------------------------------
# Exception catalog. The (operation, statuscode, networksubstatuscode,
# statusmessage, mdeserrorcode) tuples and their weights reproduce the
# "Application Exceptions" tables in the screenshot - weights ARE the observed
# counts there, so the recreated table ranks the same way.
# --------------------------------------------------------------------------
ERROR_CATALOG = [
    {"op": "networkCheckCard", "statuscode": 48101, "netsub": "9007", "msg": "Par Ineligible",                    "mderr": "NET_RANGE_CHECK",                  "http": 400, "weight": 2195},
    {"op": "networkCheckCard", "statuscode": 48000, "netsub": "9006", "msg": "Duplicate Request",                 "mderr": "REPLAYED_TRAN_ATTEMPTING",         "http": 400, "weight": 928},
    {"op": "linkAndProvision", "statuscode": 48002, "netsub": "",     "msg": "Invalid Par",                       "mderr": "CVC_VERIFICATION",                 "http": 401, "weight": 685},
    {"op": "networkCheckCard", "statuscode": 48101, "netsub": "9007", "msg": "Par Ineligible",                    "mderr": "WRITE_LISTID_RANGE_CHECK",         "http": 400, "weight": 435},
    {"op": "getStatus",        "statuscode": 48411, "netsub": "",     "msg": "Invalid Digital Par",               "mderr": "WRITE_LISTID_RANGE_CHECK",         "http": 404, "weight": 378},
    {"op": "resume",           "statuscode": 48403, "netsub": "9007", "msg": "Invalid One Time Password Value",   "mderr": "INVALID_ACTIVATION_CODE_VALUE",    "http": 403, "weight": 262},
    {"op": "sendOTP",          "statuscode": 48421, "netsub": "9017", "msg": "OTP is Expired",                    "mderr": "EXPIRED_ACTIVATION_CODE_VALUE",    "http": 403, "weight": 175},
    {"op": "linkAndProvision", "statuscode": 48001, "netsub": "",     "msg": "Invalid Par",                       "mderr": "CAFB_CHECK",                       "http": 401, "weight": 108},
    {"op": "linkAndProvision", "statuscode": 50000, "netsub": "",     "msg": "Inner Unavailable",                 "mderr": "",                                 "http": 503, "weight": 71},
    {"op": "networkCheckCard", "statuscode": 48015, "netsub": "5021", "msg": "PAN Tap Cryptogram Invalid",        "mderr": "TOP_CRYPTOGRAM_VERIFICATION_FAILED", "http": 400, "weight": 34},
    # The dropdown in the troubleshooting board explicitly lists 50000 / 50001.
    {"op": "getADPPRProvisionRequest", "statuscode": 50001, "netsub": "", "msg": "Downstream Timeout",            "mderr": "",                                 "http": 500, "weight": 40},
]

# --------------------------------------------------------------------------
# PCF apps status table (MANDATORY PCF APPS). Reproduces the screenshot: STL
# side largely degraded (DOWN / red), KSC healthy (UP / green). instances come
# from the "number_of_instances" column.
# --------------------------------------------------------------------------
PCF_APPS = [
    {"cf_app_name": "sides-token-batch-service-prod",              "app_group": "MBOS_Token_Batch_Service",  "instances": 8,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-change-notification-batch",       "app_group": "MBOS_Token_Batch_Service",  "instances": 2,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-offboarding-batch-processor",           "app_group": "MBOS_Offboarding",          "instances": 1,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-offboarding-consumer",                  "app_group": "MBOS_Offboarding",          "instances": 1,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-config-open-api-message-processor-prod","app_group": "MBOS_Configuration",        "instances": 1,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-user-tdb-topic-consumer",               "app_group": "MBOS_Authentication",       "instances": 1,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-registration-service",            "app_group": "MBOS_Token_Service",        "instances": 16, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-account-maintenance-token-consumer",    "app_group": "MBOS_Token_Service",        "instances": 3,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-consumer-spring-boot",            "app_group": "MBOS_Token_Service",        "instances": 79, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-hard-delete-processor-prod",      "app_group": "MBOS_Token_Service",        "instances": 14, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-operation-event-consumer-prod",   "app_group": "MBOS_Token_Service_DNFR",   "instances": 6,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-security-counter-processor",      "app_group": "MBOS_Token_Security_Counter","instances": 1, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-funding-account-request-service",       "app_group": "MBOS_Token_Service",        "instances": 4,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-lifecycle-orchestrator",          "app_group": "MBOS_Token_Service",        "instances": 22, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-provisioning-callback-consumer",        "app_group": "MBOS_Token_Service",        "instances": 11, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-device-binding-service",               "app_group": "MBOS_Authentication",       "instances": 9,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-notification-dispatcher",         "app_group": "MBOS_Token_Service",        "instances": 5,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-metadata-sync-processor",         "app_group": "MBOS_Token_Service_DNFR",   "instances": 7,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-cardholder-consent-service",           "app_group": "MBOS_Configuration",        "instances": 3,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-audit-event-consumer",           "app_group": "MBOS_Token_Security_Counter","instances": 4, "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-mdes-eventbus-relay-prod",             "app_group": "MBOS_Configuration",        "instances": 6,  "ksc": "UP", "stl": "DOWN"},
    {"cf_app_name": "sides-token-suspension-processor",           "app_group": "MBOS_Token_Service",        "instances": 8,  "ksc": "UP", "stl": "DOWN"},
]

# Cross-site MDES Standalone Status grid (components x hosts). KSC green, STL red.
STANDALONE_COMPONENTS = [
    "BatchProcessor", "MbcToolsConsumerApplicationRunner", "SwitchingProcessorProcessor",
    "TokenEventDispatcher", "ProvisioningReconciler", "NotificationRelayProcessor",
    "CredentialSyncRunner",
]
STANDALONE_HOSTS = {
    "mcs2ksc02": "UP", "mcs2ksc03": "UP", "mcs2ksc04": "UP",
    "mcs2stl52": "DOWN", "mcs2stl53": "DOWN", "mcs2stl54": "DOWN",
}

# Token-resolution reference data (TUR_01 panel / Search_2).
TOKEN_RESOLUTION_SOURCES = ["ON_FILE", "NETWORK_LOOKUP", "ISSUER_PROVIDED", "CACHE"]
BINS = ["512345", "541234", "552011", "222300", "515676"]

_INDEX_TAGS = {
    "pcf": "dd_index:app_pcf",
    "nginx": "dd_index:app_apigw",
    "ept": "dd_index:ept_web",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _wchoice(items: List[Dict[str, Any]], key: str = "weight") -> Dict[str, Any]:
    return random.choices(items, weights=[i[key] for i in items], k=1)[0]


def _pick_site() -> str:
    return random.choices(list(SITES), weights=[s["weight"] for s in SITES.values()], k=1)[0]


def _rt(baseline_ms: int, spike: bool = False) -> int:
    """Per-event response time (ms), rounded - no spurious precision. Occasional
    KSC-style spikes reproduce the p90 blip in the screenshot."""
    val = random.gauss(baseline_ms, baseline_ms * 0.28)
    if spike:
        val *= random.uniform(4, 9)
    return max(5, round(val))


def _op_meta(op: str) -> Dict[str, Any]:
    for o in INBOUND_OPS:
        if o["op"] == op:
            return o
    extra = _EXTRA_OPS.get(op, {"baseline_ms": 200, "endpoint": op, "uri": f"/api/auth/{op}"})
    return {"op": op, "baseline_ms": extra["baseline_ms"], "endpoint": extra["endpoint"], "uri": extra["uri"]}


def _tags(site: str, source: str, extra: List[str] | None = None) -> str:
    base = [
        f"site:{site}", "env:demo", _INDEX_TAGS[source],
        f"cf_space_name:{SPACE}", "vertical:payments",
        "dd-demo-toolkit:true", "team:dd-demo-payments",
        "customer:mastercard", "program:apple-pay-mdes",
    ]
    if extra:
        base.extend(extra)
    return ",".join(base)


# --------------------------------------------------------------------------
# Log builders - one dict per log record, shaped for the v2 logs intake.
# --------------------------------------------------------------------------
def _apigw_log(site: str, op_meta: Dict[str, Any], destination: str, phase: str,
               corr_id: str, conv_id: str, device_id: str, http_status: int,
               rt_ms: int | None) -> Dict[str, Any]:
    gwuri = f"/spb/1/0/devices/{device_id}/{op_meta['endpoint']}"
    log = {
        "ddsource": "nginx",
        "service": "apigw",
        "hostname": SITES[site]["apigw_host"],
        "ddtags": _tags(site, "nginx", [f"operation:{op_meta['op']}"]),
        "message": f"{destination} {phase} {op_meta['op']} status={http_status} corr={corr_id[:8]}",
        "host": SITES[site]["apigw_host"],
        "gwrequesturi": gwuri,
        "uri": op_meta["uri"],
        "endpoint": op_meta["endpoint"],
        "gwhttpstatus": http_status,
        "gwdestinationtype": destination,       # INBOUND / OUTBOUND
        "operation": phase,                     # REQUEST / RESPONSE (per SPL eval)
        "op_name": op_meta["op"],               # provisioning op (clean facet for panels)
        "correlationid": corr_id,
        "conversationid": conv_id,
        "device_id": device_id,
        "site": site,
    }
    if rt_ms is not None:
        log["response_time_ms"] = rt_ms
    return log


def _pcf_final_log(site: str, op: str, corr_id: str, conv_id: str, device_id: str,
                   err: Dict[str, Any] | None, http_status: int, rt_ms: int) -> Dict[str, Any]:
    level = "INFO" if err is None else "WARN"
    msg = {
        "message": "Request Details. FINAL_LOG_STMT",
        "operation": op,
        "correlationid": corr_id,
        "conversationId": conv_id,
        "statuscode": (err["statuscode"] if err else 200),
        "statusmessage": (err["msg"] if err else "Success"),
        "mdeserrorcode": (err["mderr"] if err else ""),
        "networksubstatuscode": (err["netsub"] if err else ""),
        "level": level,
        "response_time_ms": rt_ms,
        "SEID": device_id,
    }
    return {
        "ddsource": "pcf",
        "service": APP,
        "status": "info" if err is None else "warn",
        "hostname": f"{site}-pcf-wallet-01",
        "ddtags": _tags(site, "pcf", [f"cf_app_name:{APP}", f"operation:{op}"]),
        "message": f"Request Details. FINAL_LOG_STMT op={op} status={msg['statuscode']}",
        "cf_app_name": APP,
        "cf_space_name": SPACE,
        "site": site,
        "msg": msg,
    }


def _pcf_error_event(site: str, op: str, corr_id: str, conv_id: str, err: Dict[str, Any]) -> Dict[str, Any]:
    xception = (
        f"com.mastercard.mdes.wallet.{err['mderr'] or 'DownstreamException'}: "
        f"{err['msg']} (statuscode={err['statuscode']})"
    )
    return {
        "ddsource": "pcf",
        "service": APP,
        "status": "error",
        "hostname": f"{site}-pcf-wallet-01",
        "ddtags": _tags(site, "pcf", [f"cf_app_name:{APP}", f"operation:{op}"]),
        "message": f"{err['msg']} op={op} corr={corr_id[:8]}",
        "cf_app_name": APP,
        "cf_space_name": SPACE,
        "site": site,
        "log": {"level": "Error"},
        "msg": {
            "message": err["msg"],
            "operation": op,
            "conversationId": conv_id,
            "correlationid": corr_id,
            "level": "Error",
            "xception": xception,
            "mdeserrorcode": err["mderr"],
            "statuscode": err["statuscode"],
        },
    }


def _token_resolution_log(site: str, conv_id: str, device_id: str) -> Dict[str, Any]:
    return {
        "ddsource": "pcf",
        "service": APP,
        "status": "info",
        "hostname": f"{site}-pcf-wallet-01",
        "ddtags": _tags(site, "pcf", [f"cf_app_name:{APP}", "operation:tokenResolution"]),
        "message": f"Token resolution conv={conv_id[:8]}",
        "cf_app_name": APP,
        "site": site,
        "msg": {
            "conversationId": conv_id,
            "TUR_01": f"TUR{random.randint(10**11, 10**12 - 1)}",
            "srcTokenUniqueReference": f"DSRC{random.randint(10**11, 10**12 - 1)}",
            "TokenResolutionSource": random.choice(TOKEN_RESOLUTION_SOURCES),
            "bin": random.choice(BINS),
            "systemUniqueId": device_id,
        },
    }


def _ept_web_log(site: str, conv_id: str, device_id: str) -> Dict[str, Any]:
    return {
        "ddsource": "ept",
        "service": "ept-web",
        "hostname": f"mes2{site}web01",
        "ddtags": _tags(site, "ept", ["source:outbound"]),
        "message": f"EPT outbound provisioning event conv={conv_id[:8]} device={device_id}",
        "site": site,
        "conversationid": conv_id,
        "device_id": device_id,
    }


# --------------------------------------------------------------------------
# Transaction - a correlated bundle of logs sharing corr/conv/device.
# --------------------------------------------------------------------------
def build_transaction(error_rate: float = 0.10, spike_rate: float = 0.01) -> List[Dict[str, Any]]:
    site = _pick_site()
    corr_id = str(uuid.uuid4())
    conv_id = uuid.uuid4().hex[:18]
    device_id = f"SE{random.randint(10**9, 10**10 - 1)}"
    is_error = random.random() < error_rate

    if is_error:
        err = _wchoice(ERROR_CATALOG)
        op = err["op"]
        http_status = err["http"]
    else:
        err = None
        op = _wchoice(INBOUND_OPS)["op"]
        http_status = 200

    om = _op_meta(op)
    spike = random.random() < spike_rate
    rt_ms = _rt(om["baseline_ms"], spike=spike)

    logs: List[Dict[str, Any]] = []
    # APIGW inbound request + response (the nginx access-log call trail).
    logs.append(_apigw_log(site, om, "INBOUND", "REQUEST", corr_id, conv_id, device_id, http_status, None))
    logs.append(_apigw_log(site, om, "INBOUND", "RESPONSE", corr_id, conv_id, device_id, http_status, rt_ms))
    # PCF FINAL_LOG_STMT (the operational + troubleshooting error table source).
    logs.append(_pcf_final_log(site, op, corr_id, conv_id, device_id, err, http_status, rt_ms))
    if err is not None:
        logs.append(_pcf_error_event(site, op, corr_id, conv_id, err))
    # Provisioning transactions also resolve a token + hit the EPT outbound tier.
    if op in ("getADPPRProvisionRequest", "createToken", "linkAndProvision", "networkCheckCard"):
        logs.append(_token_resolution_log(site, conv_id, device_id))
        logs.append(_ept_web_log(site, conv_id, device_id))
        # Outbound gateway leg (doStandIn / put_pending_commands / submitCommand).
        ob = _wchoice(OUTBOUND_OPS)
        ob_meta = {"op": ob["op"], "baseline_ms": ob["baseline_ms"], "endpoint": ob["op"], "uri": f"/out/{ob['op']}"}
        ob_status = http_status if is_error else 200
        logs.append(_apigw_log(site, ob_meta, "OUTBOUND", "REQUEST", corr_id, conv_id, device_id, ob_status, None))
        logs.append(_apigw_log(site, ob_meta, "OUTBOUND", "RESPONSE", corr_id, conv_id, device_id, ob_status,
                               _rt(ob["baseline_ms"], spike=spike)))
    return logs


def build_status_heartbeats() -> List[Dict[str, Any]]:
    """PCF app status + MDES standalone status heartbeats. Emitted every cycle so
    the status table / grid always reflect current UP/DOWN state."""
    out: List[Dict[str, Any]] = []
    for site in SITES:
        for app in PCF_APPS:
            status = app[site]
            out.append({
                "ddsource": "pcf",
                "service": APP,
                "status": "info" if status == "UP" else "error",
                "hostname": f"{site}-pcf-platform-01",
                "ddtags": _tags(site, "pcf", [f"cf_app_name:{app['cf_app_name']}", f"app_status:{status}"]),
                "message": f"PCF app health {app['cf_app_name']} site={site} status={status}",
                "site": site,
                "app": {
                    "cf_app_name": app["cf_app_name"],
                    "app_group": app["app_group"],
                    "status": status,
                    "up": 1 if status == "UP" else 0,
                    "instances": app["instances"] if status == "UP" else 0,
                },
            })
    for host, status in STANDALONE_HOSTS.items():
        site = "ksc" if "ksc" in host else "stl"
        for comp in STANDALONE_COMPONENTS:
            out.append({
                "ddsource": "pcf",
                "service": "mdes-standalone",
                "status": "info" if status == "UP" else "error",
                "hostname": host,
                "ddtags": _tags(site, "pcf", [f"component:{comp}", f"standalone_host:{host}", f"app_status:{status}"]),
                "message": f"MDES standalone {comp} on {host} status={status}",
                "site": site,
                "standalone": {"component": comp, "host": host, "status": status,
                               "up": 1 if status == "UP" else 0},
            })
    return out


def build_backlog_events() -> List[Dict[str, Any]]:
    """Provisioning backlog (TokenProfile_2xConsumer). KSC occasionally spikes a
    bar, STL stays near zero - matching the screenshot."""
    out: List[Dict[str, Any]] = []
    for site in SITES:
        if site == "ksc":
            depth = random.choice([0, 0, 0, 0, random.randint(80, 260)])
        else:
            depth = random.choice([0, 0, 0, 0, 0, random.randint(0, 5)])
        if depth <= 0:
            continue
        out.append({
            "ddsource": "pcf",
            "service": APP,
            "status": "warn",
            "hostname": f"{site}-pcf-wallet-01",
            "ddtags": _tags(site, "pcf", ["consumer:TokenProfile_2xConsumer"]),
            "message": f"Provisioning backlog TokenProfile_2xConsumer site={site} depth={depth}",
            "site": site,
            "msg": {"consumer": "TokenProfile_2xConsumer", "backlog_depth": depth},
        })
    return out


def build_cycle(transactions: int = 60, error_rate: float = 0.10) -> List[Dict[str, Any]]:
    """One emit cycle: a batch of correlated transactions + status heartbeats +
    backlog events."""
    logs: List[Dict[str, Any]] = []
    for _ in range(transactions):
        logs.extend(build_transaction(error_rate=error_rate))
    logs.extend(build_status_heartbeats())
    logs.extend(build_backlog_events())
    return logs


if __name__ == "__main__":  # quick local smoke: print one cycle's shape
    import json
    cycle = build_cycle(transactions=3)
    print(f"{len(cycle)} logs in a 3-transaction cycle")
    print(json.dumps(cycle[:6], indent=2))
