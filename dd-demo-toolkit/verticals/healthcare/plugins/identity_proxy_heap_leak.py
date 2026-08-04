"""
Identity Proxy Heap Leak — drives the identity-proxy-jvm container's
retained-allocation leak via the cascade-state shared volume.

The Java service polls /cascade-state/identity-proxy-phase.json every
second. When the phase is "ramp" or "sustained", it allocates 1 MB/s
of retained byte arrays until the heap saturates (~82% of -Xmx).
On "recovering" or "normal" it clears the leak and GCs.

Phases:
  1. normal   (idle, ~5 min countdown): baseline JVM metrics + Profiler data
  2. ramp     (3 min):  leak starts, GC overhead climbs, latency creeps up
  3. sustained (5 min): heap saturated, full GC storms, 500 errors at ~20%
  4. recovering (2 min): leak cleared, heap drains, latency returns to normal

Disjoint from wifi_cascade:
  - spatial:   targets identity-proxy service, not edge devices
  - namespace: JVM runtime metrics (jvm.heap_memory, jvm.gc.*), not hospital.*
  - incident_domain: identity-proxy-heap-leak vs care-experience
  - temporal:  fires ~5 min after start; wifi fires at ~75s
"""

import json
import logging
import os
import random
from typing import Any, List, Optional

from dd_demo_toolkit.simulator.plugins import IncidentPlugin

logger = logging.getLogger("identity_proxy_heap_leak")

_CASCADE_STATE_DIR = "/cascade-state"
_PHASE_FILE = os.path.join(_CASCADE_STATE_DIR, "identity-proxy-phase.json")


class IdentityProxyHeapLeak(IncidentPlugin):

    RAMP_TICKS = 12        # 3 min
    SUSTAINED_TICKS = 20   # 5 min — long enough for Watchdog baseline + anomaly
    RECOVERY_TICKS = 8     # 2 min
    EVENT_TICKS = RAMP_TICKS + SUSTAINED_TICKS + RECOVERY_TICKS

    def __init__(self):
        self._ticks_until_next = random.randint(18, 24)
        self._active_tick: Optional[int] = None
        logger.info(
            "Identity Proxy Heap Leak initialized. First incident in ~%d min",
            self._ticks_until_next * 15 // 60,
        )

    def get_incident_name(self) -> str:
        return "Identity Proxy: Memory Leak -> GC Overhead -> Heap Exhaustion"

    def reset(self) -> None:
        self._ticks_until_next = random.randint(18, 24)
        self._active_tick = None
        self._write_phase("normal", 0)

    def on_tick(self, tick_count: int, fleet: List[Any], engine: Any) -> None:
        if self._active_tick is None:
            if self._ticks_until_next > 0:
                self._ticks_until_next -= 1
                return
            self._active_tick = 0
            logger.info("IDENTITY PROXY HEAP LEAK STARTING")

        phase_tick = self._active_tick % self.EVENT_TICKS

        if phase_tick < self.RAMP_TICKS:
            phase = "ramp"
        elif phase_tick < self.RAMP_TICKS + self.SUSTAINED_TICKS:
            phase = "sustained"
        else:
            phase = "recovering"

        self._write_phase(phase, phase_tick)

        engine.incident_state["identity-proxy"] = {
            "phase": phase,
            "incident_domain": "identity-proxy-heap-leak",
        }

        self._active_tick += 1
        if phase_tick >= self.EVENT_TICKS - 1:
            self._active_tick = None
            self._ticks_until_next = random.randint(36, 48)
            self._write_phase("normal", 0)
            logger.info(
                "IDENTITY PROXY HEAP LEAK CYCLE COMPLETE. Next in ~%d min",
                self._ticks_until_next * 15 // 60,
            )

    def _write_phase(self, phase: str, tick: int) -> None:
        if not os.path.isdir(_CASCADE_STATE_DIR):
            return
        try:
            with open(_PHASE_FILE, "w") as f:
                json.dump({"phase": phase, "tick": tick}, f)
        except OSError:
            pass
