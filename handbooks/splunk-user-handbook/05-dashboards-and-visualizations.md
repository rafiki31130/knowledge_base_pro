# Chapter 5 — Dashboards and visualizations

> You can already build a dashboard. The question is whether the next one you ship will be fast, readable, and survive a Splunk minor upgrade — or whether it will join the graveyard of 30-panel pages that everyone leaves open and nobody trusts. This chapter pins down the handful of patterns that turn a dashboard from a search-saturation device into something an on-call peer will actually open at 3am.

## Quick refresher

Keep these in working memory; the rest of the chapter leans on them.

- **Dashboard Studio vs Classic SimpleXML.** In 9.x, **Dashboards Studio** is the forward direction (JSON definition, modern visualization library, layouts, defaults biased toward base searches). **Classic SimpleXML** still exists, still ships, still works — and still owns most of the dashboards installed in 9.x estates. Migration is one-way and lossy (see [Dashboards and Visualizations — Studio Overview](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/Overview), [Classic SimpleXML](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/AboutdashboardsandSimpleXML)).
- **Base searches and chained / post-process searches.** A **base search** runs once; **chained searches** transform its results without going back to the indexer. One read for N panels instead of N reads (see [Use base searches](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/Savedsearches)).
- **Inputs and tokens.** A dashboard input (time picker, dropdown, multiselect, text) sets a **token** that the searches reference (`$token$` in both Classic SimpleXML and Studio JSON). Dependent inputs are inputs whose values come from a search that itself uses another input's token.
- **Drilldown.** Clicking a panel can navigate to another dashboard, run a contextual search, or open a URL. Drilldowns inherit time and tokens from the source unless you bound them explicitly.

## Major good practices

1. **Use base searches whenever two or more panels share scope.** A six-panel dashboard whose panels all start with `index=web sourcetype=access_combined earliest=-24h@h` is six independent reads of the same dataset. Promote the common prefix to a base search, then chain each panel's `stats`/`timechart`/`top` after the `|` of a post-process pipeline. The indexer load drops by roughly N; the search head still computes each panel locally, so visual specificity is preserved. See [Use base searches](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/Savedsearches).
2. **Set tight defaults on the time picker, and never default to `All time`.** A dashboard's default time range is a forcing function: most users will not change it. Default to `-24h@h` or `-7d@h` with a `latest` you can defend, and snap (`@h`, `@d`) so the search head's job cache helps you. `All time` on a busy index is a near-guaranteed indexer spike every time someone bookmarks the page.
3. **Bound every multiselect input to a small, deterministic source.** If a dropdown of hosts is fed by `index=os | stats values(host)` over an open window, you have hidden a full-fat search behind a UI widget. Back the input with a `lookup` (e.g. `assets.csv`) or with `tstats values(host) where index=os earliest=-24h@h` against an indexed field — the input renders in tens of milliseconds instead of seconds, and the list does not balloon to thousands of values during an incident.
4. **In Dashboards Studio, prefer the built-in visualization library; in Classic, lean on SimpleXML drilldown via `$token$`.** Studio's chart, single-value, table, and choropleth come pre-themed and respond to layout changes — reach for a custom visualization only when none of the built-ins fit. In Classic, contextual drilldown via `$click.value$`, `$row.field$`, and `$earliest$`/`$latest$` covers most navigation needs without writing JavaScript (see [About tokens](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/AboutTokens) for the Studio model and [Classic SimpleXML](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/AboutdashboardsandSimpleXML) for the SimpleXML one).
5. **Add a `?` info panel at the top of every dashboard.** One small Markdown panel — owner, primary data sources (`index=`, `sourcetype=`), refresh cadence, intended audience, link to the runbook — costs you ten minutes and saves a stranger an hour of guessing. It is also the first thing your future self reads when a dashboard surprises you six months later.
6. **Make refresh cadence explicit and conservative.** A dashboard with eight panels and a 30-second auto-refresh, left open on eight desks, generates roughly 60 base-search dispatches per minute against the same data. Default to manual refresh; if you must auto-refresh, push the interval to several minutes and shorten it only on dashboards a single on-call peer is actively driving.
7. **Pick Studio or Classic per dashboard and write it down.** Both technologies are supported in 9.x, but mixing them in the same dashboard is not really an option — the runtime, the JSON/XML definition, and the drilldown model are different. Decide at design time, note the choice in the info panel, and migrate (or do not) as a separate piece of work.

