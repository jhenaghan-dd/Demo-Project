"""
Regression tests for the oilgas vertical's simulation contract.

Every assertion here corresponds to a failure mode that has already shipped
broken in another vertical. `dd-demo validate` catches none of them — it is an
asset linter that reads monitors/dashboards/notebooks/workflows/slos and never
loads config.yaml through ConfigLoader at all
(dd_demo_toolkit/validation/runner.py:23-31). So a config that ConfigLoader
outright rejects still validates clean, and a config that loads but emits flat
midpoints validates clean too.

Hermetic and offline: builds the engine in-process, never touches the Datadog
API, never starts a container.
"""

import collections

import pytest

from dd_demo_toolkit.config import ConfigLoader
from dd_demo_toolkit.simulator.engine import SimulatorEngine

VERTICAL = "oilgas"
PREFIX = "oilgas."

# Only these are valid for _DOWNSTREAM_TEMPLATES (simulator/engine.py:244-260).
# `nodejs` parses fine and then silently produces no child spans — a live bug in
# waste_management's my-wm-portal.
SUPPORTED_LANGUAGES = {"java", "dotnet", "python", "go", "swift"}


@pytest.fixture(scope="module")
def config():
    return ConfigLoader("verticals").load_vertical(VERTICAL)


@pytest.fixture(scope="module")
def engine(config):
    return SimulatorEngine(config)


def _iter_metrics(config):
    for cat_name, cat in config["device_categories"].items():
        for device in cat["devices"]:
            for metric in device.get("metrics", []):
                yield cat_name, device, metric


def test_config_loads_and_declares_expected_shape(config):
    """ConfigLoader rejects a bad services block outright; validate does not."""
    assert config["vertical"]["env_prefix"] == "oilgas"
    assert config["vertical"]["name"] == VERTICAL
    assert len(config["services"]) == 5


def test_every_service_can_actually_emit(config):
    """A service with no operations emits NOTHING.

    `_generate_service_trace` early-returns on `if not service or not
    service.operations` (engine.py:707-709) before the spans, the per-service
    logs, the auto-created oilgas.app.* counters and the cross-service
    peer.service edge that draws the Service Map. The Service Catalog entry
    still deploys, so the failure renders as an empty service page.
    """
    for svc in config["services"]:
        name = svc.get("name")
        assert (
            svc.get("language") in SUPPORTED_LANGUAGES
        ), f"{name}: language {svc.get('language')!r} produces no downstream spans"
        assert (
            isinstance(svc.get("operations"), list) and svc["operations"]
        ), f"{name}: empty operations means zero spans and no Service Map edge"
        for dep in svc.get("dependencies") or []:
            assert dep.get("operation"), (
                f"{name}: dependency on {dep.get('service')} has no operation; "
                "_normalize_dependencies_config rewrites it to '' and the span "
                "renders nameless"
            )


def test_third_party_hop_never_errors(config):
    """Hop 4 clears the vendor. 'Error rate flat throughout' must be literally
    true, not merely narrated."""
    vendor = next(s for s in config["services"] if s["name"] == "thirdparty-signal-api")
    for op in vendor["operations"]:
        assert op["error_rate"] == 0.0, f"{op['name']} must not error"


def test_every_metric_is_namespaced_and_ranged(config):
    """An undeclared range defaults to [0, 100] and, with drift 0, emits a flat
    50 forever (MetricConfig.range at engine.py:435, seeding at :66-70)."""
    for _cat, device, metric in _iter_metrics(config):
        name = metric["name"]
        assert name.startswith(PREFIX), f"{name} escapes the env_prefix namespace"
        assert "range" in metric, f"{name} has no explicit range"
        lo, hi = metric["range"]
        assert lo <= hi, f"{name} has an inverted range {metric['range']}"


def test_counts_and_totals_do_not_drift(config):
    """Drift on a row count produces fractional rows — the spurious-precision
    bug. Exact integers require drift 0."""
    for _cat, device, metric in _iter_metrics(config):
        name = metric["name"]
        if name.endswith("_count") or name.endswith("_total"):
            assert (
                metric.get("drift", 0) == 0
            ), f"{name} on {device['model']} drifts; row counts must be exact"


