"""Create / delete the WasteManagement Fleet Operations dashboard.

Standalone deploy for the fleet-at-scale demo — the fleet isn't a `verticals/`
vertical, so it isn't picked up by `dd-demo setup`. This thin script reuses the
toolkit's ``DatadogAPIClient`` to POST the dashboard JSON directly. The
dashboard carries the ``[dd-demo-toolkit:`` description marker, so the standard
``dd-demo teardown --all-verticals`` sweep removes it like any other toolkit
dashboard.

Usage (wrapped by `make wm-fleet-dashboard` under `op run`):
    python deploy_dashboard.py create
    python deploy_dashboard.py delete
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dd_demo_toolkit.utils.dd_api import DatadogAPIClient

DASH = Path(__file__).parent / "dashboards" / "fleet_operations.json"
_TITLE = "WasteManagement — Fleet Operations (Fleet-at-Scale)"
_MAP_URL_SENTINEL = "__WM_FLEET_MAP_URL__"
# A running `wm-tunnel` (tunnel.sh) writes its live HTTPS URL here; used to
# embed the map iframe when WM_FLEET_MAP_URL isn't set explicitly.
_TUNNEL_URL_FILE = Path(__file__).resolve().parents[2] / ".secrets" / "wm_tunnel_url.txt"


def _map_url() -> str:
    """The HTTPS URL to embed, or "" for a native-only dashboard.

    Precedence: explicit WM_FLEET_MAP_URL env (used by `make wm-fleet-demo`),
    then a live tunnel URL written by the `wm-tunnel` process (the UI flow).
    """
    env = os.getenv("WM_FLEET_MAP_URL", "").strip()
    if env:
        return env
    try:
        return _TUNNEL_URL_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resolve_map_iframe(payload: dict) -> None:
    """Inject WM_FLEET_MAP_URL into the iframe widget, or drop it if unset.

    The iframe renders in the viewer's browser, so it needs an HTTPS URL that
    browser can reach — a Cloudflare quick tunnel to the local map server, or a
    hosted copy (see README). If the env var isn't set, we remove the iframe
    (and its header note) rather than ship a dashboard with a broken __sentinel__
    panel.
    """
    url = _map_url()
    widgets = payload.get("widgets", [])
    if url:
        for w in widgets:
            if w.get("definition", {}).get("url") == _MAP_URL_SENTINEL:
                w["definition"]["url"] = url
        print(f"embedding live map iframe -> {url}")
        return
    # No URL: strip the iframe and the "Live GPS fleet map — embedded" header.
    payload["widgets"] = [
        w for w in widgets
        if w.get("definition", {}).get("url") != _MAP_URL_SENTINEL
        and "Live GPS fleet map — embedded" not in w.get("definition", {}).get("content", "")
    ]
    print("No map URL — deploying the native dashboard without the embedded map panel.")
    print("  To embed the live map: start the wm-tunnel process (UI 'WasteManagement'")
    print("  tab, or `bash docker/waste_management/tunnel.sh`) then re-create the")
    print("  dashboard — or set WM_FLEET_MAP_URL=https://<host> explicitly.")


def _delete_existing(client: DatadogAPIClient) -> int:
    """Delete every dashboard with our exact title. Shared by create (for
    idempotency — the UI button is one click, easy to hit repeatedly) and
    delete. Returns how many were removed."""
    victims = [d for d in client.list_dashboards().get("dashboards", [])
               if d.get("title") == _TITLE]
    for d in victims:
        client.delete_dashboard(d["id"])
        print(f"removed existing dashboard id={d['id']}")
    return len(victims)


def create() -> None:
    client = DatadogAPIClient()
    payload = json.loads(DASH.read_text())
    _resolve_map_iframe(payload)
    # Idempotent: clear any prior same-title dashboard so repeated deploys
    # (e.g. clicking "Create dashboard" in the UI) don't accumulate duplicates.
    _delete_existing(client)
    resp = client.create_dashboard(payload)
    dash_id = resp.get("id", "")
    url = resp.get("url", "")
    site = client.site
    full = f"https://app.{site}{url}" if url else "(url not returned)"
    print(f"created dashboard id={dash_id}")
    print(f"open: {full}")


def delete() -> None:
    """Delete every dashboard whose title matches (idempotent re-runs)."""
    client = DatadogAPIClient()
    if _delete_existing(client) == 0:
        print("no matching dashboard to delete")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    {"create": create, "delete": delete}.get(action, create)()
