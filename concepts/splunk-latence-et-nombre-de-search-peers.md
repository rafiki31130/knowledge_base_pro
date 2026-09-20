# Latence de recherche et nombre de search peers : protocole de mesure et résultats

À volume interrogé constant, **ajouter des search peers ralentit les recherches**. L'affirmation est banale ; ce qui l'est moins, c'est de la mesurer proprement sur un banc et de séparer ce qui vient du fan-out de ce qui vient de la plateforme de test elle-même. Cette fiche décrit le protocole employé, les résultats obtenus, et surtout les pièges qui rendent ce type de mesure faux sans qu'on s'en aperçoive.

Elle ne remplace pas le [Splunk Search Performance Handbook](../handbooks/splunk-search-performance-handbook/README.md), qui enseigne à décomposer un temps de recherche et n'expose aucune mesure propre. Elle en est le pendant empirique : une campagne, ses chiffres, ses limites.

## Ce qu'on cherche à mesurer

La question posée est : **à données et requêtes rigoureusement identiques, que coûte le passage de N à 2N peers ?**

Le piège est que la réponse naïve — lancer la même recherche sur des clusters de tailles différentes — mesure trois choses à la fois :

1. l'effet réel du fan-out ;
2. la dérive de l'environnement entre deux séries (cache chaud ou froid, buckets différents, horloges) ;
3. la contention de l'hôte de virtualisation, qui grandit mécaniquement avec le nombre de VM.

Tout le protocole consiste à rendre 2 et 3 observables pour pouvoir les écarter.

## Protocole

### Banc

- Cluster d'indexeurs **multisite**, deux sites, facteurs `origin:1, total:2`.
- Search head cluster de 3 membres, un cluster manager, un deployer.
- Peers identiques : **1 vCPU, 512 Mio de RAM** chacun.
- Hôte de virtualisation unique de type poste de travail : 32 processeurs logiques, 64 Gio de RAM, **un seul volume** portant les disques de toutes les VM.
- Chaque peer porte un **générateur d'événements local**, à débit constant par peer. L'ingestion ne transite donc pas par un forwarder partagé qui deviendrait lui-même un goulot.

### Progression

Les paliers se construisent **par ajout en place** : 2, 4, 8, 16, 32, 48 peers. Jamais de reconstruction entre deux paliers. Une seule variable change d'un palier au suivant — **le nombre de peers**. Ni la mémoire par peer, ni les facteurs de réplication, ni le débit d'ingestion, ni les requêtes.

La reconstruction est tentante parce qu'elle part d'un état propre. Elle est à proscrire : elle change simultanément l'âge des buckets, le contenu du cache et la disposition des fichiers sur le disque.

### Requêtes

Quatre requêtes, jouées à chaque palier :

| Rôle | Nature | Ce qu'elle expose |
| --- | --- | --- |
| dense | balaye un grand nombre d'événements | coût du transfert et du `map` |
| terme rare | ne ramène qu'une poignée d'événements | coût du fan-out **sans** travail utile |
| `tstats` | accélérée sur index | coût résiduel hors rawdata |
| **témoin** | figée sur les 2 peers d'origine, volume constant | **dérive de l'environnement** |

Le témoin est la pièce maîtresse. Il interroge toujours les deux mêmes peers, sur la même fenêtre, et ramène le même nombre d'événements à tous les paliers. Si sa durée bouge, ce n'est pas le fan-out : c'est l'environnement.

### Série de mesure

À chaque palier, dans l'ordre :

1. rotation des buckets, pour que les données interrogées soient dans le même état ;
2. **fenêtre de temps figée** de 900 s, dans le passé, identique pour tout le palier ;
3. 3 recherches de chauffe, non comptées ;
4. **30 recherches mesurées** par requête, espacées de 5 s, lancées depuis le **même membre** du SHC.

Pour chaque exécution on relève `runDuration`, `startup.handoff`, le temps par peer, `eventCount` et `scanCount`. Pendant toute la série on échantillonne l'hôte — pourcentage des processeurs logiques, longueur de file du volume, mémoire libre — et les peers : pagination, OOM, redémarrages de `splunkd`.

### Porte de validité

