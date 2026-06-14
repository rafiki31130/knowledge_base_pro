# Chapter 4 — SPL: acceleration with `tstats`, summary indexing and data models

> Your investigation searches return in two seconds; your scheduled saved searches and your dashboards do not. That gap is not about better SPL — it is about which acceleration mechanism sits underneath. This chapter pins down the three you can actually reach for as a power user (`tstats` on indexed fields, report acceleration, data model acceleration), tells you when summary indexing is the right primitive instead, and draws the line where you have to stop and ask an admin. After reading it, you should be able to look at a slow recurring search and say "this one wants `tstats summariesonly=t`" or "this one wants report acceleration", not "this one needs more hardware".

## Quick refresher

Keep these in working memory; the rest of the chapter assumes them.

- **Indexed fields vs search-time fields.** Indexed fields (`index`, `sourcetype`, `host`, `source`, `_time`, plus any field admin-extracted in `props.conf`/`transforms.conf` at index time) live in the `tsidx` files. Search-time fields are extracted on the search head from `_raw` at query time. `tstats` only reads indexed fields — that is where its speed comes from.
- **`tstats`.** A statistical command that scans `tsidx` files directly without rehydrating events. Orders of magnitude faster than `stats` when you can stay inside indexed fields, useless on anything else.
- **Data model + acceleration.** A data model is a schema (a tree of objects with constraints and calculated fields) layered on top of raw events. **Acceleration** materializes the model's tsidx-compatible summaries on a rolling window. `| tstats summariesonly=t … FROM datamodel=Authentication` reads only those summaries.
- **Report acceleration.** A per-saved-search summarization that backfills and maintains a small summary store for one specific report. Tied to one saved search, one schedule.
- **Summary indexing.** A "do-it-yourself" pattern: a scheduled search writes its results to a dedicated index (`summary_*`), and downstream searches read from that index instead of the raw one. Older, more flexible, more maintenance.
- **CIM.** The Common Information Model ships pre-built data models (`Authentication`, `Network_Traffic`, `Web`, etc.) that many Splunkbase add-ons normalize their data into. If your sourcetype is CIM-mapped and the model is accelerated, you get `tstats` performance for free.

## Major good practices

