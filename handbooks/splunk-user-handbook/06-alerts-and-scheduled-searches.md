# Chapter 6 — Alerts and scheduled searches

> You already know how to click "Save As → Alert" on a search. What you have not yet internalized is that every alert you create is a small piece of automation that will outlive your attention span, run at 3am, and either wake somebody up or be silently ignored. This chapter is about the handful of choices — cadence, throttling, body content, action wiring, ownership — that decide which of the two happens. By the end of it you should be able to take an alert that floods Slack and stabilize it without touching the SPL, and you should know which knobs you cannot turn yourself.

## Quick refresher

Keep these ideas in working memory; the rest of the chapter assumes them.

- **Scheduled vs real-time alerts.** A **scheduled alert** is a saved search that runs on a cron-like cadence and evaluates a trigger condition on its results. A **real-time alert** runs a continuous (`per-result`) or rolling-window real-time search and triggers on the fly. Real-time is admin territory in practice; default to scheduled.
- **Saved search = scheduled search = alert.** They are the same object under the hood. What turns a saved search into an alert is `is_scheduled=1` plus a non-trivial `alert.track`/`alert_condition`. Knowing this explains why "share my alert" and "share my saved search" hit the same permission UI.
- **Trigger condition.** Evaluated against the **result count** of the search by default. "Number of results > 0" is the standard form. Per-result triggers fire once per row.
- **Throttling and suppress fields.** **Throttling** silences the alert for N minutes after a fire. **Suppress fields** make throttling **per entity** — throttle by `src_ip` and a flood on host A does not silence host B.
- **Alert actions.** Email, webhook, run-a-script, custom alert actions packaged in apps. Each runs on the search head as part of the scheduler.
- **Capabilities that gate this chapter.** `schedule_search` (any scheduled search), `schedule_rtsearch` (real-time), `edit_search_scheduler_priority`. Without them, the UI saves but the scheduler will not run your search.
- **Scheduler quotas.** Per role and global. A search that "saves fine but never fires" is often a scheduler-quota collision, not a SPL bug.

## Major good practices

1. **Default to scheduled, not real-time.** A 5-minute scheduled search that scans the last 5 minutes detects what a real-time search would, at a fraction of the cost, with bounded resource use and without the `schedule_rtsearch` capability. Real-time alerts also bypass scheduler-level quotas — which is exactly why admins gate them. If you genuinely need sub-minute latency, that is a conversation with the admin (see escalation), not a checkbox flip. The official Alerting Manual frames the choice explicitly (see [Alerting Manual — About Splunk alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Aboutalerts)).
2. **Set throttling on every alert that fires more than once, ever.** The default — no throttling — turns "1 noisy condition" into "1 incident per scan interval per entity", and the on-call rotation will mute the channel within a week. Throttling is two settings: a duration (`Suppress alert for N minutes`) and, ideally, suppress fields keyed to the entity (`src_ip`, `host`, `user`). Without suppress fields, throttling silences the *whole* alert during the window, which is usually too coarse.
3. **Write the trigger as a single precise condition.** Push the predicate into SPL — `where count > 10` — and leave the trigger UI on "Number of results > 0". This keeps the logic in one place, in source, where you can review and diff it, instead of split between SPL and a UI knob a maintainer might miss. See [Alerting Manual — Create scheduled alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Definescheduledalerts).
4. **Make the alert body actionable.** Assume the recipient is on-call at 3am, reading on a phone, with no context. Include: the entity key (`src_ip`, `host`, `user` that triggered), the time window evaluated, the result count, and a link back to the dispatched search (`results_link` token) so the on-call can re-open the artifact and pivot. An alert that says only "Search results triggered" gets muted on its second fire.
5. **Schedule off-peak and staggered.** A search set to `*/5 * * * *` runs at `:00`, `:05`, `:10` of every hour — alongside everybody else's `*/5` searches. Use the **schedule window** (Splunk picks a slot within N minutes) or shift the cron explicitly (`2-59/5 * * * *`). The scheduler queue is a shared resource; a power user who staggers wins runtime even when the cluster is hot.
6. **Own your alerts, and make ownership visible.** Put your team prefix in the saved search name (`payments_failed_logins`), set the description field, and review the alert quarterly. Alerts owned by a leaver who never set an owner-handoff are the most common source of flapping alerts a year later — nobody knows what they meant.
7. **Choose alert action destinations the admin has already vetted.** Email through the configured SMTP, webhook to a destination already on the allow-list, run-a-script that ships in an installed app — these work. A webhook to a brand-new endpoint will fail silently if outbound from the search head is firewalled, which is the default in any serious deployment.

