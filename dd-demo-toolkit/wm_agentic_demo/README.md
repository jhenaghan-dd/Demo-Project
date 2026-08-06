# WM Operations Agent — Agentic LLM Observability

Two standalone, **agentless** assets that stream realistic WasteManagement
agentic-AI telemetry to Datadog **LLM Observability** — no Agent, no OTel
collector, no Docker. Point them at an org with an API key and they light up
the LLM Obs surface, branded for WM's customer-service + dispatch operations.

Both share `ml_app=wm-ops-agent`, so a conversation can show **live agent
traces** and the **model-comparison scorecard** side by side. All data is
synthetic — no customer data, no real provider keys. Metros/routes/truck IDs
mirror the `docker/waste_management` fleet, so the agent story and the fleet
map line up.

| File | Surface | The story |
|---|---|---|
| **`wm_ops_experiments.py`** | LLM Obs → **Experiments** | *(the stronger one)* One WM eval dataset × a model matrix → a head-to-head scorecard: decision accuracy, WM-policy citation recall, F1, a PII gate, and **safety-refusal correctness**. "Pick the agent model with data, not vibes." |
| **`wm_ops_agent.py`** | LLM Obs → **Traces / Evaluations** | Live multi-step agent traces: planner → RAG → tools → (dispatch) sub-agent → guardrail → generate, with evals, cost, and a periodic quality regression. |

## What they show

**Experiments (`wm_ops_experiments.py`)** — a repeatable, versioned eval over 10
WM scenarios (missed-pickup recovery, billing, service start/stop, bulk pickup,
recycling contamination, dispatch reroute) plus three **safety** turns that MUST
be refused/rerouted: hazardous-material curbside (→ HHW drop-off), prompt
injection, and unauthorized credit. Each record carries machine-checkable
targets (`decision`, `must_cite_policies`, `must_mention`, `expected_action`,
`safety`). Evaluators: `exact_match_decision`, `policy_citation_recall`,
`must_mention_recall`, `precision_score`, `f1_score_combined`, `pii_leak_check`,
and `safety_refusal_correct` (surfaces `missed_refusal` as a filterable
category). Weaker/cheaper models miss refusals and drop policy citations — that
gap is the whole point.

**Traces (`wm_ops_agent.py`)** — a root `wm-ops-agent` span orchestrating
`plan_actions` → `gather_context` (embedding → `wm_service_kb` retrieval, with
reformulation on low confidence) → domain tools (`account_lookup`,
`route_status`, `pickup_scheduler`, `billing_system`, …) → for a dispatch
reroute, a nested **`route-optimizer-agent`** that loops over candidate
`wm-truck-NNNN` trucks and reassigns stops → `verify_safety` guardrail →
`generate_response` (+ self-critique/revise). Hazmat / injection /
unauthorized-credit turns surface as `GuardrailBlocked` error traces. A ~3-min
degraded window every ~15 min slows retrieval and drops groundedness so
evaluations (and any monitors on them) fire and heal. Tagged with `metro`,
`route`, `scenario`, `role`, `model`, `provider`, `service_line`, `phase`.

## Run it

```bash
export DD_API_KEY=<key>            # required
export DD_APP_KEY=<key>            # required for --experiments
export DD_SITE=datadoghq.com       # or us3/us5/eu/ap1/ddog-gov

./run.sh                           # live agent TRACES (Ctrl-C to stop)
./run.sh --count 25                # N trace conversations then exit
./run.sh --experiments             # the model-comparison SCORECARD
./run.sh --experiments --limit 2   # first 2 models (quick smoke)
```

`run.sh` reuses your Python if `ddtrace` is importable, otherwise it creates a
throwaway `.venv-agentic`. Containerized (non-Docker) runs: see `Containerfile`.

## Where to look in Datadog

**LLM Observability**, filter to `ml_app:wm-ops-agent`:
- **Experiments** → project **WM Operations Agent Quality** — the model
  scorecard; sort by `f1_score_combined` or filter
  `safety_refusal_correct = missed_refusal` to see exactly where a cheaper
  model would have complied with a hazmat/injection/credit request.
- **Traces** → open a `dispatch_reroute` trace to watch the sub-agent fan out
  across `wm-truck` trucks; open a `hazardous_material` / `prompt_injection`
  trace to see the guardrail block.
- **Evaluations** → groundedness / hallucination over time; watch them dip in a
  degraded window.

## Configuration

| Var | Default | Purpose |
|---|---|---|
| `DD_API_KEY` | — (required) | Agentless auth |
| `DD_APP_KEY` | — (experiments only) | Experiments API |
| `DD_SITE` | `datadoghq.com` | Datadog site |
| `DD_LLMOBS_ML_APP` | `wm-ops-agent` | LLM Obs application name (shared by both) |
| `EXPERIMENT_PROJECT` | `WM Operations Agent Quality` | Experiments project |
| `EXPERIMENT_DATASET` | `wm_ops_agent_eval_v1` | Experiments dataset |
| `WMOPS_CYCLE_SEC` / `WMOPS_DEGRADED_SEC` | `900` / `180` | Trace degrade-cycle timing |

Separate from the Docker `dd-demo-toolkit` stack and from the
`docker/waste_management` fleet — these stand alone so you can run them anywhere
(laptop, jump host) without the container fleet.
