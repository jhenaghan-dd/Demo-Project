"""
Agribusiness — Cross-Cutting Data-Platform Cascade (flagship: Bunge).

THE demo centerpiece and the AIOps proof point. Models the unique cross-cutting
risk from the briefing: the GCP Bunge Data Platform feeds every revenue app, so
when its CME market-data feed goes stale, FRM pricing degrades and every app
prices off bad data at once — a SILENT failure with no infra alert today.

What the cascade drives (three coupled layers — this is the data->app->revenue
correlation Watchdog/Bits surface, and the wedge vs an APM-only AI):

  1. Data platform (root, DEVICE metrics) — agri.dataplatform.* on the GCP
     pipelines: pricing_feed_age_sec, pipeline_freshness_sec, error_rate, records.
  2. FRM pricing (DEVICE metrics) — agri.pricing.* on the pricing engines:
     stale_quote_pct, quote_latency_ms, error_rate.
  3. Revenue apps (APPLICATION metrics, via incident_state["app_impact"]) —
     agri.app.errors_total / agri.app.latency_ms for frm-pricing-platform,
     bunge-mobile-bff, bungeag-web, mybunge-portal, bungeservices-portal. The
     engine reads app_impact in _generate_service_trace and amplifies each
     service's trace error-rate + latency, so the app-error/latency monitors and
     SLOs actually move during the cascade (not just the device tiers).

Site / network / SAP / Oracle / host namespaces are deliberately LEFT to their
normal random-walk so the RCA notebook's "rule out the network / DB / SAP" step
is honest and the AI can isolate the data platform as the leading indicator.

ServiceNow auto-remediation (SIMULATED close-loop) — Eduardo's #1 ask. This env
has no live ServiceNow integration, so the loop is imitated: the plugin drives
the agri.itsm.* gauges (auto-opened / auto-closed / open / enriched / MTTR /
noise-reduction / alerts-suppressed) and writes simulated ServiceNow ticket logs
onto the bunge-data-platform service — auto-open when the customer-facing symptom
appears (entering 'degraded'), auto-resolve at the end of recovery. Feeds the
"AIOps — ServiceNow Auto-Remediation" dashboard, the close-loop notebook, and
workflows.yaml.

Narrative (matches the agribusiness dashboards, monitors, notebooks):

  Phase 1 ramp_up (8 ticks ~2m):
      The CME pricing feed ages — agri.dataplatform.pricing_feed_age_sec drifts
      from ~6s (fresh) toward ~120s; pipeline freshness slips; throughput dips.
      FRM pricing + the apps are NOT yet impacted — the dangerous, silent window.
  Phase 2 degraded (10 ticks ~2.5m):
      Feed stale (150-260s); pipeline error rate climbs. FRM reacts —
      stale-quote % climbs toward ~7%. Revenue apps begin to error/slow.
      ServiceNow incident AUTO-OPENS here (first customer-facing symptom).
  Phase 3 outage (12 ticks ~3m):
      Peak. Feed 300-500s stale, stale-quote % ~8-13%. Every app consuming the
      feed errors + slows in unison (see the APM dependency map + app monitors).
  Phase 4 recovering (10 ticks ~2.5m):
      Feed refreshes — feed age drops first, then stale-quote %, then app
      errors/latency normalize. ServiceNow incident AUTO-RESOLVES at the end.

4-axis disjointness (currently the only agribusiness plugin; documented so
future plugins stay disjoint per CLAUDE.md / STYLE_GUIDE §9.3):
  1. Spatial    — production environment, the (global) data-platform + FRM
                  pricing + ServiceNow-connector fleet. A future plugin should
                  pick a different environment/region or device set.
  2. Namespace  — only agri.dataplatform.*, agri.pricing.*, agri.itsm.*, and
                  the app_impact multipliers for the 5 revenue services.
                  agri.site.*, agri.network.*, agri.sap*.*, agri.db.*,
                  agri.host.* are untouched (keeps the "rule out" RCA clean).
  3. Incident-domain — engine.incident_state key 'data_platform_cascade',
                  incident_domain=data-platform-freshness (matches the monitors).
  4. Temporal   — first fires ~15 min after start; re-fires ~15 min after the
                  previous incident completes (see FIRST_FIRE_TICKS / GAP_TICKS).
"""

