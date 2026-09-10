# Bunge "Art of the Possible" — Handoff (2026-06-22)

> **Update (2026-06-22, post-build pass).** Fixed a demo-breaking simulator
> defect and built out the AIOps story. Changes since the first handoff:
> - **Engine-scale + clamp fix (critical).** `environment_scale: production`
>   was `3.0` (copied from finance) and the cascade-driven metrics had narrow
>   normal-band `range`s. The engine clamps plugin values to `range` then
>   multiplies by scale — so the cascade was flattened *and* baselines
>   false-fired several monitors (connectivity emitted ~290%). Set scale to
>   1.0 and widened the 7 cascade-driven ranges. Verified headless: clean
>   escalation, baselines below every threshold. This rescued the *whole*
>   vertical, not just the cascade.
> - **App errors/latency now spike in the cascade** (was the #1 open item).
>   New engine hook (`incident_state["app_impact"]`) lets the plugin drive
>   `agri.app.*`; the two app monitors were rewritten rate-based. Bunge Mobile
>   error rate and FRM latency now cross threshold during outage.
> - **Cascade cadence** retuned to surface ~15 min in and recur ~15 min after
>   each incident (like the other verticals) — it runs on *this* env; no
>   separate demo org needed for the AIOps scene to have live signal.
> - **ServiceNow close-loop (Eduardo's #1) built — SIMULATED.** New
>   `workflows.yaml` (enrich→open→close), a plugin-driven `agri.itsm.*` signal
>   set, an "AIOps — ServiceNow Auto-Remediation" dashboard, and a close-loop
>   notebook with simulated enriched-ticket text. No live ServiceNow in this
>   env (the step deploys as a no-op until a connection is bound — expected).
> - **Dynatrace differentiation pack built** as a notebook (scorecard table +
>   two live proof-point charts).
> - Validates clean: `dd-demo validate --vertical agribusiness` → **0 errors**
>   (2 expected ServiceNow no-op warnings).
>
> Still **not live-verified against a real Datadog org** — all of the above is
> headless/unit-verified. John runs once (step #5 below) and collects data.

> **Update 2 (2026-06-22, first live deploy).** First `make setup` ran against
> the org and surfaced issues — all fixed:
> - **3 deploy errors fixed (pre-existing latent bugs).** (a) `custom_unit` was
>   nested inside a `query_value` request (SAP Sync Lag widget) → moved to the
>   widget definition. (b) Four `agri.app.*` queries filtered by
>   `environment:production` — app metrics carry **no** environment tag, so they
>   returned no data *and* the comma-before-`OR` was a syntax error. Dropped the
>   env filter on all four (2 dashboards + 2 notebooks). All dashboards/notebooks
>   now deploy.
> - **`vertical:agribusiness` now on all simulator telemetry.** The engine now
>   attaches `vertical:<name>` to device metrics, app metrics, spans, and logs
>   (it previously only rode on the per-vertical agent `DD_TAGS`, which has no
>   agribusiness entry). Benefits every vertical. **Team `dd-demo-agribusiness`
>   IS created and services are tagged `vertical:agribusiness` + mapped to it**
>   (services.py auto-injects `team:dd-demo-<vertical>`) — confirmed in the
>   deploy log.
> - **LLM Observability gated per vertical.** The `ai-care-companion` you saw is
>   healthcare's ml_app — the LLM Obs generator was always-on for every vertical.
>   Added a `llm_observability:` config hook (enabled / ml_app_name) and **set
>   agribusiness to `enabled: false`** so it stops emitting a non-Bunge ml_app.
>   (Residual healthcare LLM data already in the org will age out / can be
>   filtered by ml_app.) Flip to `enabled: true` + `ml_app_name:` to show a
>   Bunge GenAI app later.
> - **Stale-deploy root cause — FIXED at the source (no more `make build`).** The
>   first deploy showed "3 dashboards / 1 notebook / no workflows.yaml" because the
>   UI's Deploy ran the `setup` *container* off a baked image. Rather than tell the
>   SE to run `make build` (which violates the UI-first directive), the lifecycle
>   containers (`setup`/`simulator`/`teardown`/`teardown-all`) now **bind-mount
>   `./dd_demo_toolkit` + `./verticals` read-only into `/app`** (editable install),
>   so Deploy and the simulator always read current local files. **Just click
>   Deploy again in the UI** — you'll get 4 dashboards, 3 notebooks, 2 workflows,
>   the `vertical` tag, and no LLM/RUM leakage. No rebuild, no relaunch.
> - **myBunge mobile RUM — partially shipped.** (a) The shared RUM metrics
>   emitter was hospitality-hardcoded and emitted `hospitality.rum.*` for *every*
>   vertical (another off-message leak) — now config-gated (`rum.enabled`) and
>   **disabled for agribusiness** so the leak stops. (b) `make rum-provision` is
>   now vertical-aware: it reads `rum.app_name`/`rum.app_type` from config and
>   provisions a native **"myBunge Mobile"** RUM application (type `react-native`)
>   — the app shows up in RUM › Applications, and the client token is fetched
>   programmatically via your API/APP keys (no manual token minting).
>   **Still to do:** populate that app with genuine myBunge session data. The
>   toolkit has no mobile-RUM-intake path today (native sessions come from the
>   browser SDK + Playwright `care-portal` path), so this needs a new
>   vertical-aware session generator and a **live smoke-test** (RUM intake can't
>   be verified headlessly). Note: myBunge is a PWA per its service def, so the
>   proven browser path (a re-themed care-portal + traffic generator) is the
>   lower-risk route to real sessions if "mobile-type" isn't a hard requirement.
>   To run provisioning: select **rum** in the product picker, then
>   `make rum-provision`.

Demo prep for the Bunge VP/champion session. Champion **Eduardo Solis** (building
global monitoring from scratch, AIOps = #1); economic buyer **Tiago**; presenter
**John Rath** + Brian/Steve. **Dynatrace** is co-evaluating into a Gartner scorecard;
selection ~Nov 2026.

## What's built (done)

**Toolkit assets — `dd-demo-toolkit/verticals/agribusiness/`** (its own vertical,
env_prefix `agri`; *not* a finance/manufacturing overlay, so no banking/factory
noise on screen):
- **`config.yaml`** — the estate: VMware hosts, **Oracle (DBM)**, 185-site network +
  NDM, AWS/GCP, the **GCP Bunge Data Platform** (the cross-cutting linchpin), the
  **SAP landscape**, and the **FRM pricing** engine. 6 services with a dependency
  graph where **every revenue app → `bunge-data-platform`** (that graph *is* the pitch).
- **3 dashboards** — Global KPI (exec), Apps & Data Platform (cross-cutting),
  Infrastructure/Network/SAP.
- **13 monitors, 5 SLOs** (incl. myBunge 10-min scale-ticket SLA — modeled as a
  99.9% availability SLO, not a literal 10-min-freshness SLO), **6 Service Catalog** entries.
- **Cross-cutting cascade plugin** `plugins/data_platform_cascade.py` — stale CME
  feed → FRM mispricing (4 phases, ~10 min; peaks feed-age ~480s, stale-quote ~12%);
  trips the **CME Feed Staleness** (root) + **FRM Stale-Quote** (symptom) monitors;
  leaves network/SAP/DB/host **untouched** (disjoint, so "rule out the network" is honest).
- **RCA notebook** "Data-Platform Cascade RCA" — the human investigation that **matches
  what Watchdog/Bits AI surface** (the trust-builder for the skeptical towers).
- **SAP modeled to the real Marketplace tiles only:** HANA → **Redpeaks**
  (`redpeaks.hana.*`, no query-level SQL), S/4HANA/NetWeaver → **Redpeaks/Agentil**,
  **SAP Cloud ALM → RapDev** (CPI/integration monitoring), Integration Suite → logs.
  Query-level/"SELECT \*" lives on **Oracle DBM** (DBM ≠ HANA). Left out Sybase/MaxDB/
  BusinessObjects (not in Bunge's stack per briefing).
- **Demo script** `Bunge-art-of-the-possible-demo-script.md` (v2) — scenes mapped to
  Eduardo's domains; AIOps centerpiece; explicit Dynatrace-vs-Watchdog/Bits wedges +
  "tricky questions" prep.

Validates clean: `dd-demo validate --vertical agribusiness` → 0 errors.

## To run the demo (UI-first — `make ui` is the only command)
1. `eval "$(op signin)"` — **re-auth required; `make ui` stops at the op check otherwise.**
2. `make ui` → Configure tab → pick **Global Agribusiness (Bunge)** → Save → Deploy.
   Deploy reads your current `verticals/` + engine code live (source is bind-mounted
   into the lifecycle containers) — **no `make build` needed** for content/engine edits.
3. **Start the Simulator ~15 min before the AIOps scene** (cascade first fires
   ~15 min in, runs ~10 min, then recurs ~15 min after each completes). It runs on
   *this* env — the data→pricing→app-error signal and the `agri.itsm.*` close-loop
   are all live here; no separate org needed for the signal (see Watchdog caveat above).
   (After editing a plugin/config, just restart the Simulator from the UI — the mount
   reloads it; a rebuild is only needed if dependencies or the Dockerfile change.)

## Remaining / open for the demo
- **Not yet live-verified** against a real Datadog org (headless/unit-verified
  only). John should deploy once and confirm **all 4 dashboards** populate (the new
  one is **AIOps — ServiceNow Auto-Remediation**) and that the cascade fires within
  ~15 min. The `op` session must be re-authed first (see step 1 below).
- **ServiceNow loop is SIMULATED, not live.** The `workflows.yaml` steps deploy as
  no-ops (no ServiceNow connection in this env — validator flags this as expected).
  Demo the loop via the **AIOps dashboard** (auto-opened/closed/open/MTTR, driven in
  lockstep with the cascade) and the **close-loop notebook** (simulated enriched
  ticket text). To make it execute: bind a ServiceNow connection + add the verified
  action ID (`WORKFLOW_ACTIONS.md`).
- **Watchdog/Bits insights still need org history.** The cascade now drives clean,
  recurring signal on this env (data → pricing → app errors), so Watchdog has
  something to detect — but Watchdog baselines still want some history. If demoing on
  a fresh org, pre-run the sim a while or use an org that's seen `agri.*` before.
- **Nice-to-have polish:** model Eduardo's named KPI **"harvest truck counts per
  factory"** as a metric on the Global dashboard; per-app (myBunge/BungeServices) views.

## New assets this pass (where to find them)
- `verticals/agribusiness/workflows.yaml` — enrich→open→close + auto-close-on-recovery.
- `verticals/agribusiness/dashboards/agribusiness-aiops-servicenow.json` — the AIOps board.
- `notebooks.yaml` → **"AIOps Auto-Remediation — ServiceNow Close-Loop"** and
  **"Datadog vs Dynatrace — Differentiation (Bunge scorecard)"** (the leave-behind pack).
- `config.yaml` → new `itsm_automation` device category (`agri.itsm.*`, simulated).
- `dd_demo_toolkit/simulator/engine.py` → `app_impact` hook (drives `agri.app.*` from
  any plugin) + `vertical:` tag on all telemetry. Documented in `STYLE_GUIDE.md` §9.6–9.7.
- `docker-compose.yaml` → live `./dd_demo_toolkit` + `./verticals` read-only mounts on
  the `setup`/`simulator`/`teardown`/`teardown-all` services, so the UI Deploy + simulator
  read current files with no rebuild (CLAUDE.md §7 / STYLE_GUIDE §11 updated to match).

## Key facts to carry in
- Thesis: one data platform feeds every revenue app; one stale CME feed mis-prices
  all of them at once; nothing watches it today.
- Wedges vs Dynatrace: data breadth (NDM/network at 185 sites, logs, DBM, data
  platform), agentic + NL Bits AI, native ServiceNow loop, zero-config Watchdog,
  explainability. Don't dismiss Davis.
- Business case: 28 tools → ~5; MTTR (Shawn's 59-min rule); protect 10k txns/day +
  the **$190M Viterra synergy at risk without IT visibility**.
