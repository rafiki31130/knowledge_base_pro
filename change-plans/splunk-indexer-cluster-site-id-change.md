# Splunk indexer cluster — site id change

Generic change plan template for changing the `site` attribute of one or
more members of a Splunk indexer cluster. Treat this fiche as a
**template**: every value in angle brackets must be confirmed against the
target deployment, and the variant of the change must be matched to the
correct **official Splunk procedure** before execution.

> **Important.** There is no single official procedure for "changing a site
> id". Splunk documents distinct procedures for distinct variants. The
> wrong assumption — that you only need to edit `[general] site` in
> `server.conf` and restart — is **explicitly contradicted** by Splunk for
> the peer-move case (see §6, reservation 1). Identify the variant first,
> then follow the matching official procedure.

## 1. Generic description of the change

In a Splunk indexer cluster, each member (cluster manager, peer, search
head) declares which **site** it belongs to via the `site` attribute in
`server.conf` (`[general] site = <siteX>`). The cluster manager uses these
site labels together with `site_replication_factor` and
`site_search_factor` to decide where bucket copies live and which copies
are searchable.

A "site id change" covers three distinct variants, which have **different**
official procedures:

- **Variant A — Move a peer to a new site.** A peer that used to belong to
  `<site_a>` becomes part of `<site_b>` (e.g. physical relocation, mistake
  during initial deployment caught after data has accumulated). Official
  procedure: *Move a peer to a new site* — see §6 reservation 1.
- **Variant B — Migrate single-site to multisite.** The cluster, currently
  `multisite = false`, is reconfigured as a multisite cluster with
  `available_sites = <site1>,<site2>,…`. Official procedure: *Migrate an
  indexer cluster from single-site to multisite* — see §6 reservation 2.
- **Variant C — Rename a site label.** The cluster keeps its topology but
  the label `<old_site>` becomes `<new_site>` across the manager and the
  peers that carry it. Splunk does **not** publish a dedicated procedure
  for this variant; it must be built from the multisite configuration
  pages (see §6 reservation 3) and treated with extra care.

All three variants touch `server.conf` on the cluster manager
(`[clustering] available_sites`, `site_replication_factor`,
`site_search_factor`, and possibly `multisite`), and on every affected
indexer (`[general] site`) and search head (`[general] site` when
site-based search affinity is in use). They also affect forwarder
configurations using `indexerDiscovery` or `site_failover` when present.

The goal of the change is to make the cluster's site topology reflect a
new operational reality without data loss, and with bucket counts
converging back to the configured replication and search factors after the
change.

## 2. Risks and service interruption

### Risks

- **Stranded bucket copies** (Variant A specifically). If a peer is
  reassigned by editing `server.conf` instead of following the official
  offline-and-reprovision procedure, its existing local bucket copies stay
  on the peer but are accounted for under the new site. The cluster
  manager does **not** automatically rebalance them. Replication and
  search factors become inconsistent in ways that are hard to recover
  from.
- **Bucket fixup storm**. Any site change triggers the manager to
  re-evaluate per-site bucket placement. The cluster will start a fixup
  cycle that can move and replicate large volumes of data. Network and
  disk I/O on indexers will spike.
- **Replication / Search factor violations**. Until fixup completes, the
  cluster reports `Replication Factor not met` and `Search Factor not
  met`. Some buckets may briefly be searchable from fewer sites than
  intended.
- **Search affinity disruption**. If `site_search_affinity = true`,
  queries may suddenly hit a different set of indexers after the change,
  with cold-cache search latency.
- **Misalignment between manager and peers**. `available_sites` on the
  manager must list every site label declared by peers; otherwise affected
  peers will be rejected from the cluster.
- **Forwarder routing breakage**. Forwarders using site-aware indexer
  discovery may stop routing correctly until they pick up the new manager
  view.
- **Inconsistent `server.conf`**. A typo in `site = …` will prevent the
  peer from rejoining; rollback may be needed before fixup even starts.

### Service interruption

- **Ingest**: usually no full outage. Forwarders with autoLB keep sending
  data; expect transient backoffs while affected peers restart.
- **Search**: short interruption when the manager re-evaluates the
  generation. Dashboards may show partial results around each peer
  restart.
- **Cluster availability**: degraded (yellow) state for the entire fixup
  duration; not an outage, but cluster-health alerting will fire.
