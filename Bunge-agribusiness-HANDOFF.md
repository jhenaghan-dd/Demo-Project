# Bunge "Art of the Possible" — Handoff

**Current as of 2026-09-09. Branch: `bunge-agribusiness-ready`** (cut from `main`).

Champion **Eduardo Solis** (building global monitoring from scratch; AIOps = his #1).
Economic buyer **Tiago**. Presenter **John Rath** + Brian/Steve. **Dynatrace** is
co-evaluating into a Gartner scorecard; selection ~Nov 2026.

> **Read this first.** All the work now lives on **one branch,
> `bunge-agribusiness-ready`**. The older `bunge-agribusiness` branch and
> `stash@{0}` still exist but are **superseded** — the branch *alone* is broken
> (gauges emit at 3×, the cascade is clamped flat, and three widgets query a tag
> that service metrics never carry). Don't build from either.

---

## State of play

| | |
|---|---|
| Vertical | `agribusiness`, `env_prefix: agri` — its own vertical, not an overlay, so no banking/factory noise on screen |
| Estate | 142 devices, 10 device types, 6 services, 46 metrics |
| Dashboards | **4 / 49 widgets**, each with 3 template variables |
| Also | 13 monitors, 5 SLOs, 6 Service Catalog entries, 3 notebooks, 2 workflows |
| Tests | 201 pass; all 8 verticals validate **0 errors** (agribusiness has the repo's *fewest* warnings, 2 — both the known ServiceNow no-op) |
| Cascade | 0 errors over 400 ticks; feed age 3.4 → 578s, stale-quote 0.6 → 13.9% |
| RUM / LLM Obs | **off** for agribusiness — no `hospitality.rum.*` or `ai-care-companion` leaking into a Bunge org |

### The four dashboards
1. **Global KPI** (exec) — 9 widgets
2. **Apps & Data Platform** (the cross-cutting story) — 8
3. **Infrastructure / Network / SAP** — 19, incl. the new Compute & Cloud section
4. **AIOps — ServiceNow Auto-Remediation** — 13

---

## New this pass (2026-09-09)

**Region drill-down.** All four dashboards now carry template variables —
`region`, `environment`, `business_segment`. `environment` defaults to
`production`, so **every dashboard opens exactly as it did before**; you gain the
drill-down without changing what's on screen. This is the "global rollup, then
drill to region" ask the boards previously couldn't answer at all.

Two sets of queries are deliberately *not* wired to the variables:
- the three `agri.app.*` queries — service metrics carry only `service_name`, so a
  `$region` filter returns nothing. This is the exact trap that blanked three
  widgets in June.
- the `agri.itsm.*` `{*}` counters — global ServiceNow-programme gauges, not
  per-region quantities.

**Compute & Cloud section** (6 new widgets on the Infra/Network/SAP board), all on
metrics that were already emitting but appeared on no dashboard:
- busiest VMware hosts by CPU, and **VM density** — consolidation headroom, i.e.
  the "where does the Viterra estate land" question
- **GKE node CPU/memory and pod restarts** — closes a real gap: Cloud is one of the
  four towers in the brief and had *no* widget at all
- Oracle active connections and replication lag

Toplists and timeseries only — **no Host Map or Geomap**, despite those being the
obvious "datacenter" picks. The engine sets `host.name` for services and never for
simulated devices, and the regions aren't country codes, so both render empty.
Zero of the repo's 796 existing widgets use either type; that's the tell.

`agribusiness` was also added to the CI validate matrix (it was never checked
before — the same gap that let `waste_management` and `oilgas` drift).

---

## Open items — read before you present

**1. Not yet deployed to the org.** `dd-demo status --vertical agribusiness`
reports **0 dashboards** — the June deploy is gone. Everything above is verified
headless (tests, local validate, a 400-tick cascade run) but the new template
variables and the 6 new widgets have **never been accepted by the live Datadog
API**. That's the one class of bug local validate cannot catch — it's how the
nested `custom_unit` slipped through in June.

Deploy them and eyeball all four boards before you're in front of anyone:

```
eval "$(op signin)"                       # if needed
cd dd-demo-toolkit
# .env currently says healthcare/ascension — switch to agribusiness
make ui                                   # Configure → Global Agribusiness (Bunge) → Save → Deploy
```

Heads-up: **23 Ascension containers are up (most 7 days)**. Bringing agribusiness
up on the simulator means taking that stack down (`make down`, reversible with
`make up`). Deploying *dashboards* alone does not.

**2. Data needs the simulator.** `make validate-live` asserts every dashboard
metric returned a point in the last hour, so it only passes with the agribusiness
simulator running. Filter it — `-k agri` — or it fails on every vertical that
isn't running. Start the simulator **~15 min before** the AIOps scene: the cascade
first fires ~15 min in, runs ~10, then recurs ~15 min after each completes.

**3. ServiceNow loop is SIMULATED.** The two `servicenow_*` steps deploy as
`com.datadoghq.core.noop`. The action ID is not published anywhere and could not be
verified without a bound connection — and **guessing is worse than the fallback**:
an unknown actionId degrades to a no-op, but a *wrong* one 400s the entire workflow
create. The 30-second recipe to grab the real ID from the UI is in the header of
`verticals/agribusiness/workflows.yaml`.

Demo the loop the way it actually works today: the **AIOps dashboard**
(auto-opened / auto-closed / open / MTTR / noise-reduction, driven in lockstep with
the cascade) plus the **close-loop notebook**. Those are live signal, not slideware.

**4. Watchdog/Bits still want org history.** The cascade gives Watchdog something
to detect, but baselines need time. On a fresh org, pre-run the sim.

**5. Nice-to-have, not done.** Eduardo's named KPI *"harvest truck counts per
factory"* as a metric on the Global board; per-app myBunge/BungeServices views.

---

## Repo hygiene note (not demo-blocking)

`pyproject.toml` pins `black>=23.0` with no upper bound. black 26.5.1 now wants to
reformat 33 files and flake8 reports 326 findings — **identical on pristine `main`**,
so this predates the Bunge work. CI only runs on `main` and on PRs into `main`, so a
branch push is quiet; opening a PR will go red on lint until black is pinned.

---

## Key facts to carry in

- **Thesis:** one GCP data platform feeds every revenue app; one stale CME feed
  mis-prices all of them at once; nothing watches it today. The service dependency
  graph — every revenue app → `bunge-data-platform` — *is* the pitch.
- **Wedges vs Dynatrace:** data breadth (NDM across 185 sites, logs, DBM, the data
  platform itself), agentic + NL Bits AI, native ServiceNow loop, zero-config
  Watchdog, explainability. Don't dismiss Davis.
- **Business case:** 28 tools → ~5; MTTR (Shawn's 59-minute rule); protect 10k
  txns/day and the **$190M Viterra synergy at risk without IT visibility**.
- **SAP is modeled to the real Marketplace tiles only:** HANA → Redpeaks, S/4HANA
  and NetWeaver → Redpeaks/Agentil, SAP Cloud ALM → RapDev, Integration Suite →
  logs. Query-level/"SELECT \*" lives on **Oracle DBM** (DBM ≠ HANA). Sybase/MaxDB/
  BusinessObjects deliberately left out — not in Bunge's stack per the briefing.
- The cascade leaves network, SAP, DB and host metrics **untouched**, so "let's rule
  out the network" is an honest step in the RCA rather than theatre.

`Bunge-art-of-the-possible-demo-script.md` is a linear scene-by-scene walkthrough.
Treat it as a **source of talk-track lines**, not a running order.
