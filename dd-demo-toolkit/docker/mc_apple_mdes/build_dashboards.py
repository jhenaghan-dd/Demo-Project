"""Generate the two Datadog dashboard JSONs from the MDES log schema.

Both boards are built entirely on **log-based** queries (data_source: logs /
logs_stream), because the Splunk originals were SPL over log events - this is
the faithful recreation, and it lets the p90 panels compute a TRUE percentile
over the per-event ``@response_time_ms`` measure instead of a fabricated metric
percentile.

Run:  python build_dashboards.py   to  writes dashboards/*.json
"""
from __future__ import annotations

import json
from pathlib import Path

from event_model import STANDALONE_HOSTS

OUT = Path(__file__).parent / "dashboards"
OUT.mkdir(exist_ok=True)

APP = "mdes-mntbwltorc-wallet-api"
FINAL = f'service:{APP} @msg.message:"Request Details. FINAL_LOG_STMT"'
APIGW = "service:apigw"

# Datadog status-code palette for the HTTP-trend panels.
HTTP_COLORS = {
    "200": "green", "400": "orange", "401": "yellow", "403": "warm",
    "404": "purple", "500": "red", "503": "vivid_pink",
}


# --------------------------------------------------------------------------
# Widget helpers
# --------------------------------------------------------------------------
def _layout(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def note(content, x, y, w, h, bg="white", align="center", size="16"):
    return {
        "definition": {
            "type": "note", "content": content, "background_color": bg,
            "font_size": size, "text_align": align, "vertical_align": "center",
            "show_tick": False, "tick_pos": "50%", "tick_edge": "left",
            "has_padding": True,
        },
        "layout": _layout(x, y, w, h),
    }


def _logs_query(name, search, facet=None, aggr="count", metric=None, limit=10, order="desc"):
    q = {
        "data_source": "logs",
        "name": name,
        "indexes": ["*"],
        "search": {"query": search},
        "compute": {"aggregation": aggr},
    }
    if metric:
        q["compute"]["metric"] = metric
    if facet:
        q["group_by"] = [{
            "facet": facet, "limit": limit,
            "sort": {"aggregation": aggr, "order": order, **({"metric": metric} if metric else {})},
        }]
    return q


def logs_timeseries(title, x, y, w, h, search, facet=None, aggr="count", metric=None,
                    display="line", scale=None, limit=15):
    q = _logs_query("q", search, facet=facet, aggr=aggr, metric=metric, limit=limit)
    definition = {
        "title": title,
        "type": "timeseries",
        "requests": [{
            "response_format": "timeseries",
            "queries": [q],
            "formulas": [{"formula": "q"}],
            "display_type": display,
            "style": {"palette": "dog_classic", "line_type": "solid", "line_width": "normal"},
        }],
        "show_legend": True,
        "legend_layout": "auto",
        "legend_columns": ["avg", "max", "value"],
    }
    if scale:
        definition["yaxis"] = {"scale": scale, "include_zero": False}
    return {"definition": definition, "layout": _layout(x, y, w, h)}


def logs_table(title, x, y, w, h, columns, sort_index=0, count=100):
    """query_table: columns = list of (formula_alias, query_dict).
    Multiple queries to multiple columns (used for the KSC/STL pivots)."""
    queries = [c[1] for c in columns]
    formulas = [{"formula": c[1]["name"], "alias": c[0]} for c in columns]
    return {
        "definition": {
            "title": title,
            "type": "query_table",
            "requests": [{
                "response_format": "scalar",
                "queries": queries,
                "formulas": formulas,
                "sort": {"count": count, "order_by": [{"type": "formula", "index": sort_index, "order": "desc"}]},
            }],
        },
        "layout": _layout(x, y, w, h),
    }


def logs_list_stream(title, x, y, w, h, query_string, columns):
    return {
        "definition": {
            "title": title,
            "type": "list_stream",
            "requests": [{
                "response_format": "event_list",
                "columns": [{"field": f, "width": "auto"} for f in columns],
                "query": {
                    "data_source": "logs_stream",
                    "query_string": query_string,
                    "indexes": [],
                    "storage": "hot",
                },
            }],
        },
        "layout": _layout(x, y, w, h),
    }


def group(title, x, y, w, h, widgets, bg="vivid_blue"):
    return {
        "definition": {
            "title": title, "type": "group", "layout_type": "ordered",
            "background_color": bg, "widgets": widgets,
        },
        "layout": _layout(x, y, w, h),
    }


# --------------------------------------------------------------------------
# Table-column query builders (grouped by a facet, one column per site).
# --------------------------------------------------------------------------
def _table_query(name, search, group_facets, aggr="count", metric=None, limit=100, limits=None):
    # NOTE: Datadog rejects a query whose group-by dimensions can produce more
    # than 10,000 groups (the PRODUCT of the per-facet limits). For multi-column
    # tables, pass small per-facet `limits` on the deeper columns: the exception
    # tuples are correlated so each nesting level has few real children, and a
    # small limit there keeps the product low without dropping any real rows.
    per = limits if limits is not None else [limit] * len(group_facets)
    q = {
        "data_source": "logs", "name": name, "indexes": ["*"],
        "search": {"query": search},
        "compute": {"aggregation": aggr},
        "group_by": [{"facet": f, "limit": per[i], "sort": {"aggregation": "count", "order": "desc"}}
                     for i, f in enumerate(group_facets)],
    }
    if metric:
        q["compute"]["metric"] = metric
    return q


# ==========================================================================
# Dashboard A - Operational
# ==========================================================================
def build_operational():
    tvars = [
        {"name": "site", "prefix": "site", "available_values": ["stl", "ksc"], "default": "*"},
    ]
    widgets = []
    y = 0

    widgets.append(note(
        "## MDES Apple Pay Provisioning - Operational Dashboard\n"
        "Apple inbound, application, and outbound provisioning flow across the **STL** and **KSC** sites.",
        0, y, 12, 2, bg="gray", align="left"))
    y += 2

    # ---- Inbound at gateway (per site) ----
    for site in ("stl", "ksc"):
        sq = f"site:{site}"
        children = [
            logs_timeseries(f"Inbound Traffic Volume - {site.upper()} Gateway (by operation)",
                            0, 0, 6, 4,
                            f"{APIGW} @gwdestinationtype:INBOUND @operation:REQUEST {sq}",
                            facet="@op_name", display="line"),
            logs_timeseries(f"Inbound Response Time p90 (ms) - {site.upper()} Gateway",
                            6, 0, 6, 4,
                            f"{APIGW} @gwdestinationtype:INBOUND @operation:RESPONSE {sq}",
                            facet="@op_name", aggr="pc90", metric="@response_time_ms"),
            logs_timeseries(f"HTTP Response Trend - {site.upper()} Gateway (log scale)",
                            0, 4, 12, 3,
                            f"{APIGW} @gwdestinationtype:INBOUND @operation:RESPONSE {sq}",
                            facet="@gwhttpstatus", display="bars", scale="log"),
        ]
        widgets.append(group(f"Apple Inbound Metrics at API Gateway - {site.upper()}",
                             0, y, 12, 8, children,
                             bg="vivid_blue" if site == "stl" else "vivid_green"))
        y += 8

    # ---- Application tier ----
    app_children = []
    for i, site in enumerate(("stl", "ksc")):
        app_children.append(
            logs_timeseries(f"Application Traffic - {site.upper()} (by operation)",
                            i * 6, 0, 6, 4,
                            f"{FINAL} site:{site}", facet="@msg.operation"))
    for i, site in enumerate(("stl", "ksc")):
        app_children.append(
            logs_timeseries(f"Provisioning Backlog - {site.upper()} (TokenProfile_2xConsumer)",
                            i * 6, 4, 6, 3,
                            f"service:{APP} @msg.consumer:TokenProfile_2xConsumer site:{site}",
                            aggr="max", metric="@msg.backlog_depth", display="bars"))
    widgets.append(group("Metrics at Application", 0, y, 12, 8, app_children, bg="gray"))
    y += 8

    # ---- Application metrics: status tables + exceptions ----
    status_children = []
    # PCF apps pivot: rows = cf_app_name, cols = KSC / STL instance count.
    status_children.append(logs_table(
        "Mandatory PCF Apps - instances (0 = DOWN)", 0, 0, 6, 6,
        columns=[
            ("KSC", _table_query("ksc", "service:%s @app.cf_app_name:* site:ksc" % APP,
                                 ["@app.cf_app_name"], aggr="max", metric="@app.instances")),
            ("STL", _table_query("stl", "service:%s @app.cf_app_name:* site:stl" % APP,
                                 ["@app.cf_app_name"], aggr="max", metric="@app.instances")),
        ], sort_index=0))
    # MDES standalone grid: rows = component, cols = each host (1 = UP, 0 = DOWN).
    # Columns derive from STANDALONE_HOSTS so adding hosts auto-expands the grid.
    host_cols = []
    for host in STANDALONE_HOSTS:
        host_cols.append((host, _table_query(
            host.replace("mcs2", "h_"),
            f"service:mdes-standalone @standalone.host:{host}",
            ["@standalone.component"], aggr="max", metric="@standalone.up")))
    status_children.append(logs_table(
        "Cross-site MDES Standalone Status (1 = UP, 0 = DOWN)", 6, 0, 6, 6,
        columns=host_cols, sort_index=0))
    # Exceptions per site - all 5 columns from the Splunk original (operation,
    # statuscode, networksubstatuscode, statusmessage, mdeserrorcode). Per-facet
    # limits [8,8,4,4,4] give a group-product of 4096, under Datadog's 10k cap;
    # each nested level has few real children so no exception row is dropped.
    for i, site in enumerate(("stl", "ksc")):
        status_children.append(logs_table(
            f"Application Exceptions - {site.upper()}", i * 6, 6, 6, 6,
            columns=[("Count", _table_query(
                "c", f"{FINAL} -@msg.statuscode:200 site:{site}",
                ["@msg.operation", "@msg.statuscode", "@msg.networksubstatuscode",
                 "@msg.statusmessage", "@msg.mdeserrorcode"],
                limits=[8, 8, 4, 4, 4]))],
            sort_index=0))
    widgets.append(group("Application Metrics - PCF Status & Exceptions", 0, y, 12, 13,
                         status_children, bg="gray"))
    y += 13

    # ---- Outbound at gateway ----
    for site in ("stl", "ksc"):
        sq = f"site:{site}"
        children = [
            logs_timeseries(f"Outbound Traffic Volume - {site.upper()} Gateway (by operation)",
                            0, 0, 6, 4,
                            f"{APIGW} @gwdestinationtype:OUTBOUND @operation:REQUEST {sq}",
                            facet="@op_name"),
            logs_timeseries(f"Outbound Response Time p90 (ms) - {site.upper()} Gateway",
                            6, 0, 6, 4,
                            f"{APIGW} @gwdestinationtype:OUTBOUND @operation:RESPONSE {sq}",
                            facet="@op_name", aggr="pc90", metric="@response_time_ms"),
            logs_timeseries(f"Outbound HTTP Response Trend - {site.upper()} (log scale)",
                            0, 4, 12, 3,
                            f"{APIGW} @gwdestinationtype:OUTBOUND @operation:RESPONSE {sq}",
                            facet="@gwhttpstatus", display="bars", scale="log"),
        ]
        widgets.append(group(f"Apple Outbound Metrics at API Gateway - {site.upper()}",
                             0, y, 12, 8, children,
                             bg="vivid_blue" if site == "stl" else "vivid_green"))
        y += 8

    return {
        "title": "MDES Apple Pay Provisioning - Operational Dashboard",
        "description": "Operational view of Apple Pay (MDES) provisioning across STL/KSC. "
                       "Synthetic recreation of a Mastercard Splunk dashboard. [dd-demo-toolkit:payments]",
        "layout_type": "ordered",
        "template_variables": tvars,
        "widgets": widgets,
        "reflow_type": "fixed",
    }


# ==========================================================================
# Dashboard B - Troubleshooting (Logs)
# ==========================================================================
def build_troubleshooting():
    tvars = [
        {"name": "convid", "prefix": "@msg.conversationId", "available_values": [], "default": "*"},
        {"name": "corr_id", "prefix": "@msg.correlationid", "available_values": [], "default": "*"},
        {"name": "seid", "prefix": "@msg.SEID", "available_values": [], "default": "*"},
        {"name": "errorcode", "prefix": "@msg.statuscode", "available_values": ["50000", "50001", "48101", "48000", "48002"], "default": "*"},
    ]
    widgets = []
    y = 0
    widgets.append(note(
        "## Apple Trouble Shooting - Logs\n"
        "Pivot on **Conversation ID** (`$convid`), **Correlation ID** (`$corr_id`), **SEID** (`$seid`), or **Error Code** (`$errorcode`) "
        "using the template variables above; every panel filters to the selected transaction.",
        0, y, 12, 2, bg="gray", align="left"))
    y += 2

    # 1. Troubleshooting - Errors PCF (FINAL_LOG_STMT, errors). In Splunk this is
    # a raw "head 10" event listing, so it's a log stream, not an aggregation.
    widgets.append(logs_list_stream(
        "Troubleshooting - Errors PCF (FINAL_LOG_STMT)", 0, y, 12, 4,
        f'{FINAL} -@msg.statuscode:200 $errorcode $seid $convid',
        ["timestamp", "@msg.operation", "@msg.correlationid", "@msg.conversationId",
         "@msg.statuscode", "@msg.mdeserrorcode", "@msg.networksubstatuscode", "@msg.statusmessage"]))
    y += 4

    # 2. APIGW Call Trail for Correlation ID
    widgets.append(logs_list_stream(
        "APIGW Call Trail for Correlation ID $corr_id", 0, y, 12, 4,
        f"{APIGW} $corr_id",
        ["timestamp", "@operation", "@endpoint", "@gwrequesturi", "@correlationid", "@gwhttpstatus", "@device_id", "site"]))
    y += 4

    # 3. APIGW Call Trail for Conversation ID
    widgets.append(logs_list_stream(
        "APIGW Call Trail for Conversation ID $convid", 0, y, 12, 4,
        f"{APIGW} $convid",
        ["timestamp", "@operation", "@endpoint", "@gwrequesturi", "@correlationid", "@device_id", "@gwhttpstatus", "site"]))
    y += 4

    # 4. EPT Web logs for convid
    widgets.append(logs_list_stream(
        "EPT Web logs for $convid", 0, y, 6, 4,
        f"service:ept-web source:outbound $convid",
        ["timestamp", "host", "@conversationid", "@device_id", "message"]))
    # 5. PCF Error events for convid
    widgets.append(logs_list_stream(
        "PCF Error events for $convid", 6, y, 6, 4,
        f'service:{APP} status:error $convid',
        ["timestamp", "@msg.operation", "@msg.message", "@msg.xception", "@msg.level"]))
    y += 4

    # 6. Token resolution (Search_2)
    widgets.append(logs_list_stream(
        "Token Resolution (TUR_01) for $convid", 0, y, 12, 4,
        f'service:{APP} @msg.TUR_01:* $convid',
        ["timestamp", "@msg.TUR_01", "@msg.srcTokenUniqueReference", "@msg.TokenResolutionSource", "@msg.bin", "@msg.systemUniqueId"]))
    y += 4

    return {
        "title": "Apple Trouble Shooting - Logs (MDES)",
        "description": "Log drill-down for Apple Pay (MDES) provisioning: pivot by conversation/correlation/SEID. "
                       "Synthetic recreation of a Mastercard Splunk dashboard. [dd-demo-toolkit:payments]",
        "layout_type": "ordered",
        "template_variables": tvars,
        "widgets": widgets,
        "reflow_type": "fixed",
    }


def main():
    (OUT / "mdes_operational.json").write_text(json.dumps(build_operational(), indent=2))
    (OUT / "mdes_troubleshooting_logs.json").write_text(json.dumps(build_troubleshooting(), indent=2))
    print(f"wrote {OUT}/mdes_operational.json")
    print(f"wrote {OUT}/mdes_troubleshooting_logs.json")


if __name__ == "__main__":
    main()
