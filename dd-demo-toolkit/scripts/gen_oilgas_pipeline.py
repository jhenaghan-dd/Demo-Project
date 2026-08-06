#!/usr/bin/env python3
"""
Generate the 28 `pipeline_step` device blocks for the oilgas vertical.

Why a generator: 28 steps x 4 metrics is 112 hand-maintained timeseries, and the
plugin needs a baseline for every one of them. Hand-editing guarantees the config
and the plugin drift apart. Here the step table is declared once and the config is
rewritten from it, idempotently, between sentinel comments in config.yaml.

The plugin does NOT get a generated copy of the baselines. It derives them from
the emitted config at runtime:

    baseline = metric.range[1]      # steady state
    trough   = metric.range[0]      # incident value

That works because the engine clamps inclusively
(`max(range[0], min(range[1], v))`, simulator/engine.py:662) and every row-count
metric declares `drift: 0`, so `random.gauss(0, 0)` is exactly 0.0 and a plugin
write lands on the endpoint untouched. One source of truth, no duplication.

Usage (from dd-demo-toolkit/):
    python scripts/gen_oilgas_pipeline.py           # rewrite config.yaml in place
    python scripts/gen_oilgas_pipeline.py --check   # exit 1 if out of date (CI)
    python scripts/gen_oilgas_pipeline.py --stdout  # print the block only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "verticals" / "oilgas" / "config.yaml"

BEGIN = "  # >>> BEGIN GENERATED — scripts/gen_oilgas_pipeline.py — DO NOT EDIT BY HAND"
END = "  # <<< END GENERATED"

# The nightly run, as an upstream drilling shop would actually stage it. Order is
# load-bearing: the narrative turns on step 12 (outbound drop to the signal
# vendor), step 14 (vendor signal ingest) and step 15 (return pickup).
#
# rows_out is declared; rows_in is the previous step's rows_out. Attrition is
# ordinary filtering, not the incident.
STEPS: list[tuple[str, int, int]] = [
    # (slug,                        rows_out, duration_sec)
    ("raw-land-wits-frames", 5200, 42),
    ("decode-wits-binary", 5180, 35),
    ("validate-frame-checksums", 5120, 18),
    ("dedupe-frame-window", 5040, 27),
    ("normalize-units", 5040, 15),
    ("merge-rig-state", 5020, 33),
    ("depth-index-align", 5000, 58),
    ("mudlog-join", 4990, 74),
    ("survey-interpolate", 4990, 61),
    ("drilling-params-rollup", 4960, 46),
    ("quality-flag-annotate", 4960, 22),
    ("stage-outbound-vendor-drop", 4960, 38),  # 12 - outbound S3 drop
    ("compress-encrypt-outbound", 4960, 29),
    ("thirdparty-signal-ingest", 4940, 165),  # 14 - the suspicious hop
    ("vendor-return-pickup", 4940, 44),  # 15 - return pickup
    ("decode-vendor-signals", 4930, 36),
    ("reconcile-vendor-keys", 4900, 52),
    ("formation-tops-enrich", 4900, 67),
    ("offset-well-lookup", 4880, 81),
    ("rop-model-features", 4880, 93),
    ("bit-wear-features", 4870, 88),
    ("vibration-spectra-features", 4870, 124),
    ("feature-store-upsert", 4850, 57),
    ("forecast-model-score", 4850, 142),
    ("confidence-band-compute", 4840, 49),
    ("recommendation-assemble", 4840, 31),
    ("warehouse-stage-load", 4820, 118),
    ("publish-forecast-mart", 4800, 64),
]

RAW_INPUT_ROWS = 5200

# Two trough factors, because the third party is not merely proportional.
#
# Steps 1-13 process exactly what the field uploaded: 30% short, matching the
# brief's "the outbound drop was 30% smaller than typical".
#
# Steps 14-28 are worse than proportional. The vendor enriches by matching on
# keys it did not receive, so partial input costs it matches it would otherwise
# have made - the brief's "a third-party system returns incomplete signals
# because its input was partial". This is what makes step 14 a genuine
# discontinuity in the 28-bar toplist rather than one more uniformly short bar,
# and it is why the investigation pauses there before clearing the vendor.
FIELD_TROUGH = 0.70
VENDOR_TROUGH = 0.60
VENDOR_BOUNDARY_STEP = 14


def _trough(step_no: int, baseline: int) -> int:
    factor = FIELD_TROUGH if step_no < VENDOR_BOUNDARY_STEP else VENDOR_TROUGH
    return int(round(baseline * factor))


def build_block() -> str:
    lines: list[str] = [
        BEGIN,
        "  # 28 nightly pipeline steps. Each is a `count: 1` device with a distinct",
        "  # `model:`, which surfaces as the `device_model` tag - so one",
        "  # `by {device_model}` split yields 28 named series.",
        "  #",
        "  # Every metric declares `range: [trough, baseline]` and `drift: 0`. The",
        "  # plugin writes range[1] in steady state and range[0] during the incident;",
        "  # both survive the engine's inclusive clamp exactly. Do not widen a range",
        "  # without regenerating, or the plugin's trough will be clamped away.",
        "  nightly_pipeline:",
        "    devices:",
    ]

    rows_in = RAW_INPUT_ROWS
    for idx, (slug, rows_out, duration) in enumerate(STEPS, start=1):
        model = f"step-{idx:02d}-{slug}"
        in_lo, out_lo = _trough(idx, rows_in), _trough(idx, rows_out)
        dur_lo = int(round(duration * 0.6))
        lines += [
            "    - type: pipeline_step",
            "      manufacturer: Custom",
            f"      model: {model}",
            '      firmware: "1.0"',
            "      count: 1",
            "      metrics:",
            "      - name: oilgas.pipeline.rows_in_count",
            "        type: gauge",
            '        unit: "1"',
            f"        range: [{in_lo}, {rows_in}]",
            "        drift: 0",
            "      - name: oilgas.pipeline.rows_out_count",
            "        type: gauge",
            '        unit: "1"',
            f"        range: [{out_lo}, {rows_out}]",
            "        drift: 0",
            "      - name: oilgas.pipeline.step_status_state",
            "        type: gauge",
            '        unit: "1"',
            "        range: [0, 1]",
            "        drift: 0",
            "      - name: oilgas.pipeline.step_duration_sec",
            "        type: gauge",
            "        unit: s",
            f"        range: [{dur_lo}, {duration}]",
            "        drift: 0",
        ]
        rows_in = rows_out

    lines.append(END)
    return "\n".join(lines) + "\n"


def splice(text: str, block: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit(
            f"sentinel markers not found in {CONFIG}.\n"
            f"Expected a region delimited by:\n{BEGIN}\n{END}"
        )
    return pattern.sub(lambda _: block, text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 if config.yaml is stale")
    ap.add_argument("--stdout", action="store_true", help="print the block and exit")
    args = ap.parse_args()

    block = build_block()
    if args.stdout:
        sys.stdout.write(block)
        return 0

    current = CONFIG.read_text(encoding="utf-8")
    updated = splice(current, block)

    if args.check:
        if current != updated:
            print(f"STALE: {CONFIG} does not match the step table.", file=sys.stderr)
            print("Run: python scripts/gen_oilgas_pipeline.py", file=sys.stderr)
            return 1
        print(f"up to date: {len(STEPS)} steps")
        return 0

    if current == updated:
        print(f"unchanged: {len(STEPS)} steps")
    else:
        CONFIG.write_text(updated, encoding="utf-8")
        print(f"wrote {len(STEPS)} steps to {CONFIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