## Anti-patterns to ban

1. **Real-time, per-result alerts on a busy sourcetype.** Each matching event spawns a new alert action invocation. On a noisy index that is hundreds of fires per minute, gigabytes of email, and a scheduler queue saturated by alert plumbing. If you genuinely need real-time, the conversation starts with the admin — not with the checkbox.
2. **No throttling, no suppress fields, "we'll see how noisy it is".** You will not see — you will be muted by the on-call. Even `Suppress alert for 1 minute` keyed to the entity is enormously better than nothing. Pick a window proportional to the cadence: a 5-minute scan with a 5-minute suppress is the floor.
3. **`Number of results > 0` as the only filter when the SPL returns thousands of rows.** The alert will fire on the *whole* result set every scan and dump a CSV with 5000 lines into the email body. The body becomes unreadable, mail relays bounce it, and the on-call learns to filter you. Either tighten the SPL (`stats` then `where`) or use a per-result trigger with a suppress field — not both unbounded.
4. **Cron `* * * * *` on a search that scans the last 24 hours.** You are recomputing the same 24-hour window every minute. The scheduler runs it, then the next minute runs it again with one minute of new data and 23 hours 59 minutes of overlap. Either shorten the lookback (`earliest=-5m@m`) or stretch the cadence (`*/5`), but not both wrong.
5. **Splitting "A and B" into two alerts to "see them separately".** You have just created a race condition and a double-page. Conditions that must be true together belong in one SPL pipeline (`stats … by entity | where condA AND condB`), one trigger, one alert. The two-alerts setup also makes correlation impossible after the fact — you have two timestamps for an event that fired once in reality.
6. **Embedding secrets in the alert body or the webhook URL.** API tokens in the body get logged downstream; webhook URLs with a token in the path get persisted in every receiver. Use the configured alert action's credential mechanism (encrypted-at-rest in `passwords.conf`, admin-managed), not inline.
7. **Stale alerts owned by a leaver, kept "in case".** They flap, nobody mutes them because nobody owns them, and they erode trust in the channel. Either re-own (`chown` via the UI), re-validate the SPL, and adopt — or disable, then delete after one quarter of silence.
8. **`Number of results > 0` on a search that returns `_time` only.** The trigger fires because there *are* results, but the body has nothing useful — no field to throttle on, no entity to act on. Always carry the entity key into your final `stats`/`table` so it is available to suppress fields and to the body template.

## Worked examples

### A scheduled alert that stays sane

You want to alert on bursts of failed SSH logins per source IP, every 5 minutes, over the last 5 minutes:

```spl
index=os sourcetype=linux_secure action=failure earliest=-5m@m latest=@m
| stats count by host, src_ip
| where count > 10
```

Wire it up:

- **Trigger:** Number of results > 0.
- **Schedule:** every 5 minutes, with a 60-second schedule window to avoid landing exactly on `:00`.
- **Throttle:** Suppress for 30 minutes, **suppress fields** `src_ip,host`.
- **Action:** email with body containing `$result.src_ip$`, `$result.host$`, `$result.count$`, `$job.earliestTime$..$job.latestTime$`, and `$results_link$`.

What to notice: the predicate (`count > 10`) lives in SPL, where you can diff it. The throttle is keyed to the entity, so a sustained attack from one IP does not silence a fresh attack from another. The window is closed on both sides with `@m` snapping, so a 5-minute scan reads exactly 5 minutes of data — no drift, no overlap. See [Alerting Manual — Throttle alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Throttlealerts).

### A throttle keyed to the right field

A junior teammate built this alert:

```spl
index=security sourcetype=cisco:asa action=blocked earliest=-15m@m latest=@m
| stats count by src_ip, dest_ip, dest_port
| where count > 100
```

Their throttle: "Suppress for 60 minutes" — no suppress fields. First fire was a port scan from `192.0.2.10` against the whole DMZ; throttle kicked in and silenced the alert for an hour, during which two unrelated `src_ip` got nothing.

The fix is one form field: set **suppress fields** to `src_ip`. Now each `src_ip` is throttled independently, and the alert keeps firing for new attackers while the original one is quiet. The lesson generalizes: if your SPL groups `by X`, your suppress field is almost certainly `X` — or a coarser key (`network`) you compute in SPL specifically so the throttle can key on it.

### Real-time, no throttling, vs the corrected scheduled version

The wrong version — please do not deploy this:

```spl
index=os sourcetype=linux_secure action=failure
```

…saved as **Real-time, per-result alert**, action "Send email", no throttling. Result: every failed SSH login on the estate generates an email. A misconfigured cron job hitting an ssh bastion at 60 attempts/minute will send 60 emails per minute until somebody notices. The scheduler load is the smallest of the three problems.

