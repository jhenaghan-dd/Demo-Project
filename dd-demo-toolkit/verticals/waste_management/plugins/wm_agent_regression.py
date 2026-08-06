"""
WasteManagement — Telematics GPS Null-Rate Spike → Ops-Agent Decision
Regression cascade.

Drives the notebook RCA (`wm-agent-decision-regression-rca`) end to end: a
synthetic upstream data-quality event surfaces as `wm.data.gps_null_rate_pct`
climbing, pipeline staleness follows, and within ~2 minutes the agent eval
scores on all three model nodes regress IN LOCKSTEP — the tell that this is an
input (data) problem, not a model problem — then recover after the DAG hotfix.

This vertical has a single plugin, so the 4-axis bifurcation rules (STYLE_GUIDE
§9.3) are trivially satisfied — it's disjoint from every other vertical's
plugins by metric namespace (`wm.*`), location (waste_management), and
incident_domain (`route-data-pipeline`).

  Phase 1 — drift_up (8 ticks ≈ 2m): GPS null-rate climbs on the pipelines.
  Phase 2 — upstream_impact (8 ticks ≈ 2m): ingestion lag + last-run-age climb;
            the agent hasn't seen the bad positions yet. (2-leading-indicator)
  Phase 3 — decision_regression (12 ticks ≈ 3m): bad data reaches the agent;
            decision accuracy + F1 drop across all three models together,
            hallucination climbs. (3-symptom)
  Phase 4 — recovery (10 ticks ≈ 2m30s): DAG hotfix drains the null spike; the
            eval scores climb back to baseline. (5-recovery)
"""

import logging
import random
from typing import Any, List, Optional

from dd_demo_toolkit.simulator.plugins import IncidentPlugin

logger = logging.getLogger("wm_agent_regression_incident")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _drift(value: float, magnitude: float = 1.0, bias: float = 0.0) -> float:
    return value + random.gauss(bias, magnitude)


