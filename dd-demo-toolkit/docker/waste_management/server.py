"""WasteManagement fleet map server — live positions API + static map.

Serves the Leaflet fleet map plus the JSON it polls:

  GET /                 -> the Leaflet fleet map (static/index.html)
  GET /api/routes       -> route polylines + depots/landfills (drawn once)
  GET /api/positions    -> live per-truck snapshot (polled by the map)
  GET /healthz          -> {"ok": true, "trucks": N}

Deliberately stdlib-only (http.server): the map view has zero pip
dependencies beyond the sim's PyYAML, so it runs identically on a laptop
(`python server.py`) and in the container.

The server does NOT own the fleet's tick loop — it reads a ``Fleet`` handed to
``serve()``. In the container, ``run.py`` builds one fleet and shares it
between this map server and the Datadog host emitter, so the dots on the map
and the hosts in Datadog are the *same* trucks. Run standalone (``__main__``)
it builds its own fleet and ticks it, for a quick map-only preview.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fleet_sim import Fleet

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wm-fleet-server")

STATIC_DIR = Path(__file__).parent / "static"
PORT = int(os.getenv("FLEET_MAP_PORT", "8088"))


def _make_handler(fleet: Fleet):
    """Build a request handler bound to a specific fleet instance."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: object, code: int = 200) -> None:
            self._send(code, json.dumps(payload).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._serve_static("index.html", "text/html; charset=utf-8")
            elif path == "/api/positions":
                self._json({"trucks": fleet.snapshot()})
            elif path == "/api/routes":
                self._json(fleet.routes_geojson())
            elif path == "/healthz":
                self._json({"ok": True, "trucks": len(fleet.trucks)})
            else:
                self._json({"error": "not found", "path": path}, code=404)

        def _serve_static(self, name: str, content_type: str) -> None:
            f = STATIC_DIR / name
            if not f.exists():
                self._json({"error": "missing static asset", "name": name}, code=404)
                return
            self._send(200, f.read_bytes(), content_type)

        def log_message(self, fmt: str, *args) -> None:  # quieter access log
            return

    return Handler


def serve(fleet: Fleet, port: int = PORT) -> None:
    """Blocking: serve the map + positions API for an already-ticking fleet."""
    log.info("wm-fleet map server on :%d — %d trucks, %d routes",
             port, len(fleet.trucks), len(fleet.routes))
    ThreadingHTTPServer(("0.0.0.0", port), _make_handler(fleet)).serve_forever()


def main() -> None:
    # Standalone map-only preview: own the fleet and tick it here.
    fleet = Fleet()
    threading.Thread(target=fleet.run_forever, daemon=True).start()
    serve(fleet)


if __name__ == "__main__":
    main()
