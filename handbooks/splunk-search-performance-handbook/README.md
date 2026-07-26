# Splunk Search Performance Handbook

Anatomie temporelle d'une recherche Splunk en environnement distribué, multisite et en clusters — **du clic sur *Rechercher* jusqu'à l'affichage des résultats** — et les **leviers d'optimisation** activables à chaque phase.

## What this handbook is and isn't

**C'est** une carte du temps d'une recherche distribuée : les phases dans l'ordre où le temps s'y dépense (parse et optimisation sur le search head, admission, distribution, map sur les indexeurs, reduce sur le search head, restitution), l'instrument exact qui expose chaque phase, et le levier précis qui agit dessus. Chaque chapitre énonce ses leviers de façon **autoportante** et ne renvoie à un autre document que lorsqu'un mécanisme y est *pleinement* traité.

**Ce n'est pas** un tutoriel de pose de cluster, ni le [Splunk User Handbook](../splunk-user-handbook/README.md) (usage SPL power-user), ni un guide de gouvernance WLM ([gouvernance-utilisateurs-splunk](../gouvernance-utilisateurs-splunk/README.md)), ni un guide du knowledge bundle ([splunk-shc-knowledge-bundle](../splunk-shc-knowledge-bundle/README.md)) — vers lesquels il renvoie quand le sujet y est couvert en propre.

## Persona

**Architecte / admin Splunk** exploitant une plateforme distribuée on-prem 9.x : search head cluster (SHC), un ou plusieurs indexer clusters multisite, deployer/deployment server, éventuellement ITSI. Le lecteur sait lire un `props.conf`, connaît le clustering et dimensionne les indexeurs. On ne lui réexplique ni ce qu'est un index, un bucket, un forwarder, un search head, ni ce qu'est un `tsidx` ou un bloom filter *en tant que structure* — on décrit leur **effet temporel** et le levier qui agit dessus.

## Scope

- **Splunk Enterprise 9.x on-prem, SPL1.** Terminologie 9.4 (`manager`/`peer`, `allowlist`/`denylist`). Multisite IDXC + SHC.
- **Hors scope** : Splunk Cloud, SmartStore (pointé, non détaillé), SPL2, Observability ; ITSI/ES sauf le cas *federated search* cité au chapitre 04 ; versions 10.x.
- **Fondé sur la documentation** (`docs.splunk.com/9.4` + Splexicon + `help.splunk.com` pour le Workload Management) : chaque affirmation temporelle est traçable à une source. Le handbook **enseigne à mesurer** (quoi lire au Job Inspector et dans les logs) ; il ne rapporte pas de mesures propres.

## How to use this handbook

Chaque chapitre est lisible seul ; l'ordre proposé suit le pipeline temporel. **Face à une recherche lente**, partez du chapitre [99](99-cheatsheet-decomposer-un-temps.md) : son arbre « où est passé le temps ? » vous mène, depuis le marqueur dominant du Job Inspector, au chapitre de la phase concernée et à son levier.

## Table of contents