class WMAgentRegressionCascade(IncidentPlugin):
    """Upstream telematics data quality → downstream ops-agent eval regression,
    fleet-wide on the pipeline nodes and all three agent-eval model nodes so the
    lockstep drop is unambiguous when split by `model` on the scorecard."""

    # Phase durations (15s/tick → ~10 min full cascade)
    DRIFT_UP_TICKS = 8
    UPSTREAM_IMPACT_TICKS = 8
    REGRESSION_TICKS = 12
    RECOVERY_TICKS = 10
    EVENT_TICKS = DRIFT_UP_TICKS + UPSTREAM_IMPACT_TICKS + REGRESSION_TICKS + RECOVERY_TICKS

    # Pipeline baselines (healthy) and the phase-3 peak of the bad-data event.
    BASELINE_NULL_PCT = 0.8
    BASELINE_LAG_SEC = 25.0
    BASELINE_AGE_MIN = 6.0
    PEAK_NULL_PCT = 9.0
    PEAK_LAG_SEC = 120.0
    PEAK_AGE_MIN = 35.0

    # Per-model healthy baselines (mirror config.yaml ranges).
    MODEL_BASELINES = {
        "claude-3-5-sonnet": {"acc": 0.95, "f1": 0.94, "halluc": 1.5, "safety": 0.99},
        "gpt-4o":            {"acc": 0.91, "f1": 0.90, "halluc": 2.5, "safety": 0.97},
        "gpt-4o-mini":       {"acc": 0.78, "f1": 0.76, "halluc": 5.0, "safety": 0.84},
    }
    # Phase-3 troughs — where each metric lands during the regression.
    MODEL_TROUGHS = {
        "claude-3-5-sonnet": {"acc": 0.80, "f1": 0.78, "halluc": 4.0, "safety": 0.95},
        "gpt-4o":            {"acc": 0.76, "f1": 0.74, "halluc": 5.5, "safety": 0.93},
        "gpt-4o-mini":       {"acc": 0.60, "f1": 0.58, "halluc": 9.0, "safety": 0.75},
    }

    # Metric names — must match config.yaml device declarations.
    NULL_METRIC = "wm.data.gps_null_rate_pct"
    LAG_METRIC = "wm.data.ingestion_lag_sec"
    AGE_METRIC = "wm.data.last_run_age_min"
    ACC_METRIC = "wm.agent_eval.decision_accuracy"
    F1_METRIC = "wm.agent_eval.f1_score"
    HALLUC_METRIC = "wm.agent_eval.hallucination_rate_pct"
    SAFETY_METRIC = "wm.agent_eval.safety_refusal_rate"

    def __init__(self) -> None:
        self._ticks_until_next = random.randint(2, 6)
        self._active_tick: Optional[int] = None
        self._pipelines: List[Any] = []
        self._models: List[Any] = []
        logger.info("WM agent regression cascade initialized. First event in ~%ds",
                    self._ticks_until_next * 15)

    def get_incident_name(self) -> str:
        return ("WasteManagement — Telematics GPS Null-Rate Spike → "
                "Ops-Agent Decision Regression (fleet-wide, all models)")

    def reset(self) -> None:
        self._ticks_until_next = random.randint(2, 6)
        self._active_tick = None
        self._pipelines = []
        self._models = []

    # -- tick entry point ----------------------------------------------
    def on_tick(self, tick_count: int, fleet: List[Any], engine: Any) -> None:
        if not self._pipelines and not self._models:
            for d in fleet:
                dtype = getattr(d, "type", None) or (
                    d.get("device_type") if isinstance(d, dict) else None)
                if dtype == "telematics_pipeline_node":
                    self._pipelines.append(d)
                elif dtype == "agent_eval_node":
                    self._models.append(d)
            if self._pipelines or self._models:
                logger.info("Indexed %d telematics pipelines + %d model nodes",
                            len(self._pipelines), len(self._models))

        self._advance_clock()
        phase, phase_tick = self._current_phase()

        if hasattr(engine, "incident_state"):
            if phase == "normal":
                engine.incident_state.pop("wm_agent_regression", None)
            else:
                engine.incident_state["wm_agent_regression"] = {
                    "phase": phase,
                    "phase_tick": phase_tick,
                    "incident_domain": "route-data-pipeline",
                    "signal_chain_root": "telematics-gps-null-spike",
                }

        self._apply_overrides(phase, phase_tick)
        if phase != "normal":
            logger.info("WM AGENT CASCADE [%s t=%d] pipelines=%d models=%d",
                        phase, phase_tick, len(self._pipelines), len(self._models))

    # -- phase / clock -------------------------------------------------
    def _current_phase(self) -> tuple:
        if self._active_tick is None:
            return ("normal", 0)
        t = self._active_tick
        a = self.DRIFT_UP_TICKS
        b = a + self.UPSTREAM_IMPACT_TICKS
        c = b + self.REGRESSION_TICKS
        d = c + self.RECOVERY_TICKS
        if t < a:
            return ("drift_up", t)
        if t < b:
            return ("upstream_impact", t - a)
        if t < c:
            return ("decision_regression", t - b)
        if t < d:
            return ("recovery", t - c)
        return ("normal", 0)

    def _advance_clock(self) -> None:
        if self._active_tick is not None:
            self._active_tick += 1
            if self._active_tick >= self.EVENT_TICKS:
                self._active_tick = None
                self._ticks_until_next = random.randint(80, 120)
                logger.info("WM agent cascade complete. Next event in ~%dm",
                            self._ticks_until_next * 15 // 60)
        else:
            self._ticks_until_next -= 1
            if self._ticks_until_next <= 0:
                self._active_tick = 0
                logger.info("WM AGENT CASCADE STARTING (telematics GPS null-spike)")

    # -- state writers -------------------------------------------------
    def _set_state(self, device: Any, metric: str, value: float) -> None:
        state = getattr(device, "state", None)
        if state is None and isinstance(device, dict):
            state = device.setdefault("state", {})
        if state is not None:
            state[metric] = value

    def _device_model(self, device: Any) -> Optional[str]:
        return getattr(device, "model", None) or (
            device.get("model") if isinstance(device, dict) else None)

    def _interp(self, lo: float, hi: float, progress: float) -> float:
        return lo + (hi - lo) * progress

    # -- phase overrides -----------------------------------------------
    def _apply_overrides(self, phase: str, phase_tick: int) -> None:
        if phase == "normal":
            self._hold_baseline()
        elif phase == "drift_up":
            self._phase_drift_up(phase_tick)
        elif phase == "upstream_impact":
            self._phase_upstream_impact(phase_tick)
        elif phase == "decision_regression":
            self._phase_regression(phase_tick)
        elif phase == "recovery":
            self._phase_recovery(phase_tick)

    def _hold_baseline(self) -> None:
        for p in self._pipelines:
            self._set_state(p, self.NULL_METRIC, _clamp(_drift(self.BASELINE_NULL_PCT, 0.15), 0.2, 1.8))
            self._set_state(p, self.LAG_METRIC, _clamp(_drift(self.BASELINE_LAG_SEC, 4), 8, 55))
            self._set_state(p, self.AGE_METRIC, _clamp(_drift(self.BASELINE_AGE_MIN, 1), 2, 12))
        for m in self._models:
            base = self.MODEL_BASELINES.get(self._device_model(m))
            if not base:
                continue
            self._set_state(m, self.ACC_METRIC, _clamp(_drift(base["acc"], 0.008), 0.5, 0.99))
            self._set_state(m, self.F1_METRIC, _clamp(_drift(base["f1"], 0.008), 0.5, 0.99))
            self._set_state(m, self.HALLUC_METRIC, _clamp(_drift(base["halluc"], 0.3), 0.3, 12))
            self._set_state(m, self.SAFETY_METRIC, _clamp(_drift(base["safety"], 0.004), 0.6, 1.0))

    def _phase_drift_up(self, t: int) -> None:
        progress = (t + 1) / self.DRIFT_UP_TICKS
        for p in self._pipelines:
            self._set_state(p, self.NULL_METRIC,
                            _clamp(_drift(self._interp(self.BASELINE_NULL_PCT, self.PEAK_NULL_PCT, progress), 0.2), 0.2, 12))
            self._set_state(p, self.AGE_METRIC, _clamp(_drift(self.BASELINE_AGE_MIN, 1), 2, 14))
        # Agent still healthy — bad data hasn't landed yet.
        self._hold_models_baseline()

    def _phase_upstream_impact(self, t: int) -> None:
        progress = (t + 1) / self.UPSTREAM_IMPACT_TICKS
        for p in self._pipelines:
            self._set_state(p, self.NULL_METRIC, _clamp(_drift(self.PEAK_NULL_PCT, 0.3), 4, 12))
            self._set_state(p, self.LAG_METRIC,
                            _clamp(_drift(self._interp(self.BASELINE_LAG_SEC, self.PEAK_LAG_SEC, progress), 4), 20, 140))
            self._set_state(p, self.AGE_METRIC,
                            _clamp(_drift(self._interp(self.BASELINE_AGE_MIN, self.PEAK_AGE_MIN, progress), 1.5), 4, 40))
        self._hold_models_baseline()

    def _phase_regression(self, t: int) -> None:
        progress = (t + 1) / self.REGRESSION_TICKS
        for p in self._pipelines:
            self._set_state(p, self.NULL_METRIC, _clamp(_drift(self.PEAK_NULL_PCT, 0.3), 4, 12))
            self._set_state(p, self.LAG_METRIC, _clamp(_drift(self.PEAK_LAG_SEC, 5), 60, 150))
            self._set_state(p, self.AGE_METRIC, _clamp(_drift(self.PEAK_AGE_MIN, 2), 20, 45))
        for m in self._models:
            model = self._device_model(m)
            base, trough = self.MODEL_BASELINES.get(model), self.MODEL_TROUGHS.get(model)
            if not base or not trough:
                continue
            self._set_state(m, self.ACC_METRIC, _clamp(_drift(self._interp(base["acc"], trough["acc"], progress), 0.01), 0.4, 0.99))
            self._set_state(m, self.F1_METRIC, _clamp(_drift(self._interp(base["f1"], trough["f1"], progress), 0.01), 0.4, 0.99))
            self._set_state(m, self.HALLUC_METRIC, _clamp(_drift(self._interp(base["halluc"], trough["halluc"], progress), 0.4), 0.5, 14))
            self._set_state(m, self.SAFETY_METRIC, _clamp(_drift(self._interp(base["safety"], trough["safety"], progress), 0.006), 0.6, 1.0))

    def _phase_recovery(self, t: int) -> None:
        progress = (t + 1) / self.RECOVERY_TICKS
        for p in self._pipelines:
            self._set_state(p, self.NULL_METRIC, _clamp(_drift(self._interp(self.PEAK_NULL_PCT, self.BASELINE_NULL_PCT, progress), 0.25), 0.2, 12))
            self._set_state(p, self.LAG_METRIC, _clamp(_drift(self._interp(self.PEAK_LAG_SEC, self.BASELINE_LAG_SEC, progress), 4), 15, 140))
            self._set_state(p, self.AGE_METRIC, _clamp(_drift(self._interp(self.PEAK_AGE_MIN, self.BASELINE_AGE_MIN, progress), 1.5), 3, 40))
        for m in self._models:
            model = self._device_model(m)
            base, trough = self.MODEL_BASELINES.get(model), self.MODEL_TROUGHS.get(model)
            if not base or not trough:
                continue
            self._set_state(m, self.ACC_METRIC, _clamp(_drift(self._interp(trough["acc"], base["acc"], progress), 0.01), 0.4, 0.99))
            self._set_state(m, self.F1_METRIC, _clamp(_drift(self._interp(trough["f1"], base["f1"], progress), 0.01), 0.4, 0.99))
            self._set_state(m, self.HALLUC_METRIC, _clamp(_drift(self._interp(trough["halluc"], base["halluc"], progress), 0.4), 0.5, 14))
            self._set_state(m, self.SAFETY_METRIC, _clamp(_drift(self._interp(trough["safety"], base["safety"], progress), 0.006), 0.6, 1.0))

    def _hold_models_baseline(self) -> None:
        for m in self._models:
            base = self.MODEL_BASELINES.get(self._device_model(m))
            if not base:
                continue
            self._set_state(m, self.ACC_METRIC, _clamp(_drift(base["acc"], 0.008), 0.5, 0.99))
            self._set_state(m, self.F1_METRIC, _clamp(_drift(base["f1"], 0.008), 0.5, 0.99))
            self._set_state(m, self.HALLUC_METRIC, _clamp(_drift(base["halluc"], 0.3), 0.3, 12))
            self._set_state(m, self.SAFETY_METRIC, _clamp(_drift(base["safety"], 0.004), 0.6, 1.0))