The corrected version:

```spl
index=os sourcetype=linux_secure action=failure earliest=-5m@m latest=@m
| stats count dc(user) as users by host, src_ip
| where count > 20 OR users > 5
```

Scheduled every 5 minutes; throttle 30 minutes by `src_ip,host`; body includes the count, the distinct-user count, the time window, and `$results_link$`. Same detection intent, bounded resource use, actionable output, no need for `schedule_rtsearch`.

### Staggering schedules to avoid scheduler collisions

You have six alerts you want roughly every 5 minutes. Setting them all to `*/5 * * * *` puts six dispatches on the queue at `:00`, `:05`, `:10` — alongside whatever else the org has scheduled on the same beat. Instead, stagger:

| Alert | Cron |
| --- | --- |
| `payments_failed_logins` | `1-59/5 * * * *` |
| `payments_5xx_burst` | `2-59/5 * * * *` |
| `payments_db_slowquery` | `3-59/5 * * * *` |
| `payments_anomalous_egress` | `4-59/5 * * * *` |
| `payments_role_change` | `0-59/5 * * * *` |
| `payments_kvstore_drift` | `6-59/10 * * * *` |

Each still runs at its target cadence; collisions go from "six at once" to "one per minute". On a saturated scheduler this is the difference between firing on time and skipping a slot.

## When to escalate to an admin

- **You need `schedule_search` to save a search as scheduled.** The UI lets you fill the form; the scheduler silently never runs it. The capability is granted per role in `authorize.conf`. Ask for: "grant `schedule_search` to role `analyst`; justification: <one sentence about the use case>; expected number of scheduled searches: N; expected cadence: 5-60 min". Bring the SPL of one example search.
- **You need `schedule_rtsearch` for a real-time alert.** Strongly admin-gated because real-time bypasses scheduler quotas and pins indexers. Be ready to justify why scheduled is not enough — most "real-time" requests are satisfied by a 1-minute scheduled search, and the conversation usually ends there. Ask for: "grant `schedule_rtsearch` to role `Y`, use case `Z`, with explicit ack that a 1-minute scheduled search was considered and rejected because: …".
- **Your alert needs to webhook to a new external destination.** Outbound from search heads is firewalled in any serious deployment; a new destination needs the URL on the allow-list and possibly a per-destination credential. Ask for: "approve outbound webhook to `https://alerts.example.com/ingest`; payload: JSON shaped `{…}`; auth: bearer token in `passwords.conf` stanza `alert_action:payments_webhook`".
- **Your alerts collide with the org-wide scheduler schedule.** Symptoms: alerts saved fine but skipped slots in `Settings → Searches, reports and alerts → Activity`, or `Scheduler queue saturation` warnings in `internal` logs you cannot read. The admin sees the global view. Ask for: "review scheduler queue saturation impacting alerts `payments_*`; my current cron pattern is `*/5`; can I shift to staggered slots or is the whole `*/5` band saturated?".
- **Your alert is sending PII into email/Slack and your team's policy says it shouldn't.** Body templating happens in the alert action, but enterprise-wide redaction (e.g. masking PAN, IBAN, email) lives in the alert action's config, packaged in an app the admin maintains. Ask for: "approve a redaction pattern in the email action for sourcetype `…`; pattern: `…`; reason: data-classification policy".
- **You inherit a flapping alert owned by a leaver.** You can re-own via the UI if you have the right perms, but the right move is to involve the admin: ownership transfer + a sanity check on the SPL + a chance to disable it cleanly. Ask for: "transfer ownership of `<saved_search_name>` from `<leaver>` to me; I will validate and adopt or disable within two weeks".

## Sources

- [Splunk Enterprise 9.4 — Alerting Manual — About Splunk alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Aboutalerts)
- [Splunk Enterprise 9.4 — Alerting Manual — Create scheduled alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Definescheduledalerts)
- [Splunk Enterprise 9.4 — Alerting Manual — Throttle alerts](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Throttlealerts)
- [Splunk Enterprise 9.4 — Alerting Manual — About alert actions](https://docs.splunk.com/Documentation/Splunk/9.4/Alert/Aboutactions)
- [Splunk Enterprise 9.4 — Admin Manual — About users and roles](https://docs.splunk.com/Documentation/Splunk/9.4/Admin/Aboutusersandroles)
- [Splexicon](https://docs.splunk.com/Splexicon) — canonical definitions for *alert*, *scheduled search*, *throttling*, *suppress fields*, *alert action*, *capability*.
