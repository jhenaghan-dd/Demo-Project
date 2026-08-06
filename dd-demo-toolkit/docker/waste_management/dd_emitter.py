"""WasteManagement fleet-at-scale → Datadog host emitter.

Turns every simulated truck into a distinct Datadog **host** object without a
single cloud instance. For each truck it submits, via POST /api/v2/series with
a ``resources: [{type: host}]`` entry:

  * ``system.cpu.user`` / ``system.load.1`` / ``system.mem.pct_usable`` —
    synthetic system signals so the truck looks alive in the Host Map (which
    colours hosts by exactly these), and
  * ``wm.truck.*`` — the domain telemetry (hopper load, engine temp, fuel,
    speed, stops) that drives the fleet dashboards and monitors.

On first sighting of a host it also sets **host-level tags** (region, metro,
route, instance-type, …) so the fleet groups and filters like real cloud
infrastructure. One process → hundreds of hosts, no AWS.

Reuses the toolkit's ``DatadogAPIClient`` (retries, site routing, auth) rather
than re-implementing HTTP. Credentials come from the process environment
(``DD_API_KEY`` / ``DD_APP_KEY`` / ``DD_SITE``), populated by ``op run`` in the
Make targets — see the repo secret-handling policy.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

from dd_demo_toolkit.utils.dd_api import DatadogAPIClient

log = logging.getLogger("wm-fleet-emitter")

_GAUGE = 3  # v2 series metric type enum

# How many series to send per request. 96 trucks × 8 metrics ≈ 768 series;
# chunking keeps each POST small and well under API limits at large fleets.
_CHUNK = 200

# Host-tag PUTs are one-per-host and sequential, so cap how many we set per
# emit cycle. The fleet gets fully tagged within a few cycles instead of
# blocking the whole first cycle on hundreds of serial API calls.
_HOST_TAGS_PER_CYCLE = 15

# Static per-host tags never change, so set them once per host (tracked here).
_ENV = os.getenv("DD_ENV", "demo")


def _truck_metric_tags(t: Dict[str, Any]) -> List[str]:
    tags = [
        "service:wm-fleet",
        f"env:{_ENV}",
        f"metro:{t['metro']}",
        f"region:{t['region']}",
        f"route:{t['route_id']}",
        f"status:{t['status']}",
        "dd-demo-toolkit:true",
        "vertical:waste_management",
    ]
    if t["fault"]:
        tags.append(f"fault:{t['fault']}")
    return tags


def _truck_host_tags(t: Dict[str, Any]) -> List[str]:
    # Host-object tags: what the Host Map groups/filters by. Model them on the
    # cloud-host tag keys (region, availability-zone, instance-type) so the
    # synthetic fleet reads like real infra.
    return [
        f"region:{t['region']}",
        f"availability-zone:{t['region']}-1",
        f"metro:{t['metro']}",
        f"route:{t['route_id']}",
        "instance-type:diesel-rolloff",
        "service:wm-fleet",
        "team:fleet-ops",
        "vertical:waste_management",
        "dd-demo-toolkit:true",
    ]


def _system_signals(t: Dict[str, Any]) -> Dict[str, float]:
    """Map truck telemetry to system.* so hosts look alive in the Host Map."""
    # Engine working harder (collecting/high load) => higher CPU/load proxy.
    duty = 0.15 + 0.7 * (t["load_pct"] / 100.0) + (0.15 if t["status"] == "collecting" else 0.0)
    duty = min(1.0, duty)
    return {
        "system.cpu.user": round(20 + duty * 70, 2),          # 20–90 %
        "system.load.1": round(0.3 + duty * 3.5, 2),          # 0.3–3.8
        "system.mem.pct_usable": round(max(5, 70 - t["load_pct"] * 0.4), 2),
    }


class FleetEmitter:
    def __init__(self, fleet, emit_every_ticks: int = 2):
        self.fleet = fleet
        self.emit_every_ticks = max(1, emit_every_ticks)
        self.client = DatadogAPIClient()  # raises if creds missing — fail loud
        self._tagged: set[str] = set()

    def _series_for(self, t: Dict[str, Any], ts: int) -> List[Dict[str, Any]]:
        tags = _truck_metric_tags(t)
        host = t["truck_id"]
        metrics = {
            **_system_signals(t),
            "wm.truck.load_pct": t["load_pct"],
            "wm.truck.engine_temp_f": t["engine_temp_f"],
            "wm.truck.fuel_pct": t["fuel_pct"],
            "wm.truck.speed_mph": t["speed_mph"],
            "wm.truck.stops_served": t["stops_served"],
        }
        return [
            {
                "metric": name,
                "type": _GAUGE,
                "points": [{"timestamp": ts, "value": float(value)}],
                "resources": [{"name": host, "type": "host"}],
                "tags": tags,
            }
            for name, value in metrics.items()
        ]

    def emit_once(self) -> int:
        """Submit one round of metrics for the whole fleet. Returns host count."""
        ts = int(time.time())
        trucks = self.fleet.snapshot()
        series: List[Dict[str, Any]] = []
        for t in trucks:
            series.extend(self._series_for(t, ts))

        for i in range(0, len(series), _CHUNK):
            try:
                self.client.submit_series(series[i:i + _CHUNK])
            except RuntimeError as e:
                log.warning("series submit failed (chunk %d): %s", i // _CHUNK, e)

        # Set host tags once per host (best-effort; hosts must exist first, so
        # this runs after the metric submit above on the first cycle).
        self._sync_host_tags(trucks)
        return len(trucks)

    def _sync_host_tags(self, trucks: List[Dict[str, Any]]) -> None:
        set_this_cycle = 0
        for t in trucks:
            host = t["truck_id"]
            if host in self._tagged:
                continue
            if set_this_cycle >= _HOST_TAGS_PER_CYCLE:
                break  # remaining hosts get tagged on later cycles
            try:
                self.client.update_host_tags(host, _truck_host_tags(t))
                self._tagged.add(host)
                set_this_cycle += 1
            except RuntimeError as e:
                # 404 = host not yet registered; retry next cycle.
                log.debug("host-tag set deferred for %s: %s", host, e)

    def run_forever(self) -> None:
        """Emit on the fleet's cadence × emit_every_ticks."""
        interval = self.fleet.tick_seconds * self.emit_every_ticks
        log.info("wm-fleet emitter: %d trucks, every %.0fs", len(self.fleet.trucks), interval)
        while True:
            start = time.monotonic()
            n = self.emit_once()
            log.info("emitted metrics for %d hosts (%d tagged)", n, len(self._tagged))
            time.sleep(max(0.0, interval - (time.monotonic() - start)))
