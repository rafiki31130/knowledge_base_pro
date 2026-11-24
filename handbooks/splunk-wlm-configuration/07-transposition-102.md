# 07. Transposer vers Splunk Enterprise 10.2 sans extrapoler

## Statut

**Non vérifié : tout résultat d'exécution en 10.2.** Cette édition n'a exécuté aucun essai sur un build 10.2. Une configuration ressemblante, une page de documentation ou un succès 10.4.5 ne lèvent pas cette réserve.

Cette liste prépare une qualification future. Elle ne donne pas mandat de la lancer en production. Un risque déjà démontré, notamment l'OOM ingest, n'a pas à être reproduit par défaut.

## Relisez le contrat du build cible

1. Relevez la révision exacte de tous les rôles.
2. Vérifiez la matrice OS et les exigences de grappe.
3. Lisez les spécifications installées des trois fichiers WLM.
4. Lisez les valeurs par défaut du même build.
5. Comparez les stanzas, clés, types et valeurs admises.
6. Comparez les prédicats et l'ordre d'évaluation.
7. Comparez les commandes et routes REST natives.
8. Vérifiez les exigences de reload et de restart.
9. Vérifiez les identités et les canaux de reprise.
10. Fixez le retour avant l'activation.

Ne transposez pas par analogie `allow_basic`, `apply_rules_to_non_detached_searches` ou `threaded`. Le contrat 10.4.5 réserve ces réglages au support. Leur présence dans une spec ne constitue pas une recommandation d'activation.

Le point documentaire disponible rapporte l'ordre search heads avant pairs. Relisez la section complète du guide cible. Une phase appelée observation qui active WLM reste une bascule avec plafonds effectifs.

## Programme de qualification à rejouer

| Lot | Essais et contrôles | Preuve attendue avant conclusion |
| --- | --- | --- |
| Prérequis système | Unité native, délégation, mode cgroups, plafond de service, swap, politique de relance et de boot | Unité chargée, contrôleurs et droits effectifs, plafond noyau correct, accès de secours recevable |
| Activation et retour ciblé | SHC, bundle CM, défauts, repli T07, OFF/ON des pairs, cycles T18 | Réception par membre, même configuration active, reload ou restart réellement constaté, retour reçu |
| Plafonds | T11 à chaud et à froid | Contraste MemoryMax/MemTotal à poids constants, valeurs systemd et noyau distinctes, plafonds par niveau, retour et recalcul vérifiés |
| CPU | T01, T02 et T03 | Demande sur les pairs, deltas monotones, emprunts, partage intégré et excursions courtes séparés |
| Mémoire de recherche | T04 avec swap puis, si admis, sans swap ; T05 avec témoin calibré | RAM et swap, PID/dispatch, pool et feuille, événements, journal noyau, MainPID et progression du témoin |
| Ingestion | T06 avec offre témoin/pression identique | Fenêtre commune complète, séquences uniques, retard, files, CPU et pagination sur tous les participants |
| Précédence et admission | T10, T12 et T13 | Deux ordres comparables, fin réelle, contraste effectif OFF/ON, témoins hors prédicat et impact sur les apps internes |
| Prédicats et rôles | T14 admin/non-admin et T15 | Cas littéral et index explicite, droits distants convergés, héritage contrôlé, preuve positive de placement sans supposer la visibilité REST |
| Délais et utilisateur | T17 et T09 | Recherches ad hoc et scheduler distinctes, durée native et bornes murales séparées, menu Web et Job Inspector réellement ouverts, propriétaire et tiers selon le besoin |
| Retrait et retour d'un pair | Arrêt natif puis T16 | Quiescence, relance réelle, état CM, offre maintenue connue, résultats complets et intervalle de retour après start |
| Grappe mixte, si retenue et supportable | M1 à M6 adaptés au couple OS/build cible | Unité propre à chaque mode, CPU normalisé, mémoire/swap séparés, statut WLM distribué, détection des membres manquants et réception du retour |
| Supervision | MC, REST WLM, wlm_monitor, _audit, OOM noyau | Inventaire complet, données fraîches, distinction OOM/abort et détection explicite de WLM non appliqué |
| Risque ingest, exceptionnel | T08 seulement si un essai destructif distinct est accepté | Portée des plafonds réellement distribuée, secours indépendant, journal de la victime et récupération complète de configuration |

## Fermez les réserves une par une

Une qualification future doit préciser :

- le build et les OS effectivement exécutés ;
- le critère initial et les adaptations ;
- les passes favorables, négatives ou non concluantes ;
- la fenêtre de mesure et le nombre de répétitions ;
- les retours exercés et ceux seulement préparés ;
- les fonctions ou populations encore non vérifiées.

Ne remplacez pas cette liste par « compatible 10.2 ». Un contrôle arithmétique ne prouve pas une base exclusive. Une recherche visible dans la MC ne prouve pas son placement sur chaque pair. Un fonctionnement mixte en laboratoire ne démontre pas la supportabilité du mélange en production.

## Sources

- [Périmètre réel de l'édition 10.4.5](./00-perimetre-et-preuves.md).
- [Résultats et réserves T01 à T18, M1 à M6](./03-resultats-qualification.md).
- [Configurer cgroups v2, documentation Splunk 10.2](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/10.2/set-up-linux-for-workload-management/configure-cgroups-v2-in-splunk-enterprise).
- [Exigences système des grappes, documentation Splunk 10.2](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.2/deploy-the-indexer-cluster/system-requirements-and-other-deployment-considerations-for-indexer-clusters).

Les deux pointeurs 10.2 proviennent des références documentaires déjà disponibles. Ils ne sont pas revérifiés par accès Web pour cette édition et ne constituent pas une exécution de qualification.