import logging
import random
from typing import Any, List, Optional

from dd_demo_toolkit.simulator.plugins import IncidentPlugin

logger = logging.getLogger("data_platform_cascade")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _drift(value: float, magnitude: float = 1.0, bias: float = 0.0) -> float:
    return value + random.gauss(bias, magnitude)


class DataPlatformCascade(IncidentPlugin):
    """Cross-cutting: stale CME feed -> FRM mispricing -> revenue-app impact,
    with a simulated ServiceNow auto-remediation close-loop."""

    RAMP_TICKS = 8
    DEGRADED_TICKS = 10
    OUTAGE_TICKS = 12
    RECOVERY_TICKS = 10
    EVENT_TICKS = RAMP_TICKS + DEGRADED_TICKS + OUTAGE_TICKS + RECOVERY_TICKS

    # Cadence (15s/tick). Surfaces ~15 min after start and recurs ~15 min after
    # each incident completes — matching how the other verticals pace. Tune
    # these two ranges to change the recurrence; everything else follows.
    FIRST_FIRE_TICKS = (56, 64)   # ~14-16 min
    GAP_TICKS = (56, 64)          # ~14-16 min idle between incidents

    INCIDENT_ENV = "production"

    # Real metric names registered by the engine (verticals/agribusiness/config.yaml).
    DP_FEED_AGE = "agri.dataplatform.pricing_feed_age_sec"
    DP_FRESHNESS = "agri.dataplatform.pipeline_freshness_sec"
    DP_ERR = "agri.dataplatform.pipeline_error_rate"
    DP_RECORDS = "agri.dataplatform.records_processed_per_sec"

    PR_STALE = "agri.pricing.stale_quote_pct"
    PR_LAT = "agri.pricing.quote_latency_ms"
    PR_ERR = "agri.pricing.error_rate"

    # agri.itsm.* — simulated ServiceNow connector gauges.
    ITSM_OPEN = "agri.itsm.incidents_open"
    ITSM_OPENED = "agri.itsm.incidents_auto_opened"
    ITSM_CLOSED = "agri.itsm.incidents_auto_closed"
    ITSM_ENRICHED = "agri.itsm.incidents_enriched"
    ITSM_SUPPRESSED = "agri.itsm.alerts_suppressed"
    ITSM_NOISE = "agri.itsm.noise_reduction_pct"
    ITSM_MTTR = "agri.itsm.mttr_minutes"
    ITSM_CLOSE_RATE = "agri.itsm.auto_close_rate_pct"

    # Per-service application impact at PEAK (intensity 1.0). The engine
    # (_generate_service_trace -> _service_incident_multipliers) multiplies each
    # service's trace error-rate and latency by these, scaled by phase intensity.
    APP_IMPACT_PEAK = {
        "frm-pricing-platform": {"error_mult": 9.0, "latency_mult": 2.8},
        "bunge-mobile-bff":     {"error_mult": 12.0, "latency_mult": 1.8},
        "bungeag-web":          {"error_mult": 7.0, "latency_mult": 1.6},
        "mybunge-portal":       {"error_mult": 5.0, "latency_mult": 1.5},
        "bungeservices-portal": {"error_mult": 5.0, "latency_mult": 1.5},
    }

    # Clean baselines held during 'normal' so the cascade reads as an obvious
    # anomaly (mirrors the finance/BD plugin pattern).
    BASE_FEED_AGE = 6.0
    BASE_FRESHNESS = 60.0
    BASE_DP_ERR = 0.003
    BASE_RECORDS = 3500.0
    BASE_STALE = 0.5
    BASE_LAT = 80.0
    BASE_PR_ERR = 0.003

    def __init__(self) -> None:
        self._ticks_until_next = random.randint(*self.FIRST_FIRE_TICKS)
        self._active_tick: Optional[int] = None
        self._pipelines: List[Any] = []
        self._pricers: List[Any] = []
        self._itsm: List[Any] = []
        # ServiceNow close-loop tallies (simulated).
        self._inc_opened = 0
        self._inc_closed = 0
        self._inc_enriched = 0
        self._cur_inc_id: Optional[str] = None
        self._cur_mttr = 12.0
        self._prev_phase = "normal"
        logger.info(
            "Data-Platform Cascade initialized. First incident in ~%d min",
            self._ticks_until_next * 15 // 60,
        )

    def get_incident_name(self) -> str:
        return ("Cross-Cutting Data-Platform Cascade: Stale CME Feed -> FRM "
                "Mispricing -> Revenue-App Impact")

    def reset(self) -> None:
        self._ticks_until_next = random.randint(*self.FIRST_FIRE_TICKS)
        self._active_tick = None
        self._pipelines = []
        self._pricers = []
        self._itsm = []
        self._inc_opened = 0
        self._inc_closed = 0
        self._inc_enriched = 0
        self._cur_inc_id = None
        self._cur_mttr = 12.0
        self._prev_phase = "normal"

    # ------------------------------------------------------------------ tick
    def on_tick(self, tick_count: int, fleet: List[Any], engine: Any) -> None:
        if not self._pipelines and not self._pricers:
            for d in fleet:
                if self._device_location(d, "environment") != self.INCIDENT_ENV:
                    continue
                dtype = self._device_type(d)
                if dtype == "data_pipeline":
                    self._pipelines.append(d)
                elif dtype == "pricing_engine":
                    self._pricers.append(d)
                elif dtype == "servicenow_connector":
                    self._itsm.append(d)
            if self._pipelines or self._pricers:
                logger.info("Indexed %d data pipelines, %d pricing engines, "
                            "%d servicenow connectors (production)",
                            len(self._pipelines), len(self._pricers), len(self._itsm))

        self._advance_clock()
        phase, phase_tick = self._current_phase()
        intensity = self._phase_intensity(phase, phase_tick)

        # --- ServiceNow close-loop transitions (simulated) ---
        open_log = self._maybe_auto_open(phase)
        close_log = self._maybe_auto_close(phase, phase_tick)

        if hasattr(engine, "incident_state"):
            if phase == "normal":
                engine.incident_state.pop("data_platform_cascade", None)
            else:
                entry = {
                    "phase": phase,
                    "phase_tick": phase_tick,
                    "incident_domain": "data-platform-freshness",
                    "signal_chain_root": "stale-cme-pricing-feed",
                    "environment": self.INCIDENT_ENV,
                }
                app_impact = self._app_impact(intensity)
                if app_impact:
                    entry["app_impact"] = app_impact
                tx_logs = [log for log in (open_log, close_log) if log]
                if tx_logs:
                    entry["tx_logs"] = tx_logs
                engine.incident_state["data_platform_cascade"] = entry

        self._apply(phase, phase_tick)
        self._drive_itsm(intensity)
        self._prev_phase = phase
        if phase != "normal":
            logger.info("DATA-PLATFORM CASCADE [%s t=%d] pipelines=%d pricers=%d intensity=%.2f",
                        phase, phase_tick, len(self._pipelines), len(self._pricers), intensity)

    # -------------------------------------------------- device shape helpers
    def _device_type(self, device: Any) -> Optional[str]:
        return getattr(device, "type", None) or (
            device.get("device_type") if isinstance(device, dict) else None
        )

    def _device_location(self, device: Any, key: str) -> Optional[str]:
        loc = getattr(device, "location", None)
        if loc is None and isinstance(device, dict):
            loc = device
        if not isinstance(loc, dict):
            return None
        return loc.get(key)

    def _set(self, device: Any, metric: str, value: float) -> None:
        state = getattr(device, "state", None)
        if state is None and isinstance(device, dict):
            state = device.setdefault("state", {})
        if state is not None:
            state[metric] = value

    # ----------------------------------------------------------- phase/clock
    def _current_phase(self) -> tuple:
        if self._active_tick is None:
            return ("normal", 0)
        t = self._active_tick
        a = self.RAMP_TICKS
        b = a + self.DEGRADED_TICKS
        c = b + self.OUTAGE_TICKS
        d = c + self.RECOVERY_TICKS
        if t < a:
            return ("ramp_up", t)
        if t < b:
            return ("degraded", t - a)
        if t < c:
            return ("outage", t - b)
        if t < d:
            return ("recovering", t - c)
        return ("normal", 0)

    def _advance_clock(self) -> None:
        if self._active_tick is not None:
            self._active_tick += 1
            if self._active_tick >= self.EVENT_TICKS:
                self._active_tick = None
                self._ticks_until_next = random.randint(*self.GAP_TICKS)
                logger.info("Data-platform cascade complete. Next in ~%d min",
                            self._ticks_until_next * 15 // 60)
        else:
            self._ticks_until_next -= 1
            if self._ticks_until_next <= 0:
                self._active_tick = 0
                logger.info("DATA-PLATFORM CASCADE STARTING (stale CME feed)")

    def _interp(self, lo: float, hi: float, progress: float) -> float:
        return lo + (hi - lo) * progress

    # ---------------------------------------------------------- app impact
    def _phase_intensity(self, phase: str, t: int) -> float:
        """0..1 severity used to scale app-impact + ITSM signals. Apps stay
        clean through ramp_up (the silent window); impact emerges in degraded,
        peaks in outage, and decays through recovery."""
        if phase == "degraded":
            return 0.3 + 0.4 * ((t + 1) / self.DEGRADED_TICKS)   # 0.3 -> 0.7
        if phase == "outage":
            return 0.8 + 0.2 * ((t + 1) / self.OUTAGE_TICKS)     # 0.8 -> 1.0
        if phase == "recovering":
            return max(0.0, 0.6 * (1 - (t + 1) / self.RECOVERY_TICKS))  # 0.6 -> 0
        return 0.0  # normal, ramp_up

    def _app_impact(self, intensity: float) -> dict:
        if intensity <= 0:
            return {}
        return {
            svc: {
                "error_mult": 1.0 + (peak["error_mult"] - 1.0) * intensity,
                "latency_mult": 1.0 + (peak["latency_mult"] - 1.0) * intensity,
            }
            for svc, peak in self.APP_IMPACT_PEAK.items()
        }

    # -------------------------------------------------- servicenow close-loop
    def _maybe_auto_open(self, phase: str) -> Optional[dict]:
        """Auto-open a (simulated) ServiceNow incident the moment the
        customer-facing symptom appears — i.e. entering the 'degraded' phase."""
        if phase == "degraded" and self._prev_phase != "degraded":
            self._inc_opened += 1
            self._inc_enriched += 1
            self._cur_inc_id = f"INC{1000000 + self._inc_opened}"
            self._cur_mttr = round(random.uniform(10.5, 14.0), 1)
            logger.info("[SIM ServiceNow] %s auto-opened", self._cur_inc_id)
            return {
                "service": "bunge-data-platform",
                "level": "warning",
                "message": (
                    f"[ServiceNow {self._cur_inc_id}] AUTO-OPENED by Datadog Workflow — "
                    "Watchdog detected CME pricing-feed staleness on the GCP data platform. "
                    "Enriched: blast radius = 5 revenue apps (Bunge Mobile, myBunge, "
                    "BungeServices, FRM, BungeAg); runbook attached; assigned data-platform-sre. "
                    "[SIMULATED — no live ServiceNow integration in this env]"
                ),
                "extra": {
                    "servicenow.incident": self._cur_inc_id,
                    "servicenow.action": "auto_open",
                    "aiops.simulated": True,
                },
            }
        return None

    def _maybe_auto_close(self, phase: str, phase_tick: int) -> Optional[dict]:
        """Auto-resolve at the end of recovery, while incident_state still
        exists (the last recovering tick)."""
        if phase == "recovering" and phase_tick == self.RECOVERY_TICKS - 1 and self._cur_inc_id:
            self._inc_closed += 1
            inc_id = self._cur_inc_id
            logger.info("[SIM ServiceNow] %s auto-resolved (MTTR %.1fm)", inc_id, self._cur_mttr)
            log = {
                "service": "bunge-data-platform",
                "level": "info",
                "message": (
                    f"[ServiceNow {inc_id}] AUTO-RESOLVED by Datadog Workflow — "
                    "pricing_feed_age < 20s and FRM stale-quote < 1% sustained. "
                    f"MTTR {self._cur_mttr}m vs ~59m manual baseline. [SIMULATED]"
                ),
                "extra": {
                    "servicenow.incident": inc_id,
                    "servicenow.action": "auto_close",
                    "aiops.simulated": True,
                    "mttr_minutes": self._cur_mttr,
                },
            }
            self._cur_inc_id = None
            return log
        return None

    def _drive_itsm(self, intensity: float) -> None:
        """Set the simulated ServiceNow connector gauges every tick (incl.
        normal), so the AIOps dashboard always has live data."""
        open_now = max(0, self._inc_opened - self._inc_closed)
        if intensity > 0:
            suppressed = 18.0 + 40.0 * intensity     # raw signals collapsed into 1 incident
            noise = 90.0 + 5.0 * intensity
        else:
            suppressed = max(0.0, _drift(1.0, 0.8))
            noise = 88.0
        for d in self._itsm:
            self._set(d, self.ITSM_OPEN, float(open_now))
            self._set(d, self.ITSM_OPENED, float(self._inc_opened))
            self._set(d, self.ITSM_CLOSED, float(self._inc_closed))
            self._set(d, self.ITSM_ENRICHED, float(self._inc_enriched))
            self._set(d, self.ITSM_SUPPRESSED, _clamp(_drift(suppressed, 1.5), 0, 80))
            self._set(d, self.ITSM_NOISE, _clamp(noise, 80, 96))
            self._set(d, self.ITSM_MTTR, self._cur_mttr)
            self._set(d, self.ITSM_CLOSE_RATE, _clamp(_drift(86.0, 1.0), 70, 95))

    # -------------------------------------------------------------- overrides
    def _apply(self, phase: str, t: int) -> None:
        if phase == "normal":
            self._hold_pipelines_baseline()
            self._hold_pricers_baseline()
        elif phase == "ramp_up":
            self._phase_ramp_up(t)
        elif phase == "degraded":
            self._phase_degraded(t)
        elif phase == "outage":
            self._phase_outage(t)
        elif phase == "recovering":
            self._phase_recovering(t)

    def _hold_pipelines_baseline(self) -> None:
        for p in self._pipelines:
            self._set(p, self.DP_FEED_AGE, _clamp(_drift(self.BASE_FEED_AGE, 1.5), 2, 28))
            self._set(p, self.DP_FRESHNESS, _clamp(_drift(self.BASE_FRESHNESS, 10), 30, 300))
            self._set(p, self.DP_ERR, _clamp(_drift(self.BASE_DP_ERR, 0.001), 0.001, 0.02))
            self._set(p, self.DP_RECORDS, _clamp(_drift(self.BASE_RECORDS, 250), 500, 5000))

    def _hold_pricers_baseline(self) -> None:
        for p in self._pricers:
            self._set(p, self.PR_STALE, _clamp(_drift(self.BASE_STALE, 0.15), 0.1, 1.8))
            self._set(p, self.PR_LAT, _clamp(_drift(self.BASE_LAT, 8), 40, 210))
            self._set(p, self.PR_ERR, _clamp(_drift(self.BASE_PR_ERR, 0.001), 0.001, 0.009))

    def _phase_ramp_up(self, t: int) -> None:
        # Only the data platform moves; pricing stays clean (silent window).
        progress = (t + 1) / self.RAMP_TICKS
        for p in self._pipelines:
            self._set(p, self.DP_FEED_AGE,
                      _clamp(_drift(self._interp(self.BASE_FEED_AGE, 120.0, progress), 6), 4, 160))
            self._set(p, self.DP_FRESHNESS,
                      _clamp(_drift(self._interp(self.BASE_FRESHNESS, 150.0, progress), 12), 40, 220))
            self._set(p, self.DP_ERR, _clamp(_drift(self.BASE_DP_ERR, 0.0015), 0.001, 0.02))
            self._set(p, self.DP_RECORDS,
                      _clamp(_drift(self._interp(self.BASE_RECORDS, 2800, progress), 250), 1500, 5000))
        self._hold_pricers_baseline()

    def _phase_degraded(self, t: int) -> None:
        progress = (t + 1) / self.DEGRADED_TICKS
        for p in self._pipelines:
            self._set(p, self.DP_FEED_AGE, _clamp(_drift(self._interp(150, 260, progress), 25), 120, 340))
            self._set(p, self.DP_FRESHNESS, _clamp(_drift(self._interp(150, 230, progress), 18), 120, 300))
            self._set(p, self.DP_ERR, _clamp(_drift(self._interp(0.01, 0.035, progress), 0.004), 0.006, 0.06))
            self._set(p, self.DP_RECORDS, _clamp(_drift(self._interp(2800, 1800, progress), 220), 1000, 3500))
        for p in self._pricers:
            self._set(p, self.PR_STALE, _clamp(_drift(self._interp(self.BASE_STALE, 7.0, progress), 0.6), 0.4, 10))
            self._set(p, self.PR_LAT, _clamp(_drift(self._interp(self.BASE_LAT, 210.0, progress), 18), 60, 320))
            self._set(p, self.PR_ERR, _clamp(_drift(self._interp(self.BASE_PR_ERR, 0.02, progress), 0.003), 0.002, 0.05))

    def _phase_outage(self, t: int) -> None:
        progress = (t + 1) / self.OUTAGE_TICKS
        for p in self._pipelines:
            self._set(p, self.DP_FEED_AGE, _clamp(_drift(self._interp(300, 480, progress), 40), 260, 620))
            self._set(p, self.DP_FRESHNESS, _clamp(_drift(self._interp(230, 285, progress), 18), 200, 320))
            self._set(p, self.DP_ERR, _clamp(_drift(self._interp(0.035, 0.06, progress), 0.006), 0.02, 0.09))
            self._set(p, self.DP_RECORDS, _clamp(_drift(self._interp(1800, 900, progress), 200), 400, 2400))
        for p in self._pricers:
            self._set(p, self.PR_STALE, _clamp(_drift(self._interp(7.0, 12.5, progress), 0.8), 5, 16))
            self._set(p, self.PR_LAT, _clamp(_drift(self._interp(210, 360, progress), 25), 160, 460))
            self._set(p, self.PR_ERR, _clamp(_drift(self._interp(0.02, 0.045, progress), 0.004), 0.015, 0.07))

    def _phase_recovering(self, t: int) -> None:
        progress = (t + 1) / self.RECOVERY_TICKS
        # Feed refreshes first; pricing trails.
        for p in self._pipelines:
            self._set(p, self.DP_FEED_AGE, _clamp(_drift(self._interp(420, self.BASE_FEED_AGE, progress), 25), 4, 520))
            self._set(p, self.DP_FRESHNESS, _clamp(_drift(self._interp(280, self.BASE_FRESHNESS, progress), 18), 40, 300))
            self._set(p, self.DP_ERR, _clamp(_drift(self._interp(0.055, self.BASE_DP_ERR, progress), 0.005), 0.001, 0.07))
            self._set(p, self.DP_RECORDS, _clamp(_drift(self._interp(1000, self.BASE_RECORDS, progress), 250), 500, 5000))
        for p in self._pricers:
            self._set(p, self.PR_STALE, _clamp(_drift(self._interp(12.0, self.BASE_STALE, progress), 0.8), 0.3, 14))
            self._set(p, self.PR_LAT, _clamp(_drift(self._interp(340, self.BASE_LAT, progress), 20), 50, 400))
            self._set(p, self.PR_ERR, _clamp(_drift(self._interp(0.04, self.BASE_PR_ERR, progress), 0.004), 0.002, 0.06))