- **Estimated duration**: peer restart is seconds; fixup is a function of
  total bucket count, RF/SF, and inter-peer bandwidth — minutes for a
  small cluster, hours for a large one. **Variant A's official procedure
  requires wiping the peer's index database** (see §6 reservation 1),
  which means the peer rebuilds its bucket copies from other peers — plan
  the window against the full re-replication, not against a simple
  restart.

## 3. Change plan

The exact sequence depends on the variant. Pick the matching official
procedure (linked in §6) and follow it. The skeleton below highlights what
is common.

### 3.1 Pre-change (all variants)

1. **Snapshot the current topology** for the rollback plan:
   ```bash
   splunk show cluster-status -auth <admin>:<password>
   splunk list cluster-config -auth <admin>:<password>
   splunk btool server list clustering --debug
   splunk btool server list general --debug
   ```
   Persist this output outside the cluster nodes.
2. **Capture bucket health baseline**: number of buckets, RF/SF status,
   list of buckets currently in fixup.
3. **Confirm cluster manager is healthy** (no recurring fixup errors in
   `splunkd.log`).
4. **Pause ingestion-sensitive jobs** for the maintenance window.
5. **Enable maintenance mode** on the cluster manager to suppress fixup
   while you reconfigure:
   ```bash
   splunk enable maintenance-mode -auth <admin>:<password>
   splunk show maintenance-mode -auth <admin>:<password>   # confirm
   ```

### 3.2 Variant A — Move a peer to a new site

Follow the official procedure (§6 reservation 1) **literally**. Summary:

1. **Take the peer offline** with `splunk offline` so the manager
   reassigns its bucket copies to other peers in its current site **before**
   the peer leaves.
2. Wait for the manager to confirm the reassignment is complete.
3. (Physical relocation if applicable.)
4. **Delete the entire Splunk Enterprise installation on the peer**,
   including its index database with all bucket copies.
5. **Reinstall Splunk Enterprise**, re-enable clustering, set
   `[general] site = <new_site>`.
6. Confirm the peer rejoins the cluster:
   ```bash
   splunk show cluster-status -auth <admin>:<password>
   ```
   The peer should appear with its new `Site` value, RF/SF re-converging
   as the manager replicates bucket copies back to it.

Repeat per affected peer, sequentially, never in parallel.

### 3.3 Variant B — Migrate single-site to multisite

Follow the official procedure (§6 reservation 2). Summary, in order:

1. **Configure the cluster manager for multisite** and restart it. Example
   shape (real values per the deployment):
   ```bash
   splunk edit cluster-config \
     -mode manager \
     -multisite true \
     -available_sites <site1>,<site2> \
     -site <site1> \
     -site_replication_factor origin:<r>,total:<R> \
     -site_search_factor      origin:<s>,total:<S>
   splunk restart
   ```
2. **Decide whether existing buckets must adhere to the new multisite RF/SF**;
   the manager has a configuration toggle for this — confirm against the
   official page.
3. **Enable maintenance mode** on the manager to avoid unnecessary fixup
   during peer reconfiguration.
4. **Configure each existing peer** for multisite, specifying its manager
   and its `site`. Restart per peer.
5. **Add new peers** if the new topology requires them.
6. **Configure each search head** for multisite, specifying its manager
   and its `site`.

### 3.4 Variant C — Rename a site label

Splunk does not publish a dedicated procedure for renaming a site label in
place. The two sub-sections below give a **lab-validated** result (tested on a
multisite cluster of 1 manager + 2 peers, one peer per site, 1 search head,
`site_replication_factor origin:1,total:2`, search head on `site0`): the **naïve**
in-place rename fails on two counts, and a **working method** exists by combining
`splunk offline` with `site_mappings`.

#### 3.4.1 The naïve sequence FAILS — do not use it

The "obvious" sequence — add `<new_site>` to `available_sites`, then under
maintenance mode edit `[general] site = <new_site>` on each peer and restart it
with a plain restart, then drop `<old_site>` — **fails on two independent counts**,
both observed empirically:

1. **Search outage during peer restarts.** A plain `splunkd` restart drops the
   peer abruptly; the primary (searchable) copies it held are not handed off
   first. Searches for that peer's data go incomplete until the peer returns —
   the surviving cross-site copy is **not** promoted in time. (Under maintenance
   mode the manager does not reassign primaries at all; even outside maintenance
   mode the handoff is not graceful with a plain restart.)