## Anti-patterns to ban

1. **The 30-panel dashboard where every panel re-runs the same base scope.** Symptom: opening the page makes the indexer's search queue spike. Why it is wrong: you are paying N times to read the same events. Fix: extract the common prefix into a base search and chain post-process searches; if the panels truly need different scopes, split into separate dashboards.
2. **Auto-refresh `30s` left on by default.** Symptom: indexer load that does not correlate with anyone actively looking at a screen. Why it is wrong: an idle dashboard consumes the same scheduler budget as an active one, but produces no value. Fix: manual refresh by default, with documented exceptions for live monitoring views.
3. **Drilldowns that open a search with no time bound.** Symptom: a single click from a dashboard panel opens a search that runs against `All time` or inherits a much wider window than the source. Why it is wrong: a curious user paid one search; a misconfigured drilldown silently pays for many. Fix: pass `$earliest$`/`$latest$` (Classic) or the equivalent Studio token mapping into the destination search, and verify in the Job Inspector after deploy.
4. **Mixing Studio and Classic in the same dashboard.** Symptom: a "let me just convert one panel" experiment that never finishes. Why it is wrong: the conversion is one-way, lossy, and the two runtimes do not share a drilldown contract. Fix: pick the target per dashboard, plan a full conversion as a separate change, and keep the original until the new one has been used in anger.
5. **Hard-coding values that should be `$token$`.** Symptom: a dashboard with `host=web01` baked into every search, and a copy of the same dashboard for `db01`. Why it is wrong: the second time you copy-paste the JSON or XML, you have admitted the design is wrong. Fix: promote the variant axis to an input, parameterize the searches with the input's token, and delete the duplicates.
6. **Tables with fifty columns "in case someone needs them".** Symptom: a wide horizontal scrollbar and a 5-second render. Why it is wrong: every column is a search-time field extraction the search head has to materialize, and the user cannot read the result anyway. Fix: render the small set of columns that drive the decision, and put the rest behind a row-level drilldown.
7. **Multiselect inputs backed by an unbounded `stats values()`.** Symptom: the dropdown takes seconds to populate and contains thousands of entries. Why it is wrong: you have buried a full base search inside a UI element, and made the dashboard slower to load than to use. Fix: back the input with a `lookup` or with `tstats` over a short window against an indexed field.

## Worked examples

### Convert a 6-panel dashboard to one base search and chained panels

Six panels currently each start with the same scope:

```spl
index=web sourcetype=access_combined earliest=-24h@h latest=now
| stats count by status
```

```spl
index=web sourcetype=access_combined earliest=-24h@h latest=now
| timechart count by host limit=5
```

```spl
index=web sourcetype=access_combined earliest=-24h@h latest=now
| top uri_path limit=10
```

— and so on. Six reads of the same events. Promote the prefix to a base search and rewrite each panel as a post-process:

Base search:

```spl
index=web sourcetype=access_combined earliest=-24h@h latest=now
```

Panel 1 — status histogram (post-process of the base):

```spl
| stats count by status
```

Panel 2 — host trend:

```spl
| timechart count by host limit=5
```

Panel 3 — top URIs:

```spl
| top uri_path limit=10
```

What to notice. The post-process pipelines run on the search head, not the indexers, so transforming commands that fan out (`stats by host`, `timechart`) are fine, but anything that needs `_raw` again (a late `regex` against `_raw`, for instance) will silently break or read incorrectly. Keep the base search wide enough to include every field the post-processes reference, and use `fields` early in the base to drop noise without dropping the fields the panels need.

### Build a dependent input pair bounded by a lookup

Two inputs: `env` (environment) drives the list of hosts shown by `host`. The naive version backs `host` with `index=os | stats values(host) by env` — a full base search every time `env` changes. The good version uses a small `assets.csv` lookup that maps `host → env`:

```spl
| inputlookup assets.csv
| where env=$env$
| stats values(host) AS host
```

The dropdown renders in tens of milliseconds, the list is bounded by what is in `assets.csv` (an explicit asset inventory, not whatever happened to log in the last hour), and an empty environment immediately reveals an inventory gap instead of an indexer load spike. The same shape works for `app_owner_payments`-scoped dashboards: bound the user-facing selector to the lookup the owning team maintains.

