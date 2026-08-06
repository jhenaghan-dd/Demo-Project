# From Field to Forecast — Project Plan

**Account:** BPX / BPX Energy (BP's US onshore oil & gas E&P, Denver). **Source of truth:** the AoP brief "BPX Art of the Possible: Brief for John Rath" (Google Doc `1-Sj4HWbCJQ7fzWX2v_s8ku4mpFMO4TB7deMeDzv_Zzk`, Bryan Bottinelli, created 2026-08-05, shared 2026-08-05 22:48Z) plus the older, technically richer internal prep brief (Google Doc `1tbLKk-8_gpRk2DoMhS8CyjFJptha2LcySI28YcjUJmI`, May 2026). **This plan is built from the real documents, not a verbal summary** — but the two documents contradict each other on three material points, flagged inline and in §9.

**Path convention (corrected):** all paths are relative to **`dd-demo-toolkit/`** unless noted. The repo-root-only files are `AGENTS.md`, `CONTRIBUTING.md`, `SUPPORT.md`, `CODEOWNERS`, the root `README.md`, and `.github/`. Repo root is `/Users/john.rath/Documents/Claude/Projects/Demo Project`. This matters because `AGENTS.md:11-13` already requires running every command from inside `dd-demo-toolkit/`.

---

## 0. TL;DR and the one decision that matters

**Is it doable with no Snowflake, no pipeline, no Palantir? Yes — for four of five hops, at high confidence. Partially for the Snowflake hop, and that is the one honest weak spot.** The toolkit already ships a structurally identical demo: `verticals/waste_management/` tells "upstream data-quality defect silently poisons an AI's inputs; all models regress in lockstep; walk upstream," driven by one 270-line plugin (`verticals/waste_management/plugins/wm_agent_regression.py`). Field-to-Forecast is that story with more hops and different nouns.

**The one decision: we build ≤1.25 SE-days before James Battraw confirms priorities, and nothing more.**

The gate is not a formality. Verified: there is **no BPX event on the calendar through 2026-09-15**, and **zero replies** from `james.battraw@bpx.com`, `steven.barto@bpx.com`, `brian.monroe@bpx.com` or `ustat.singh@bpx.com` to the 2026-07-30 outreach (Gmail threads `19fb46fe278727b5`, `19fb47924051fbaf`). Our champion Ustat Singh left BP on/around 2026-07-29. Brian Monroe previously told us "Ustat is the most critical for this, as he owns my observability platform" — **nobody currently owns observability at BPX.** James is a Digital Security Architect whose only recorded priority signal is a January **2025** team call about Cloud SIEM and Code Security: roughly 19 months and one reorg stale.

**Built before the gate (0.75 SE-days, all of it survives any answer):**
1. `verticals/oilgas/config.yaml` — minimal *loadable* config (~40 lines, including a real `services:` block with `language:` and `operations:`). Locks the two irreversible decisions: `env_prefix` and vertical-vs-overlay.
2. `verticals/oilgas/notebooks.yaml` — one markdown-only investigation notebook, six cells, each closing in a question for James. Deployable, openable, teardownable. Post-gate it becomes the final RCA notebook by inserting chart cells between the existing markdown cells.
3. A one-page **honest capability table**, generated from the toolkit's own `PRODUCT_CATALOG` (`dd_demo_toolkit_ui/server.py:98-165`) rather than hand-written, as the gate packet.
4. The filled-in `.github/ISSUE_TEMPLATE/new-vertical.yml` — the repo's own sanctioned intake form.
5. **Two toolkit fixes:** `--build` inserted at the correct argv position in **both** the `setup` and `teardown` entries of `dd_demo_toolkit_ui/process_supervisor.py:97-115`; and `pyproject.toml [tool.isort] multi_line_mode` → `multi_line_output`.

**Also pre-Phase-1 but post-gate-independent (0.5 SE-days, core PR):** an opt-out for the simulator's generic LLM Obs and RUM submitters (§4, "Housekeeping"). This is a change to shared core code, not vertical housekeeping, and it is separately budgeted.

**Held until after the gate:** every device metric, every plugin, every dashboard, every monitor, all LLM Obs, all containers, all secondary demos.

Cost of a "no" or a pivot: three quarters of a day. Cost of a "yes": the plan below, **~8.75 SE-days core** (0.75 pre-gate + 0.5 core PR + 6.5 Phase 1 + 1 Phase 2), plus 0–6.5 optional.

**Where the judges disagreed, and how I resolved it.** The RVP panel favoured entering through the security door (James owns security; "I only care about Cloud SIEM" is the most likely sentence in that first call). The feasibility, convention and gate-discipline panels all favoured the minimal metric-plane build. I resolved it by **not choosing**: the security hedge is a one-page capability table plus two added gate questions (both zero build), and `verticals/oilgas/sds.yaml` is a costed post-gate add if security has any weight. We do **not** pre-build a `SecurityRuleManager` — that was 1.5 SE-days spent before confirming Cloud SIEM is even enabled in the org, which it may not be (see §9, R3).

---

## 1. Feasibility verdict

| Component | Doable? | Toolkit machinery | Fidelity risk |
|---|---|---|---|
| **Oil & gas vertical exists** | **YES, free** | `ConfigLoader.list_verticals()` (`dd_demo_toolkit/config.py:43-58`) is a filesystem scan gated only on `config.yaml` existing. No registry. UI dropdown populated dynamically by `dd_demo_toolkit_ui/server.py:312-338`. Template: `verticals/waste_management/`. | None |
| **28-step pipeline** | **YES** | 28 device entries with `count: 1` and distinct `model:` values → 28 `device_model` tags (`simulator/engine.py:679`). Precedent: `verticals/waste_management/config.yaml:110-295` gives three LLM models distinct tags this way; `:299-306` models an Airflow DAG as a device (`model: AirflowDAG`, **`count: 4`** — its healthy location spread comes from that count, which our 28 singletons will *not* have; see §3). **Upgrades available:** a real ddtrace orchestrator emitting one trace with 28 named spans, or reskinning the existing `data_obs/` Kafka stack (next row). | Med. No DAG topology view, no per-run Gantt. Data Jobs Monitoring does not exist: `grep -i 'spark\|databricks\|airflow'` returns two `model: AirflowDAG` device labels (`verticals/waste_management/config.yaml:304`, `verticals/finance/overlays/ey.yaml:251`) plus three Service Catalog description strings (`verticals/finance/config.yaml:322`, `verticals/finance/services.yaml:131`, `verticals/insurance/services.yaml:275`). `databricks` is genuinely zero. |
| **Data Streams Monitoring (real pipeline lineage)** | **YES — and previously overlooked** | `data_obs/` is a working Kafka + `dd-trace-py` DSM stack: `producer.py` → `feature_pipeline.py` → `eval_consumer.py`, gated behind the `data-obs` compose profile (`docker-compose.yaml:197-345`) with `make up-data-obs` / `down-data-obs` / `logs-data-obs` (`Makefile:178-185`). `dsm` is **`available: True`** in `PRODUCT_CATALOG` (`server.py:129-131`). Its own README describes our exact narrative: an upstream `DATA_QUALITY_FAULT_PCT` spikes `null_rate_pct` and the downstream eval agent's F1 falls, with auto-discovered pathway topology. | Low on mechanism, **med on reskin cost** — it is EY-namespaced (`risk-feature-events-raw`, `risk-eval-agent`, Postgres `ey_risk`). Costed as a Phase 3 alternative in §7, not folded into Phase 1. |
| **Snowflake — metrics + service map** | **YES** | A `warehouse` device_category + a `warehouse-loader` entry in `services:` (with `operations:`). Metrics must stay inside `oilgas.*`: a top-level `snowflake.*` namespace requires a real compose service **and** an edit to `PLATFORM_METRIC_PREFIXES` in `dd_demo_toolkit/validation/core.py:128` (currently exactly `{otelcol, postgresql, care.companion}`) and would fail `tests/test_dashboard_query_coverage.py`. | **HIGH — the weak hop, but no longer the *only* option.** |
| **Snowflake — Data Catalog / lineage / DQ monitors** | **NO for Snowflake specifically; "unwired, not absent" for dbt** | Zero Snowflake anywhere in the repo. Org verified empty: `get_data_catalog_schema` → `{"schema":null}`, `search_data_entities(entity_type:"*")` → 0 entities, `get_data_observability_monitor_coverage` → 0 monitors. The Data Observability MCP surface is read-only; **there is no POST path for synthetic entities.** **But** `dataobs` is `available: False` for a *specific, documented* reason (`server.py:90-95`): "`data_obs/` runs dbt and produces manifest.json / run_results.json, but the upload to Datadog is NOT wired (datadog-ci dropped the dbt plugin in v5)… available=False until the Agent dbt integration is configured." A warehouse with declared freshness SLAs already exists at `data_obs/dbt_project/models/sources.yml` (`loaded_at_field: received_at`, `warn_after: 30 minute` / `error_after: 90 minute`, plus `not_null` tests) over real Postgres. | **Hard dependency, owner John Rath:** 0.5-day spike on the Agent dbt integration before Phase 1 (§7). If it works, hop 2 stops being an imitation. If it does not, the navigation ban stands as an *evidenced* decision. |
| **"Expert"/Xpert chatbot — quality scorecard** | **YES** | Three `expert_eval_node` devices, `count: 1`, distinct `model:` per BPX's real stack. Clone `verticals/waste_management/dashboards/wm-agent-eval-scorecard.json` (11 widgets, already uses `by {device_model}`). | Low |
| **Expert — real LLM Obs traces** | **YES, post-gate** | Port `wm_agentic_demo/wm_ops_agent.py` (564 lines, agentless `ddtrace.llmobs`, no provider keys). **Verified live in this org today** — `search_llmobs_spans` returns `span_kind:agent` + `span_kind:retrieval` for `ml_app:wm-ops-agent`, project "WM Operations Agent Quality" created 2026-07-27. | Low on surface, med on content (prose quality of drilling RAG docs) |
| **Third-party signal vendor** | **YES — conditional on `operations:`** | `services:` entry with a probabilistic `dependencies` edge. **`_generate_service_trace` returns immediately on `if not service or not service.operations` (`simulator/engine.py:707-709`)** — so a service with no operations emits *nothing*: no spans, no `oilgas.app.*`, no logs, no Service Map edge. Every service must declare ≥1 operation. The `peer.service` edge is drawn by `_generate_cross_service_span` (`engine.py:891-925`), reached only from inside that function (`engine.py:807-813`). | Low **once operations are declared**. Do not drill into a flame graph; spans are synthetic. |
| **Logs (service + incident)** | **YES — and required** | Two paths, both free once `operations:` exists: per-service `LoggingHandler` loggers with automatic trace-log correlation (`engine.py:712`, `:816-822`), and **plugin-written transaction logs** via `incident_state[name]["tx_logs"]` → `_emit_incident_tx_logs` (`engine.py:786`, `:824-840`), emitted inside the active span so trace_id/span_id are injected. This is what gives SDS something to mask and Bits a log source. | Low |
| **Field network outage (root cause)** | **PARTIAL** | `field_gateway` devices emitting `oilgas.field.link_up` (0/1, precedent `hospital.device.online` at `verticals/healthcare/config.yaml:76-80`). | Med. **No NDM/SNMP/CNM telemetry path exists** — the only `snmp` hit repo-wide is a prose comment at `verticals/healthcare/overlays/quest.yaml:20`; `npm` is `available: False` (`server.py:113-118`). Say "these are the signals your edge gateways already expose," not "this is NDM." |
| **The data gap itself** | **PARTIAL — by design** | Real gauge suppression IS possible (~4 lines at `simulator/engine.py:665-693`; OTel `_LastValueAggregation.collect()` returns None and nulls when `.set()` is skipped, while counters are CUMULATIVE and keep re-exporting). **We are not building it.** See §4. | N/A |
| **Backdating / historical timeline** | **NO** | Every OTel emission is stamped at collection time (`utils/otel.py:69-72`, `simulator/engine.py:688-693`). The only timestamped writer is `DatadogAPIClient.submit_series()` (`utils/dd_api.py:885-909`) and **both** its callers hardcode `ts = int(time.time())` (`docker/waste_management/dd_emitter.py:124`, `docker/waste_management/backend_servers.py:120`). Datadog's historical-acceptance window is **UNVERIFIED in this repo**. | Time-compression, disclosed once. See §4. |
| **Bits AI SRE walking all five hops** | **PARTIAL** | Bits' documented data sources (Metrics, APM traces, Logs, Dashboards, Events, Change Tracking, GitHub source, Watchdog, RUM, Network Path, DBM, Continuous Profiler) do **not** include LLM Observability or Data Observability. **UNVERIFIED-in-repo — no Bits doc, skill file or test in this tree states this; see R4.** So hops 1 and 2 must be *projected* into metrics and logs for Bits, with the rich surface as the human's click-through. | See §5 |
| **Palantir** | **DEFER** | Zero references in the repo. Also gated on validation Q5 (Ustat said the OTEL export was producing "nonsense"). | Gated |
| **AWS scaling-policy change** | **PARTIAL, low value** | No AWS/CloudWatch/ASG anywhere. **Correction: an Agent is NOT required** — `docker/waste_management/dd_emitter.py:81-90` (`_system_signals`) synthesizes `system.cpu.user`, `system.load.1`, `system.mem.pct_usable` and posts them through `submit_series()` with `resources: [{"name": host, "type": "host"}]`. The same path would accept `aws.*`-shaped series. Nearest in-simulator technique: a step-change gauge (precedent `verticals/healthcare/overlays/quest/plugins/quest_hl7_config_cascade.py:375`) plus a Datadog Event. | High. Recommend kill — on narrative grounds, not capability grounds. See §6. |

**Bottom line for the SE: yes, build it.** The one thing you cannot deliver *today* is a lineage/catalog surface for a warehouse — and that is one 0.5-day integration spike away from being partly false, which is why the spike is a named pre-Phase-1 dependency rather than a shrug.

---

## 2. Patterns and conventions we must follow

Checklist. Every line traces to a file.

**Where things live**
- [ ] Run all build/test/lint from inside `dd-demo-toolkit/`, not the repo root — `dd-demo validate` resolves `verticals` as a **relative** path (`dd_demo_toolkit/cli.py:741`) and reports a false "not found" from the repo root. (`AGENTS.md:11-13`)
- [ ] A vertical is registered by creating `verticals/<name>/config.yaml`. Nothing else. (`dd_demo_toolkit/config.py:53-56`)
- [ ] Directory name **must equal** `config.yaml → vertical.name` (`tests/test_config.py:97-107`) — but note that test iterates a hardcoded four-vertical list at `:100`, so it will not cover `oilgas` unless the list is extended.

**Config loading has teeth that `dd-demo validate` does not**
- [ ] `ConfigLoader.REQUIRED_TOP_LEVEL` includes `services`; `REQUIRED_SERVICE_FIELDS = ["name", "language", "operations"]` (`config.py:32`), and `config.py:181-188` raises `ConfigError` for any service missing any of the three, plus asserts `operations` is a list. A malformed `services:` block kills `dd-demo simulate`, `dd-demo setup`/Deploy, and the UI dropdown.
- [ ] **`dd-demo validate` is an asset linter, not a config linter.** `validate_vertical` (`dd_demo_toolkit/validation/runner.py:68-96`) reads `env_prefix` with a raw `yaml.safe_load` helper (`:34-42`, returning `None` on any error) and then lints only `ALL_RESOURCE_TYPES = [monitors, dashboards, notebooks, workflows, slos]` (`:23`). A config that `ConfigLoader` outright rejects still validates clean. Worse: if `env_prefix` fails to resolve, `dashboards.validate` skips the DDD001 env_prefix check entirely (`if env_prefix:`, `dashboards.py:78`).
- [ ] **Therefore every gate must include** `python -c "from dd_demo_toolkit.config import ConfigLoader; from dd_demo_toolkit.simulator.engine import SimulatorEngine; SimulatorEngine(ConfigLoader('verticals').load_vertical('oilgas'))"` plus `pytest tests/test_config.py tests/test_validation.py`. Three tests auto-enrol a new vertical the moment `config.yaml` exists: `tests/test_validation.py:224-225` (`@pytest.mark.parametrize("vertical", ConfigLoader("verticals").list_verticals())`), and `tests/test_config.py:183` / `:221`, both of which call `load_vertical()` on every discovered vertical.

**Vertical vs overlay** — an overlay is structurally impossible for oil & gas:
- [ ] `_merge_overlay` (`dd_demo_toolkit/config.py:225-280`) is additive on exactly three keys and **never writes `result['vertical']`** — so an overlay cannot change `env_prefix`.
- [ ] Device lists **concatenate**; an overlay cannot remove base devices. Overlaying on healthcare leaves ~288 hospital devices emitting alongside the rigs.
- [ ] Only **one** overlay deploys at a time (`--sub-vertical` is single-valued: `cli.py:803-815`, `.env` `DD_DEMO_SUB_VERTICAL`, UI dropdown). Four stories cannot be four sibling overlays.
- [ ] **Therefore:** generic base vertical `oilgas`, customer content in `verticals/oilgas/overlays/bpx/` post-gate.

**Naming**
- [ ] `env_prefix` is inlined **literally** into every query string and is never templated at deploy (`CLAUDE.md` §2/§7). Renaming later is a repo-wide coordinated edit. Choose once.
- [ ] Metric shape `{env_prefix}.<domain>.<name>`; counters end `_total`; gauges carry a unit suffix (`STYLE_GUIDE.md:398-417`). **Boolean/state gauges are a recurring exception across healthcare (`hospital.device.online`) and now oil & gas — we add an explicit `_state` convention plus a STYLE_GUIDE §3 exemption in the same PR (DoD #6).**
- [ ] Every dashboard metric must start with the vertical's `env_prefix` — WARNING in the linter (DDD001), **hard failure** in `tests/test_dashboard_query_coverage.py:105-116`.
- [ ] **No underscore may flow into `DD_HOSTNAME`** — `docker-compose.yaml:24-28` documents that an env-derived `waste_management-simulator` crashes the Datadog OTel exporter (RFC1123).

**Tags**
- [ ] `vertical:<name>` and `dd-demo-toolkit:true` are **auto-injected**. Never in YAML. (`STYLE_GUIDE.md:340-342`)
- [ ] Never invent tag KEYS. Allowed: `team:`, `incident_domain:`, `signal_chain:`, `safety:`, `compliance:`, `audience:`, `workflow:`, `workflow-type:`. **Forbidden (ERROR, DDT001):** `sub_vertical:`, `customer:`, `overlay:` (`dd_demo_toolkit/validation/tags.py:11-14`).
- [ ] **`validation/notebooks.py` never calls `check_tags`** (unlike `monitors.py:65`, `slos.py:63`, `workflows.py:74`), and `resources/notebooks.py:282` discards YAML tags entirely and sends only `["team:dd-demo-<vertical>"]`. That is why `verticals/waste_management/notebooks.yaml:14-19` ships three violations invisibly (`vertical:waste_management`, `dd-demo-toolkit:true`, and an invented `signal_chain_root:` key). **Do not clone them.** Author `oilgas/notebooks.yaml` with no `tags:` block, and wire `check_tags` into `validation/notebooks.py` (two lines + hermetic test + STYLE_GUIDE entry) as a Phase 1 hygiene item.
- [ ] `signal_chain:` vocabulary is fixed: `1-root-cause`, `2-leading-indicator`, `3-symptom`, `4-cascade`, `5-recovery` (`STYLE_GUIDE.md:347`).
- [ ] Group by **`device_model`**, never `model` — the engine emits `device_model` (`simulator/engine.py:679`); `by {model}` returns zero groups silently.
- [ ] Do **not** use `device_category:` — the engine emits `category` (`simulator/engine.py:681`). 14+ query sites in healthcare/quest use the phantom key and silently return no data.

**Query rules with teeth**
- [ ] `by {dim}` before `.as_count()` (ERROR: DDD004/DDM003/DDN004/DDS003).
- [ ] No `||`/`&&` in monitor query alerts — split into two monitors (ERROR: DDM001).
- [ ] **No percentile aggregators** anywhere (WARNING DDD006/DDM002/DDN005/DDS002, and the SE's standing preference). Use the two-formula avg+max band trick (`STYLE_GUIDE.md:54-71`).
- [ ] Every notebook timeseries request needs `formulas:` or it renders empty (ERROR: DDN001). `show_legend: true` (DDN002).
- [ ] Dashboard requests with `queries` need `response_format` (ERROR: DDD002). `query_value` widgets reject `suffix` (ERROR: DDD003).
- [ ] Dashboard top-level `tags` accepts only keys `team` and `ai` — anything else 400s the whole create (`STYLE_GUIDE.md:528-543`). Omit the key; `resources/dashboards.py:167-188` appends `team:dd-demo-<vertical>` itself.
- [ ] Notebook `type:` must be one of postmortem/runbook/investigation/documentation/report/workspace/threat_hunting (ERROR: DDN003).
- [ ] **Set `"precision": 0` on every count/percent `query_value` widget** (`STYLE_GUIDE.md:454`). Source-side `drift: 0` alone does not prevent float tails on any metric that drifts.

**Three silent killers — all shipped broken in existing verticals**
- [ ] **Do NOT declare `environment_scale`.** `simulator/engine.py:667-670` multiplies every emitted value by it; finance's `production: 3.0` (`verticals/finance/config.yaml:37-40`) puts EY's F1 gauge at **2.55**, so its quality monitors can never fire. `waste_management` correctly omits it.
- [ ] **Declare `range` wide enough to span baseline AND trough.** `simulator/engine.py:656-663` clamps plugin writes back into range — this erases 15/15 EY trough values and 12/12 waste_management trough values today.
- [ ] **Every metric is seeded at its range MIDPOINT** (`DeviceProfile.__post_init__`, `engine.py:66-70`) and `MetricConfig.range` defaults to `[0, 100]` (`engine.py:435`). With `drift: 0` the value never moves off the midpoint. A `[0,1]` boolean with `drift: 0` emits a flat **0.5** forever; a rangeless counter `add()`s **50 per tick** (`engine.py:690`). **Rule: declare an explicit `range` on every metric, and the plugin must write every metric the dashboards read, on every device, on every tick, in every phase including idle.** `hospital.device.online` (`verticals/healthcare/config.yaml:76-80`, `range: [0,1]`, `drift: 0.01`, no plugin) is the shipped proof of the failure: it is never 1 and never 0.

**Plugins**
- [ ] Subclass `IncidentPlugin` (`simulator/plugins/__init__.py:9-45`): `on_tick(tick_count, fleet, engine)` + `get_incident_name()`. Zero-arg constructor. **The root `README.md:743-770` documents a `setup/tick/get_phases` API that does not exist — ignore it.**
- [ ] `fleet` is typed `List[Dict]` but the engine passes `List[DeviceProfile]`. Use getattr-with-dict-fallback (`STYLE_GUIDE.md:807-817`). Two shipped plugins (manufacturing, insurance) are **completely dead** because they trusted the annotation.
- [ ] **Plugin exceptions are silently swallowed** — `simulator/engine.py:621-625` logs and continues. Grep simulator logs for `failed:` before trusting a cascade.
- [ ] **4-axis disjointness** (spatial / metric namespace / `incident_domain` value / temporal) documented as a 4-row docstring table (`STYLE_GUIDE.md:782-789`; the temporal rule "initial idle ≥ 50 ticks more than other plugins; inter-event idle ≥ 30 ticks more" is at `:789`). **Must include `verticals/_shared/plugins/identity_proxy_heap_leak.py`**, which `cli.py:636` loads unconditionally for every vertical. See §4 for how we satisfy the temporal axis (profile exclusion, documented — not tick spacing).
- [ ] **Hold explicit baselines during the normal phase** — and, per the midpoint rule above, during idle and on non-targeted devices too (`verticals/healthcare/overlays/adventhealth/plugins/adventhealth_care_experience.py:111-120, 288-298`).
- [ ] Scope by a **wide** dimension. A narrow spatial filter mutates ~1 of N devices and drowns in drift (same file, lines 25-33).
- [ ] Plugins can write **logs**: `incident_state[<name>]["tx_logs"]` is drained by `_emit_incident_tx_logs` (`engine.py:824-840`) inside the active service span, so trace-log correlation is automatic. Use it for the field-gateway root-cause log line and for the SDS-maskable content.

**Gates / definition of done** (`AGENTS.md:84-91`)
1. `pytest` passes. **NOTE: it is RED today** — `tests/test_config.py:176` asserts exactly 5 verticals, the loader returns 6. Fix in Phase 0/1.
2. `black --check`, `isort --check-only`, `flake8 --max-line-length=100 --extend-ignore=E203,W503` clean over `dd_demo_toolkit dd_demo_toolkit_ui`. **NOTE: unachievable today** — `pyproject.toml:109 [tool.isort]` declares `multi_line_mode`, an invalid key that crashes isort with `UnsupportedSettings`. The real key is `multi_line_output`. Fix in Phase 0.
3. `dd-demo validate --vertical oilgas` → 0 errors **plus the ConfigLoader/SimulatorEngine smoke call and the three auto-enrolling tests** (see above). Item 3 alone is not a gate.
4. Hermetic offline regression test for new behavior (models: `tests/test_dashboard_list_grouping.py`, `tests/test_monitor_teardown_synthetics.py`, `tests/test_fleet_location_distribution.py`).
5. No secrets, no new tag keys, no unrelated churn. One logical change per PR (`CONTRIBUTING.md:44`).
6. **New rule class learned → add it to `STYLE_GUIDE.md` in the same PR** (`CLAUDE.md` §0, `CONTRIBUTING.md:47`). `STYLE_GUIDE.md` currently has **zero** rules for: boolean-state metric naming, midpoint seeding, services-without-operations, per-entry location placement, cardinality budgeting, LLM Obs, log-based assets, timestamps/backfill, or simulated external SaaS. We will learn at least five of those.

**UI-first** (`CLAUDE.md` §0.6, lines 79-84)
- [ ] Every SE-facing capability ships a UI surface — "a `server.py` endpoint + a control in `static/`, not a CLI-only command." Precedent already exists: `GET /api/doctor` (`server.py:713`), `GET /api/validate` (`server.py:737`). **This applies to the Phase 1 verification harness and the Phase 2 readback**, both of which get an endpoint + button, implemented as importable functions the CLI wraps.
- [ ] `make ui` is the front door. Never instruct `make build`/`make setup` — **fix the flow instead**.
- [ ] Any side process needs a `PROCESS_DEFS` entry (`compose_reconcile: False` for non-compose children, per `dd_demo_toolkit_ui/process_supervisor.py:135-179`) **plus** a row in `static/index.html` **plus** the name in `static/app.js`. `docker/mc_apple_mdes/` skipped this and is a standing violation.

**Hardcoded lists that must be updated for a 7th vertical — twelve, not eight**

Toolkit-relative: `tests/test_config.py:176` (`assert len(verticals) == 5` → 7; the `expected` list at `:177` is a subset check and passes as-is) · `CLAUDE.md:120-121` · `dd-demo-toolkit/README.md:96-99` · `.env.template:65` · `STYLE_GUIDE.md` §1.9 env_prefix table.
Repo-root: `.github/workflows/ci.yml:96` (matrix) · `.github/ISSUE_TEMPLATE/bug.yml:10-16` (a `required: true` dropdown — nobody can file a bug against oilgas today) · `CODEOWNERS` · root `README.md:336-345` · **`CONTRIBUTING.md:37`** (`for v in finance healthcare hospitality insurance manufacturing; do dd-demo validate …` — the copy-paste "run the same checks CI runs" block other SEs follow) · **`AGENTS.md:65`** (`dd-demo validate --vertical <finance|healthcare|hospitality|insurance|manufacturing>` — the first thing a coding agent reads) · **`SUPPORT.md:25`** (ownership table).

All twelve already omit `waste_management`. **The seven four-vertical arrays in `tests/test_config.py` (`:16`, `:34`, `:55`, `:72`, `:100`, `:143`, `:157`) are deliberate coverage of the original four, pass unchanged, and are out of scope** — except `:100`, which is the directory-name==`vertical.name` assertion and is worth extending so `oilgas` is actually covered by the rule §3 leans on.

---

## 3. Vertical design: oil & gas

**Name / prefix decision: `oilgas` used as directory name, `vertical.name`, AND `env_prefix` — one string.**

It matches the `^[a-z_][a-z0-9_]*$` pattern enforced at `tests/test_config.py:158`, is self-documenting in metric names, is RFC1123-safe (no underscore, so it can never crash the OTel exporter if it ever reaches `DD_HOSTNAME`), and is verified free — taken prefixes are `finserv`, `hospital`, `hospitality`, `insurer`, `mfg`, `wm` (plus `agri` on the unmerged `bunge-agribusiness` branch). Collapsing the three tokens removes a class of silent mismatch; note that the test which asserts directory == `vertical.name` covers only a hardcoded four-vertical list (`:100`), so we extend it.

**Display name:** `Upstream Oil & Gas` on the base vertical. **Not** "BPX" — customer nouns go in the overlay.

### File tree to create

```
verticals/oilgas/
  config.yaml            # vertical block, locations.dimensions, 5 device_categories, services[]
  services.yaml          # 5 Service Catalog entries
  monitors.yaml          # ~10 monitors, signal_chain 1..3, incident_domain:field-to-forecast
  slos.yaml              # 2 count-based SLOs over REAL counters (see below)
  notebooks.yaml         # 1 investigation notebook (PRE-GATE: markdown-only, NO tags: block)
  README.md              # SE bring-up runbook — modelled on DEMO_RUNBOOK.md
  sds.yaml               # post-gate, only if security has weight (§6 / §8 Q3)
  dashboards/
    oilgas-expert-answer-quality.json    # step 1
    oilgas-data-platform.json            # steps 2 + 3
    oilgas-field-connectivity.json       # steps 4 + 5
  plugins/
    field_to_forecast.py                 # ONE plugin, 6 phases, drives all five device groups
  overlays/                              # POST-GATE ONLY
    bpx.yaml
    bpx/
      monitors.yaml
      notebooks.yaml
      dashboards/*.json
```

**Explicitly NOT created:** `workflows.yaml`, `cases.yaml`, `incidents.yaml`, `dashboards.yaml`. `waste_management` ships none of these. `incidents.yaml` is a hard-coded no-op (`dd_demo_toolkit/resources/manager.py:352-355`) and `dashboards.yaml` is dead code — nothing reads it; `resources/dashboards.py:144` only globs `dashboards/*.json`.

**`README.md` is a new class of deliverable:** `find verticals -name "*.md"` returns nothing today — no vertical ships docs. Since §3's whole justification for the base/overlay split is reuse at the next E&P account, and distribution is contribute-back-via-PR (`GA_ROADMAP.md:58-60`), the next SE must not inherit a 6-phase plugin, a navigation ban and no instructions. Model on `DEMO_RUNBOOK.md` (AdventHealth): prerequisites, deploy order, the 11-minute phase timeline with expected values per phase, the /data-obs navigation ban and why, the synthetic-data disclosure script, teardown, and known limitations (no NDM, no Data Catalog, `DD_HOSTNAME` per R13). The §8 capability table folds into it. Adding "every new vertical ships a README" to STYLE_GUIDE is one of the DoD #6 contributions.

### `config.yaml` model

**Locations — one dimension, and here is why.**

`engine.py:441-447` computes `location = {name: vals[i % len(vals)] for name, vals in dim_values}` where `i` iterates `range(count)` **within a single device entry**. Verified in-process against the earlier draft of this config: the 6 field gateways spread one-per-pad correctly, but `step pads: {'pad-a': 28}` — every `count: 1` device lands on `values[0]` of every dimension. That silently pinned all 28 pipeline steps, the warehouse, the handoff node and all three Expert models to the same pad the outage targets. WM's `AirflowDAG` entry looks healthy only because it is `count: 4`, not 28×1.

The fix is to make `values[0]` **truthful for every singleton** and to carry the pad in the one entry that has a real count:

```yaml
locations:
  dimensions:
    - name: site
      values:
        - central-ops          # values[0] — where every singleton legitimately lives
        - permian-pad-a
        - permian-pad-b
        - eagle-ford-pad-c
        - eagle-ford-pad-d
        - haynesville-pad-e
        - haynesville-pad-f
```

One dimension, seven values. `field_gateway` is declared as **one entry with `count: 7`**, so `i % 7` covers every site exactly once — six well-pad gateways plus the central-ops aggregation gateway. Every other device (28 steps, 1 handoff, 1 warehouse, 3 eval nodes) is `count: 1` and therefore lands on `site: central-ops`, which is *correct*: the pipeline, the warehouse and the chatbot do live at central ops. Basin is readable inside the site name, so there is no second dimension to fall out of sync. **No `environment_topology`, no `region`/`environment` dimension** — not because it is dead config (it is read at `engine.py:288` and consumed at `:401-404`, and exercised by `tests/test_fleet_location_distribution.py:28,:72`) but because we declare no `environment` dimension for it to constrain.

**Harness assertion (Phase 1):** for every `device_type`, the emitted `site` distribution matches the declared intent — 7 distinct sites for `field_gateway`, exactly `central-ops` for everything else.

**Device categories and metrics.** Every metric declares an explicit `range`. `drift: 0` on anything that must be an exact integer or boolean; the plugin holds the baseline on **every device, every tick, every phase, including idle**. No percentile aggregators consume any of these.

| Category | Device type | count | Metric (range, drift) |
|---|---|---|---|
| `field_edge` | `field_gateway` | **7** (one entry) | `oilgas.field.link_up_state` ([0,1], 0 — plugin writes 1.0 to all 7 every tick, 0.0 to the target during outage) · `oilgas.field.records_received_per_min` ([0, 900], 0 — plugin holds ~720) · `oilgas.field.backhaul_latency_ms` ([25, 400], 4) · `oilgas.field.failover_engaged_state` ([0,1], 0 — plugin writes 0.0 every tick to all 7; **the damning finding is that it never rises**) · **counters** `oilgas.field.link_ticks_total` ([1,1], 0) and `oilgas.field.link_down_ticks_total` ([0,0], 0 — plugin lifts the target device's state to 1.0 during outage) |
| `handoff` | `handoff_node` | 1 | `oilgas.handoff.records_out_count` ([0, 5200], 0) · `oilgas.handoff.records_in_count` ([0, 5200], 0) |
| `nightly_pipeline` | `pipeline_step` ×28 | 1 each | `oilgas.pipeline.rows_in_count` ([0, 5200], 0) · `oilgas.pipeline.rows_out_count` ([0, 5200], 0) · `oilgas.pipeline.step_status_state` ([0,1], 0 — plugin writes 1.0 to all 28 every tick) · `oilgas.pipeline.step_duration_sec` ([5, 240], 0) |
| `warehouse` | `warehouse_node` | 1 | `oilgas.warehouse.rows_loaded_count` ([0, 5200], **0**) · `oilgas.warehouse.table_freshness_min` ([0, 720], 0) · `oilgas.warehouse.null_row_pct` ([0, 40], 0) · `oilgas.warehouse.query_queue_depth_count` ([0, 60], **0**) |
| `expert_eval` | `expert_eval_node` ×3 | 1 each | `oilgas.expert.answer_confidence_ratio` ([0, 1], 0) · `oilgas.expert.grounding_score_ratio` ([0, 1], 0) · `oilgas.expert.stale_input_rate_pct` ([0, 100], 0) · **counters** `oilgas.expert.answers_total` ([40, 60], 0 → ~50/tick) and `oilgas.expert.low_confidence_answers_total` ([0, 4], 0 → 2/tick baseline ≈ 4%) |

Every `_count` metric carries `drift: 0` — including the two warehouse counts, which is where the fractional-row-count version of the "hopper load 65.28475%" bug would otherwise appear. Display-side, every count/percent `query_value` widget sets `"precision": 0` (`STYLE_GUIDE.md:454`). **Harness assertion: no metric whose name ends `_count` or `_total` has non-zero drift.**

The 28 `pipeline_step` entries each carry `manufacturer: Custom` and a distinct `model:` — `step-01-raw-land`, … `step-14-thirdparty-signal-ingest`, … `step-28-publish-forecast-mart`. That `model:` surfaces as the `device_model` tag, giving 28 named series from one `by {device_model}` split. **Generate these 28 blocks with a committed script under `scripts/`, not by hand** — 28 × 4 metrics is 112 timeseries of hand-maintenance otherwise, and the generator also emits the plugin's baseline table so the two can never drift apart.

The three `expert_eval_node` devices carry BPX's actual model stack (per the May prep brief: Xpert is Bedrock + Claude 3): `claude-3-bedrock`, `claude-3-5-bedrock`, `gpt-4o-azure`.

**Services — every entry needs `language:` as a real key and a non-empty `operations:` list.** Verified against the real loader: a block declaring only `name` (with `language` as a trailing YAML comment) raises `ConfigError: Service at index 0 missing required field 'language'` and the vertical does not load at all. And an *empty* `operations: []` loads clean but produces nothing, because `_generate_service_trace` early-returns at `engine.py:707-709` before the spans, the logs, the `oilgas.app.*` counters (`:789-800`) and the cross-service `peer.service` edge (`:807-813`). Shape copied from `verticals/waste_management/config.yaml:332-415`:

```yaml
services:
- name: expert-api
  host: expert-api-01
  language: python
  framework: FastAPI
  operations:
  - name: "POST /api/expert/ask"
    latency_base_ms: 1400
    latency_p99_ms: 3800
    error_rate: 0.011
  - name: "GET /api/expert/citations"
    latency_base_ms: 180
    latency_p99_ms: 620
    error_rate: 0.004
  dependencies:
  - service: warehouse-loader
    operation: "query_forecast_mart"
    probability: 0.85

- name: warehouse-loader
  host: warehouse-loader-01
  language: python
  framework: SQLAlchemy
  operations:
  - name: "query_forecast_mart"
    latency_base_ms: 240
    latency_p99_ms: 900
    error_rate: 0.003
  - name: "load_nightly_batch"
    latency_base_ms: 3100
    latency_p99_ms: 7400
    error_rate: 0.002

- name: pipeline-orchestrator
  host: pipeline-orch-01
  language: python
  framework: Airflow
  operations:
  - name: "run_nightly_forecast_dag"
    latency_base_ms: 2600
    latency_p99_ms: 6800
    error_rate: 0.002
  dependencies:
  - service: thirdparty-signal-api
    operation: "POST /v1/signal-batch"
    probability: 0.8
  - service: warehouse-loader
    operation: "load_nightly_batch"
    probability: 0.9

- name: thirdparty-signal-api
  host: signal-vendor-edge-01
  language: java
  framework: SpringBoot
  operations:
  - name: "POST /v1/signal-batch"
    latency_base_ms: 310
    latency_p99_ms: 1100
    error_rate: 0.0          # innocent hop — absence of signal is the evidence
  - name: "GET /v1/signal-batch/{id}"
    latency_base_ms: 90
    latency_p99_ms: 300
    error_rate: 0.0

- name: field-ingest-gateway
  host: field-ingest-01
  language: go
  framework: gRPC
  operations:
  - name: "ingest_wits_frame"
    latency_base_ms: 45
    latency_p99_ms: 210
    error_rate: 0.006
  dependencies:
  - service: pipeline-orchestrator
    operation: "run_nightly_forecast_dag"
    probability: 0.3
```

Notes: `error_rate: 0.0` on `thirdparty-signal-api` is what makes "error rate flat throughout" literally true rather than an assertion. Every dependency declares an explicit `operation:` — `_normalize_dependencies_config` (`engine.py:198-204`) defensively rewrites a missing one to `""`, which does not crash but produces a nameless span with `http.url=""`, and hop 4 asks the SE to open that service page. **Do not declare `language: nodejs`** — `_DOWNSTREAM_TEMPLATES` (`engine.py:244-260`) supports only java/dotnet/python/go/swift, and nodejs silently produces no child spans (a live bug in `waste_management`'s `my-wm-portal`).

**Phase 1 exit check:** `oilgas.app.requests_total{service_name:thirdparty-signal-api}` returns points before any hop-4 widget is built.

**Explicitly omitted from config.yaml:** `environment_scale` (silent killer, §2); `environment_topology` (**not dead — read at `engine.py:288`, used at `:401-404`, tested at `tests/test_fleet_location_distribution.py:28,:72` — omitted because we declare no `environment` dimension for it to constrain**); `ip_base` / `pinned_devices` / `line_pool` (genuinely dead — repo-wide grep finds no readers); `emit_interval_sec` (no product-code reader, test fixture only).

### Custom-metric volume and who pays for it

Not previously assessed anywhere in this plan or in the repo (`grep -i 'cost\|cardinality\|billing\|quota'` over `STYLE_GUIDE.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `GA_ROADMAP.md` returns only `CLAUDE.md:500`, about fleet placement).

Cardinality is per-device, not per-model: `_emit_device_metrics` (`engine.py:665-693`) attaches `device_id`, `device_type`, `device_manufacturer`, `device_model`, `device_firmware`, `category`, `battery_powered`, plus every location dimension and `service` to every emission — all constant per device, so one series per (metric, device).

| Group | Series |
|---|---|
| `field_gateway` 7 × 6 metrics | 42 |
| `pipeline_step` 28 × 4 | 112 |
| `handoff_node` 1 × 2 | 2 |
| `warehouse_node` 1 × 4 | 4 |
| `expert_eval_node` 3 × 5 | 15 |
| `oilgas.app.*` 3 × 5 services (only `service_name`) | 15 |
| **Phase 1 total** | **~190 custom timeseries** |

Phase 3 adds 28 spans per simulated nightly run, real LLM Obs spans, and one container stack. **This goes in the Phase 0 gate packet alongside the capability table, with a named answer to "which org absorbs it."** A cardinality-budget rule is one of the DoD #6 STYLE_GUIDE contributions.

### Where the customer overlay sits

`verticals/oilgas/overlays/bpx/`, built **only after the gate**. It carries: the correct Xpert/Expert spelling, real BPX site identifiers, the Fabric orchestrator, and a BPX `team:` roster (new **values** under the existing key — new keys are forbidden). This is the sanctioned pattern (`CLAUDE.md` §6, precedent `verticals/finance/overlays/ey/`), it costs nothing structurally, and it means the base vertical is reusable at the next E&P account — which matters given Bryan has already offered to make the brief external-facing (Slack DM `D0AL9GJB49G`, 2026-08-05 17:49:35).

---

## 4. Simulation architecture

### The timeline problem — solved by compression, not backfill

The narrative is: outage 02:15–02:45 → overnight 28-step run → morning wrong recommendation. Three verified facts kill backfill:

1. **Nothing in the repo writes past-timestamped telemetry on the OTel path.** `gauge.set()` takes no timestamp (`engine.py:688-693`); spans are created without OTel's optional `start_time` (`engine.py:753, 871, 916`); logs go through `LoggingHandler` stamped at emit (`utils/otel.py:154-169`); the meter exports on a fixed 15s `PeriodicExportingMetricReader` (`utils/otel.py:69-72`).
2. **The only timestamped writer is `DatadogAPIClient.submit_series()`** (`utils/dd_api.py:885-909`, `POST /api/v2/series` with explicit per-point `timestamp`) — and **both** of its callers hardcode `ts = int(time.time())`: `docker/waste_management/dd_emitter.py:124` and `docker/waste_management/backend_servers.py:120`.
3. **Datadog's historical-acceptance window is UNVERIFIED in this repo.** Commonly cited as ~1h past for metrics and ~18h for logs, but nothing here tests it.

**Decision: compress the overnight run into the live cascade.** The plugin's six phases play out over **13 minutes** (see the corrected arithmetic below), plus a 1.5–2.5 minute initial idle. The notebook narration says "the 02:15 window" while the charts show the last hour.

**Say it once, out loud:** "this is the same sequence compressed into a quarter of an hour so you can watch it happen." That is cheaper and far safer than building a backfill emitter against an unverified window. **If the demo genuinely requires a T-8h timeline** (only if a customer insists), that is a new one-shot tool on `submit_series()` plus an empirical acceptance test: **+1.5 SE-days and a real risk of silent point rejection.**

### Re-running the cascade — a first-class requirement, not an afterthought

Time-compression means the whole narrative lives in the trailing ~13 minutes of live data. Today there is no way to replay it: `dd_demo_toolkit_ui/server.py` exposes only `/api/processes/{name}/start` and `/stop` (`:490`, `:498`), `static/index.html` has rows only for `simulator`, `setup`, `teardown`, `teardown-all` and the five `wm-*` entries, and the plugin's idles are random. If the call starts twenty minutes late, or the customer asks to see it again, or a second call follows, the SE's only lever is stop-and-restart-and-wait.

**Phase 1 deliverable (0.5 day, inside the estimate):** a deterministic trigger. An `engine.incident_trigger: set` the plugin honours at the top of `on_tick`, a `POST /api/incident/{vertical}/trigger` endpoint, and a button in `static/index.html` + `static/app.js` — UI-first per `CLAUDE.md` §0.6. **Phase 2 exit criterion: the cascade re-triggered on demand twice within one simulator session.** Deploy-side reset is already handled — the compose `setup` service passes `--clean` (`docker-compose.yaml:67`) — so this is specifically about telemetry.

### The data gap — a measured deficit, not an absence

Two reasons we do **not** build emission suppression:

1. **Bits only auto-launches on a transition to ALERT** (UNVERIFIED-in-repo; see R4). Warn, no-data, renotification and test notifications do not trigger it. A network outage naturally produces no-data — a literal telemetry hole would *prevent the investigation from starting*.
2. The change is real but unnecessary. For the record it is ~4 lines: an `engine.suppressed_device_ids: set` checked at the top of `_emit_device_metrics` (`engine.py:665-693`, currently unconditional). **Only gauges gap** — OTel `_LastValueAggregation.collect()` returns None and nulls when unset (verified in the installed opentelemetry-sdk 1.41.1), while Counter/Histogram are CUMULATIVE and keep re-exporting. And it must **never** be implemented by mutating `device.metrics`: that list and its `MetricConfig` objects are **shared across every instance of a device entry** (`engine.py:428-469`; `d0.metrics is d1.metrics` is True), so it would silently gap the whole fleet.

**Instead:** `oilgas.field.link_up_state` → 0 at one site (an ALERT-triggerable threshold breach) and `oilgas.field.records_received_per_min` → ~0 (a measured deficit). Both fully queryable, both fully alertable.

If asked "if the site was offline, why is Datadog still getting metrics?" — the gateway is up, the **cellular backhaul** is down. `link_up_state: 0` is the gateway reporting its own uplink state over the surviving path. That is how real edge telemetry behaves and it is a stronger story than a blank chart.

### Component mechanics

- **Field outage** — seven `field_gateway` devices, one per `site` (one entry, `count: 7`). Plugin scopes to one site *and* `device_type:field_gateway`. All seven get `link_up_state = 1.0` and `failover_engaged_state = 0.0` written **every tick**; during the outage phase the target flips to 0.0 and its `link_down_ticks_total` state lifts to 1.0.
- **Root-cause log line** — the plugin appends to `incident_state['field-to-forecast']['tx_logs']` targeting `field-ingest-gateway`: a warning naming the site, the uplink carrier, the failover state, and (deliberately) a well coordinate, a lease identifier and a contractor ID. `_emit_incident_tx_logs` (`engine.py:824-840`) writes it inside the active span, so it is trace-correlated, Bits-readable, **and** it is the content `sds.yaml` masks. This is what turns the Phase 3 SDS item from a no-op into a real demo.
- **Third-party handoff** — real Service Map edge from `peer.service` on the engine's cross-service span (`engine.py:891-925`), plus `records_out_count` / `records_in_count` matching exactly while OUT is already 30% short. The vendor returned everything it was given, and `error_rate: 0.0` makes the flat error rate true rather than lucky.
- **28-step pipeline** — 28 devices × 4 metrics. The plugin holds the baseline on steps 1–13 as well as the shorted 14–28; otherwise the toplist shows 28 bars all at their midpoints and step 14 is not visibly short. **Post-gate upgrades:** either a real ddtrace orchestrator emitting one trace per nightly run with 28 named child spans (step 14 records a span **event** and a warning log but does **not** set error, so "all 28 steps completed, no errors" is literally true in the APM UI), or a reskin of `data_obs/` for genuine DSM pathway lineage. Costed separately in §7.
- **Snowflake** — `warehouse_node` gauges + a `warehouse-loader` service with real operations. Metrics stay inside `oilgas.*`.
- **Expert** — Tier A (core): three eval-node devices driven **down in lockstep**; that lockstep is the "is it the AI? no" beat, lifted from `verticals/waste_management/notebooks.yaml:68-74`. Tier B (post-gate, +2 SE-days): real `ddtrace.llmobs` from `wm_agentic_demo/wm_ops_agent.py`, with the retrieval span modelling a **warehouse query** (`database`, `schema`, `table`, `query_id`, `rows_returned`, `rows_expected`, `partition_watermark`) rather than a vector KB, plus new evals `retrieval_coverage`, `input_freshness_ok`, `abstention_correct`, `answer_correctness`. Nothing in the repo scores "answered anyway despite insufficient input" today; those four turn the wrong-answer beat from an assertion into a measurement.

### The plugin

One `IncidentPlugin` at `verticals/oilgas/plugins/field_to_forecast.py`. Six phases at 15s/tick (`EMIT_INTERVAL=15`, `.env.template:112`, read at `cli.py:618`):

| Phase | Ticks | Elapsed | What moves |
|---|---|---|---|
| normal | — | — | all baselines HELD explicitly on all 40 devices |
| field_outage | 8 | 2:00 | `link_up_state`→0, `records_received_per_min`→0, `failover_engaged_state` stays 0 at one site; `link_down_ticks_total` state →1 |
| gap_in_flight | 6 | 1:30 | handoff `records_out_count` drops ~30% |
| pipeline_runs_anyway | **8** | 2:00 | steps 14–28 `rows_in/out` short; `step_status_state` held at 1 on all 28 |
| warehouse_loaded_short | 6 | 1:30 | `rows_loaded_count` short, `table_freshness_min` climbs, `null_row_pct` rises |
| expert_wrong | **10** | 2:30 | all three models' confidence/grounding drop **in lockstep**; `low_confidence_answers_total` state → ~20/tick |
| recovery | **6** | 1:30 | everything decays back |
| **total** | **44** | **11:00** | |

**Arithmetic corrected.** The earlier draft's 8+6+10+6+12+10 = 52 ticks × 15s = **13:00**, not the "~11 min" it claimed. Rather than restate the budget, the phases above are shortened to hit a true 11:00, and that number is what the Phase 2 timing rehearsal and the "start the simulator ~3 minutes before the call" guidance are budgeted against.

Initial idle `random.randint(6, 10)` ticks (1.5–2.5 min); inter-event idle `random.randint(60, 90)` so it does not re-fire mid-conversation; plus the on-demand trigger above. Publishes `engine.incident_state['field-to-forecast'] = {phase, phase_tick, incident_domain, signal_chain_root, site, tx_logs}`.

**4-axis disjointness vs `verticals/_shared/plugins/identity_proxy_heap_leak.py`** — which `cli.py:636` loads unconditionally for every vertical. `STYLE_GUIDE.md:789` requires "initial idle ≥ 50 ticks more than other plugins"; the shared plugin uses `random.randint(18, 24)` with a 40-tick event window (`identity_proxy_heap_leak.py:38-45`), so satisfying that literally would mean an initial idle ≥ 74 ticks (18+ minutes of dead air before the demo starts) — unacceptable. **We take a documented exemption instead, and the docstring table says so explicitly rather than claiming spacing it does not have:** the shared plugin's `on_tick` (`:60-100`) writes only `/cascade-state/identity-proxy-phase.json` and `engine.incident_state['identity-proxy']` — **it mutates no device metric and emits no telemetry of its own.** Its telemetry comes from the `identity-proxy-jvm` container, which is gated behind the `mock-app` compose profile (`docker-compose.yaml:1008-1009`). With that profile down there is nothing for Bits to confuse. **Phase 2 pre-demo checklist gains: confirm the `mock-app` profile is not running (`DD_DEMO_MOCK_FLEET` not `true`).**

### Housekeeping that is actually a core change, not housekeeping

Gating off the simulator's generic LLM Obs and RUM submitters is **not** a vertical-local edit — there is no gate to flip. `SimulatorEngine.__init__` constructs both unconditionally inside bare try/except: `LLMObsSubmitter(endpoint=…, vertical_name=…)` at `engine.py:344-359` and `RUMSubmitter(meter=self.meter)` at `engine.py:362-368` — the latter taking no vertical argument at all, so there is nothing to branch on. Repo-wide grep for `ENABLE_RUM|RUM_ENABLED|LLMOBS_ENABLED|ENABLE_LLM|DISABLE_RUM|DISABLE_LLM` returns nothing. And `llm_obs.py:1014-1069` selects its scenario library by reassigning **module-level globals**, with an unrecognised vertical falling through to `ml_app: ai-assistant` (`:1064-1068`) and enterprise-support scenarios — in a demo about an AI chatbot, a stray `ai-assistant` ml_app in the LLM Obs list is a liability. Meanwhile `RUMSubmitter.__init__` (`rum.py:346-372`) creates ~18 `hospitality.rum.*` gauges on the shared meter regardless of vertical.

**Therefore:** a separate pre-Phase-1 core PR, **0.5 SE-days, budgeted outside the Phase 1 estimate**. Add opt-out keys to config (`simulator: {llm_obs: false, rum: false}`), read them in `SimulatorEngine.__init__` before constructing either submitter, default to today's behaviour so all six existing verticals are unchanged, ship a hermetic test asserting `engine.llm_obs is None` / `engine.rum is None` for a tmp_path config with the flags off (DoD #4), and add a regression check that finance's `risk-eval-agent`, healthcare's `ai-care-companion` and hospitality's `ai-stay-planner` LLM Obs traces still fire. One logical change, one PR (`CONTRIBUTING.md:44`), one new STYLE_GUIDE rule class (DoD #6).

---

## 5. The investigation walk

**What Bits can and cannot do here — stated plainly, and marked for what it is.** Bits' documented data sources (Metrics, APM traces, Logs, Dashboards, Events, Change Tracking, GitHub source, Watchdog, RUM, Network Path, DBM, Continuous Profiler), its supported monitor types (Metric, Anomaly, Forecast, Integration, Outlier, Logs, APM-metrics, Composite, SLO, Synthetics — **not `data-quality alert`**), and the ALERT-transition-only auto-launch behaviour are **all UNVERIFIED-in-repo**: there is no Bits documentation, skill file or test in this tree that states them. They come from Datadog's public docs. They are folded into R4 alongside the other Bits unknowns. The design conclusion — project every hop into metrics and logs, rehearse rather than promise — is the right call regardless of whether the source list is exactly twelve. Separately, the Bits MCP tools (`trigger_bits_ai_investigation`, `get_bits_ai_investigation`) are documented in the `datadog/advanced-products` skill but **are not exposed in this session** — Bits must be driven live in the UI and cannot be scripted.

**Consequence for the design:** every hop is projected into metrics **and logs** (and, post-gate, APM traces) that Bits can traverse. The rich surfaces are the human's click-through. **Do not promise an end-to-end autonomous walk until it has been rehearsed** — acceptance bar in §7.

| # | What the SRE does | Datadog surface | Telemetry required | Asset we build |
|---|---|---|---|---|
| **1** | "Is it the AI?" Expert regressed — but all three models regressed **together**, ruling out model and prompt. | Dashboard `Expert — Answer Quality`: 4 `query_value` KPIs with 3-tier conditional formats and `"precision": 0`, one timeseries `avg:oilgas.expert.answer_confidence_ratio{device_type:expert_eval_node} by {device_model}` with a threshold marker, one `query_table` across the three models. *(Post-gate: the LLM Obs trace with the warehouse-shaped retrieval span, as a human aside.)* | The three eval gauges + two counters on three `expert_eval_node` devices with distinct `device_model`. Plugin holds all three at baseline during normal AND idle, and drops them together in `expert_wrong`. | `dashboards/oilgas-expert-answer-quality.json` — find-and-replace clone of `verticals/waste_management/dashboards/wm-agent-eval-scorecard.json` (11 widgets, already correct: `by {device_model}`, `$device_model` template var, no top-level `tags`). Plus the **trigger monitor** on `oilgas.expert.answer_confidence_ratio`, tagged `signal_chain:3-symptom`. |
| **2** | "Is the data in the warehouse bad?" Last night's load is short and the mart is stale. | Top group of `Data Platform`: `rows_loaded_count` with a marker at expected nightly volume, `table_freshness_min` with an SLA marker, `null_row_pct`. **Navigation rule: do not open /data-obs or the Data Catalog — unless the pre-Phase-1 dbt spike lands (see §7), in which case this hop upgrades to real dbt freshness/tests/lineage.** | The four `oilgas.warehouse.*` gauges, all `drift: 0` on the two counts. Warehouse and Expert move **together** — no lag; the warehouse IS Expert's input. | Top widget group of `dashboards/oilgas-data-platform.json`. Layout cloned from the "Data lineage — upstream of the eval set" row in `verticals/finance/overlays/ey/dashboards/ey-llm-eval-scorecard.json:155-199`, which already pairs eval widgets with upstream pipeline health on one board. Monitor tagged `signal_chain:2-leading-indicator`. |
| **3** | "Did the pipeline fail?" No. All 28 steps `status:1`, zero errors — but step 14 took 30% fewer input records than step 13 emitted, and the deficit propagates to 28. | Second group of `Data Platform`: toplist of `avg:oilgas.pipeline.rows_in_count{device_type:pipeline_step} by {device_model}` (28 bars, step 14 visibly short) · `query_value` of `min:oilgas.pipeline.step_status_state` reading 1 · timeseries of steps 12–16 · the `pipeline-orchestrator` service logs. *(Post-gate: the real 28-span trace waterfall, or the DSM pathway view.)* | 28 `pipeline_step` devices, `drift: 0` so row counts are exact integers, **and the plugin holding steps 1–13 at baseline and all 28 `step_status_state` at 1.0 every tick.** | Second widget group + the 28 generated device blocks + a row-count-continuity monitor tagged `signal_chain:2-leading-indicator`. |
| **4** | "Did the third party fail?" No. Outbound at step 12 was already 30% smaller; the return at 15 matched it exactly. | APM Service Map edge + the `thirdparty-signal-api` service page (real operations, real spans, real `oilgas.app.*`), plus a two-formula chart of `records_out_count` and `records_in_count`. | `services:` entry with `operations:` and a probabilistic dependency carrying an explicit `operation:` (drives `oilgas.app.*`, the service logs and the `peer.service` edge) + the two handoff gauges. `error_rate: 0.0` throughout — absence of signal is the evidence. | `services:` block + `services.yaml` catalog entry + 2 widgets. **No monitor** — an innocent hop should not have a firing alert. |
| **5** | **ROOT CAUSE.** The site's cellular backhaul dropped ~30 min and Starlink failover never engaged. | Dashboard `Field Connectivity`: `min:oilgas.field.link_up_state{device_type:field_gateway} by {site}` (six sites at 1, one at 0) · `records_received_per_min by {site}` · `failover_engaged_state` flat 0 at the affected site (the second, damning finding) · `backhaul_latency_ms` · **the plugin-written `field-ingest-gateway` warning log**, trace-correlated. | Seven `field_gateway` devices from one `count: 7` entry, spread one-per-site. **Not** NDM — say so. | `dashboards/oilgas-field-connectivity.json` (~8 widgets) + the `signal_chain:1-root-cause` monitor. **The monitor MESSAGE is a first-class deliverable** — per Datadog's Bits knowledge-source docs, monitor-message troubleshooting text is the primary lever for steering an investigation. It names the site, the 30-minute window, the failed failover, and links the notebook. |

**Always filter by `device_type:` before grouping by `site`.** The `site` dimension is only multi-valued for `field_edge`; every other device sits at `central-ops` by design (§3).

**SLOs — two, both over real counters.** A count-based SLO over a gauge deploys with a 200 and shows no data, which is exactly the R14 failure mode. `oilgas.app.requests_total`/`errors_total` carry only `service_name` (`engine.py:789`) and cannot be split by site, step or model, so they are not enough. Hence the two purpose-built counter pairs declared in §3:
1. **Field uplink availability** — `(sum:oilgas.field.link_ticks_total{...}.as_count() - sum:oilgas.field.link_down_ticks_total{...}.as_count()) / sum:oilgas.field.link_ticks_total{...}.as_count()`.
2. **Expert answer confidence** — `(sum:oilgas.expert.answers_total{...}.as_count() - sum:oilgas.expert.low_confidence_answers_total{...}.as_count()) / sum:oilgas.expert.answers_total{...}.as_count()`.

**Bits enablement — three named deliverables, not a hope:**
1. **`bits.md`** in the vertical — tagging conventions, the five-hop service topology, and a glossary (pad, NPT, WITSML, mudlog, tour). This exists for **no vertical today**.
2. **First-look troubleshooting text written into every monitor message**, with links to the specific dashboard and notebook.
3. **Trigger monitors of supported types only.** The outage is a threshold breach on a liveness gauge, never an absence.

---

## 6. Secondary demos

### (1) IoT sensor failure — **KEEP, 0 SE-days**

**First, correct the brief.** The AoP brief says this maps to "an EXISTING hospital smart-bed Wi-Fi demo." **That demo does not exist.** Verified:
- `verticals/healthcare/plugins/wifi_cascade.py` targets **infusion pumps** and **wireless APs** on Floor 3 / East. `get_incident_name()` returns "Floor 3 East WiFi AP Outage → Infusion Pump Cascade"; `_matches_target` is only ever called with `"infusion_pump"` (line 82) and `"wireless_ap"` (line 84).
- `smart_bed` (Hill-Rom Centrella, count 30) exists at `verticals/healthcare/config.yaml:185-251` emitting `hospital.bed.*` on pure random walk, driven by **no plugin at all**.
- `verticals/healthcare/dashboards/dashboard-nursecall-beds.json` is an 18-widget BI board with no incident, no cascade, no root cause. *(It also has uncommitted working-tree edits right now — two widgets re-grouped from `by {call.type}` to `by {department}`, a partial fix for a phantom tag. Any reuse must be based on the working-tree version, not HEAD.)*

**This must be corrected with Bryan before it reaches a customer deck.**

The good news: what *does* exist is a better fit than smart beds would have been. `wifi_cascade.py` is a 4-phase staggered-causality cascade whose entire design point is the temporal lag that lets RCA infer direction (docstring lines 15-17), with a per-device staggered drop (`1.0 if phase_tick < i else 0.0`, line 251).

**Recommendation: build nothing new.** The primary demo's `oilgas.field.*` layer with its own `Field Connectivity` dashboard **is** the IoT-sensor-failure story (gateway link degrades → sensor records stop → downstream starves), and it stands alone as an asset the SE can open without touching the pipeline narrative. That satisfies the SE's "no scripted demo flows" preference directly.

*If a genuinely independent second cascade is demanded post-gate:* port the **shape** (not the assets — it is `hospital.*`-namespaced and not a `_shared` plugin) into `verticals/oilgas/plugins/wellhead_radio.py`, honouring 4-axis disjointness from the primary. **+1.5 SE-days.**

### (2) AWS scaling-policy change → batch delay — **KILL, on narrative grounds**

**Correction to the earlier rationale.** The previous draft justified the kill partly by claiming `system.*`/`kubernetes.*` "need an Agent the simulator does not have." That is false and must not reach a customer-facing capability table: `docker/waste_management/dd_emitter.py:81-90` (`_system_signals`) synthesizes `system.cpu.user`, `system.load.1` and `system.mem.pct_usable` and posts them through `submit_series()` with `resources: [{"name": host, "type": "host"}]` — no Agent involved. That is exactly how the WM fleet-at-scale demo materializes hosts in the Host Map, and the same path would accept `aws.*`-shaped series. So an AWS lane is *buildable*, at roughly +1 SE-day (a step-change gauge `oilgas.compute.asg_desired_capacity` stepping immediately before `step_duration_sec` climbs — technique from `verticals/healthcare/overlays/quest/plugins/quest_hl7_config_cascade.py:375` — paired with a real Datadog **Event**, which IS a Bits source).

**Still recommend killing it.** BPX is ~100% AWS with 6,000+ Lambdas; a simulated scaling policy is the one lane most likely to invite "show me it against our account," which is a POV-shaped conversation, not a demo-shaped one. It also risks colliding temporally with the primary cascade and muddying a Bits investigation. Better to do four hops well. The kill is a judgement call about the conversation, not a capability limit — say it that way if asked.

### (3) Palantir silently-failing automation — **DEFER, hard-gated**

Zero Palantir references anywhere in the repo. The AoP brief itself makes it conditional (validation Q5: "Has anything changed with Palantir OTEL export? This was broken when Ustat left" — he said it produced "nonsense" data).

If Q5 comes back positive: `oilgas.palantir.last_success_age_min` climbing while `oilgas.palantir.runs_started_total` keeps incrementing — the automation reports itself running while producing nothing. Note a **true** silence is not natively expressible: counters are cumulative and re-export forever, so "stopped" must be a plugin writing 0 (the only place in the repo doing this is `verticals/healthcare/overlays/quest/plugins/quest_hl7_config_cascade.py:569`).

**Sequencing rule:** build it **last**, even on a positive answer. It inherits the same absence-modelling problem as the primary cascade, so building it early is *more* expensive, not less. A fourth concurrent `incident_domain` also materially degrades Bits' ability to isolate the primary story. **+0.5 SE-days, post-Phase-2 only.**

---

## 7. Phasing and sequencing

### Phase 0 — Pre-gate skeleton · **0.75 SE-days**

**Goal:** make the narrative openable in Datadog, lock the two irreversible decisions, and remove the build sprint's worst footguns — cheap enough that a "no" or a pivot is painless.

**Deliverables:**
1. `verticals/oilgas/config.yaml` — a *loadable* minimum: `vertical`, `locations` (the one `site` dimension), one `device_categories` entry, and a **real `services:` block** with `name`/`language`/`operations` on every entry (~40 lines). Enough for `ConfigLoader.list_verticals()` to register it and for it to appear in the `make ui` dropdown. **Locks `env_prefix` permanently.**
2. `verticals/oilgas/notebooks.yaml` — one `type: investigation` notebook, **markdown cells only, no `tags:` block**, six cells (symptom + one per hop), each closing in an explicit question for James. *Verified deployable:* `dd_demo_toolkit/validation/notebooks.py:52-55` only lints cells whose `definition.type == "timeseries"`, so markdown-only passes clean with no empty widgets.
3. **The honest capability table** (one page) — the security hedge, zero build. **Generated from `PRODUCT_CATALOG` (`server.py:98-165`, or `GET /api/products` at `:299`) by a small script under `scripts/`**, annotated with oilgas-specific detail, so it cannot drift from the toolkit's own truth. Ships with the custom-metric volume figure from §3.
4. Filled `.github/ISSUE_TEMPLATE/new-vertical.yml` for `oilgas`.
5. The sharpened questions (§8) to Bryan in Slack DM `D0AL9GJB49G` — he has already offered to meet James first.
6. **Toolkit fix, 30 min:** `--build` inserted **immediately after `"run"`** in the `setup` argv (`process_supervisor.py:97-101` → `["docker","compose","--profile","setup","run","--build","--rm","--remove-orphans","setup"]`) — appending it after `"setup"` passes it to the container as a command argument and silently does nothing. **Apply the same fix to the `teardown` entry immediately below**, which has the identical staleness bug: a teardown against the stale baked `verticals/` copy (`Dockerfile:16` `COPY verticals/ ./verticals/`, no bind mount) matches notebooks and cases against the OLD names and orphans the deployed copies. Requires Compose ≥ v2.13. One hermetic test asserting both argvs, using the existing monkeypatched-`PROCESS_DEFS` fixture at `tests/test_ui_supervisor.py:89-99` (DoD #4). The `simulator` `up` entry already has `--build` (`:88`).
7. **Fix `pyproject.toml:109 [tool.isort]`:** `multi_line_mode` → `multi_line_output`, as its own tiny PR. Until this lands, `isort --check-only` aborts and DoD #2 is unachievable by anyone.

**Exit criteria (all four, not just the first):**
- `dd-demo validate --vertical oilgas` → 0 findings. **This is an asset linter only** (`validation/runner.py:23,:34-42,:68-96`) and proves nothing about config.yaml.
- `python -c "from dd_demo_toolkit.config import ConfigLoader; from dd_demo_toolkit.simulator.engine import SimulatorEngine; SimulatorEngine(ConfigLoader('verticals').load_vertical('oilgas'))"` succeeds — this one call catches the services-block, location-distribution and midpoint-baseline classes in one shot.
- `pytest tests/test_config.py tests/test_validation.py` green (`test_validation.py:224-225`, `test_config.py:183`, `:221` all auto-enrol `oilgas`).
- `oilgas` in the `make ui` dropdown · notebook deploys from the UI Deploy button and opens cleanly · `isort --check-only` runs · gate packet with Bryan.

**Trigger for next phase:** written answers to Q1, Q3, Q4, Q7 (§8).

---

### Pre-Phase-1 — two things that do not wait on James · **1.0 SE-days**

1. **LLM Obs / RUM opt-out core PR — 0.5 day.** Scoped and justified in §4. Separate PR, hermetic test, regression check on the three existing LLM Obs verticals.
2. **dbt-on-Agent integration spike — 0.5 day. Hard dependency, owner: John Rath.** `dataobs` is `available: False` for a documented reason (`server.py:90-95`, `data_obs/dbt_runner/run_loop.sh` `report_artifacts()`): datadog-ci dropped the dbt plugin in v5 and the supported path is now the **Datadog Agent dbt integration**, which has never been configured here. `data_obs/dbt_project/models/sources.yml` already declares `loaded_at_field: received_at` with `warn_after: 30 minute` / `error_after: 90 minute` plus `not_null`/`unique` tests over real Postgres. **Outcome is binary and recorded either way:** if the artifacts land, hop 2 upgrades from a gauge imitation to real freshness/lineage/tests and R2 stops being the load-bearing weakness; if they do not, the /data-obs navigation ban stands as an evidenced decision rather than an assumption, and it goes in the vertical README with the reason.

---

### GATE — James Battraw priority confirmation · **0 build days, unbounded calendar risk**

**This is a real gate, and it is its own milestone with its own owner (Bryan).** Nobody starts Phase 1 until a meeting exists on a calendar. Scheduling realities: no BPX event through 2026-09-15; zero replies since 2026-07-30; Bryan proposed "the week of the 10th" to Brian Monroe but John has an all-day OOO starting 2026-08-10 (Yellowstone — Slack, 2026-07-31 09:59).

---

### Phase 1 — Core build: the five-hop metric + log plane · **6.5 SE-days (range 5.5–7.5)**

**Goal:** every hop is a real, queryable, alertable Datadog metric with a dashboard behind it, a monitor in front, a log line beside it, and one plugin makes them move in the right order — on demand.

**Deliverables:**
- **Prerequisite, sequenced first:** commit the untracked WM/MDES/agentic assets on a deliberate branch. `git ls-files dd-demo-toolkit/verticals/waste_management/` returns nothing today. Adding `waste_management` to the CI matrix or bumping the vertical count before that commit makes CI fail on a directory that does not exist in the checkout, and `tests/test_config.py:176` would pass locally at 7 while failing in CI at 5.
- Full `config.yaml`: 5 device categories, ~23 metric names with **explicit ranges on every one**, 28 generated pipeline-step blocks (via a committed `scripts/` generator that also emits the plugin's baseline table), five services each with `operations:`. No `environment_scale`; ranges spanning baseline-to-trough; `drift: 0` on every `_count`/`_total`/state metric.
- `plugins/field_to_forecast.py` — 6 phases totalling 44 ticks, **baseline holds on all 40 devices every tick in every phase including idle**, `tx_logs` for the root-cause log line, `incident_state` publication, deterministic-trigger support, and a 4-axis disjointness docstring table whose temporal row states the `mock-app`-profile exemption explicitly (§4).
- Deterministic re-trigger: engine hook + `POST /api/incident/{vertical}/trigger` + UI control (§4).
- 3 dashboards (`"precision": 0` on every count/percent `query_value`), ~10 monitors (single-threshold, `signal_chain` ladder, `incident_domain:field-to-forecast`, first-look troubleshooting text in every message), **2 count-based SLOs over the four purpose-built counters** (§5), `services.yaml`.
- Notebook upgraded: timeseries cells inserted between the Phase 0 markdown cells; every request with `formulas:` and `show_legend: true`; still no `tags:` block.
- **`verticals/oilgas/README.md`** — the SE bring-up runbook (§3).
- **`bits.md`** for the vertical.
- **Repo hygiene, in this order:** (1) commit the untracked assets; (2) update all twelve hardcoded lists from §2 with `oilgas` **and** `waste_management` — `.github/workflows/ci.yml:96`, `.github/ISSUE_TEMPLATE/bug.yml:10-16`, `CODEOWNERS`, root `README.md:336-345`, `CONTRIBUTING.md:37`, `AGENTS.md:65`, `SUPPORT.md:25`, `CLAUDE.md:120-121`, `dd-demo-toolkit/README.md:96-99`, `.env.template:65`, `STYLE_GUIDE.md` §1.9; (3) bump `tests/test_config.py:176` from 5 to 7 and extend the directory-name list at `:100`. The other six four-vertical arrays are intentional and out of scope.
- Wire `check_tags` into `validation/notebooks.py` (two lines + hermetic test + STYLE_GUIDE entry) so the WM notebook tag violations stop being invisible.
- **Products declaration:** state which `PRODUCT_CATALOG` keys `oilgas` lights up, so the vertical is ready for `products.yaml` / `dd-demo coverage` when that roadmap phase lands (`GA_ROADMAP.md`: the 90% GA target is measured by product modules, not vertical count).
- **The verification harness** (1 day of the 6.5, called out explicitly), shipped **UI-first** as `GET /api/harness` + a button in `static/index.html`/`app.js`, implemented as an importable function the CLI and a hermetic pytest both wrap (`CLAUDE.md` §0.6 lines 81-84; precedent `GET /api/doctor` at `server.py:713`, `GET /api/validate` at `:737`). It loads the merged config, builds the fleet in-process, dumps the emitted attribute set and observed range per metric, then asserts:
  - (a) every query string in every dashboard/monitor/SLO/notebook resolves to a declared metric and a tag key the engine actually emits (authoritative list: `engine.py:675-686`);
  - (b) every monitor threshold is reachable given the declared range;
  - (c) **every declared gauge's steady-state value equals its documented baseline, not its range midpoint** — the check that catches the 0.5-boolean class;
  - (d) **every declared service has ≥1 operation**;
  - (e) **the emitted `site` distribution per `device_type` matches the declared intent**;
  - (f) **no metric ending `_count`/`_total` has non-zero drift.**

**Reasoning on the 6.5-day estimate:** `waste_management` measured 1,422 lines across 8 files for a 2-hop story at ~2 SE-days. Field-to-Forecast is 5 hops with 28 generated step devices, a 6-phase plugin, a log plane, a deterministic trigger, a README, and a six-assertion harness — but the three dashboards are clones and the plugin is a structural copy. Honest range 5.5–7.5. If the harness overruns, this becomes 7.5.

**Exit criteria:** the four Phase 0 gates still green · `dd-demo validate --vertical oilgas` clean · full `pytest` green · the harness passes on planted failures (a `device_category:` phantom tag; a threshold outside a declared range; a service with `operations: []`; a boolean left at midpoint; a `_count` with drift) · `oilgas.app.requests_total{service_name:thirdparty-signal-api}` returns points · the cascade is visibly distinguishable from baseline on all three dashboards.

---

### Phase 2 — Live verification and Bits rehearsal · **1 SE-day**

**Goal:** prove the story survives a real org and a non-deterministic AI.

- `make validate-live` (`tests/test_dashboard_live_data.py`, integration-marked, run via `Makefile:371-372`) with the simulator up: every dashboard metric has data points in the last hour. Highest-value pre-demo gate in the repo.
- **Readback verification** in the style of `docker/identity_proxy_apm/query_back.sh`, exposed through the same `/api/harness` surface: prove the data is *queryable* via `GET /api/v1/query`, not merely that the deploy returned 200.
- **At least five Bits investigations** triggered from the Expert monitor, observed end to end, driven live in the UI (the MCP tools are not available).
- **Acceptance bar: Bits reaches the field-outage root cause without SE intervention in at least 3 of 5 runs.** If it does not, tune the monitor messages and the `tx_logs` content — they are the levers.
- Timing rehearsal against the corrected **11:00 cascade + 1.5–2.5 min initial idle**: it lands inside the conversation window; no monitor evaluation window (`last_5m`/`last_15m`) is longer than the phase it must catch.
- **Re-run rehearsal: the cascade re-triggered on demand twice in one simulator session**, plus a written answer in the README for "what the SE does if the call slips past recovery."
- **Pre-demo checklist gains:** the `mock-app` compose profile is down (`DD_DEMO_MOCK_FLEET` not `true`), so the shared identity-proxy plugin contributes no competing telemetry.
- Teardown rehearsal: `dd-demo teardown --vertical oilgas` from the UI. Dashboards match on the auto-injected `[dd-demo-toolkit:oilgas]` description marker (`resources/dashboards.py:185-188`); **notebooks and cases match by NAME/TITLE** (`STYLE_GUIDE.md:370-394`) — do not rename after this point without tearing down first, or you orphan the deployed copy.

**Exit criteria:** two consecutive clean rehearsals; the SE can open any dashboard or the notebook in any order and talk to it (no fixed sequence — this is the conversational requirement, not a script).

---

### Phase 3 — Optional upgrades, each individually gated · **0–6.5 SE-days, demand-driven**

| Upgrade | Gated on | Effort |
|---|---|---|
| **Real pipeline plane** — *either* reskin `data_obs/` (Kafka topics + service names + dbt models renamed to O&G nouns, reusing the `data-obs` compose profile, `make up-data-obs`, and `DATA_QUALITY_FAULT_PCT` as the live upstream fault) *or* build a bespoke `docker/oilgas_pipeline/` 28-span ddtrace orchestrator. **Decide from the Phase 0.5 desk check; prefer the reskin** — it hooks into existing infra rather than hand-rolling a new stack, and it lights up DSM, which is `available: True` and which no current demo uses outside finance. | Recommended regardless if there is budget | +1.5 (reskin) / +2 (bespoke) |
| **Real LLM Obs for Expert** — port `wm_agentic_demo/wm_ops_agent.py`, warehouse-shaped retrieval span, four new evals | Q4: Xpert still going to production | +2 |
| **`verticals/oilgas/sds.yaml`** — Sensitive Data Scanner masking well coordinates, lease identifiers, contractor IDs. `resources/sds.py` ships and `verticals/finance/overlays/payment-processor/sds.yaml` is a working template — but the "zero new toolkit code" claim only holds **because Phase 1 now ships a logs plane**. SDS masks log content; the earlier gauge-only design would have given it nothing to scan. The finance template works precisely because the simulator deliberately emits `card.pan` values into `authorization-engine` logs. So this upgrade adds the sensitive fields to the field-gateway and step-14 log lines, then scopes the SDS group by `filter_query: "service:field-ingest-gateway"` with `product_list: [logs]`. SDS is the **only** security product marked `available: True`. | Q3: security has any weight | +0.5 |
| **`verticals/oilgas/overlays/bpx/`** — customer nouns, correct Xpert spelling, real pad IDs | Q1 positive | +1 |
| **Palantir silent-failure lane** | Q5 positive, build last | +0.5 |
| **Data Observability, if the Phase 0.5 spike succeeded** — wire the Agent dbt integration into the demo path, flip `dataobs` to `available: True` in `PRODUCT_CATALOG`, lift the navigation rule, and rebuild hop 2 on real freshness + test results | Phase 0.5 spike positive | +1 |

**Compose-profile warning for any new profile:** it must be gated in **four** places or it silently fails from the UI — `profiles:` on each service, the `_X`/`_X_PROFILE` pair folded into `_LIFECYCLE_PROFILES` (`Makefile:45-62`), a documented flag in `.env.template`, **and** the independently-implemented mirror in `dd_demo_toolkit_ui/process_supervisor.py:498-534`. Also give any new host-Python stream a **unique `--tag` marker**: `make wm-fleet-demo-down` runs `pkill -f "\.venv-ui/bin/python run.py"` (`Makefile:213`) and would silently kill a generically-named oil-and-gas stream mid-demo. Reskinning `data_obs/` avoids most of this — the `data-obs` profile and its three make targets already exist and are already wired.

**Total: 0.75 pre-gate + 1.0 spikes/core-PR + 6.5 committed build (Phase 1 at 5.5 + Phase 2 at 1) = 8.25 SE-days to a rehearsed demo, plus 0–6.5 optional = up to 14.75 SE-days fully loaded.**

---

## 8. The validation gate with James

**Positioning guardrails, from the briefs, non-negotiable:**
- **Do not lead with Dynatrace bashing.** "James may not have the same frustrations Ustat had. Build the positive case first." The May prep brief goes further: "Do not compare feature-for-feature against Dynatrace. If we start listing capabilities side by side, we have already lost the frame." Our credibility play is John's ex-Dynatrace Principal Engineer origin story, not a teardown.
- **Do not open with a Datadog homepage or infrastructure overview** — "Vinny and Ustat have seen generic observability demos."
- **Security may be the door.** The AoP brief: "The security angle (Cloud SIEM, Code Security) is James's entry point. Consider leading with that and bridging to the art-of-the-possible."
- **Land on revenue, not a metric.** Ustat: "The people that drive all of this is where the money's coming from, which is drilling for oil and gas."
- **Keep scope small.** "If Vinny agrees to a POV, make it small and specific: Xpert and the pipeline. Not a full platform evaluation."
- **State the synthetic-data disclosure out loud in the first two minutes** — ship the `Synthetic?` disclosure table pattern from `docker/mc_apple_mdes/README.md:16-38`. With a security architect this is cheaper than being caught.

### Decision table

Each row states what *changes in the build* on each answer, not just whether we proceed. Q7 and Q8 are additions to the brief's six; both are zero-build and both gate design decisions that Phase 1 otherwise hard-codes blind.

| # | Question | Why | If YES → what changes in the build | If NO → what changes in the build |
|---|---|---|---|---|
| **1** | Does the pipeline-visibility problem still resonate, or did Ustat own that personally? | The entire narrative derives from a departed champion's quotes. This is the premise. | Phase 1 as specified; add the BPX overlay in Phase 3. | **Stop.** Do not build the metric plane. Re-scope around whatever James names. Cost so far: 0.5 days. |
| **2** | Is field ops / drilling leadership still the audience? Ustat said C-suite and drilling leadership drive decisions — still true under the new structure? | Decides whether the notebook closes on rig NPT dollars or on engineering MTTR. | Notebook ROI section in O&G units (non-productive rig time $/hr, deferred production bbl/day). `STYLE_GUIDE.md:756-758` reference figures are healthcare-only and must be replaced. | Reframe the close as data-platform reliability; drop the drilling-economics framing. Same assets, different last cell. |
| **3** | **What is your relationship to the observability side — do you care about Bits SRE, or is your focus purely Cloud SIEM and Code Security?** | The single highest-leverage question. James is a Digital Security Architect and there is currently **no** observability owner at BPX. | Phase 1 unchanged. | **Do not proceed with Phase 1.** Pivot to security — and know the cupboard first: **SDS is the only working security resource** (`dd_demo_toolkit/resources/sds.py`, template `verticals/finance/overlays/payment-processor/sds.yaml`); `csm` and `asm` are `available: False` in `PRODUCT_CATALOG` (`dd_demo_toolkit_ui/server.py`); zero Cloud SIEM detection rules and zero Code Security assets exist in the repo. **A security pivot is a bigger build than this plan, not a smaller one.** Knowing that before committing is worth the half day. |
| **3b** | **When you say "Code Security" — do you mean SAST/SCA on your Java estate, or runtime protection?** *(added; not in the brief)* | Decides deliverability outright. Zero cost to ask. | **SAST/SCA:** we cannot deliver it and must say so. Requires the repo connected to Datadog plus CI integration; zero assets in the repo; `ci` is `available: False`; and `GA_ROADMAP.md:47-49` flags an unresolved blocker — `pyproject [project.urls]` points at `DataDog/dd-demo-toolkit` while the git remote is a personal fork. **Runtime protection:** deliverable as AAP — one JVM flag (`-Ddd.appsec.enabled=true` on `docker-compose.yaml:992-1002`) plus the traffic generator `identity-proxy` has always lacked. **UNVERIFIED whether AAP is enabled in this org.** | n/a |
| **4** | Is Xpert still on track for production? *(Note: brief says 30 → 3,000 employees, as of May 2026.)* | Decides whether we spend 2 days on real LLM Obs. **This is why Datadog is back in the account** — "Dynatrace cannot monitor it." | Phase 3 LLM Obs upgrade, +2 days. Also settle the **Xpert vs Expert** spelling here (see §9, R6). | Ship the gauge-only scorecard on the three `expert_eval_node` devices. Do not spend the 2 days. |
| **5** | Has anything changed with the Palantir OTEL export? | It was producing "nonsense" data when Ustat left. | Palantir lane, +0.5 days, **built last** — it inherits the absence-modelling problem from the primary cascade. | Drop entirely. Spend the time on the hop-2 dbt spike (Q-item 8 in §10) instead, which is the weaker hop. |
| **6** | Who else should we be talking to about observability/pipeline? Suraj Koneri was the serverless/Lambda person; Ian Gallagher's role is unclear. | Finds the successor owner. Answering Q3 "no" makes this the most valuable question in the set. | Route the demo to that person; James becomes the security thread. | Escalate to Brian Monroe — he accepted the last exec invite while Vinny declined it. |
| **7** | **Walk me through the nightly path from field capture to the forecast mart — is it one orchestrator, Step Functions, or Lambda-per-hop?** *(added; not in the brief)* | R7 is a live contradiction between the two source documents and Phase 1 hard-codes 28 `pipeline_step` devices and three dashboards around whichever answer is right. Asking after the build is too late. | **Monolithic orchestrator:** 28 generated step devices exactly as specified in §3. **Distributed (Step Functions / Lambda-per-hop, which the May brief and "6,000+ Lambdas" both suggest):** model the run across 3–4 named `services:` with real `operations:` from the start, so the Service Map has shape — this changes the Phase 1 config generator and the hop-3 dashboard, not just the Phase 3 upgrade. | n/a — there is no "no." The answer reshapes Phase 1 either way, which is exactly why it must precede it. |
| **8** | **Where does Monte Carlo sit today, and what does it not catch?** *(added; not in the brief)* | R2's entire differentiator is cross-layer correlation *versus* Monte Carlo's in-warehouse data quality. If Monte Carlo already owns the Snowflake slice and BPX is happy with it, hop 2 is not a differentiator, it is a duplicate. | **Monte Carlo covers Snowflake DQ well:** de-emphasise hop 2 as a *finding* and re-frame it as the *hand-off point* — the value is that hops 1, 3, 4 and 5 are in the same investigation. **Monte Carlo is shaky or unadopted:** the dbt-integration spike (§10 item 8) becomes worth funding and hop 2 gets real freshness/test signal instead of gauges. | n/a — same reasoning as Q7. |

### The honest capability table (the gate packet, one page)

**Generate this page from the toolkit's own `PRODUCT_CATALOG`** (`dd_demo_toolkit_ui/server.py`, ~lines 98-165; also served at `GET /api/products`, server.py:299) rather than hand-maintaining it — a small script under `scripts/` that emits the table and then annotates each row with the oilgas-specific detail below. Hand-maintaining it guarantees drift the first time a product's `available` flag changes, and the catalog already carries the *reason* for the two rows this plan previously got wrong.

Every "No" or "Maybe" below is a **named hard dependency with an owner**, not an unsupported assumption.

| Product | Catalog `available` | Can we show it for oilgas? | Detail / hard dependency and owner |
|---|---|---|---|
| Metrics, Monitors, SLOs, Dashboards, Notebooks | — (toolkit core) | **Yes, fully** | Toolkit-native. Note the two SLOs must be built over real **counters** — see §3; `.as_count()` over a gauge deploys 200 and shows nothing. |
| APM / Distributed Tracing / Service Map | `apm: True` | **Yes — conditional on config** | Synthetic spans with real `peer.service` edges. **Hard dependency:** every `services:` entry needs a real `language:` key and a non-empty `operations:` list, or `_generate_service_trace` early-returns and the service emits nothing at all (engine.py:707-709). Owner: John, Phase 1, asserted by the verification harness. |
| Log Management | `logs: True` | **Yes, once services have operations** | Trace-correlated service logs come free from `service_loggers` (engine.py:712) — which again requires `operations:`. A structured field-gateway log at the root-cause hop gives Bits a log source. Owner: John, Phase 1. |
| Infrastructure Monitoring | `infra: True` | **Partial** | Device fleet renders, but `DD_HOSTNAME` is hardcoded to `wm-fleet-simulator` (R13). Do not open the Host Map. Owner: John, deferred. |
| LLM Observability | `llmobs: True` | **Yes** | Agentless `ddtrace.llmobs`, proven live in this org today (`ml_app:wm-ops-agent`, project created 2026-07-27). **Hard dependency:** Q4 positive; +2 days. Owner: John, Phase 3. |
| Bits AI / Watchdog | `bits: True` | **Yes, with caveats** | Its documented source list (Metrics, APM, Logs, Dashboards, Events, Change Tracking, GitHub, Watchdog, RUM, Network Path, DBM, Profiler), the exclusion of LLM Obs and Data Obs, the supported-monitor-type list, and "only auto-launches on an ALERT transition" are all **UNVERIFIED in this repo** — they come from Datadog's public docs, not from anything in the tree. Design conclusion holds regardless: project every hop into metrics and rehearse. **Hard dependencies:** Bits Investigation enabled, AI Credits available, `bits_investigations_write` granted — all three UNVERIFIED. Owner: John, five-minute org check before Phase 2. |
| **Data Streams Monitoring** | `dsm: True` | **Yes — and unassessed until now** | A working, committed Kafka + DSM stack ships at `data_obs/`: `producer.py → feature_pipeline.py → eval_consumer.py`, all `dd-trace-py` with `DD_DATA_STREAMS_ENABLED=true`, gated behind the `data-obs` compose profile with `make up-data-obs` / `down-data-obs` / `logs-data-obs` (Makefile:178-185). Its README describes this exact narrative — an upstream `null_rate_pct` fault degrading a downstream eval score, with pipeline lineage upstream and LLM Obs downstream on one Service Catalog page. **This is a live alternative to 28 synthetic gauge devices for hops 2-3 and must be costed, not silently omitted** (§1, §7 Phase 3). Owner: John, half-day assessment inside Phase 0. |
| Sensitive Data Scanner | `sds: True` | **Yes, but not free** | Existing manager (`resources/sds.py`) and a working template. **Hard dependency:** SDS masks *log content*, and oilgas currently emits no logs containing well coordinates, lease IDs or contractor IDs — the finance template works only because the simulator deliberately emits `card.pan` into `authorization-engine` logs. Re-cost from +0.5 to +1 day, or make it conditional on the logs plane landing first. Owner: John, Phase 3, gated on Q3. |
| **Data Observability / dbt lineage** | `dataobs: False` | **Not today — unwired, not absent** | The catalog comment states the reason verbatim: `data_obs/` runs dbt and produces `manifest.json` / `run_results.json`, but the upload is not wired (datadog-ci dropped the dbt plugin in v5; see `data_obs/dbt_runner/run_loop.sh` `report_artifacts()`), and **the Agent's dbt integration is the supported path**. Real freshness SLAs and column tests already exist at `data_obs/dbt_project/models/sources.yml` (`loaded_at_field: received_at`, `warn_after: 30 minute`, `error_after: 90 minute`, `not_null` tests) over a real Postgres. **Hard dependency:** configure the Agent dbt integration. Owner: John, costed as a half-day spike before Phase 1 (§10 item 8). If the spike fails, the navigation ban stands as an *evidenced* decision. |
| Data Catalog (synthetic Snowflake entities) | — | **No** | Distinct from the dbt path above. Org catalog verified empty (`get_data_catalog_schema` → null, `search_data_entities` → 0, monitor coverage → 0) and the Data Observability MCP surface is read-only plus annotate-existing — **no POST path for synthetic entities.** No owner; not deliverable. Navigation rule stands: do not open the Data Catalog. |
| Cloud SIEM | `csm: False` (nearest catalog row) | **Possible, not built** | Needs a new resource manager (none exists). **0 custom rules and 0 signals in this org over 30 days — ambiguous between "not enabled" and "quiet org."** Owner: John, org check; do not build before it resolves. |
| App & API Protection | `asm: False` | **Maybe** | One JVM flag plus a traffic generator. Org support UNVERIFIED. Owner: John, org check. |
| Code Security (SAST/SCA) | `ci: False` | **No** | Needs the repo connected to Datadog plus CI integration; zero assets; `GA_ROADMAP.md:47-49` blocker on the fork/remote mismatch. No owner; not deliverable in this window. |
| NDM / CNM / Network Path | `npm: False` | **No** | No NDM/SNMP telemetry path exists in the toolkit; the only repo hit for SNMP is a prose comment at `verticals/healthcare/overlays/quest.yaml:20`. Say "signals your edge gateways already expose," never "this is NDM." No owner; not deliverable. |
| Data Jobs Monitoring | — (not in catalog) | **No** | Needs real Airflow/Spark. The repo has two `model: AirflowDAG` device labels and three Service Catalog description strings; no integration, no assets. No owner; not deliverable. |
| CI Visibility / Test Optimization | `ci: False` | **No** | Same dependency as Code Security. |

**Two things this page must also carry, and currently does not:**

1. **Cost.** Phase 1 emits roughly 157 unique custom-metric timeseries at steady state (28 pipeline_step × 4 + 6 field_gateway × 4 + 3 expert_eval_node × 5 + 1 warehouse × 4 + 1 handoff × 2), and cardinality is *per-device*, not per-model — `simulator/engine.py:665-693` attaches `device_id`, `device_type`, `device_manufacturer`, `device_model`, `device_firmware`, `category`, `battery_powered`, every location dimension and `service` to every emission. Phase 3 adds a 28-span-per-run trace, real LLM Obs spans, and a container stack. State the number and name the org that absorbs it. The repo offers no guidance here (see R15).
2. **Which product keys oilgas lights up.** `GA_ROADMAP.md:55-57` is explicit that the GA measure is "Datadog product modules … measured by `dd-demo coverage`. Not 'more verticals.'" Declaring the key list now (`apm`, `logs`, `infra`, `llmobs`, `bits`, `sds`, and possibly `dsm`) makes the vertical ready for `products.yaml` when roadmap Phase 2 lands, and makes this build count toward the metric the roadmap actually optimises.

---

## 9. Risks and open questions

**R1 — The gate may never happen.** Zero replies from any `@bpx.com` address since the 2026-07-30 outreach (threads `19fb46fe278727b5`, `19fb47924051fbaf`); no calendar event through 2026-09-15; champion departed 2026-07-29; six prior reschedules of the exec session culminating in Vinny declining the 2026-06-04 instance (`vinny.sharma@bpx.com` responseStatus=declined, event `53573q16uj3092jjoogi9o5tvh`). **Mitigation:** 0.5-day pre-gate footprint, and the gate is a named milestone owned by Bryan.

**R2 — Hop 2 (the warehouse) is the load-bearing weakness — but it is defended by more than navigation discipline, and the plan previously understated the options.** Steps 2 and 3 are the heart of Ustat's "what happens between step 1 and step 28" quote, and as designed they are custom gauges named to look like a warehouse and a DAG. Three corrections to the earlier framing:
- **Data Streams Monitoring is `available: True` and backed by a working committed stack** (`data_obs/`, `data-obs` compose profile, `make up-data-obs`). Reusing it for the ingest → transform → eval hops is a real option and honours the standing "hook into existing infra, never hand-roll a container stack" preference. It is not a drop-in — it is Kafka-shaped, EY-named, and does not model a 28-step nightly batch — but it must be *assessed and costed*, not omitted.
- **Data Observability is unwired, not absent.** dbt artifacts already exist; the supported upload is the Agent dbt integration. Half-day spike, named owner, recorded result. If it works, hop 2 gets real freshness thresholds and column tests and stops being the weak hop.
- **The Data Catalog specifically remains out of reach** — the org's catalog is verifiably empty and there is no write path for synthetic entities. The navigation rule survives, scoped to the Catalog rather than to all of /data-obs.

**Compounding, and unchanged:** BPX already runs **Monte Carlo** for exactly this Snowflake data-quality slice (May prep brief: "data quality and anomaly detection inside Snowflake, specifically for AI model inputs"). The differentiator must be pitched as **cross-layer correlation** (network → pipeline → warehouse → AI in one investigation), which Monte Carlo structurally cannot do — not as a better data-quality check. Gate Q8 now tests this directly. **Consider asking for a Snowflake trial at the gate as a named external dependency.**

**R3 — Cloud SIEM enablement is UNVERIFIED.** 0 custom detection rules (`defaultRule:false` → `total_count 0`) and 0 security signals of any type over 30 days. That is equally consistent with "not enabled" and "quiet org." **This is why we do not pre-build a `SecurityRuleManager`.** Verify before spending anything on the security lane.

**R4 — Bits prerequisites, non-determinism, and the source list itself.** The claims that Bits has twelve data sources, that LLM Obs and Data Obs are not among them, that `data-quality alert` is not a supported monitor type, and that only ALERT transitions trigger an auto-investigation are all **UNVERIFIED in this repo** — there is no Bits documentation, skill file or test in the tree that states them; they come from Datadog's public docs. They are held to the same evidentiary standard as the other externals in this section. The design conclusion is unaffected: project every hop into metrics, treat the rich surfaces as human click-through, and rehearse rather than promise. Separately UNVERIFIED: whether Bits Investigation is enabled in this org, whether AI Credits are available, and whether `bits_investigations_write` is granted. The Bits MCP tools (`trigger_bits_ai_investigation`, `get_bits_ai_investigation`) are documented in the `datadog/advanced-products` skill but **are not exposed in this session**, so Bits must be driven live in the UI and cannot be scripted. **Mitigation:** the 3-of-5 rehearsal acceptance bar.

**R5 — Uncommitted work-in-progress on `main`, and a sequencing trap inside it.** 12 modified + 6 untracked paths, including `GA_ROADMAP.md`, `STYLE_GUIDE.md`, `resources/dashboards.py`, `utils/dd_api.py`, `process_supervisor.py`, `app.js`, `index.html`, `otel-collector-config.yaml`, the EY overlay, and `dashboard-nursecall-beds.json`; untracked `verticals/waste_management/`, `docker/waste_management/`, `docker/mc_apple_mdes/`, `wm_agentic_demo/`. **The best templates for this build have never been committed.** One `git clean -fd` destroys the WM and MDES assets. **The trap:** Phase 1's repo-hygiene item adds `waste_management` to the CI matrix and bumps the vertical-count assertion — both of which fail in CI, where `waste_management/` does not exist in the checkout. Hygiene must be sequenced (1) commit the untracked assets on a deliberate branch, (2) then update the hardcoded lists, (3) then bump the count — or scoped to `oilgas` only until WM is committed.

**R6 — Xpert vs Expert: the two source documents contradict each other, and one contradicts itself.** The May prep brief says **Xpert** exclusively ("built on Amazon Bedrock (Anthropic Claude 3) running text-to-SQL... against a Snowflake database"). The August AoP brief lists "Xpert (on Bedrock)" in its environment section and then uses **Expert** ~10 times in the narrative including validation question 4. Bryan's 2026-07-30 email says "Expert and Bedrock." **Getting a customer's own product name wrong in front of a new architect is an unforced own-goal.** Resolve at the gate before a single asset is named — it is load-bearing across every metric, tag, `ml_app` and dashboard title.

**R7 — The "28-step pipeline" framing may not match BPX's reality.** It appears only in the August AoP brief. The May prep brief, closer to Ustat's actual words, describes something structurally different: "A Step Function runs in AWS, picks up data from somewhere, and puts it somewhere else. Another process comes and picks up that file from an S3 bucket." BPX runs 6,000+ Lambdas and Fargate. A monolithic 28-step orchestrator is simpler than their architecture. **Mitigation upgraded:** this is no longer deferred to a Phase 3 upgrade that may never be funded — gate **Q7** asks it directly, and the answer reshapes the Phase 1 config generator and the hop-3 dashboard.

**R8 — The August brief omits tools the May brief treats as central.** Ustat named five incumbents: Dynatrace, ScienceLogic, Cribl, **Monte Carlo**, **Wiz**. The AoP brief lists only three. Palantir and Databricks appear only in the August brief with no corroboration. **UNVERIFIED where they came from.**

**R9 — "The January team call" is likely January 2025.** The AoP brief says James's security focus came from "the January team call"; Bryan's 2026-07-30 email dates it "the session Steven Villarreal ran with your team in January '25." Planning around a 19-month-old priority signal is exactly the risk Q3 exists to catch.

**R10 — Source transcripts were not retrievable.** The Zoom/meeting connector rejected credentials ("This connector rejected the current credentials even after refresh"); `search_meetings(q='BPX')` returned empty and `recordings_list` for July 2026 returned 0. **Every Ustat quote in this plan is second-hand from the briefs and UNVERIFIED against a transcript.** To verify: reconnect the connector and re-run.

**R11 — Repo gates are red before we start, and `dd-demo validate` is weaker than it looks.** `pytest` fails (`tests/test_config.py:176` expects 5 verticals, gets 6); `isort` crashes on an invalid `multi_line_mode` key; 324 flake8 findings and 33 black-reformattable files. Phase 0 fixes the two blocking items; the flake8/black baseline is explicitly **out of scope** and must not be charged to this build. **Additionally:** `dd-demo validate` is an *asset* linter, not a *config* linter — `validation/runner.py:68-96` reads `config.yaml` only to pull `env_prefix` and then lints monitors/dashboards/notebooks/SLOs/workflows. A `config.yaml` that `ConfigLoader` outright rejects still validates clean, and if `env_prefix` fails to resolve, the DDD001 env_prefix check silently stops firing. Phase 0's exit criteria must therefore include an explicit `ConfigLoader('verticals').load_vertical('oilgas')` + `SimulatorEngine(cfg)` smoke assertion and the three auto-enrolling tests (`tests/test_validation.py:224`, `tests/test_config.py:183`, `:221`).

**R12 — Docs contradict code on live-mounting.** `CLAUDE.md:561-576` claims `verticals/` and `dd_demo_toolkit/` are volume-mounted. **False:** `Dockerfile:14-17` `COPY`s them, `docker-compose.yaml` has no such bind mount, and `git log -S './verticals:/app/verticals'` is empty. `STYLE_GUIDE.md:874` and `GA_ROADMAP.md:38-39` are correct. The Phase 0 `--build` fix resolves the practical impact — **for both the `setup` and `teardown` PROCESS_DEFS entries**; teardown against a stale baked `verticals/` matches notebooks and cases by their *old* names and orphans the deployed copies. **Also correct CLAUDE.md §7 in the same PR** so the next engineer is not misled.

**R13 — `DD_HOSTNAME` is hardcoded to `wm-fleet-simulator`** (`docker-compose.yaml:28`) for every vertical, and `otel-collector-config.yaml:65,82` still hardcode `finance-simulator`. Oil-and-gas simulator metrics will land on a WasteManagement host unless parameterized. Low impact for a metric-plane demo; note it before anyone opens the Host Map.

**R14 — Two shipped verticals are quietly broken in exactly the way this build could break, and a third failure mode was found during verification.** EY's `environment_scale: 3.0` puts every quality gauge permanently out of threshold, and both EY and waste_management have every plugin trough value clamped away by `simulator/engine.py:656-663`. **Newly confirmed:** `DeviceProfile.__post_init__` seeds every metric at its range midpoint, so a `drift: 0` gauge with `range: [0, 1]` emits a flat **0.5** forever and a rangeless metric emits a flat **50** — `hospital.device.online` is shipped proof. Both produce assets that deploy with a 200, render green, and demonstrate nothing. The Phase 1 verification harness is the mitigation, it must assert steady-state values as well as threshold reachability, and it is the item most likely to be cut under schedule pressure. **Do not cut it.**

**R15 — No cost, cardinality or quota budget exists anywhere, in this plan or in the repo.** Phase 1 is ~157 unique custom-metric timeseries with high per-device tag cardinality; Phase 3 adds spans, LLM Obs payloads and a container stack. Grepping `STYLE_GUIDE.md`, `CLAUDE.md`, `CONTRIBUTING.md` and `GA_ROADMAP.md` for cost/cardinality/billing/quota returns only `CLAUDE.md:500`, which is about fleet placement. The plan budgets SE-days precisely and org spend not at all. **Mitigation:** state the timeseries count and the absorbing org in the Phase 0 gate packet; add a cardinality-budget rule to `STYLE_GUIDE.md` as one of the new rule classes §2 already commits to contributing.

**R16 — There is no on-demand re-trigger, and the whole narrative lives in the trailing minutes of live data.** The §4 time-compression decision means the story exists only inside the cascade window. The plugin idles a random 4-8 ticks before the first event and a random 60-90 ticks (15-22 minutes) between events. The UI exposes only `/api/processes/{name}/start` and `/stop`, and `static/index.html` has rows for `simulator`, `setup`, `teardown`, `teardown-all` and the five `wm-*` entries — nothing that fires a cascade. If the call starts late, or the customer asks to see it again, or a second call follows, the SE's only lever is stop-and-restart-and-wait. Deploy-side reset is already fine (`setup` passes `--clean`, `docker-compose.yaml:67`); this is specifically about telemetry. **Mitigation:** a deterministic phase-trigger in Phase 1 — an engine hook the plugin honours, a `POST /api/incident/{vertical}/trigger` endpoint, and a control in `static/index.html` + `static/app.js` (UI-first per `CLAUDE.md` §0.6) — plus "cascade re-triggered on demand twice in one simulator session" as a Phase 2 exit criterion.

**R17 — The vertical ships no SE-facing documentation, and distribution is contribute-back-via-PR.** The plan's documentation deliverables (`bits.md`, monitor-message text, STYLE_GUIDE additions) are all demo-time or linter artifacts. `find verticals -name "*.md"` returns nothing today — no vertical ships docs — but the precedent exists at `dd-demo-toolkit/DEMO_RUNBOOK.md` (AdventHealth): prerequisites, deploy order, what should appear in Datadog and where, the demo arc. This matters here specifically because §3 justifies the base-vertical/overlay split on reuse at the next E&P account and `GA_ROADMAP.md:58-60` makes contribute-back the distribution model. The next SE inherits a config tree, a multi-phase plugin with non-deterministic timing, a Data Catalog navigation ban they must know about, and no instructions. **Mitigation:** `verticals/oilgas/README.md` in the Phase 1 file tree — prerequisites, deploy order, the phase timeline with expected values, the navigation ban and why, the synthetic-data disclosure script, teardown, and known limitations (no NDM, no Data Catalog, `DD_HOSTNAME` per R13). Fold the §8 capability table into it rather than leaving it a loose one-pager.

---

## 10. What I need from you before starting

1. **Xpert or Expert?** Confirm the spelling before any asset is named. It is inlined into metric names, `device_model` values, `ml_app`, dashboard titles and monitor messages.
2. **Approve `oilgas` as the env_prefix**, or name an alternative now. It cannot be changed later without a repo-wide edit. (Verified free and pattern-valid; the six taken prefixes are `finserv`, `hospital`, `hospitality`, `insurer`, `mfg`, `wm`.)
3. **Which branch do we cut from, and do we commit the untracked assets first?** `main` has 12 modified + 6 untracked paths including all of `waste_management`, `docker/mc_apple_mdes/` and `wm_agentic_demo/`. `version-two` still exists locally and on origin. Per R5, committing the untracked assets is a *prerequisite* to the Phase 1 hygiene edits, not a nice-to-have.
4. **Six BPX-plausible identifiers** for the placeholders the AoP brief leaves unfilled (`[Site Name]`, `[Well Pad X]`, `[Pipeline Name]`, `[date]`, `[Well/Pad identifier]`): basin names, pad names, the forecast mart/table name, and the nightly pipeline name. No BPX site names appear in any document, email, Slack message or calendar entry I searched — these must be invented and they become tag values and dashboard titles.
5. **Confirm the gate owner and target date with Bryan.** He has offered ("If I need to meet with James first before we start getting granular then Im game" — Slack `D0AL9GJB49G`, 2026-08-05 17:49). Nobody starts Phase 1 until a meeting exists. Note your OOO the week of 2026-08-10. Bryan also suggested turning the brief into an external-facing teaser — that is a cheap Phase 0 artifact and worth saying yes to.
6. **Confirm the smart-bed correction reaches Bryan before it reaches a customer.** The AoP brief's claim of an existing hospital smart-bed Wi-Fi demo is factually wrong (§6). The real asset is an AP → infusion-pump cascade and it is a better analogue anyway — but we cannot promise a smart-bed demo.
7. **Two org checks** (five minutes each, both currently UNVERIFIED): is **Bits Investigation** enabled with AI Credits and `bits_investigations_write`? Is **Cloud SIEM** enabled — 0 rules and 0 signals in 30 days is ambiguous.
8. **Approve a half-day dbt-integration spike inside Phase 0.** `data_obs/` already produces `manifest.json` / `run_results.json` with real freshness thresholds and column tests; the only missing piece is the Agent dbt integration (`dd_demo_toolkit_ui/server.py` catalog comment and `data_obs/dbt_runner/run_loop.sh` both name it as the supported path). This is the single biggest available upgrade to the weakest hop, and half a day buys an evidenced answer either way. Owner: John.
9. **Decide whether to reuse `data_obs/` (Data Streams Monitoring) for hops 2-3.** `dsm` is `available: True` with a working `data-obs` compose profile and make targets. It is Kafka-shaped and EY-named, so reuse means renaming topics/services rather than a drop-in — but it is real product surface versus synthetic gauges, and hooking into existing infra is the standing preference. I need a keep/reskin/reject call before the Phase 1 config generator is written.
10. **Do you want to ask BPX for a Snowflake trial at the gate?** It costs nothing to ask and it is the only path to a genuine warehouse surface.
11. **Kill or keep the AWS scaling-policy secondary?** My recommendation is kill (§6) — but on the "invites a POV-shaped conversation" and "collides temporally with the primary cascade" grounds, not on a false capability claim. Synthetic `system.*`-style series with host resources *are* postable via `DatadogAPIClient.submit_series()` (that is how the WM fleet demo materialises hosts), so the lane is buildable if you want it. Confirm.
12. **Which org absorbs the custom-metric volume**, and is ~157 timeseries plus Phase 3 spans acceptable there? (R15.)
13. **Any O&G ROI reference figures you already trust** — non-productive rig time $/hr, deferred production bbl/day, cost of a bad drilling recommendation. `STYLE_GUIDE.md:756-758` supplies healthcare numbers only, and the notebook's ROI section is where the demo lands on revenue rather than on a metric.

---

## Reviewer disagreements

Findings I did not apply as written, and why.

**1. "Data Observability is unwired, not absent — cost it as a spike rather than declaring it impossible." (blocking) — applied, but narrowed.** The finding is right that the earlier text conflated two different things and that the repo itself names the remediation path. I have split the capability table into a **dbt lineage/freshness** row (unwired, spike costed, named owner) and a **Data Catalog** row (genuinely unreachable). The finding's framing implies the whole `/data-obs` surface becomes available if the Agent dbt integration is configured; it does not. The dbt integration produces dbt-shaped lineage and test results over the demo's Postgres — it does not create Snowflake catalog entities, and the org-level verification stands: `get_data_catalog_schema` → null, `search_data_entities(entity_type:"*")` → 0, monitor coverage → 0, and the MCP surface is read-only plus annotate-existing. So the navigation ban survives, scoped to the Data Catalog rather than to all of `/data-obs`, and the spike is costed rather than assumed.

**2. "Data Streams Monitoring must at minimum be assessed" (blocking) — applied as an assessment and a decision I am escalating, not as an adopted design.** The finding is correct that omitting `dsm: True` with a working committed stack was an error, and it is now a first-class row in both the feasibility framing (R2) and the capability table, with a keep/reskin/reject call surfaced as §10 item 9. I stopped short of the finding's implication that `data_obs/` supersedes the metric plane. It models a three-hop Kafka stream with an EY risk-data narrative; the BPX story is a 28-step nightly batch, and Q7 may reveal it is actually Step Functions and Lambdas — a third shape again. Adopting Kafka DSM before Q7 is answered would trade one wrong-shaped simulation for another. The honest position is: real product surface, real reuse candidate, blocked on the same architecture question as the 28 devices.

**3. "§8's hand-written capability table duplicates `PRODUCT_CATALOG`" (minor) — applied, with a caveat.** Generating the page from the catalog is right and I have made it the instruction. But the catalog carries `available` for the *toolkit*, not for *oilgas* — `apm: True` is true generically and conditionally false for this vertical until every service has `operations:`. So the generator must annotate, not just dump, and the "Can we show it for oilgas?" column stays hand-written per row. Pure generation would produce a more consistent and less honest page.

**4. "Bits' twelve data sources / monitor types / ALERT-only trigger are asserted without a repo-verifiable citation" (minor) — applied as a marking, not as a design change.** These are now explicitly labelled UNVERIFIED-in-repo inside R4 and the capability table, which is the consistency the finding asks for. I did not soften the design conclusion that depends on them. Projecting every hop into metrics and rehearsing rather than promising is the correct call whether the source list is exactly twelve or not, and the 3-of-5 acceptance bar is an empirical test that does not depend on the doc being right.

**5. Findings scoped to §§0-7 (services `operations:`, per-entry location round-robin, midpoint gauge seeding, phase-duration arithmetic, 4-axis temporal disjointness, `--build` argv position, hardcoded-list undercount, SLO counter availability, logs plane, harness UI surface, `drift: 0` on `_count` metrics) — not restated here.** They are owned by the first-half writer. Where their consequences reach my sections I have carried them through rather than duplicated them: the `operations:` requirement appears as a named hard dependency on the APM and Logs capability rows; the midpoint-seeding defect is folded into R14 as a third confirmed failure mode the harness must catch; the hygiene sequencing trap is folded into R5; and the `dd-demo validate` coverage gap is folded into R11.