| # | Chapitre | Phase / objet |
| --- | --- | --- |
| 00 | [Modèle temporel et instruments de mesure](00-modele-temporel-et-mesure.md) | Pivot : les phases + la carte des instruments (Job Inspector, `search.log`, `metrics.log`, `remote_searches.log`) |
| 01 | [Soumission et parsing SPL](01-soumission-et-parsing-spl.md) | Temps SH-side avant dispatch : parse, expansion KO, optimiseur, streaming/transforming |
| 02 | [Admission et ordonnancement](02-admission-et-ordonnancement.md) | Temps d'attente : scheduler, WLM, quotas, dispatch dir |
| 03 | [Distribution](03-distribution.md) | Bundle readiness, fan-out : taille du bundle, mode de réplication, timeouts, hygiène des peers |
| 04 | [Map sur les indexeurs](04-map-sur-indexeurs.md) | **Cœur du temps** : buckets, search affinity multisite, tsidx/bloom, rawdata, extraction search-time, fixup |
| 05 | [Reduce sur le search head et restitution](05-reduce-et-restitution.md) | Commandes centralisées, preview, job artifact, TTL, pagination |
| 06 | [L'accélération comme levier](06-acceleration-comme-levier.md) | `tstats`/DMA/report accel/summary : coût/bénéfice temporel et dimensionnement |
| 07 | [Restitution UI](07-restitution-ui.md) | Impact temporel des dashboards : base searches, post-process, cadence de refresh |
| 99 | [Cheatsheet — décomposer un temps](99-cheatsheet-decomposer-un-temps.md) | Arbre de décision + table consolidée symptôme → phase → chapitre → levier |

## Conventions

- **Anonymisation** : tous les identifiants sont des placeholders génériques — hôtes `sh01`/`idx01`/`cm01`/`captain01`, sites `site1`/`site2`, index `main`/`os`/`network`/`security`, sourcetypes `access_combined`/`linux_secure`, utilisateurs `alice`/`bob`. Aucun élément d'une infrastructure réelle.
- **Notation** : SPL en bloc ` ```spl `, configuration en ` ```ini ` avec la stanza `[…]` et la couche `.conf` nommée, extraits de logs en ` ```text ` anonymisés, champs du Job Inspector en `code inline` (`command.search.rawdata`, `dispatch.stream.remote.<peer_guid>`, `scanCount`). Schémas en Mermaid.
- **Citation** : une affirmation factuelle non triviale porte un lien inline vers une source canonique ; section `## Sources` en fin de chapitre, URLs figées en 9.4. Splexicon est cité pour les définitions, jamais comme preuve d'un comportement.

## Global sources

- [Search Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Search/) · [Search Reference](https://docs.splunk.com/Documentation/Splunk/9.4/SearchReference/) — Job Inspector, jobs, commandes SPL, optimisation.
- [Distributed Search Manual](https://docs.splunk.com/Documentation/Splunk/9.4/DistSearch/) — recherche distribuée, knowledge bundle, `distsearch.conf`.
- [Managing Indexers and Clusters of Indexers](https://docs.splunk.com/Documentation/Splunk/9.4/Indexer/) — multisite, search affinity, search factor, buckets, rebalance.
- [Knowledge Manager Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Knowledge/) — data models, accélération, summary indexing.
- [Capacity Planning Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Capacity/) — fonctionnement de la recherche, dimensionnement.
- [Admin Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Admin/) — `limits.conf`, `savedsearches.conf`, `distsearch.conf`, rôles/quotas.
- [Troubleshooting Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Troubleshooting/) — `metrics.log`, journalisation interne.
- [Dashboards and Visualizations](https://docs.splunk.com/Documentation/Splunk/9.4/DashStudio/) — base searches, post-process, tokens.
- [Workload Management](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/9.4/) — pools, admission rules (nouveau portail `help.splunk.com`).
- [Splexicon](https://docs.splunk.com/Splexicon) — définitions canoniques.

**Livrables KB voisins** (renvois D3) : [splunk-shc-knowledge-bundle](../splunk-shc-knowledge-bundle/README.md), [splunk-user-handbook](../splunk-user-handbook/README.md), [gouvernance-utilisateurs-splunk](../gouvernance-utilisateurs-splunk/README.md), et les concepts [buckets multisite](../../concepts/splunk-buckets-multisite-lifecycle.md), [rebalance multisite](../../concepts/splunk-rebalance-multisite.md), [phases de parsing](../../concepts/splunk-parsing-phase-uf-vs-hf.md), [ITSI federated search](../../concepts/splunk-itsi-federated-search.md).

## Versioning note

Handbook écrit contre **Splunk Enterprise 9.4** on-prem, SPL1. Les comportements sont versionnés (`en 9.x, …`) ; toute divergence de version mineure est signalée inline. La documentation Splunk migrant progressivement vers `help.splunk.com`, les URLs `docs.splunk.com/9.4` restent la forme canonique retenue (redirigées le cas échéant), sauf pour le Workload Management dont la page 9.4 vit sur `help.splunk.com`.
