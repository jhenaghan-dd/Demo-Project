"""WasteManagement fleet-at-scale — combined entrypoint.

Builds ONE fleet and shares it between three cooperating loops:

  1. the movement/telemetry tick loop (fleet_sim),
  2. the Datadog host emitter (dd_emitter) — turns each truck into a host,
  3. the map server (server) — serves the live Leaflet fleet map.

Because all three read the same ``Fleet`` snapshot, a dot on the map and its
host in the Datadog Infrastructure list are guaranteed to be the same truck in
the same state. This is the container entrypoint (`make up-wm-fleet`); for a
map-only preview with no Datadog credentials, run ``server.py`` directly.

Set ``WM_FLEET_EMIT=false`` to run the map without emitting to Datadog (useful
for a laptop demo of just the visualization).
"""
from __future__ import annotations

import logging
import os
import threading

from fleet_sim import Fleet
from server import serve

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wm-fleet")


def main() -> None:
    fleet = Fleet()
    log.info("fleet built: %d trucks across %d routes", len(fleet.trucks), len(fleet.routes))

    # 1. Movement loop.
    threading.Thread(target=fleet.run_forever, daemon=True).start()

    # 2. Datadog host emitters (opt-out for credential-free map preview):
    #    trucks-as-hosts AND the backend-server (app-tier) hosts.
    if os.getenv("WM_FLEET_EMIT", "true").lower() != "false":
        try:
            from dd_emitter import FleetEmitter

            emit_every = int(fleet.cfg["fleet"].get("emit_every_ticks", 2))
            emitter = FleetEmitter(fleet, emit_every_ticks=emit_every)
            threading.Thread(target=emitter.run_forever, daemon=True).start()
            log.info("truck host emitter started")
        except Exception as e:  # missing creds shouldn't kill the map
            log.warning("truck host emitter disabled: %s", e)

        # Backend-server hosts (opt out with WM_EMIT_SERVERS=false).
        if os.getenv("WM_EMIT_SERVERS", "true").lower() != "false":
            try:
                from backend_servers import BackendServerEmitter

                servers = BackendServerEmitter(emit_interval_sec=fleet.tick_seconds * 2)
                threading.Thread(target=servers.run_forever, daemon=True).start()
                log.info("backend-server host emitter started (%d servers)", len(servers.hosts))
            except Exception as e:
                log.warning("backend-server emitter disabled: %s", e)
    else:
        log.info("WM_FLEET_EMIT=false — map only, not emitting to Datadog")

    # 3. Map server (blocking).
    serve(fleet)


if __name__ == "__main__":
    main()