2. **Persistent replication/search-factor violation (stranded buckets).** A
   bucket's **origin site is fixed at creation and is not re-homable** by any
   direct command. Once `<old_site>` is removed from `available_sites`, a bucket
   whose origin is `<old_site>` requires an origin copy on a site that no longer
   has a peer → the constraint is unsatisfiable. Crucially, the manager then
   reports **`No fixup tasks in progress`** *while* RF/SF stay **not met**: it
   does not even attempt to repair. Waiting does not help — this is structural,
   not a delay. Interposing a "wait for RF/SF met after each step" gate does not
   rescue it; the gate simply times out after the first peer.

Net: the naïve in-place rename leaves the cluster **searchable but
under-replicated**, with no automatic recovery.

#### 3.4.2 Working method — `splunk offline` + `site_mappings`

The fix addresses each failure with the matching official mechanism:

- **Continuity** ← `splunk offline` (graceful). It instructs the manager to
  **reassign the peer's primary/searchable copies to surviving peers before the
  peer stops**, so searchability is preserved across the down window. Use plain
  `splunk offline` (**not** `--enforce-counts`, which would try to fully
  re-establish RF/SF — impossible with one peer per site — and block).
- **Re-homing the stranded copies** ← `site_mappings`. This is Splunk's official
  **site-decommissioning** mechanism: mapping `<old_site>:<new_site>` tells the
  manager that the origin bucket copies bound to the (now removed) `<old_site>`
  belong to `<new_site>`, which makes the conformance accounting recompute and
  the copies re-home onto the new site's peer. This is the signal the manager
  lacks in the naïve sequence.

Validated sequence (per peer carrying `<old_site>` → `<new_site>`):

1. Pre-flight: confirm the cluster is healthy and **all buckets are warm and
   fully replicated** (`Replication/Search factor met`, `No fixup`). Hot,
   not-yet-replicated buckets are the real cause of long outages — let them roll
   and replicate first.
2. Add the new site label(s) to the manager's `available_sites` (old and new
   coexist), restart the manager. (The manager is not in the data path; its
   restart does not interrupt search.)
3. For each peer: `splunk offline` (plain) → wait for the manager to confirm the
   primary reassignment → edit `[general] site = <new_site>` → `splunk start`.
   Searchability is preserved throughout (graceful handoff).
4. On the manager, **in the same restart**: set
   `[clustering] site_mappings = <old_site>:<new_site>[,<old_site2>:<new_site2>]`
   **and** remove the old label(s) from `available_sites`, then restart the
   manager. RF/SF re-converges (origin copies re-homed to the new site) —
   observed convergence from seconds to ~1 minute.
5. **Cleanup**: once RF/SF are met and stable, remove the now-inert
   `site_mappings` stanza at the next maintenance window (see reservation §6.16).

This sequence achieved **zero search interruption and full RF/SF reconvergence**
in lab. It is still **not** an officially documented "rename a site" procedure —
it is a deliberate, validated composition of two official mechanisms; treat the
reserves in §6 (especially scale revalidation) as binding before production use.

### 3.5 Exit maintenance and fixup (all variants)

1. Disable maintenance mode:
   ```bash
   splunk disable maintenance-mode -auth <admin>:<password>
   ```
2. Watch fixup start and progress:
   ```bash
   splunk show cluster-status -auth <admin>:<password>
   splunk list excess-buckets -auth <admin>:<password>
   ```
3. Let the cluster converge before declaring the change complete.

## 4. Rollback plan

### 4.1 Decision criteria

Trigger rollback if:

- A reconfigured peer fails to rejoin the cluster and the cause is not a
  trivial typo correctable in minutes.
- The cluster reports a persistent `Replication Factor not met` that is
  not making forward progress over a sustained window.
- Search results show systematic gaps mapped to the site change (not just
  transient cold-cache latency).
- The cluster manager itself becomes unstable after its own restart.

### 4.2 Rollback steps

The reversibility cost depends on the variant.

- **Variant A — Move a peer**. There is no symmetric "un-offline + un-wipe"
  rollback once step 4 of §3.2 has run on the peer. Rollback before step 4
  means re-enabling the peer in its original site (its bucket copies are
  still local). Rollback after step 4 means reprovisioning the peer with
  `<old_site>` — the data has been redistributed across the original site
  and will replicate back. Plan the window accordingly.