1. **Reach for `tstats` whenever you only need indexed fields.** `index=os sourcetype=linux_secure | stats count by host` is a job for `tstats`: `| tstats count where index=os sourcetype=linux_secure by host`. You skip event hydration entirely. On a busy index the speed-up is one to three orders of magnitude. The trade-off is hard: you cannot reach `_raw` or any search-time-extracted field from inside `tstats`. See [Search Reference — tstats](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Tstats).
2. **If a CIM data model covers your dataset, take the fast path.** Authentication failures, web hits, network flows, and endpoint events all have CIM models. `| tstats summariesonly=t count FROM datamodel=Authentication WHERE Authentication.action=failure BY Authentication.user` reads only the accelerated summaries and returns near-instantly. The work upfront is making sure your sourcetype is CIM-tagged by the right add-on; once it is, the model and its acceleration do the rest. See [Knowledge Manager Manual — About data models](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Aboutdatamodels) and the [Common Information Model documentation](https://docs.splunk.com/Documentation/CIM/latest/User/Overview).
3. **Use `tstats prestats=t` then post-process with `stats`.** This is the composable variant: `| tstats prestats=t count FROM datamodel=Web BY Web.src, _time span=1h | stats sum(count) as hits by Web.src` lets you reuse the same summary read for several aggregations and apply post-filters that `tstats` cannot express directly. It is also the form you stitch into base searches in dashboards (Chapter 5).
4. **Schedule report acceleration only for reports you actually use daily.** Each accelerated report runs a backfill once and then a maintenance summarization on its schedule, paying disk and indexer cost. Reserve it for a saved search that powers a frequently opened dashboard or a frequently triggered alert; do not enable it across the board "to make Splunk fast". See [Reporting Manual — Manage report acceleration](https://docs.splunk.com/Documentation/Splunk/9.4/Report/Manageacceleratesearch).
5. **Inspect coverage before trusting `summariesonly=t`.** Run `| datamodel <model> <object> summarize | search …` to see the model's acceleration size, retention, and gaps. If acceleration was disabled, paused, or recently rebuilt, `summariesonly=t` will silently miss recent or whole-range data. See [Knowledge Manager Manual — Accelerate data models](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Acceleratedatamodels).
6. **Pick the right primitive for the job.** `tstats` for ad-hoc fast reads of indexed fields. CIM + data model acceleration for shared, governed, reusable aggregations across teams. Report acceleration for a single saved search you care about. Summary indexing for use cases the other three cannot express — typically multi-step pipelines that need to keep the *output* of a transforming search around for months, well past any acceleration retention. They are not interchangeable, and choosing the wrong one shows up as either zero rows or a disk-full ticket.

## Anti-patterns to ban

1. **`| tstats … by user` when `user` is not indexed.** `tstats` returns silently empty or wrong results because the field does not exist at the tsidx layer. Symptom: a `tstats` query that returns zero rows where the equivalent `stats` returns thousands. Fix: either group by an indexed field (`host`, `sourcetype`), use a CIM data model where the field is in the model schema, or accept that this query needs `stats`. The Job Inspector's `normalizedSearch` is the giveaway.
2. **Enabling report acceleration on every dashboard panel "to make it fast".** Each acceleration is a backfilled summary plus a recurring maintenance job, and every minor edit to the underlying SPL invalidates and rebuilds it. Six accelerations on the same dashboard stress the indexers far more than the same dashboard with one shared base search (Chapter 5). Pick one or two reports per dashboard that genuinely justify it.
3. **`tstats summariesonly=t` without checking coverage.** When the model is partially accelerated, paused, or its retention is shorter than your time range, you read a hole and call the result "yesterday's metric". Symptom: counts that abruptly drop or vanish at a fixed offset from `now()`. Always run `| datamodel … summarize` once before pinning a dashboard on `summariesonly=t`.
4. **Building your own summary index by hand when a CIM data model would do it.** Hand-rolled summary indexes for "failed logins by user" or "bytes by src/dest" duplicate work the CIM Authentication and Network_Traffic models already do, with worse governance and no `tstats` ergonomics. Reserve summary indexing for genuinely custom multi-step pipelines a data model cannot express.
5. **Mixing `tstats` and `stats` results without normalizing the schema.** `tstats` against a data model returns CIM-prefixed field names (`Authentication.user`), `stats` returns the raw extracted ones (`user`). Joining or appending the two without a `rename Authentication.user AS user` produces mysterious zero overlap and silent dropouts. The fix is a single `rename` step at the boundary.
6. **Treating report acceleration as a substitute for tightening the SPL.** If the underlying search reads `index=*` over `-30d@d`, acceleration will faithfully backfill and maintain a fast view of a search that should never have been written in the first place. Acceleration accelerates correct searches; it cannot redeem broken ones.
7. **Forgetting summary indexes are a separate index.** A downstream search needs explicit `index=summary_X` to be readable, the summary index must be in the role's `srchIndexesAllowed`, and the schema you write is the schema you have to query forever (renaming a field in the summary search next month diverges from a year of history). The flexibility of summary indexing is also its trap.

## Worked examples

### Same query, `stats` versus `tstats`

You want the count of failed SSH logins per host over the last 24 hours. The `stats` version reads events from disk and applies a search-time extraction for `vendor_action`:

```spl
index=os sourcetype=linux_secure vendor_action=failure earliest=-24h@h latest=now
| stats count by host
```

If `vendor_action` is search-time extracted (the common case), `tstats` cannot filter on it directly. But the equivalent query against the **Authentication** data model — assuming your add-on tags `linux_secure` into CIM — does:

```spl
| tstats summariesonly=t count
    FROM datamodel=Authentication
    WHERE Authentication.action=failure
        AND nodename=Authentication.Failed_Authentication
        AND earliest=-24h@h latest=now
    BY Authentication.dest
```

Open the Job Inspector on both. The `stats` version's `command.search.index` will dominate; the `tstats` version's total runtime should be a fraction of a second. What you give up: the `tstats` result has no `_raw`, no extracted detail, no per-event drill-in. That is the trade — fast aggregate, not investigation.

### Build a daily summary index of failed logins

You want a year of "failed logins per user per day" without paying for a year of full-volume Authentication acceleration. The pattern is a saved search that writes to a summary index:

```spl
index=os sourcetype=linux_secure vendor_action=failure
    earliest=-1d@d latest=@d
| bin _time span=1d
| stats count as failures by _time, user, host
```

Configured as a scheduled saved search with **Summary Indexing** enabled in the action panel (Settings → Searches, reports, and alerts → Edit Schedule → Summary indexing), it writes one row per `_time`/`user`/`host` to `index=summary_authn_daily` every night. Querying a year of it is then trivial:

```spl
index=summary_authn_daily earliest=-365d@d latest=@d
| stats sum(failures) as failures by user
| sort - failures
```

Two things to notice. First, the summary search itself must be admin-enabled in practice: writing to a summary index requires the `schedule_search` capability and the right write ACLs (see escalation). Second, the schema (`_time`, `user`, `host`, `failures`) is now a contract — if you rename a field in the summary search next month, your year of history quietly diverges.

### Diagnose a `tstats summariesonly=t` returning 0 rows

A dashboard panel that has been working for months suddenly shows zero. The SPL is unchanged:

```spl
| tstats summariesonly=t count
    FROM datamodel=Network_Traffic
    WHERE earliest=-1h@h latest=now
    BY All_Traffic.src
```

Triage in three steps. First, drop `summariesonly=t`:

```spl
| tstats count
    FROM datamodel=Network_Traffic
    WHERE earliest=-1h@h latest=now
    BY All_Traffic.src
```

If counts come back, the issue is acceleration, not the model. Second, run `| datamodel Network_Traffic All_Traffic summarize`. Look at `summary_status`, `last_error`, and the accelerated range. Common causes: acceleration was paused (admin), the model was edited (every edit invalidates the summary and triggers a backfill that can take hours), or the model's retention is shorter than your dashboard's time window. Third, look at `index=_internal source=*scheduler.log* datamodel` for recent failures — readable from the search head, even if the fix is admin-side.

The lesson is that `summariesonly=t` is a fast path that depends on an admin-managed state. When it goes silent, you escalate with this exact triage already done, not with "tstats is broken".

### Report acceleration on a single saved search

You own a saved search that powers a daily compliance report:

```spl
index=security sourcetype=cisco:asa action=denied earliest=-7d@d latest=@d
| stats count by src_ip, dest_ip, dest_port
| sort - count
| head 100
```

It takes 45 seconds. The dashboard panel that displays it runs every time someone opens the page. From Settings → Searches, reports, and alerts → Edit → Acceleration, toggle "Accelerate this report" with a summary range of 7 days. Splunk runs an initial backfill (visible under Settings → Report acceleration summaries) and then maintains the summary on the saved search's schedule. The next page open returns in under a second.

What to notice: the acceleration is tied to *this saved search*. Edit the SPL — even change a field order — and Splunk invalidates the summary and backfills again. Acceleration is a contract on the search text, not its semantics. If the report is still being iterated on, wait until it stabilizes before turning acceleration on.

## When to escalate to an admin

- **A data model is not accelerated, or coverage is too low** (`| datamodel … summarize` shows `summary_status` stuck, an accelerated range shorter than your dashboards need, or a `summarize` size of zero). Acceleration is configured on the data model itself, requires the `accelerate_datamodel` capability, and consumes indexer disk per node — admin-only. Ask for: "enable acceleration on data model `<Model>` (e.g. `Authentication`), retention `N` days, justification: `<dashboard / alert that depends on it>`, expected daily volume `<…>`".
- **You need a new indexed field** (`src_ip`, `app`, etc.) so `tstats` can use it directly instead of going through a CIM model. Index-time field extractions live in `props.conf`/`transforms.conf` on the indexing tier, plus a `fields.conf` `INDEXED = true` declaration. The change has cluster-wide impact (every new event from now on is fatter on disk) and must be re-applied at parse-time, so it is strictly admin territory. Ask for: "add `<field>` as an index-time-extracted indexed field for sourcetype `<sourcetype>`, regex `<…>`, justification: `<tstats use case>`".
- **You want to enable report acceleration but cannot** (the "Accelerate" toggle is missing or returns a permission error). The `schedule_search` capability is required to own a scheduled or accelerated report. Ask for: "grant `schedule_search` to role `analyst`, scope `<app>`, justification: `<report name + business cadence>`".
- **A summary index is filling up disk, or you need a new one.** Summary indexes are real indexes — created in `indexes.conf`, with their own retention (`frozenTimePeriodInSecs`, `maxTotalDataSizeMB`) and ACLs. Both creation and retention review are admin-only. Ask for: "create summary index `summary_<name>` with retention `<N>` days, max size `<…>`, write ACL for saved search `<…>`, read ACL for role `<…>`" or "review retention on summary index `summary_<name>`, current usage `<…>`".
- **You suspect a CIM add-on is not tagging your sourcetype** (your raw events are there, but `| tstats … FROM datamodel=Authentication WHERE host="<your host>"` returns nothing). CIM normalization is configured in the relevant Splunk_TA_* add-on on the search head and forwarders — admin/app-owner only. Ask for: "verify CIM Authentication tagging for sourcetype `<sourcetype>`, expected `eventtype=authentication`, expected `Authentication.action` populated; sample event: `<…>`".

## Sources

- [Splunk Enterprise 9.4 — Search Reference — tstats](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Tstats)
- [Splunk Enterprise 9.4 — Knowledge Manager Manual — About data models](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Aboutdatamodels)
- [Splunk Enterprise 9.4 — Knowledge Manager Manual — Accelerate data models](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Acceleratedatamodels)
- [Splunk Enterprise 9.4 — Knowledge Manager Manual — About summary indexing](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Aboutsummaryindexing)
- [Splunk Enterprise 9.4 — Reporting Manual — Manage report acceleration](https://docs.splunk.com/Documentation/Splunk/9.4/Report/Manageacceleratesearch)
- [Common Information Model documentation](https://docs.splunk.com/Documentation/CIM/latest/User/Overview)
- [Splexicon](https://docs.splunk.com/Splexicon) — canonical definitions for *tstats*, *data model*, *data model acceleration*, *report acceleration*, *summary index*, *indexed field*.
