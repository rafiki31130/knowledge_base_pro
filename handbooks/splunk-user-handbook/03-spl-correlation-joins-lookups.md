# Chapter 3 — SPL: correlating events with joins, subsearches, and lookups

> You have two sets of events and you want one answer. The reflex Splunk muscle memory hands you is `join` or `[ search … ]`, and both will let you down — silently truncated, painfully slow, or quietly wrong — at exactly the moment you stop watching. This chapter rewires that reflex around `stats by`, `lookup`, `inputlookup`, and `multisearch`, and lays out what each one costs and where each one breaks. After reading it, your default move for "correlate A with B" stops being `join` and starts being a question: *do these two sets share a key, and on which side does the heavy lifting belong?*

## Quick refresher

Keep these terms straight before you write a correlation:

- **`join`.** Joins two result sets row-by-row on a shared field. Takes a subsearch as its right side, inherits every subsearch limit (see below), and runs on the search head. Cost is real, lateness is silent.
- **`lookup`.** Enriches results with rows from a **lookup table** — a CSV file or a KV Store collection that an admin has registered as a [lookup definition](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Aboutlookupsandfieldactions). Refresh cadence is whatever the admin set.
- **`inputlookup` / `outputlookup`.** Read the lookup table directly into the pipeline as events (`inputlookup`), or write the current result set out to one (`outputlookup`, capability-gated).
- **`multisearch`.** Runs two or more base searches *in parallel* and unions their events upstream of the first transforming command. Streaming-friendly.
- **`append` / `appendcols` / `appendpipe`.** Concatenate results (`append`), bolt columns on the right (`appendcols`), or fork the pipeline and re-merge (`appendpipe`). All centralized on the search head.
- **Subsearch.** Anything in `[ … ]`. Runs first, returns a result set, gets spliced into the outer search. **Default caps: 50 000 rows (`maxout`) and 60 seconds (`maxtime`).** When a cap hits, Splunk does **not** error — it truncates silently and the outer search runs on a partial answer. The single most expensive trap in this chapter.
- **Streaming vs centralized.** `stats`, `lookup`, `multisearch` are distributable to the indexers and stream. `join`, `append`, `appendcols`, `appendpipe` are centralized on the search head. See [Search Manual — Types of commands](https://docs.splunk.com/Documentation/Splunk/9.4/Search/Typesofcommands).

## Major good practices

1. **Default to `stats by <key>` when both sides live in the indexer.** If the two sets you want to correlate are events from the same indexes (even different sourcetypes), pull them in a single base search, then collapse on the shared key: `index=os sourcetype=linux_secure OR sourcetype=auth_app | stats values(action) by user`. One pass over the data, no subsearch cap, fully parallelized. This rewrite replaces the large majority of the `join`s you would otherwise write.
2. **Use `lookup` for stable enrichment, not for filtering.** A `lookup` against `users.csv` to attach `department` and `manager` to each result is exactly its job; the lookup table is broadcast to the indexers and the enrichment streams. Filtering with a lookup ("only keep rows whose user is in this CSV") is also legal but takes more care — use `inputlookup` upstream instead (next bullet).
3. **Inject a small static set with `inputlookup append=t`, not with a subsearch.** When you need to seed your search with "these 200 known hosts", write `| inputlookup hosts.csv | fields host` first, or `| inputlookup hosts.csv append=t` as a join-by-pipe. The subsearch alternative `[ inputlookup hosts.csv | fields host ]` works for tiny sets but silently truncates the day someone grows the CSV past 50 000 rows. See [Search Reference — inputlookup](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Inputlookup).
4. **Reach for `multisearch` when you have two real base searches to merge.** Two parallel scopes that you want unioned before transforming — say `index=web sourcetype=access_combined` and `index=security sourcetype=WinEventLog:Security`, both contributing to a `stats count by user` — is what `multisearch` is for. It runs the legs in parallel on the indexers and is cheaper than two `append` halves on the search head. See [Search Reference — multisearch](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Multisearch).
5. **If `join` is genuinely the right tool, pre-aggregate both sides and pin the type.** A legitimate `join` (different time windows, asymmetric aggregations that `stats by` cannot express) is rare but real. When you write one, write `join type=inner overwrite=t max=0 user [ search … | stats … by user ]` — explicit `type`, both sides reduced to one row per key before the join, `max=0` to disable the per-key row cap if you understand the consequences. The subsearch still inherits `maxout`/`maxtime`; document the assumption that the right side fits.
6. **Read the subsearch limits every time you write one.** `[ search … ]` runs first, has 60 seconds and 50 000 rows by default, and truncates without error if either is hit. Before you ship a subsearch, ask: *how many rows can the inner produce on the worst day?* If you cannot answer, the search is not finished — rewrite it as a `stats by` or seed it from an `inputlookup`. The behavior is documented in [Search Manual — About subsearches](https://docs.splunk.com/Documentation/Splunk/9.4/Search/Aboutsubsearches).
7. **Filter inside `inputlookup` with `where=`, not after.** `| inputlookup assets.csv where=env="prod"` pushes the filter into the lookup read instead of materializing the whole CSV and filtering afterwards. On a 200 000-row asset table this is the difference between a fast pipeline and a memory spike on the search head.

## Anti-patterns to ban

1. **`[ search index=foo … | stats … by user ]` as a filter, with no thought for the 50 000-row cap.** The inner runs, hits 50 000 rows, truncates, and the outer search counts what remains as if it were the whole answer. There is no banner, no warning in the results, no failure. The fix is almost always `stats by user | where …` over a single base search, or seeding from an `inputlookup`.
2. **`join type=outer` "to be safe".** Outer joins on result sets that share an index are almost always rewriteable as `stats by`, and the outer variant doubles the trap surface (you now have to reason about both the inner truncation *and* the missing-key semantics). If you wrote `outer` without a precise reason, you wrote it by reflex — back up and try `stats values(*) by key`.
3. **Nested subsearches.** `[ search … [ search … ] ]` compounds the truncation: the inner subsearch can silently truncate, the outer subsearch silently truncates on the partial answer, and the final result is two layers of "this looked plausible". Flatten to a single base search plus `stats`, or break the work across two searches with an `outputlookup` in between.
4. **`lookup users.csv` when `users.csv` is a 500 MB blob.** Lookups are broadcast to the indexers and re-read per search. A multi-hundred-MB CSV abuses that broadcast and clogs the bundle replication channel. Past roughly 10 MB the right answer is a KV Store lookup or an external lookup — and the conversation is with the admin (see escalation).
5. **`inputlookup` followed by `| where env="prod"` instead of `inputlookup … where=env="prod"`.** Same result on a small table, very different result on a large one: the first variant pulls the whole CSV before filtering, the second pushes the filter down. The cost shows up only at scale, which is exactly when the dashboard starts to hurt.
6. **Faking a `join` with `eval`/`coalesce` because the lookup was not shared into your app context.** When a `lookup` "does not work for your colleague", the lookup definition is private to your app and your colleague's context cannot resolve it. The right move is to share the lookup definition (admin or KO owner), not to inline the mapping as a 60-line `case()`. See Chapter 7 on app context.
7. **`append` two searches when `multisearch` would do.** `append` is centralized on the search head and runs the legs sequentially; `multisearch` parallelizes on the indexers. If both legs are real base searches (start with `index=…`), `multisearch` is the cheaper write.
8. **Trusting a `join` that "worked yesterday" after the data grew.** Subsearch caps bite **at the threshold**, not before. A `join` that returned the right number for six months will start truncating the day the right side crosses 50 000 rows, with no banner. Treat `join` like a debt: review it every time the dataset grows.

## Worked examples

### Replace a `join` with `stats by`

You want users who both logged into `linux_secure` and triggered an app event in `auth_app`, in the last 24 hours.

The reflex version:

```spl
index=os sourcetype=linux_secure earliest=-24h@h latest=now
| stats count as ssh_count by user
| join type=inner user
    [ search index=security sourcetype=auth_app earliest=-24h@h latest=now
      | stats count as app_count by user ]
```

The rewrite:

```spl
index=os OR index=security (sourcetype=linux_secure OR sourcetype=auth_app) earliest=-24h@h latest=now
| eval src=case(sourcetype=="linux_secure","ssh",sourcetype=="auth_app","app")
| stats count(eval(src=="ssh")) as ssh_count
        count(eval(src=="app")) as app_count
        by user
| where ssh_count > 0 AND app_count > 0
```

What to notice: one base search, one pass, no subsearch, no head-side merge. The `stats … by user` is fully distributable. On any cluster you have worked with, the second form returns in a fraction of the time of the first, and it cannot silently truncate at 50 000.

### Identity enrichment with `lookup`

You want failed SSH logins on Linux, enriched with the user's department and manager.

```spl
index=os sourcetype=linux_secure action=failure earliest=-24h@h latest=now
| stats count by user, host
| lookup users.csv user OUTPUT department, manager
| sort - count
```

What to notice: the `lookup` runs *after* `stats`, so it enriches at most one row per user — not once per event. The order matters. If you put `lookup` before `stats`, you pay the lookup cost for every failed login, which is wasteful on a busy host. As a rule, enrich after you reduce; enrich before you reduce only when the lookup result is a `by` key for the downstream `stats`.

### Seed a search from a static set with `inputlookup`

You have a CSV of 200 high-criticality hosts in `assets.csv` and you want their disk usage events for the last hour:

```spl
| inputlookup assets.csv where=criticality="high"
| fields host
| join type=inner host
    [ search index=os sourcetype=df earliest=-1h@h latest=now
      | stats latest(pct_used) as pct_used by host ]
```

The cleaner rewrite, no `join`:

```spl
index=os sourcetype=df earliest=-1h@h latest=now
    [| inputlookup assets.csv where=criticality="high" | fields host | rename host as search ]
| stats latest(pct_used) as pct_used by host
```

What to notice: the `[ inputlookup … ]` used as a *base-search seed* generates the `host=…` clauses that scope the outer search at the indexer, instead of pulling every `index=os sourcetype=df` event and joining on the head. The `rename host as search` is the conventional trick: the seed's column has to be named `search` so it is spliced as raw search terms. This is cheaper than `join` and respects the 50 000-row cap visibly — the input is a known-size CSV, not an open-ended subsearch.

### Union two scopes with `multisearch`

You want a count of authentication events per user across both web access logs and Windows security logs:

```spl
| multisearch
    [ search index=web sourcetype=access_combined action=login earliest=-24h@h latest=now ]
    [ search index=security sourcetype=WinEventLog:Security EventCode=4624 earliest=-24h@h latest=now
      | eval action="login" ]
| stats count by user
```

What to notice: both legs are real base searches with `index=`, both run in parallel at the indexers, and the union flows into a single `stats`. The `append`-based alternative would serialize on the search head and pay the centralized cost twice. Use `multisearch` whenever both legs are scoped enough to live in the base-search stage; once you would need a transforming command inside a leg, `multisearch` no longer fits and `append` or two separate searches become honest choices.

## When to escalate to an admin

- **You need a new lookup table available organisation-wide.** Publishing a CSV or KV Store collection as a usable `lookup` means defining a stanza in `transforms.conf` inside the right app, with the right permissions. That is admin work, not user work. **Ask for:** "publish lookup `<name>.csv` in app `<app>`, refresh cadence `<daily|weekly>`, sharing scope `<app|global>`, owner `<role>`; sample columns: `<list>`".
- **A KV Store lookup is missing, stale, or returning empty rows.** KV Store collections live on the search head, are managed by the admin, and are sometimes out of sync after restarts or upgrades. **Ask for:** "verify KV Store collection `<coll_X>` on the SH tier, last update timestamp, and replication status".
- **A lookup you depend on has grown past roughly 10 MB.** At that size the bundle replication channel starts to feel it, and the right answer is migration to KV Store or an external lookup. Do not paper over it with `| where size_limit` tricks. **Ask for:** "review lookup `<name>.csv` for migration to KV Store; current size `<MB>`; refresh cadence `<…>`; downstream consumers: `<list>`".
- **You repeatedly hit `maxout=50000` or `maxtime=60s` on a legitimate subsearch.** Per-role tuning is possible (`limits.conf [subsearch]`), but the right move is usually a rewrite. **Bring the rewrite proposal first**, then escalate if the rewrite is impossible. **Ask for:** "raise subsearch `maxout` to `<N>` for role `<role>`, justification: the rewrite to `stats by` is not possible because `<reason>`; current truncation observed at `<count>` rows".
- **You need `outputlookup` to write a generated table back.** `outputlookup` is gated by capability and by lookup-definition write access. Without it you cannot publish your own seed tables. **Ask for:** "grant write access on lookup `<name>.csv` to role `<role>`, justification: scheduled search `<name>` needs to refresh it every `<cadence>`".
- **A lookup behaves correctly for you and returns nothing for a colleague.** The lookup definition is private to your app, or its sharing scope is `App` and your colleague's context is in another app. This is an app-context issue, not a search bug. **Ask for:** "share lookup definition `<name>` to scope `<global|app:Y>`; current owner: `<you>`; current scope: `<private|app:X>`".

## Sources

- [Splunk Enterprise 9.4 — Search Reference — join](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Join)
- [Splunk Enterprise 9.4 — Search Reference — lookup](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Lookup)
- [Splunk Enterprise 9.4 — Search Reference — inputlookup](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Inputlookup)
- [Splunk Enterprise 9.4 — Search Reference — multisearch](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/Multisearch)
- [Splunk Enterprise 9.4 — Search Manual — About subsearches](https://docs.splunk.com/Documentation/Splunk/9.4/Search/Aboutsubsearches)
- [Splunk Enterprise 9.4 — Search Manual — Types of commands (streaming vs centralized)](https://docs.splunk.com/Documentation/Splunk/9.4/Search/Typesofcommands)
- [Splunk Enterprise 9.4 — Knowledge Manager Manual — About lookups and field actions](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/Aboutlookupsandfieldactions)
- [Splexicon](https://docs.splunk.com/Splexicon) — canonical definitions for *subsearch*, *lookup table*, *lookup definition*, *KV Store collection*.