Un run n'est pas interprété s'il ne passe pas des clauses **opposables, écrites avant la mesure** :

```text
hote_non_sature      : part des échantillons avec CPU logique > 85 %  ≤ 0,10
disque_non_sature    : part des échantillons avec file de volume > 8  ≤ 0,10
memoire_suffisante   : mémoire libre minimale ≥ plancher
peers_sains          : aucune pagination, aucun OOM, aucun redémarrage
mesure_non_vide      : aucune recherche ne ramène zéro événement
```

Deux points de méthode comptent ici :

- **Le seuil porte sur une fraction d'échantillons, pas sur un maximum.** Une pointe isolée de deux secondes sur une série de quinze minutes n'invalide rien ; une saturation soutenue, si. Un seuil sur le maximum rejette des runs parfaitement exploitables.
- **Un run invalide se rejoue, il ne se corrige pas.** On ne retire pas les points gênants, on ne rejoue pas la seule requête fautive : on refait le palier entier, fenêtre comprise.

## Résultats

Médianes de `runDuration`, en secondes, sur 30 exécutions par point :

| Peers | dense | terme rare | `tstats` | témoin | Verdict |
| ---: | ---: | ---: | ---: | ---: | --- |
| 2 | 0,162 | 0,107 | 0,116 | 0,160 | valide |
| 4 | 0,198 | 0,169 | 0,187 | 0,165 | valide |
| 8 | 0,280 | 0,376 | 0,209 | 0,170 | valide |
| 16 | 0,470 | 0,557 | 0,443 | 0,178 | valide |
| 32 | 0,935 | 0,842 | 0,726 | 0,203 | valide |
| 48 | 1,487 | 1,382 | 1,233 | 0,256 | **invalide** |
| 48 (rejeu) | 1,689 | 1,408 | 1,431 | 0,249 | **invalide** |

### Le fan-out coûte, et le témoin le prouve

Entre 2 et 32 peers, le terme rare est multiplié par **7,9** alors qu'il ne ramène toujours qu'une poignée d'événements : il ne balaye rien, ne transfère rien. Pendant le même temps le témoin passe de 0,160 à 0,203 s, soit **+27 %**.

C'est cette comparaison qui fait le résultat. Sans témoin, la croissance observée aurait pu être attribuée à une dérive du banc, et l'objection aurait été imparable.

### Le coût est à la mise en route, pas dans les peers

Le temps maximal passé sur un peer est quasi stable sur toute la série. Ce qui enfle, c'est la phase de démarrage : `startup.handoff` passe de 0,05 s à 2 peers à 3,56 s à 32 peers.

**Attention à l'interprétation de ce champ : il est cumulé sur l'ensemble des peers.** Rapporté au peer, il passe d'environ 0,024 s à 0,111 s, soit un facteur 4,6 et non 71. L'effet reste réel et important, mais lire le chiffre brut comme un temps mural conduit à une conclusion spectaculaire et fausse. Un champ cumulé se normalise avant d'être mis en courbe.

### Le plafond du banc, et ce qui sature en premier

À 48 peers, la porte de validité refuse le run, deux fois, sur les deux mêmes clauses — et plus franchement au rejeu qu'au premier essai :

| | 1er essai | Rejeu |
| --- | ---: | ---: |
| part des échantillons CPU > 85 % | 0,110 | 0,183 |
| part des échantillons file > 8 | 0,206 | 0,294 |
| file de volume maximale | 68 | 246 |

Ordre de saturation observé :

1. **La file du volume d'abord**, et elle mord déjà **au repos**, générateurs seuls, avant toute recherche. Un seul volume porte les disques de toutes les VM.
2. **Les processeurs logiques ensuite**, et seulement sous recherche.
3. **Jamais la mémoire**, à aucun palier — alors qu'une dérivation faite hors banc la désignait comme premier mur.

La sur-souscription en vCPU explique la bascule : 1,31× au dernier palier valide, 1,81× au palier refusé. Une covariable d'attente d'ordonnancement, relevée à chaque série, reste plate jusqu'à 16 peers puis monte de 17 % à 32 peers et encore de 20 % à 48. Au-delà d'environ 1,3× de sur-souscription, **ce n'est plus le fan-out qu'on mesure, c'est la file d'attente de l'hôte.**

