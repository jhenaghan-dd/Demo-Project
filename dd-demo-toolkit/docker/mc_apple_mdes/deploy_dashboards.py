"""Create / delete the two MDES Apple Pay dashboards.

Standalone deploy (this isn't a `verticals/` vertical, so `dd-demo setup` won't
pick it up). Reuses the toolkit's ``DatadogAPIClient`` to POST the dashboard
JSON directly. Both boards carry the ``[dd-demo-toolkit:payments]`` description
marker, so `dd-demo teardown --all-verticals` removes them like any other
toolkit dashboard.

Usage (wrapped by `make mc-apple-dashboards` under `op run`):
    python deploy_dashboards.py create
    python deploy_dashboards.py delete
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dd_demo_toolkit.utils.dd_api import DatadogAPIClient

import build_dashboards

DASH_DIR = Path(__file__).parent / "dashboards"
FILES = ["mdes_operational.json", "mdes_troubleshooting_logs.json"]


def _titles(payloads):
    return {p["title"] for p in payloads}


def _load_payloads():
    # Always regenerate from source so create reflects the latest schema.
    build_dashboards.main()
    return [json.loads((DASH_DIR / f).read_text()) for f in FILES]


def _delete_by_titles(client, titles):
    victims = [d for d in client.list_dashboards().get("dashboards", [])
               if d.get("title") in titles]
    for d in victims:
        client.delete_dashboard(d["id"])
        print(f"removed existing dashboard id={d['id']} ({d.get('title')})")
    return len(victims)


def create():
    client = DatadogAPIClient()
    payloads = _load_payloads()
    _delete_by_titles(client, _titles(payloads))  # idempotent re-deploys
    for payload in payloads:
        resp = client.create_dashboard(payload)
        url = resp.get("url", "")
        full = f"https://app.{client.site}{url}" if url else "(url not returned)"
        print(f"created '{payload['title']}'  to  {full}")


def delete():
    client = DatadogAPIClient()
    payloads = [json.loads((DASH_DIR / f).read_text()) for f in FILES] if all(
        (DASH_DIR / f).exists() for f in FILES) else []
    titles = _titles(payloads) if payloads else {
        "MDES Apple Pay Provisioning - Operational Dashboard",
        "Apple Trouble Shooting - Logs (MDES)",
    }
    if _delete_by_titles(client, titles) == 0:
        print("no matching dashboards to delete")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    {"create": create, "delete": delete}.get(action, create)()