- **Variant B — Migrate to multisite**. Rolling back to single-site
  requires restoring `multisite = false` and the original `[clustering]`
  block on the manager (restart), and restoring `[general] site` on every
  peer and search head (restart each). The cluster then re-converges to
  the single-site bucket layout, which is another fixup cycle.
- **Variant C — Rename**. Symmetric: re-add `<old_site>` to
  `available_sites`, revert each peer's `[general] site`, then drop
  `<new_site>` if no member references it.

Common reversal steps:

1. Re-enable maintenance mode on the cluster manager.
2. Restore the previous `server.conf` files from the snapshot taken in
   §3.1, restart the corresponding `splunkd` instances.
3. Disable maintenance mode and let the cluster converge.
4. Compare `cluster-status` and bucket counts against the pre-change
   snapshot.

### 4.3 Point of no return

- Variant A: deleting the index database of a peer (step 4 of §3.2) is
  the operational point of no return for that peer's local data — the
  cluster still owns the data through replicated copies on other peers,
  but the local copy is gone.
- Variant B: enabling `multisite = true` on the manager is the conceptual
  point of no return; from that moment, new buckets are created with the
  multisite RF/SF policy. Reverting is still possible but triggers
  another fixup cycle.
- Variant C: removing `<old_site>` from `available_sites` is the point
  where any member still labelled `<old_site>` is rejected.

## 5. Validation plan

The validation plan must check the **state after fixup has settled**.

### 5.1 Cluster health

1. `splunk show cluster-status` reports `Cluster status: Ready` and every
   peer shows the expected `Site` value.
2. `splunk list cluster-config` shows the expected `available_sites`, RF
   and SF values.
3. No bucket remains in `splunk list excess-buckets` longer than the
   normal background level seen pre-change.

### 5.2 Replication and search factors

1. `Replication Factor met` and `Search Factor met` for **all** indexes.
2. Bucket counts per site match the expected distribution given the new
   RF/SF.
3. A sample search known to target data from the reassigned indexer(s)
   returns complete results.

### 5.3 Ingest path

1. A test event sent through a forwarder reaches the cluster and lands on
   a peer whose `site` matches the routing expectation.
2. Forwarders using indexer discovery report a healthy list of peers.

### 5.4 Search path

1. Saved searches and dashboards complete in a comparable time to the
   pre-change baseline.
2. If search affinity was changed: confirm via `_internal` that searches
   dispatched after the change hit the expected peers.

### 5.5 Sign-off criteria

The change is successful when, simultaneously:

- All peers are `Up` with their new site labels.
- RF and SF are met for all indexes.
- No persistent fixup activity remains.
- A representative sample of searches returns complete results.

## 6. Open reservations

These items **must** be clarified against the specific target deployment
before this plan can be executed. They exist because this fiche is
intentionally generic.

1. **Variant A — official procedure**. Confirm the exact steps for the
   deployed Splunk version against the official page:
   [Move a peer to a new site (Splunk Docs)](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/9.0/manage-a-multisite-indexer-cluster/move-a-peer-to-a-new-site).
   The official procedure requires `splunk offline` then **deleting the
   entire Splunk installation including the index database** before
   reinstalling with the new `site` — a plain `server.conf` edit + restart
   is explicitly insufficient.
2. **Variant B — official procedure**. Confirm against the official page:
   [Migrate an indexer cluster from single-site to multisite (Splunk Docs)](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.2/deploy-and-configure-a-multisite-indexer-cluster/migrate-an-indexer-cluster-from-single-site-to-multisite).
   Verify the toggle that forces existing buckets to adhere to the new
   multisite RF/SF.
3. **Variant C — no official procedure, but a lab-validated method exists**.
   Splunk publishes no dedicated "rename a site" procedure. The **naïve**
   in-place rename (§3.4.1) is **proven to fail** (search outage + permanently
   stranded buckets / RF-SF not met, since a bucket's origin site is not
   re-homable). The **working method** (§3.4.2) composes `splunk offline`
   (continuity) with `site_mappings` (the official site-decommission re-homing
   mechanism); it achieved zero outage and full RF/SF reconvergence in a lab on
   a 1-CM + 2-peer (one per site) + 1-SH cluster, `origin:1,total:2`. It remains
   a composition, not a blessed procedure — revalidate at production scale and
   honour reservations §6.16–§6.18 before applying to production.
