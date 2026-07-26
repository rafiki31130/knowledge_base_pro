# Splunk Search Performance Handbook

> 🇫🇷 **Version française disponible** : [`../README.md`](../README.md)

Time anatomy of a Splunk search in a distributed, multisite, clustered environment — **from the click on *Search* to the display of results** — and the **optimization levers** you can act on at each phase.

## What this handbook is and isn't

**It is** a map of where a distributed search spends its time: the phases in the order the time is spent in them (parse and optimization on the search head, admission, distribution, map on the indexers, reduce on the search head, rendering), the exact instrument that exposes each phase, and the precise lever that acts on it. Each chapter states its levers in a **self-contained** way and only refers you to another document when a mechanism is *fully* covered there.

**It is not** a cluster deployment tutorial, nor the [Splunk User Handbook](../../splunk-user-handbook/README.md) (power-user SPL usage), nor a WLM governance guide ([gouvernance-utilisateurs-splunk](../../gouvernance-utilisateurs-splunk/EN/README.md)), nor a knowledge bundle guide ([splunk-shc-knowledge-bundle](../../splunk-shc-knowledge-bundle/EN/README.md)) — to which it refers when the topic is covered there in its own right.

## Persona

**Splunk architect / admin** running an on-prem distributed 9.x platform: search head cluster (SHC), one or more multisite indexer clusters, deployer/deployment server, possibly ITSI. You can read a `props.conf`, you know clustering, and you size indexers. We do not re-explain what an index, a bucket, a forwarder, or a search head is, nor what a `tsidx` or a bloom filter is *as a structure* — we describe their **effect on time** and the lever that acts on it.

## Scope

- **Splunk Enterprise 9.x on-prem, SPL1.** 9.4 terminology (`manager`/`peer`, `allowlist`/`denylist`). Multisite IDXC + SHC.
- **Out of scope**: Splunk Cloud, SmartStore (pointed to, not detailed), SPL2, Observability; ITSI/ES except the *federated search* case cited in chapter 04; 10.x versions.
- **Grounded in the documentation** (`docs.splunk.com/9.4` + Splexicon + `help.splunk.com` for Workload Management): every claim about time is traceable to a source. The handbook **teaches you to measure** (what to read in the Job Inspector and in the logs); it does not report measurements of its own.

## How to use this handbook

Each chapter reads on its own; the proposed order follows the time pipeline. **When facing a slow search**, start from chapter [99](99-cheatsheet-decomposer-un-temps.md): its "where did the time go?" tree takes you, from the dominant marker in the Job Inspector, to the chapter of the phase in question and to its lever.

## Table of contents

| # | Chapter | Phase / object |
| --- | --- | --- |
| 00 | [Time model and measurement instruments](00-modele-temporel-et-mesure.md) | Pivot: the phases + the map of instruments (Job Inspector, `search.log`, `metrics.log`, `remote_searches.log`) |
| 01 | [SPL submission and parsing](01-soumission-et-parsing-spl.md) | SH-side time before dispatch: parse, KO expansion, optimizer, streaming/transforming |
| 02 | [Admission and scheduling](02-admission-et-ordonnancement.md) | Wait time: scheduler, WLM, quotas, dispatch dir |
| 03 | [Distribution](03-distribution.md) | Bundle readiness, fan-out: bundle size, replication mode, timeouts, peer hygiene |
| 04 | [Map on the indexers](04-map-sur-indexeurs.md) | **The heart of the time**: buckets, multisite search affinity, tsidx/bloom, rawdata, search-time extraction, fixup |
| 05 | [Reduce on the search head and rendering](05-reduce-et-restitution.md) | Centralized commands, preview, job artifact, TTL, pagination |
| 06 | [Acceleration as a lever](06-acceleration-comme-levier.md) | `tstats`/DMA/report accel/summary: time cost/benefit and sizing |
| 07 | [UI rendering](07-restitution-ui.md) | Time impact of dashboards: base searches, post-process, refresh cadence |
| 99 | [Cheatsheet — decompose a time](99-cheatsheet-decomposer-un-temps.md) | Decision tree + consolidated table symptom → phase → chapter → lever |

## Conventions

- **Anonymization**: every identifier is a generic placeholder — hosts `sh01`/`idx01`/`cm01`/`captain01`, sites `site1`/`site2`, indexes `main`/`os`/`network`/`security`, sourcetypes `access_combined`/`linux_secure`, users `alice`/`bob`. No element of a real infrastructure.
- **Notation**: SPL in a ` ```spl ` block, configuration in ` ```ini ` with the `[…]` stanza and the named `.conf` layer, log excerpts in anonymized ` ```text `, Job Inspector fields in `inline code` (`command.search.rawdata`, `dispatch.stream.remote.<peer_guid>`, `scanCount`). Diagrams in Mermaid.
- **Citation**: a non-trivial factual claim carries an inline link to a canonical source; a `## Sources` section at the end of each chapter, with URLs pinned to 9.4. Splexicon is cited for definitions, never as proof of a behavior.

## Global sources

- [Search Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Search/) · [Search Reference](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/) — Job Inspector, jobs, SPL commands, optimization.
- [Distributed Search Manual](https://docs.splunk.com/Documentation/Splunk/9.4/DistSearch/) — distributed search, knowledge bundle, `distsearch.conf`.
- [Managing Indexers and Clusters of Indexers](https://docs.splunk.com/Documentation/Splunk/9.4/Indexer/) — multisite, search affinity, search factor, buckets, rebalance.
- [Knowledge Manager Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/) — data models, acceleration, summary indexing.
- [Capacity Planning Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Capacity/) — how search works, sizing.
- [Admin Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Admin/) — `limits.conf`, `savedsearches.conf`, `distsearch.conf`, roles/quotas.
- [Troubleshooting Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Troubleshooting/) — `metrics.log`, internal logging.
- [Dashboards and Visualizations](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/) — base searches, post-process, tokens.
- [Workload Management](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/9.4/) — pools, admission rules (new `help.splunk.com` portal).
- [Splexicon](https://docs.splunk.com/Splexicon) — canonical definitions.

**Neighboring KB deliverables** (D3 cross-references): [splunk-shc-knowledge-bundle](../../splunk-shc-knowledge-bundle/EN/README.md), [splunk-user-handbook](../../splunk-user-handbook/README.md), [gouvernance-utilisateurs-splunk](../../gouvernance-utilisateurs-splunk/EN/README.md), and the concepts [multisite buckets](../../../concepts/splunk-buckets-multisite-lifecycle.md), [multisite rebalance](../../../concepts/splunk-rebalance-multisite.md), [parsing phases](../../../concepts/splunk-parsing-phase-uf-vs-hf.md), [ITSI federated search](../../../concepts/splunk-itsi-federated-search.md).

## Versioning note

This handbook is written against **Splunk Enterprise 9.4** on-prem, SPL1. Behaviors are versioned (`in 9.x, …`); any minor-version divergence is flagged inline. As the Splunk documentation gradually migrates to `help.splunk.com`, the `docs.splunk.com/9.4` URLs remain the canonical form retained here (redirected where applicable), except for Workload Management, whose 9.4 page lives on `help.splunk.com`.
