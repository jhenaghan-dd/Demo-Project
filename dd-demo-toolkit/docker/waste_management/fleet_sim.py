"""WasteManagement fleet-at-scale simulator — the movement + telemetry engine.

One process animates the entire fleet. Each truck is assigned a collection
route (a street-grid polyline generated from its metro's depot) and advances
along it every tick, generating realistic telemetry: speed, hopper load,
engine temperature, fuel, and a status (transit → collecting → returning →
dumping → idle). A thread-safe snapshot of every truck's current state feeds
two consumers:

  1. ``dd_emitter`` — turns each truck into a distinct Datadog *host* by
     submitting system.* + wm.truck.* metrics tagged ``host:wm-truck-NNNN``.
  2. ``server`` — serves the snapshot as JSON to the live Leaflet fleet map.

Route geometry is deterministic (seeded per fleet_routes.yaml) so the same
streets are drawn every run. Nothing here touches Datadog or the network —
this module is pure simulation so it stays trivially testable.
"""
from __future__ import annotations

import math
import os
import random
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

CONFIG_PATH = Path(os.getenv("FLEET_ROUTES", str(Path(__file__).parent / "fleet_routes.yaml")))

# Rough metres-per-degree at mid latitudes; good enough for a demo fleet and
# keeps the sim dependency-free (no geodesy library).
_M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in km between (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Route:
    route_id: str
    metro_id: str
    metro_name: str
    region: str
    waypoints: List[Tuple[float, float]]      # ordered (lat, lon) collection path
    depot: Tuple[float, float]
    landfill: Tuple[float, float]
    length_km: float

    def polyline(self) -> List[List[float]]:
        """[[lat, lon], ...] for the map to draw the route line."""
        return [[round(la, 6), round(lo, 6)] for la, lo in self.waypoints]


@dataclass
class Truck:
    truck_id: str            # host name, e.g. wm-truck-0042
    route: Route
    # Progress is a float index into the waypoint list (e.g. 3.4 = 40% from
    # waypoint 3 to 4). Direction flips at each end (collect out, return back).
    progress: float = 0.0
    direction: int = 1
    status: str = "transit"  # transit|collecting|returning|dumping|idle
    speed_mph: float = 0.0
    load_pct: float = 0.0
    engine_temp_f: float = 185.0
    fuel_pct: float = 100.0
    stops_served: int = 0
    fault: str = ""          # "", overheat, low_fuel, stuck
    lat: float = 0.0
    lon: float = 0.0
    _dump_ticks: int = 0

    def position(self) -> Tuple[float, float]:
        wp = self.route.waypoints
        i = int(self.progress)
        frac = self.progress - i
        if i >= len(wp) - 1:
            return wp[-1]
        (la1, lo1), (la2, lo2) = wp[i], wp[i + 1]
        return (la1 + (la2 - la1) * frac, lo1 + (lo2 - lo1) * frac)

    def to_public(self) -> Dict[str, Any]:
        """The shape the map + API consume (no private fields)."""
        return {
            "truck_id": self.truck_id,
            "metro": self.route.metro_id,
            "metro_name": self.route.metro_name,
            "region": self.route.region,
            "route_id": self.route.route_id,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "status": self.status,
            "speed_mph": round(self.speed_mph, 1),
            # Hopper fill is a coarse level — whole-percent is plenty; extra
            # decimals are just noise on the map and in the wm.truck.load_pct metric.
            "load_pct": round(self.load_pct),
            "engine_temp_f": round(self.engine_temp_f, 1),
            "fuel_pct": round(self.fuel_pct, 1),
            "stops_served": self.stops_served,
            "fault": self.fault,
        }


# --------------------------------------------------------------------------
# Route generation — street-grid random walk from the depot
# --------------------------------------------------------------------------
def _generate_route(rng: random.Random, metro: Dict[str, Any], route_ix: int,
                    n_waypoints: int = 14) -> Route:
    """Build a plausible collection route as a grid-aligned polyline.

    Starts near the metro centre and takes cardinal-ish steps (~350–650 m) so
    the drawn line reads like a truck working a street grid rather than a
    straight shot. Deterministic given the shared rng seed.
    """
    center = metro["center"]
    # Fan routes out around the metro centre so they don't overlap.
    angle0 = (2 * math.pi * route_ix) / max(1, route_ix + 1) + rng.uniform(0, math.pi)
    start_r = rng.uniform(0.01, 0.05)
    lat = center["lat"] + start_r * math.sin(angle0)
    lon = center["lon"] + start_r * math.cos(angle0)

    waypoints: List[Tuple[float, float]] = [(lat, lon)]
    # Bias the walk in a general heading so the route progresses outward.
    heading = rng.uniform(0, 2 * math.pi)
    for _ in range(n_waypoints - 1):
        # Snap each step toward a cardinal direction (street-grid feel).
        heading += rng.uniform(-0.9, 0.9)
        step_deg = rng.uniform(0.003, 0.006)
        # Quantise heading to 8 compass points.
        q = round(heading / (math.pi / 4)) * (math.pi / 4)
        lat += step_deg * math.sin(q)
        lon += step_deg * math.cos(q)
        waypoints.append((lat, lon))

    length_km = sum(
        _haversine_km(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1)
    )
    return Route(
        route_id=f"{metro['id']}-r{route_ix:02d}",
        metro_id=metro["id"],
        metro_name=metro["name"],
        region=metro["region"],
        waypoints=waypoints,
        depot=(metro["depot"]["lat"], metro["depot"]["lon"]),
        landfill=(metro["landfill"]["lat"], metro["landfill"]["lon"]),
        length_km=length_km,
    )


# --------------------------------------------------------------------------
# The fleet
# --------------------------------------------------------------------------
class Fleet:
    """Holds every truck + route and advances them on a background thread."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        self.cfg = yaml.safe_load(config_path.read_text())
        self.tel = self.cfg["telemetry"]
        fleet_cfg = self.cfg["fleet"]
        self.tick_seconds = float(fleet_cfg["tick_seconds"])
        self._rng = random.Random(fleet_cfg["seed"])
        self._lock = threading.Lock()
        self.routes: List[Route] = []
        self.trucks: List[Truck] = []
        self._build(fleet_cfg)
        self._tick_count = 0

    def _build(self, fleet_cfg: Dict[str, Any]) -> None:
        rpm = int(fleet_cfg["routes_per_metro"])
        tpr = int(fleet_cfg["trucks_per_route"])
        truck_seq = 0
        for metro in self.cfg["metros"]:
            for r in range(rpm):
                route = _generate_route(self._rng, metro, r)
                self.routes.append(route)
                for _ in range(tpr):
                    t = Truck(truck_id=f"wm-truck-{truck_seq:04d}", route=route)
                    # Spread trucks along the route so they don't stack up.
                    t.progress = self._rng.uniform(0, len(route.waypoints) - 1)
                    t.fuel_pct = self._rng.uniform(45, 100)
                    t.load_pct = self._rng.uniform(0, 70)
                    t.fault = self._roll_fault()
                    t.lat, t.lon = t.position()
                    self.trucks.append(t)
                    truck_seq += 1

    def _roll_fault(self) -> str:
        fr = self.tel["fault_rates"]
        roll = self._rng.random()
        if roll < fr["overheat"]:
            return "overheat"
        if roll < fr["overheat"] + fr["low_fuel"]:
            return "low_fuel"
        if roll < fr["overheat"] + fr["low_fuel"] + fr["stuck"]:
            return "stuck"
        return ""

    # -- movement -------------------------------------------------------
    def _advance(self, t: Truck) -> None:
        wp = t.route.waypoints
        last_idx = len(wp) - 1

        if t.fault == "stuck":
            t.status, t.speed_mph = "idle", 0.0
            t.engine_temp_f = max(178.0, t.engine_temp_f - 1.0)
            return

        # Dumping dwell at the far end of the route (the landfill turn).
        if t.status == "dumping":
            t._dump_ticks -= 1
            t.speed_mph = 0.0
            t.load_pct = max(0.0, t.load_pct - 12.0)  # hopper emptying
            if t._dump_ticks <= 0:
                t.status, t.direction = "returning", -1
            return

        # Pick a speed band by phase.
        collecting = t.direction == 1
        band = self.tel["speed_mph"]["collecting" if collecting else "transit"]
        t.speed_mph = self._rng.uniform(*band)
        t.status = "collecting" if collecting else "returning"

        # Convert speed to progress along the polyline this tick.
        km_this_tick = (t.speed_mph * 1.60934) * (self.tick_seconds / 3600.0)
        # Approximate segment length to translate km -> progress fraction.
        i = min(int(t.progress), last_idx - 1)
        seg_km = max(0.02, _haversine_km(wp[i], wp[i + 1]))
        t.progress += t.direction * (km_this_tick / seg_km)

        # Collection stops fill the hopper on the outbound leg.
        if collecting and self._rng.random() < 0.5:
            t.stops_served += 1
            t.load_pct = min(100.0, t.load_pct + self.tel["load_pct"]["fill_per_stop"])

        # Fuel drains with distance; engine temp drifts toward a load-scaled target.
        t.fuel_pct = max(0.0, t.fuel_pct - km_this_tick * self.tel["fuel_pct"]["drain_per_km"])
        self._update_engine_temp(t)

        # End-of-route handling: reached far end -> dump; reached depot -> reset.
        if t.progress >= last_idx:
            t.progress = float(last_idx)
            t.status = "dumping"
            t._dump_ticks = self._rng.randint(2, 4)
        elif t.progress <= 0:
            t.progress = 0.0
            t.direction = 1
            t.load_pct = 0.0
            if t.fuel_pct < 20:
                t.fuel_pct = 100.0  # refuelled at depot

        t.lat, t.lon = t.position()

    def _update_engine_temp(self, t: Truck) -> None:
        et = self.tel["engine_temp_f"]
        target = et["min"] + (et["max"] - et["min"]) * (0.35 + 0.6 * (t.load_pct / 100.0))
        if t.fault == "overheat":
            target = et["crit"] + self._rng.uniform(0, 6)
        # First-order approach to target with a little noise.
        t.engine_temp_f += (target - t.engine_temp_f) * 0.25 + self._rng.uniform(-1.5, 1.5)
        t.engine_temp_f = max(et["min"], min(et["max"], t.engine_temp_f))

    # -- public API -----------------------------------------------------
    def tick(self) -> None:
        with self._lock:
            for t in self.trucks:
                self._advance(t)
            self._tick_count += 1

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_public() for t in self.trucks]

    def routes_geojson(self) -> Dict[str, Any]:
        """Static route lines + depots/landfills for the map to draw once."""
        with self._lock:
            metros: Dict[str, Any] = {}
            for m in self.cfg["metros"]:
                metros[m["id"]] = {
                    "name": m["name"],
                    "center": [m["center"]["lat"], m["center"]["lon"]],
                    "depot": {"name": m["depot"]["name"],
                              "pos": [m["depot"]["lat"], m["depot"]["lon"]]},
                    "landfill": {"name": m["landfill"]["name"],
                                 "pos": [m["landfill"]["lat"], m["landfill"]["lon"]]},
                }
            return {
                "metros": metros,
                "routes": [
                    {"route_id": r.route_id, "metro": r.metro_id, "line": r.polyline()}
                    for r in self.routes
                ],
            }

    def run_forever(self) -> None:
        """Block, ticking on the configured cadence. Used by the container."""
        while True:
            start = time.monotonic()
            self.tick()
            time.sleep(max(0.0, self.tick_seconds - (time.monotonic() - start)))


if __name__ == "__main__":
    # Smoke test: build the fleet, run a few ticks, print a sample.
    import json

    fleet = Fleet()
    print(f"routes={len(fleet.routes)} trucks={len(fleet.trucks)}")
    for _ in range(3):
        fleet.tick()
    print(json.dumps(fleet.snapshot()[:3], indent=2))