def test_no_environment_scale(config):
    """environment_scale multiplies every emitted value (engine.py:667-670).
    Finance's production: 3.0 is why EY's F1 gauge reads 2.55 and its quality
    monitors can never fire."""
    assert (
        "environment_scale" not in config
    ), "environment_scale silently rescales every metric in the vertical"


def test_plugin_driven_metrics_can_reach_both_endpoints(config):
    """The plugin writes range[1] at baseline and range[0] during the incident.

    The engine clamps inclusively (engine.py:662) and plugins run before the
    clamp (:621 vs :629), so with drift 0 both endpoints survive exactly. A
    degenerate range collapses the two and makes the incident invisible — the
    failure mode that erases 15/15 EY and 12/12 waste_management troughs today.
    """
    must_move = (
        "oilgas.field.link_up_state",
        "oilgas.field.link_down_ticks_total",
        "oilgas.pipeline.rows_in_count",
        "oilgas.pipeline.rows_out_count",
        "oilgas.warehouse.rows_loaded_count",
        "oilgas.expert.answer_confidence_ratio",
    )
    seen = set()
    for _cat, device, metric in _iter_metrics(config):
        if metric["name"] in must_move:
            seen.add(metric["name"])
            lo, hi = metric["range"]
            assert lo < hi, (
                f"{metric['name']} on {device['model']} has a degenerate range "
                f"{metric['range']}; the plugin could never move it"
            )
    assert seen == set(must_move), f"missing metrics: {set(must_move) - seen}"


def test_fleet_places_gateways_per_site_and_pins_the_rest(engine):
    """Placement is per-dimension round-robin WITHIN one device entry
    (engine.py:441-447), so a `count: 1` device always lands on values[0].

    28 singleton pipeline steps must therefore all sit at central-ops, and only
    field_gateway (count 7) spreads. If a future edit gives the steps a real
    count, or adds a second location dimension, this test fails — which is the
    point: pad-scoped monitors would otherwise silently sweep the whole fleet.
    """
    dist = collections.defaultdict(collections.Counter)
    for device in engine.fleet:
        dist[device.type][device.location["site"]] += 1

    gateways = dist["field_gateway"]
    assert len(gateways) == 7, f"expected one gateway per site, got {dict(gateways)}"
    assert set(gateways.values()) == {1}, f"uneven gateway spread: {dict(gateways)}"

    for device_type, sites in dist.items():
        if device_type == "field_gateway":
            continue
        assert set(sites) == {
            "central-ops"
        }, f"{device_type} must be pinned to central-ops, got {dict(sites)}"


def test_pipeline_has_all_28_steps_in_order(engine):
    """The narrative names steps 12, 14 and 15 explicitly."""
    models = sorted(d.model for d in engine.fleet if d.type == "pipeline_step")
    assert len(models) == 28, f"expected 28 steps, got {len(models)}"
    assert models[0].startswith("step-01-")
    assert models[11] == "step-12-stage-outbound-vendor-drop"
    assert models[13] == "step-14-thirdparty-signal-ingest"
    assert models[14] == "step-15-vendor-return-pickup"
    assert models[27] == "step-28-publish-forecast-mart"


def test_vendor_boundary_deficit_is_disproportionate(config):
    """Step 14 must be a visible discontinuity, not one more uniformly short bar.

    Steps 1-13 process exactly what the field uploaded (30% short). The vendor
    enriches by key match, so partial input costs it matches it would otherwise
    have made — steps 14+ come back proportionally worse. That extra drop is
    what makes the toplist point at step 14 and the investigation pause there.
    """
    troughs = {}
    for _cat, device, metric in _iter_metrics(config):
        if device.get("type") == "pipeline_step" and metric["name"].endswith("rows_in_count"):
            lo, hi = metric["range"]
            troughs[device["model"]] = lo / hi

    before = troughs["step-13-compress-encrypt-outbound"]
    after = troughs["step-14-thirdparty-signal-ingest"]
    assert after < before - 0.05, (
        f"step 14 trough ratio {after:.3f} is not visibly worse than step 13's "
        f"{before:.3f}; the discontinuity the investigation turns on is missing"
    )


def test_generated_block_is_not_stale():
    """config.yaml's 28 steps are generated. If the step table changes and the
    config is not regenerated, the plugin's baselines silently disagree."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/gen_oilgas_pipeline.py", "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"config.yaml is stale relative to the generator's step table.\n"
        f"{result.stdout}{result.stderr}"
    )