4. **Splunk version**. Cluster behaviour, terminology
   (`master`/`manager`) and CLI shape changed across versions. Match the
   procedure page to the version actually deployed.
5. **Variant identification**. Before anything else, confirm which of
   A / B / C is being executed. The risks, the rollback cost and the
   point of no return are very different.
6. **Current `available_sites`, RF and SF values**. The change must keep
   RF and SF achievable at every point in time during the rolling
   restart; with too few peers per site, taking one offline can violate
   `site_replication_factor`.
7. **Cluster size and bucket count**. Drives the expected fixup duration
   and the maintenance window length. Variant A's wipe-and-rejoin can
   move significant data across the cluster.
8. **Inter-site bandwidth and latency**. Site-aware replication moves
   data across links you may not have characterized. Confirm the link
   budget supports the fixup volume.
9. **Search head topology**. Standalone SH, SH cluster, SHs participating
   in `site_search_affinity` — each case affects search-head
   reconfiguration differently, and SHC captaincy must be preserved.
10. **Forwarder configuration**. Whether forwarders use indexer discovery,
    static `[tcpout]` server lists, or `site_failover` changes how the
    change is perceived by data sources.
11. **Authentication context**. Every CLI command above uses
    `-auth <admin>:<password>` for clarity. The real procedure should use
    the authentication mechanism in force (SSO, REST token, mTLS) and
    must not leave credentials in logs or shell history.
12. **Monitoring and alerting**. The fixup cycle will fire alerts on
    cluster health, RF/SF, and per-host I/O. Pre-arrange suppression
    windows.
13. **Backups and snapshots**. Confirm whether per-peer filesystem
    snapshots can be taken before the change as an additional safety net.
14. **Operational window and approvals**. Change-advisory-board approval,
    stakeholder communication, downstream-consumer coordination belong to
    the change governance process, not this technical plan.
15. **Naming convention for site labels**. Site labels are `site<N>`
    (`site1`–`site63`); `site0` is **reserved for search heads** (it disables
    search affinity so the SH searches all sites) and must **never** appear in
    `available_sites`. Non-numeric labels (e.g. `site_a`) are rejected. A
    manager must sit on a **real** site (not `site0`).
16. **Remove `site_mappings` after convergence** (working method, §3.4.2). The
    `site_mappings` stanza stays in the manager config after the rename; it is
    inert once RF/SF are met but is a source of confusion and should be removed
    at the next maintenance window. Verify RF/SF stay met after removal.
17. **Transient under-replication window**. During each peer's `offline`→
    rename→`start`, the cluster is briefly below its replication factor for that
    peer's buckets (fault tolerance is momentarily reduced even though search
    stays complete via the surviving copy). Size the window against the per-peer
    restart time; avoid overlapping with other risk.
18. **Scale and load revalidation**. The working method was validated on a
    **small** dataset, **one peer per site**, and **without concurrent search
    load**. Re-validate on production-representative bucket counts, peers-per-site
    and query load before generalised rollout. With ≥2 peers per site, the
    official Variant A (move-a-peer, §3.2) becomes cleanly applicable and may be
    preferable.

## References

- Splunk Docs — Move a peer to a new site:
  <https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/9.0/manage-a-multisite-indexer-cluster/move-a-peer-to-a-new-site>
- Splunk Docs — Migrate an indexer cluster from single-site to multisite:
  <https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.2/deploy-and-configure-a-multisite-indexer-cluster/migrate-an-indexer-cluster-from-single-site-to-multisite>
- Splunk Docs — Multisite indexer cluster architecture:
  <https://docs.splunk.com/Documentation/Splunk/9.4.1/Indexer/Multisitearchitecture>
- Splunk Docs — Decommission a site (source of the `site_mappings` mechanism used
  by the Variant C working method, §3.4.2):
  <https://docs.splunk.com/Documentation/Splunk/9.4.1/Indexer/Decommissionasite>
- Splunk Docs — Use maintenance mode:
  <https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Usemaintenancemode>
- See also: [ITIL change governance](../methodologies/itil-gouvernance-changement.md)
  for the surrounding change-management process.
