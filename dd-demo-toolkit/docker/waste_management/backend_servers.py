"""WM backend-server host emitter — the app tier as Datadog hosts.

Companion to dd_emitter (trucks-as-hosts). Mints the WM backend SERVERS as
distinct Datadog host objects via the same agentless path (POST /api/v2/series
with a ``resources:[{type:host}]`` entry) — no real servers, no Agent. So the
Infrastructure Host Map shows the WM app tier (ops-agent / portal / gateway /
route-opt / billing / data stores) running the WM services, right alongside the
truck fleet.

Each server host emits:
  * ``system.cpu.user`` / ``system.load.1`` / ``system.mem.pct_usable`` /
    ``system.disk.in_use`` — so it looks like a real server in the Host Map, and
  * ``wm.service.requests_per_s`` / ``wm.service.latency_ms`` /
    ``wm.service.error_rate_pct`` — light per-service app signals.

Host tags model cloud infra (``service``, ``role``, ``region``,
``availability-zone``, ``instance-type``, ``cloud_provider``) so the servers
group/filter like real EC2 hosts and correlate with the APM ``service`` the
vertical simulator emits. Scale replicas by editing ``SERVERS`` below.
"""
from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List

from dd_demo_toolkit.utils.dd_api import DatadogAPIClient

log = logging.getLogger("wm-backend-servers")

_GAUGE = 3
_CHUNK = 200
_HOST_TAGS_PER_CYCLE = 15
_ENV = os.getenv("DD_ENV", "prod")

# Backend topology: (service, host_prefix, role, replicas, region, instance_type).
# Per-role CPU/mem duty baselines give each tier a distinct, realistic profile.
SERVERS = [
    {"service": "wm-ops-agent", "prefix": "wm-ops-agent", "role": "agent", "replicas": 3,
     "region": "us-east-1", "instance_type": "m6i.xlarge", "cpu": (35, 75), "mem": (45, 70)},
    {"service": "my-wm-portal", "prefix": "my-wm-portal", "role": "frontend", "replicas": 3,
     "region": "us-east-1", "instance_type": "c6i.large", "cpu": (20, 55), "mem": (30, 55)},
    {"service": "route-optimization-api", "prefix": "route-opt", "role": "api", "replicas": 2,
     "region": "us-east-1", "instance_type": "c6i.xlarge", "cpu": (40, 85), "mem": (35, 60)},
    {"service": "ai-gateway-policy-enforcer", "prefix": "wm-ai-gw", "role": "gateway", "replicas": 2,
     "region": "us-east-1", "instance_type": "c6i.large", "cpu": (15, 45), "mem": (25, 45)},
    {"service": "billing-api", "prefix": "wm-billing", "role": "api", "replicas": 2,
     "region": "us-west-2", "instance_type": "m6i.large", "cpu": (18, 50), "mem": (35, 60)},
    {"service": "wm-postgres", "prefix": "wm-postgres", "role": "database", "replicas": 2,
     "region": "us-east-1", "instance_type": "r6i.xlarge", "cpu": (20, 55), "mem": (55, 85)},
    {"service": "wm-redis", "prefix": "wm-redis", "role": "cache", "replicas": 1,
     "region": "us-east-1", "instance_type": "r6i.large", "cpu": (10, 35), "mem": (40, 70)},
]


def _build_hosts() -> List[Dict[str, Any]]:
    hosts: List[Dict[str, Any]] = []
    for spec in SERVERS:
        for i in range(1, int(spec["replicas"]) + 1):
            hosts.append({
                "host": f"{spec['prefix']}-{i:02d}",
                "service": spec["service"],
                "role": spec["role"],
                "region": spec["region"],
                "instance_type": spec["instance_type"],
                "az": f"{spec['region']}{random.choice('abc')}",
                "cpu_band": spec["cpu"],
                "mem_band": spec["mem"],
            })
    return hosts


def _metric_tags(h: Dict[str, Any]) -> List[str]:
    return [
        f"service:{h['service']}", f"role:{h['role']}", f"region:{h['region']}",
        f"env:{_ENV}", "tier:backend", "dd-demo-toolkit:true", "vertical:waste_management",
    ]


def _host_tags(h: Dict[str, Any]) -> List[str]:
    # Cloud-host-shaped tags so the servers group/filter like real EC2 infra.
    return [
        f"service:{h['service']}", f"role:{h['role']}", f"region:{h['region']}",
        f"availability-zone:{h['az']}", f"instance-type:{h['instance_type']}",
        "cloud_provider:aws", "tier:backend", f"env:{_ENV}",
        "team:ai-platform", "vertical:waste_management", "dd-demo-toolkit:true",
    ]


class BackendServerEmitter:
    def __init__(self, emit_interval_sec: float = 15.0):
        self.interval = max(5.0, emit_interval_sec)
        self.hosts = _build_hosts()
        self.client = DatadogAPIClient()  # raises if creds missing — fail loud
        self._tagged: set[str] = set()

    def _series_for(self, h: Dict[str, Any], ts: int) -> List[Dict[str, Any]]:
        cpu = round(random.uniform(*h["cpu_band"]), 1)
        mem = round(random.uniform(*h["mem_band"]), 1)
        metrics = {
            "system.cpu.user": cpu,
            "system.load.1": round(cpu / 100.0 * random.uniform(2.5, 4.5), 2),
            "system.mem.pct_usable": round(100 - mem, 1),
            "system.disk.in_use": round(random.uniform(0.35, 0.72), 3),
            "wm.service.requests_per_s": round(random.uniform(20, 240), 1),
            "wm.service.latency_ms": round(random.uniform(20, 180), 1),
            "wm.service.error_rate_pct": round(random.uniform(0.0, 1.2), 2),
        }
        tags = _metric_tags(h)
        return [{
            "metric": name, "type": _GAUGE,
            "points": [{"timestamp": ts, "value": float(v)}],
            "resources": [{"name": h["host"], "type": "host"}],
            "tags": tags,
        } for name, v in metrics.items()]

    def emit_once(self) -> int:
        ts = int(time.time())
        series: List[Dict[str, Any]] = []
        for h in self.hosts:
            series.extend(self._series_for(h, ts))
        for i in range(0, len(series), _CHUNK):
            try:
                self.client.submit_series(series[i:i + _CHUNK])
            except RuntimeError as e:
                log.warning("server series submit failed (chunk %d): %s", i // _CHUNK, e)
        self._sync_host_tags()
        return len(self.hosts)

    def _sync_host_tags(self) -> None:
        set_this_cycle = 0
        for h in self.hosts:
            if h["host"] in self._tagged:
                continue
            if set_this_cycle >= _HOST_TAGS_PER_CYCLE:
                break
            try:
                self.client.update_host_tags(h["host"], _host_tags(h))
                self._tagged.add(h["host"])
                set_this_cycle += 1
            except RuntimeError as e:
                log.debug("host-tag set deferred for %s: %s", h["host"], e)

    def run_forever(self) -> None:
        log.info("wm-backend-servers emitter: %d server hosts, every %.0fs",
                 len(self.hosts), self.interval)
        while True:
            start = time.monotonic()
            n = self.emit_once()
            log.info("emitted metrics for %d backend-server hosts (%d tagged)", n, len(self._tagged))
            time.sleep(max(0.0, self.interval - (time.monotonic() - start)))