### A scorecard row of single-value tiles backed by `tstats`

A row of four single-value tiles (24h events, 24h unique sources, 24h error rate, 7d-vs-24h delta) is one of the worst offenders for redundant base searches when written naively. Back each tile with `tstats` against an indexed field over a tight window:

```spl
| tstats count where index=security earliest=-24h@h latest=now
```

```spl
| tstats dc(src_ip) AS unique_sources where index=security earliest=-24h@h latest=now
```

`tstats` reads from the indexed tsidx rather than `_raw`, so a four-tile row that would cost four full reads costs roughly four indexed lookups — fast enough that you can leave a manual refresh button without anyone complaining (see Chapter 4 for the broader `tstats` discussion). What to notice: `tstats` only sees indexed fields and accelerated-data-model fields, so the choice of field matters; if you find yourself reaching for a regex-extracted field in a tile, you have outgrown a `tstats` tile and should either accept the cost of a base search or ask an admin about indexed extraction.

### Wrong version vs corrected version of a drilldown

A panel on a 24h scoped dashboard has a drilldown that opens this search:

```spl
index=web sourcetype=access_combined status=$click.value$
```

No time bound. Clicking the panel opens a search that runs against the user's last-clicked time range — frequently `All time`. The corrected version forwards the source dashboard's time tokens:

```spl
index=web sourcetype=access_combined status=$click.value$ earliest=$earliest$ latest=$latest$
```

What to notice. The fix is two tokens, not a rewrite. The general rule is that every drilldown is a search the dashboard authorized on the user's behalf; if you would not write `index=web sourcetype=access_combined status=200` without a time bound in the search bar, do not let the drilldown ship that way either. Verify with the Job Inspector once after deploying any new drilldown.

## When to escalate to an admin

- **A dashboard is shared at `App` or `Global` scope but you cannot change its permissions.** → Sharing scope above `Private` is gated by the dashboard's owner and by role-level capabilities; you do not have rights to flip it. → Ask: "change permissions on dashboard `dash_X` in app `my_company_app` to <scope>, current owner `alice`, requester role `analyst`".
- **A dashboard needs acceleration via a saved scheduled search.** → Scheduling a search requires the `schedule_search` capability, which is admin-controlled and not granted to standard analyst roles. → Ask: "grant `schedule_search` to role `analyst` for accelerating dashboard `dash_X`, expected cadence `*/15 * * * *`, justification `…`".
- **A Classic dashboard depends on a custom JavaScript or CSS extension.** → Custom JS/CSS extensions are packaged inside an app's `appserver/static/` and require an admin to deploy and validate them (and to confirm they survive the next minor upgrade). → Ask: "deploy JS extension `viz_X.js` and stylesheet `viz_X.css` in app `my_company_app`, source attached, target dashboard `dash_X`".
- **A Studio dashboard renders empty or broken after a Splunk minor upgrade.** → Studio runtime ships with the Splunk Enterprise version; known regressions between 9.x minor versions exist and are tracked by Splunk. The admin can correlate with release notes and known issues. → Ask: "Studio dashboard `dash_X` broke after upgrade to 9.x.y, please check regression notes and confirm whether a definition change or a wait-for-fix is appropriate".
- **A dashboard exposes data the requester should not see.** → Index- and sourcetype-level visibility is governed by `authorize.conf` on the search head and indexing tiers, not by dashboard sharing. Trying to hide data with dashboard permissions is a leak waiting to happen. → Ask: "review role `analyst` index/sourcetype visibility, dashboard `dash_X` currently exposes `index=security` to a wider audience than intended".

## Sources

- [Splunk Enterprise 9.4 — Dashboards and Visualizations — Studio Overview](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/Overview)
- [Splunk Enterprise 9.4 — Dashboards and Visualizations — Classic SimpleXML](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/AboutdashboardsandSimpleXML)
- [Splunk Enterprise 9.4 — Dashboards and Visualizations — Use base searches](https://docs.splunk.com/Documentation/Splunk/9.4/Viz/Savedsearches)
- [Splunk Enterprise 9.4 — Dashboards and Visualizations — About tokens (Studio)](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/AboutTokens)
- [Splexicon](https://docs.splunk.com/Splexicon) — canonical definitions for *base search*, *post-process search*, *token*, *drilldown*.
