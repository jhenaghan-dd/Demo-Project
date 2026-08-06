# WasteManagement — Fleet at Scale

An "art of the possible" extension: stand up a **fleet of collection trucks**
where **every truck is a distinct Datadog host** — with **no AWS and no
per-truck container** — and show the whole fleet moving live on a map.

One local process (`run.py`) animates the fleet and drives two consumers off
the *same* truck snapshot:

| Consumer | What it produces |
|---|---|
| `dd_emitter.py` | Per-truck `system.*` + `wm.truck.*` metrics via `POST /api/v2/series` with `resources:[{type:host}]`, tagged `host:wm-truck-NNNN` → each truck is a **host** in the Infrastructure list / Host Map. Sets host tags (region, metro, route, instance-type) too. |
| `server.py` | A live **Leaflet fleet map** on `:8088` — trucks driving the street grid, coloured by status, with depots/landfills, metro filter, and per-truck telemetry popups. |

Because both read one `Fleet`, a dot on the map and its host in Datadog are
guaranteed to be the same truck in the same state.

## Files

- `fleet_routes.yaml` — metros, depots/landfills, fleet size, telemetry envelope. **Scale the fleet here** (`routes_per_metro` × `trucks_per_route`).
- `fleet_sim.py` — movement + telemetry engine (pure, no network). Routes are seeded street-grid polylines.
- `dd_emitter.py` — turns trucks into Datadog hosts (reuses the toolkit `DatadogAPIClient`).
- `server.py` — stdlib HTTP: `/` map, `/api/positions`, `/api/routes`, `/healthz`.
- `static/index.html` — the Leaflet map (loads Leaflet + CARTO tiles from CDN; needs a browser with network).
- `run.py` — combined entrypoint (movement + emitter + map).
- `dashboards/fleet_operations.json` + `deploy_dashboard.py` — the native in-Datadog **Host Map + KPI** dashboard.

## Run it (from the repo root)

```bash
make wm-fleet-demo         # ⭐ one-shot: (re)start fleet + tunnel detached AND embed the live map in the dashboard
make wm-fleet-map          # map only, on :8088 — no Datadog, no credentials
make wm-fleet              # full: emit truck-hosts to Datadog AND serve the map (needs 1Password unlocked)
make wm-fleet-dashboard    # create the Fleet Operations dashboard in Datadog
make wm-fleet-demo-down    # stop the detached fleet + tunnel
```

**Before a demo, just run `make wm-fleet-demo`** (needs 1Password unlocked). It
starts the fleet + a fresh Cloudflare tunnel detached (survive terminal close),
captures the new tunnel URL, and redeploys the dashboard with the live map
embedded — recovering cleanly after a laptop sleep/reboot. Because quick-tunnel
URLs rotate on restart, re-running it is how you refresh the embed.

`make wm-fleet` runs in the foreground (Ctrl-C to stop). It needs the
1Password desktop app unlocked — the Datadog API/APP keys are resolved from
`op://` refs in `.env` by `op run` (repo secret policy).

## Embed the live map inside the Datadog dashboard (iframe widget)

The Fleet Operations dashboard has an `iframe` widget that renders the live map
*inside* Datadog. Datadog is HTTPS and the iframe loads in the viewer's
browser, so the map must be served from an **HTTPS URL that browser can reach**
— `http://localhost:8088` won't embed (mixed content + not reachable by anyone
else).

**Free tunnel — Cloudflare quick tunnel (no account, no signup):**

```bash
brew install cloudflared                          # one-time
make wm-fleet                                      # terminal 1: fleet + map on :8088
cloudflared tunnel --url http://localhost:8088     # terminal 2: prints an https URL
```

`cloudflared` prints a line like `https://random-words.trycloudflare.com`.
Feed that to the dashboard deploy:

```bash
WM_FLEET_MAP_URL=https://random-words.trycloudflare.com make wm-fleet-dashboard
```

The iframe widget now shows the moving-truck map live inside Datadog. Without
`WM_FLEET_MAP_URL`, the dashboard deploys fine but omits the embed panel (the
Host Map + KPIs still render).

> Quick-tunnel URLs are ephemeral (they change each run) — great for a live
> demo. For a persistent shared dashboard, host `server.py` somewhere with a
> stable HTTPS URL (e.g. an `ese-sandbox` instance) and pass that instead.
> ngrok also works but its free tier now requires an account + an interstitial;
> the Cloudflare quick tunnel is the friction-free option.

## Notes on the two map paths

- **Native Datadog:** the geomap widget only does *region choropleth* for
  metrics — it won't plot arbitrary truck GPS. The right native fleet visual is
  the **Host Map widget** (in `dashboards/fleet_operations.json`), which works
  precisely because each truck is now a host.
- **Custom JS:** the moving-truck street map is the Leaflet showpiece here. No
  *native* widget runs arbitrary JS / external map tiles (the Vega-Lite
  wildcard widget can't either), but the **iframe widget** embeds the live page
  inside a dashboard — see "Embed the live map" above.

## Teardown

Hosts age out of the Infrastructure list automatically a few hours after the
emitter stops. The dashboard carries the `[dd-demo-toolkit:` marker, so
`make wm-fleet-dashboard-delete` (or `dd-demo teardown --all-verticals`)
removes it.