## Pièges rencontrés, et comment les détecter

**Un témoin qui ne mesure rien.** Dans la première version du dispositif, la clause de restriction aux peers d'origine n'était pas substituée : la requête partait littéralement avec un motif non résolu, ne correspondait à aucun événement, et rendait une durée parfaitement stable — donc rassurante. Trois runs ont été publiés avant que quiconque le remarque, parce que tout le monde vérifiait qu'une durée était produite, pas qu'elle portait sur des données.

> Règle qui en découle : **toute recherche de campagne qui ramène zéro événement invalide le run.** Le `eventCount` fait partie des mesures, pas du décor.

**Une porte de garde qui ne conserve pas ce qui l'a fait basculer.** La fraction d'échantillons au-dessus du seuil était calculée, comparée, utilisée pour rendre le verdict, puis jetée. Impossible de relire après coup le nombre exact ayant motivé un refus ; deux recalculs indépendants ont donné deux valeurs différentes, l'un ne comptant qu'une file quand la porte prenait le maximum de deux. Une clause décisive **s'écrit avec le verdict**.

**Un garde-fou de capacité non incrémental.** Le contrôle d'espace disque opposait la provision *totale* du plan à l'espace *restant*, comptant donc deux fois les VM déjà créées. Il passait tant que le cluster était petit et refusait tout au-delà, quelle que soit la place réelle. Le contrôle de mémoire, lui, ne comptait que les VM à créer. Deux garde-fous voisins, deux sémantiques : à vérifier explicitement.

**Un contrôle de convergence dont la fenêtre part au mauvais moment.** Le contrôle « chaque peer indexe » ouvrait sa fenêtre à l'instant du contrôle et non à la fin du redémarrage tournant, refusant un cluster parfaitement sain parce que les derniers peers redémarrés n'avaient encore rien produit dans l'intervalle.

## Ce que ce banc ne dit pas

- **Il n'a pas de charge concurrente.** Une seule recherche à la fois, aucun utilisateur, aucune recherche planifiée. Les effets d'admission et d'ordonnancement ne sont pas dans ces chiffres.
- **Les peers sont minuscules** — 1 vCPU, 512 Mio. L'absence de pagination à tous les paliers indique qu'ils n'étaient pas le facteur limitant, mais les valeurs absolues ne se transposent pas à des indexeurs de production.
- **Il est virtualisé sur un hôte unique.** Au-delà de la sur-souscription mesurée, la courbe se mélange à la contention de l'hôte. C'est une borne du banc, pas une propriété de Splunk.
- **Les durées absolues n'ont aucun intérêt hors contexte.** Ce qui se transpose, ce sont les *rapports* entre paliers et la *forme* de la croissance.

## À lire ensuite

- [Distribution : bundle readiness et fan-out](../handbooks/splunk-search-performance-handbook/03-distribution.md) — les leviers documentés sur la phase qui enfle ici.
- [Modèle temporel et instruments de mesure](../handbooks/splunk-search-performance-handbook/00-modele-temporel-et-mesure.md) — quoi lire au Job Inspector et dans quels logs.
- [Knowledge bundle en SHC](../handbooks/splunk-shc-knowledge-bundle/README.md) — le bundle, sa réplication et son coût.
- [Hypothèses concurrentes et preuve](../methodologies/hypotheses-concurrentes-preuve.md) — la discipline dont le témoin est une application.

## Sources

Les chiffres de cette fiche proviennent d'une campagne de mesure propre, conduite sur le banc décrit ci-dessus ; ils ne sont pas issus de la documentation Splunk. Pour les mécanismes invoqués :

- [Distributed Search Manual](https://docs.splunk.com/Documentation/Splunk/9.4/DistSearch/) — recherche distribuée, knowledge bundle, `distsearch.conf`.
- [Search Manual — Job Inspector](https://docs.splunk.com/Documentation/Splunk/9.4/Search/ViewsearchjobpropertieswiththeSearchJobInspector) — champs de décomposition d'un job.
- [Capacity Planning Manual](https://docs.splunk.com/Documentation/Splunk/9.4/Capacity/) — dimensionnement et fonctionnement de la recherche.
