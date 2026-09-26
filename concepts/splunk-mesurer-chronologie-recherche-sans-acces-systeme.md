# Mesurer la chronologie d'une recherche distribuée sans accès système aux indexeurs

Reconstituer, sur un déploiement de production, la chronologie réelle d'une recherche distribuée : durée totale, ventilation par phase, temps passé sur chaque peer, étalement des sollicitations, régime froid ou chaud. Et savoir **ce que chaque grandeur coûte à obtenir**.

La contrainte qui commande toute la fiche : l'opérateur est **administrateur Splunk par l'API REST et par l'interface**, sans aucun accès système aux indexeurs. Pas de shell, pas de `tcpdump`, pas de lecture directe de fichier. La [chronologie de référence](./splunk-chronologie-recherche-distribuee.md) a été établie par capture réseau sur un banc où l'on avait un shell ; la question est ce qu'il reste de cette méthode sans shell. La réponse : **presque tout**, et ce qui manque est nommé.

| niveau | ce qu'il suppose | ce qu'il coûte |
| --- | --- | --- |
| **1** | des droits d'administration Splunk, rien d'autre | rien : aucune écriture, aucun redémarrage |
| **2** | une modification de configuration Splunk par REST, réversible | un changement à tracer et à défaire |
| **3** | un accès système sur une machine | une demande à l'équipe qui exploite les machines |

Toutes les requêtes ci-dessous ont été **exécutées** sur un banc de 24 indexeurs multisite (Splunk 9.4) ; les extraits de sortie en proviennent. Ce sont des exemples de forme : **les valeurs absolues du banc ne se transposent pas**, ses 24 indexeurs partageant une seule machine physique.

## Les grandeurs, et le niveau qui les rend

| grandeur | niveau | par quoi |
| --- | :--: | --- |
| durée totale d'une recherche | 1 | `_audit`, ou le job inspector par REST |
| ventilation par phase, côté tête de recherche | 1 | `search.log` du job par REST |
| temps passé sur chaque peer, fan-out réel | 1 | `_internal`, `sourcetype=splunkd_access` |
| étalement des sollicitations | 1 (borne haute) | `_internal`, `sourcetype=splunkd_access` |
| ventilation **à l'intérieur d'un peer**, segments non journalisés compris | 1 | `search.log` **distant** par REST |
| régime froid ou chaud, seuil de bascule | 1 (par inférence) | `_internal` |
| peer systématiquement plus lent | 1 | `_internal` |
| charge de la machine d'un indexeur | 1 | `_introspection` |
| recherches simultanées sur un peer | 1 | `_internal`, `sourcetype=splunkd_remote_searches` |
| mêmes grandeurs sur une recherche **planifiée** | 2 | `fetch_remote_search_log` |
| lignes supplémentaires dans `splunkd.log` | 2 | `/services/server/logger` |
| verbosité du `search.log` lui-même | 3 | fichier `log-searchprocess.cfg` |
| connexion neuve ou réutilisée, poignée de main TLS complète ou abrégée | 3 | capture réseau |
| aller-retour réseau réel | 3 | capture réseau |
| preuve qu'un segment non journalisé ne contient aucun échange réseau | 3 | capture réseau |
| instant exact du `SYN`, donc étalement vrai | 3 | capture réseau |

## Niveau 1 : les journaux internes et le job inspector

### Trois repères avant la première mesure

**Les artefacts d'un job ne survivent pas longtemps.**

```text
GET /services/properties/limits/search/ttl        -> 600
GET /services/properties/limits/search/remote_ttl -> 600
```

Dix minutes après la fin du job pour en lire le `search.log` et les compteurs, sur le banc. Passé ce délai, il ne reste que ce qui est indexé dans `_audit`, `_internal` et `_introspection`. **Lire la valeur en vigueur avant de planifier une campagne** : elle fixe le délai maximal entre la recherche et son autopsie. Pour prolonger un job précis, voir [plus bas](#prolonger-lartefact-dun-job).

**Tout part du `sid`**, l'identifiant du job : dans l'URL de *Job → Inspect Job*, dans la réponse de `POST /services/search/jobs`, ou par la requête `_audit` ci-dessous.

**Mesurer perturbe.** `_internal`, `_audit` et `_introspection` sont des index distribués : chaque requête de mesure est elle-même une recherche distribuée et apparaît dans ses propres résultats. **Filtrer sur le `sid` étudié, ou sur une fenêtre antérieure à la mesure.**

### Durée totale : `_audit`

```spl
index=_audit action=search info=completed earliest=-2h
| eval sid=trim(search_id,"'")
| search sid!=scheduler_* sid!=SummaryDirector_*
| stats latest(_time) AS fin, latest(total_run_time) AS duree_s,
        latest(event_count) AS evenements, latest(result_count) AS resultats,
        latest(scan_count) AS scannes, latest(user) AS utilisateur BY sid
| eval fin=strftime(fin,"%H:%M:%S")
| sort - duree_s | head 5
| table fin sid utilisateur duree_s evenements resultats scannes
```

**Contrôle croisé** : deux recherches dont le `runDuration` mesuré par capture valait 1,244 s et 1,009 s ressortent de `_audit` à `total_run_time` **1,24** et **1,01**. La durée totale se retrouve sans rien toucher, et plusieurs heures après.

Pour un job encore vivant, le job inspector par REST :

```bash
curl -u "<admin>" "https://<tete-de-recherche>:8089/services/search/jobs/<sid>?output_mode=json"
# champs : runDuration, resultCount, eventCount, scanCount, searchProviders, performance
```

> **Ne pas lire `startup.handoff` ni `startup.configuration` comme des durées de phase.** Le job inspector agrège les `n + 1` invocations (les peers plus la tête) : ce sont des **cumuls**, pas du temps mural, et ils grandissent mécaniquement avec le nombre de peers. Voir [Latence de recherche et nombre de search peers](./splunk-latence-et-nombre-de-search-peers.md#le-coût-est-à-la-mise-en-route-pas-dans-les-peers). Ne comparer que `runDuration`, ou les grandeurs murales de cette fiche.

### Ventilation par phase, côté tête : le `search.log` du job

```bash
curl -u "<admin>" "https://<tete-de-recherche>:8089/services/search/v2/jobs/<sid>/search.log"
```

Jalons à relever, **nommés par le produit** :

| jalon | ce qu'il borne |
| --- | --- |
| `dispatchRunner - Search process mode:` | début du processus de recherche |
| `ScopedTimer - search.optimize` | fin de l'analyse et de l'optimisation |
| `SearchPhaseGenerator - Search Phases created` | plan de recherche établi |
| `SearchPhaseGenerator - dispatchcreatedSearchResultInfrastructure` | infrastructure de collecte créée |
| `SearchOrchestrator - Starting phase=1` | **début de la sollicitation des peers** |
| `ReducePhaseExecutor - Downloading all remote search.log files took` | fin de la collecte distante |
| `DispatchManager - dispatchHasFinished` | fin du dispatch |
| `dispatchRunner - RunDispatch is done` | fin |

Exemple de sortie, job de `runDuration` 0,863 s, écarts entre jalons successifs :

```text
Search process mode                           origine
search.optimize                               +32 ms
Search Phases created                         +12 ms
dispatchcreatedSearchResultInfrastructure     +40 ms
Starting phase=1                              + 0 ms
Downloading all remote search.log files       +752 ms   <- la phase de collecte
dispatchHasFinished                           +36 ms
RunDispatch is done                           + 4 ms
```

87 % du mur est dans la collecte distante. Le reste de la fiche sert à ouvrir cette boîte.

### Temps par peer et étalement : `_internal`

**La clé du niveau 1, et elle n'est pas évidente** : chaque peer journalise dans son `splunkd_access.log` la requête de recherche que la tête lui adresse, **avec sa durée de traitement**. Ce journal est indexé dans `_internal`, donc lisible en SPL depuis la tête.

```text
<adresse-de-la-tete> - splunk-system-user [<date>]
  "POST /services/streams/search?sh_sid=<sid> HTTP/1.1" 200 2413 "-"
  "Splunk/9.4.x (Linux …; arch=x86_64)" - - - 59ms
```

Splunk en extrait `sh_sid`, `spent` (millisecondes), `bytes`, `status`, `uri_path`. **`_time` est l'instant de fin du traitement** : `_time − spent/1000` est l'instant où le peer a commencé.

**Détail peer par peer, pour un `sid` :**

```spl
index=_internal sourcetype=splunkd_access uri_path="/services/streams/search"
    sh_sid="<sid>" earliest=-2h
| eval debut = _time - (spent/1000)
| eventstats min(debut) AS t0
| eval depart_ms = round((debut - t0)*1000, 1), duree_ms = spent
| table host depart_ms duree_ms bytes status
| sort depart_ms
```

| host | depart_ms | duree_ms | bytes | status |
| --- | ---: | ---: | ---: | --- |
| idx-s2-11 | 0.0 | 649 | 2419 | 200 |
| idx-s1-11 | 25.0 | 642 | 2440 | 200 |
| idx-s1-03 | 28.0 | 650 | 2424 | 200 |
| idx-s2-03 | 33.0 | 613 | 2428 | 200 |
| … | | | | |

Se lisent d'un coup d'œil : le **fan-out réel** (une ligne par peer sollicité), l'**ordre**, l'**étalement**, le **temps de chaque peer** et le **volume rendu**. Un `status` autre que `200` désigne un peer en échec.

> **Limite.** `depart_ms` mesure l'étalement des **débuts de traitement**, pas celui des `SYN`. Entre les deux : établissement de connexion, poignée de main TLS, remise de la requête, soit 19,8 ms en médiane à froid et 1,9 ms à chaud sur le banc. C'est une **borne haute** de l'étalement des sollicitations, d'autant plus large que le régime est froid.

**Résumé par recherche, la vue de campagne :**

```spl
index=_internal sourcetype=splunkd_access uri_path="/services/streams/search"
    earliest=-2h
| eval debut = _time - (spent/1000)
| eventstats min(debut) AS t0, max(debut) AS t1 BY sh_sid
| stats dc(host) AS peers, min(t0) AS depart, max(_time) AS fin,
        max(t1) AS dernier_depart, median(spent) AS par_peer_ms_median,
        max(spent) AS par_peer_ms_max BY sh_sid
| eval etalement_ms = round((dernier_depart - depart)*1000, 1),
       collecte_ms  = round((fin - depart)*1000, 1),
       horodatage   = strftime(depart, "%H:%M:%S.%3N")
| sort 0 depart
| table horodatage peers etalement_ms collecte_ms par_peer_ms_median par_peer_ms_max
```

| horodatage | peers | etalement_ms | collecte_ms | par_peer_ms_median | par_peer_ms_max |
| --- | ---: | ---: | ---: | ---: | ---: |
| 07:16:52.825 | 24 | **4248.0** | **8281.0** | **5901** | **8259** |
| 07:16:53.616 | 24 | 4370.0 | 7899.0 | 5372 | 7863 |
| 07:23:42.206 | 24 | 213.0 | 656.0 | 480 | 651 |
| 07:29:32.064 | 24 | 379.0 | 850.0 | 599 | 814 |

Une ligne par recherche distribuée. Les deux premières montrent le genre d'anomalie que cette vue fait sortir : un coût par peer dix fois supérieur au reste, à fan-out identique.

### Ventilation à l'intérieur d'un peer, segments non journalisés compris

**Le résultat le plus utile de la fiche, et le moins attendu** : le `search.log` que chaque peer produit pour sa part de la recherche est **rapatrié sur la tête** et **lisible par REST**, peer par peer.

```bash
# peers dont le journal est disponible : champ remoteSearchLogs
curl -u "<admin>" "https://<tete>:8089/services/search/jobs/<sid>?output_mode=json"

# journal d'un peer
curl -u "<admin>" "https://<tete>:8089/services/search/v2/jobs/<sid>/search.log?peer=<nom-du-peer>"
```

Il porte exactement les jalons de la [chronologie de référence](./splunk-chronologie-recherche-distribuee.md#rapprochement-avec-les-journaux-du-job), y compris les bornes des deux segments que le produit ne journalise pas :

| jalon | ce qu'il borne |
| --- | --- |
| `dispatchRunner - Search process mode:` | première ligne : création ou réutilisation du processus |
| `BundlesSetup - Setup stats for …` | début du **segment non journalisé n° 1** |
| `UserManagerPro - Load authentication` | fin du segment n° 1 |
| `dispatchRunner - search context: user=…, bs-pathname=…` | génération de bundle réellement utilisée |
| `DispatchCommandProcessor - Search requires the following indexes=` | index résolus |
| `dispatchRunner - SearchPeerInitSearchMs=` | début du **segment non journalisé n° 2** |
| `FastTyper - found nodes count` | fin du segment n° 2 |
| `dispatchRunner - RunDispatch is done` | fin du dispatch côté peer |

Sur deux recherches identiques à 24 peers, journaux récupérés pour 24 peers sur 24 :

| segment | recherche froide | recherche chaude |
| --- | --- | --- |
| `BundlesSetup` → `Load authentication` (non journalisé n° 1) | médiane **174 ms** (52 – 232) | médiane **8 ms** (4 – 52) |
| `SearchPeerInitSearchMs` → `FastTyper` (non journalisé n° 2) | médiane **68 ms** (16 – 132) | médiane **20 ms** (8 – 28) |
| première ligne → `RunDispatch is done` | médiane **432 ms** (148 – 580) | médiane **52 ms** (36 – 84) |

La ventilation interne d'un peer, **segments aveugles compris**, est donc entièrement atteignable au niveau 1. Ce qui manque est la **preuve** que ces segments ne contiennent aucun échange réseau : c'est le niveau 3.

Extraction des deux segments sur l'ensemble des peers :

```python
import re, datetime, statistics, urllib.request, base64, ssl, json
BASE, SID = "https://<tete>:8089", "<sid>"
AUTH = "Basic " + base64.b64encode(b"<utilisateur>:<mot-de-passe>").decode()
CTX  = ssl.create_default_context()

def get(p):
    r = urllib.request.Request(BASE + p, headers={"Authorization": AUTH})
    return urllib.request.urlopen(r, context=CTX, timeout=60).read().decode("utf-8", "replace")

pairs = [("aveugle_1", "BundlesSetup", "UserManagerPro"),
         ("aveugle_2", "SearchPeerInitSearchMs", "FastTyper")]

def ts(l):
    m = re.match(r"(\d\d-\d\d-\d{4} \d\d:\d\d:\d\d\.\d\d\d)", l)
    return datetime.datetime.strptime(m.group(1), "%m-%d-%Y %H:%M:%S.%f").timestamp() if m else None

job   = json.loads(get(f"/services/search/jobs/{SID}?output_mode=json"))
peers = job["entry"][0]["content"]["remoteSearchLogs"][0].split()
acc   = {n: [] for n, _, _ in pairs}
for p in peers:
    lignes = get(f"/services/search/v2/jobs/{SID}/search.log?peer={p}").splitlines()
    for nom, debut, fin in pairs:
        a = next((ts(l) for l in lignes if debut in l), None)
        b = next((ts(l) for l in lignes if fin in l), None)
        if a and b:
            acc[nom].append((b - a) * 1000)
for nom, v in acc.items():
    print(f"{nom}: mediane={statistics.median(v):.0f} ms  min={min(v):.0f}  max={max(v):.0f}  n={len(v)}")
```

> **Jalon de fin : `RunDispatch is done`, pas `Done with streaming search`.** Le second n'existe que quand le peer exécute la recherche en mode `StreamSearch` ; en `BatchSearch`, le journal se termine par `SearchPipelineExecutor - BatchSearch pipeline=0 is finished`. Un script qui cherche le premier libellé rend zéro ligne une fois sur deux.

> **Le rapatriement des journaux distants n'est ni gratuit ni universel.** Il coûte 32 ms à 24 peers contre 4 ms à 1 peer sur le banc, soit environ 9 % de la croissance du coût avec le fan-out. Et le réglage livré `fetch_remote_search_log = disabledSavedSearches` **exclut les recherches planifiées** : voir [le niveau 2](#rendre-les-searchlog-distants-disponibles-pour-les-recherches-planifiées).

### Régime froid ou chaud, et seuil de bascule

Le régime ne se lit nulle part directement. Il se **mesure** en opposant, recherche après recherche, le coût par peer à la durée d'inactivité qui la précède.

```spl
index=_internal sourcetype=splunkd_access uri_path="/services/streams/search"
    earliest=-2h
| eval debut = _time - (spent/1000)
| stats min(debut) AS depart, max(_time) AS fin, dc(host) AS peers,
        median(spent) AS par_peer_ms_median BY sh_sid
| sort 0 depart
| streamstats current=f last(fin) AS fin_precedente
| eval inactivite_s = round(depart - fin_precedente, 1),
       horodatage   = strftime(depart, "%H:%M:%S.%3N")
| where inactivite_s > 0
| table horodatage peers inactivite_s par_peer_ms_median
```

Extrait d'une plage où recherches isolées et rafales se succèdent :

| horodatage | peers | inactivite_s | par_peer_ms_median |
| --- | ---: | ---: | ---: |
| 09:08:47.568 | 24 | 554.7 | 521 |
| 09:09:04.620 | 24 | 16.3 | 753 |
| 09:09:36.248 | 24 | **30.7** | **509** |
| 09:09:37.773 | 24 | **0.8** | **61** |
| 09:10:04.695 | 24 | 26.8 | 689 |
| 09:10:17.648 | 24 | 12.1 | 161 |
| 09:10:36.155 | 24 | 0.3 | 68 |
| 09:11:58.143 | 24 | 81.3 | 664 |
| 09:12:31.559 | 24 | 8.3 | 93 |
| 09:14:04.475 | 24 | 65.5 | 652 |

Au-dessus d'une trentaine de secondes d'inactivité, le coût médian par peer se tient entre 509 et 753 ms ; en deçà de la seconde, entre 61 et 130 ms. Les deux lignes en gras sont deux recherches **strictement identiques** jouées à 1,5 s d'intervalle : **509 ms contre 61 ms**, un facteur 8,3 à travail identique.

**En production :**

1. jouer la requête sur une plage d'activité réelle, qui contient à la fois des recherches rapprochées et des recherches isolées ;
2. tracer `par_peer_ms_median` contre `inactivite_s` : un **coude** apparaît, plancher en deçà, haut et à peu près plat au-delà. **L'abscisse du coude est le seuil de fermeture des connexions du déploiement** ;
3. ne pas reporter les 28 s du banc : aucun réglage documenté ne gouverne ce seuil, il se mesure.

**Second détecteur, indépendant** : le segment non journalisé n° 1 vaut 174 ms à froid et 8 ms à chaud sur le banc, un ordre de grandeur de séparation lisible sur un seul job. Les deux détecteurs doivent converger ; s'ils divergent, c'est le premier signal utile du diagnostic.

### Un peer systématiquement plus lent

```spl
index=_internal sourcetype=splunkd_access uri_path="/services/streams/search"
    earliest=-2h
| stats count AS sollicitations, median(spent) AS ms_median, perc95(spent) AS ms_p95,
        max(spent) AS ms_max BY host
| eventstats median(ms_median) AS ms_median_parc
| eval ecart_a_la_mediane = round(ms_median / ms_median_parc, 2)
| sort - ms_median
| table host sollicitations ms_median ms_p95 ms_max ecart_a_la_mediane
```

Sur le banc, `ecart_a_la_mediane` vaut 1,14 au pire : aucun peer déviant, la dispersion est celle de la contention partagée. En production, un peer à **1,5 ou plus, de façon stable sur plusieurs centaines de sollicitations**, est un candidat sérieux, à croiser avec les deux requêtes suivantes.

### Charge de la machine d'un indexeur : `_introspection`

```spl
index=_introspection component=Hostwide earliest=-2h
| stats min(data.cpu_idle_pct) AS cpu_libre_min,
        avg(data.normalized_load_avg_1min) AS charge_moyenne,
        max(data.normalized_load_avg_1min) AS charge_max BY host
| sort - charge_max
| head 5
```

`normalized_load_avg_1min` est la charge rapportée au nombre de cœurs : au-dessus de 1, la machine a plus de travail prêt que de processeurs pour le prendre.

> **Ce que cette requête ne voit pas** : elle rend la charge **telle que l'invité la perçoit**. Si plusieurs indexeurs sont des machines virtuelles sur un même hyperviseur, un hôte saturé peut laisser chaque invité se croire peu chargé. Sur matériel dédié, la lecture est directe ; en virtualisation partagée, c'est **une borne basse**.

### Recherches simultanées sur un peer

```spl
index=_internal sourcetype=splunkd_remote_searches
    "Streamed search connection established" earliest=-2h
| rex "active_searches=(?<recherches_actives>\d+)"
| stats max(recherches_actives) AS max_simultanees, count AS connexions BY host
| sort - max_simultanees
| head 5
```

Concurrence **interne à Splunk**, à distinguer de la charge machine. Un peer lent avec `max_simultanees` élevé est saturé de recherches ; un peer lent à 1 ou 2 a un problème qui ne vient pas du volume de recherches.

> Filtrer ce `sourcetype` sur `search_id="<sid>"` rend **zéro résultat** : le champ n'y est pas extrait. D'où le `rex` et le filtre sur le libellé.

### Voies écartées

- **`sourcetype=splunkd_remote_searches` filtré sur un `sid`** pour calculer l'étalement : le `sid` apparaît dans des dizaines d'événements par peer sur toute la vie du job (264 événements pour une recherche d'une seconde, étalés sur 190 s). Inexploitable pour la chronologie.
- **`metrics.log`, `group=search_concurrency`** : compteurs d'instance, jamais rattachés à un `sid`.

## Niveau 2 : configuration Splunk, sans accès système

Tout se fait par REST avec des droits d'administration. **Chaque geste se fait avec sa lecture préalable et son retour arrière** : relever la valeur en vigueur avant d'écrire, la reposer telle quelle après.

### Rendre les `search.log` distants disponibles pour les recherches planifiées

```bash
curl -u "<admin>" "https://<tete>:8089/services/properties/limits/search/fetch_remote_search_log"
# valeur livree : disabledSavedSearches
```

Spécification livrée (`limits.conf`, strophe `[search]`) :

```text
fetch_remote_search_log = [enabled|disabledSavedSearches|disabled]
* When set to "disabledSavedSearches": Downloads all remote logs other than saved search logs
  and oneshot search logs.
* You can override this setting on a per-search basis by appending
  '|noop remote_log_fetch=[*|<indexer1;indexer2...>]' to the search string…
* Default: disabledSavedSearches
```

**a. Surcharge par recherche, sans mutation de configuration** :

```spl
… | noop remote_log_fetch=*
```

Éprouvée : champ `remoteSearchLogs` renseigné pour 24 peers, journal d'un peer récupéré par REST. **La voie à préférer** : elle ne touche à rien et ne vise que la recherche mesurée. Elle suppose de pouvoir modifier le texte de la recherche, donc ne convient pas pour observer une recherche planifiée telle qu'elle s'exécute réellement.

**b. Élévation du réglage, réversible** :

```bash
# 1. relever la valeur en vigueur et la noter
# 2. poser
curl -u "<admin>" -X POST \
  "https://<tete>:8089/servicesNS/nobody/search/configs/conf-limits/search" \
  -d "fetch_remote_search_log=enabled"
# 3. retour arriere : reposer la valeur relevee
curl -u "<admin>" -X POST \
  "https://<tete>:8089/servicesNS/nobody/search/configs/conf-limits/search" \
  -d "fetch_remote_search_log=disabledSavedSearches"
```

*Point d'entrée lu sur le banc ; l'écriture n'y a pas été exécutée.*

| | |
| --- | --- |
| **ce que ça rend** | la ventilation interne des peers pour **toutes** les recherches, planifiées comprises |
| **coût** | environ 9 % de la croissance du coût avec le fan-out, sur **toutes** les recherches tant que le réglage est posé |
| **risque** | écritures sur le disque de dispatch de la tête, pénalité sur chaque recherche planifiée |
| **retour arrière** | reposer la valeur relevée, sans redémarrage |
| **verdict** | pour une campagne bornée, jamais en permanence |

### Prolonger l'artefact d'un job

Plutôt qu'allonger `ttl` pour tout le déploiement, prolonger **le job étudié et lui seul** :

```bash
curl -u "<admin>" -X POST "https://<tete>:8089/services/search/jobs/<sid>/control" \
  -d "action=setttl&ttl=3600"
```

Ce n'est pas une mutation de configuration : le geste porte sur un artefact et expire de lui-même.

### Élever une catégorie de journalisation

```bash
# 1. relever le niveau en vigueur, pour CHAQUE categorie touchee
curl -u "<admin>" "https://<instance>:8089/services/server/logger/<categorie>?output_mode=json"
# 2. elever
curl -u "<admin>" -X POST "https://<instance>:8089/services/server/logger/<categorie>" -d "level=DEBUG"
# 3. retour arriere
curl -u "<admin>" -X POST "https://<instance>:8089/services/server/logger/<categorie>" -d "level=<niveau_releve>"
```

Vérifié en lecture seule : le registre expose plus de 1 600 catégories, dont toutes celles de la chronologie (`DistributedSearchResultCollectionManager`, `UserManagerPro`, `BundlesSetup`, `FastTyper`, `SearchOrchestrator`, `dispatchRunner`). Le point d'entrée répond aussi sur le port de gestion d'un indexeur, avec un compte d'administration : l'élévation côté peer est possible **si** le réseau et le compte le permettent, à vérifier sur chaque déploiement.

| | |
| --- | --- |
| **ce que ça rend** | des lignes supplémentaires dans **`splunkd.log`**, indexé dans `_internal`, donc exploitables en SPL |
| **ce que ça ne rend pas** | rien de plus dans le `search.log` (section suivante) |
| **risque** | volume dans `_internal`, licence, dégradation de l'instance. Une catégorie à la fois, fenêtre bornée |
| **retour arrière** | reposer le niveau relevé, immédiat, sans redémarrage |
| **gain** | **non mesuré** : rien ne garantit que ces composants écrivent aussi dans `splunkd.log`. Élever, observer sur une fenêtre courte, conclure ou renoncer |

### Ce que le niveau 2 ne peut pas faire

**Élever la verbosité du `search.log` n'est pas un geste REST.** `/services/server/logger` gouverne `splunkd.log`. Le `search.log` a son propre registre, `$SPLUNK_HOME/etc/log-searchprocess.cfg` :

```text
# search logs go a separate file
rootCategory=INFO,searchprocessAppender
appender.searchprocessAppender.fileName=${SPLUNK_DISPATCH_DIR}/search.log
```

Ce `rootCategory=INFO` explique une observation qui pourrait égarer : le `search.log` porte des lignes `INFO dispatchRunner` alors que `/services/server/logger` déclare `dispatchRunner` à `WARN`. **Deux registres distincts.** Changer la verbosité du `search.log` d'un indexeur suppose d'écrire ce fichier sur la machine : c'est du niveau 3, et c'est la seule voie connue pour tenter d'expliquer les deux segments non journalisés.

## Niveau 3 : la capture réseau, en demande prête à transmettre

### Ce que seule la capture obtient

1. Si la tête **rouvre une connexion** vers chaque peer à chaque recherche, ou réutilise la précédente.
2. Si la poignée de main TLS est **complète ou abrégée**, lisible à la présence d'un message `Certificate` du serveur, sans déchiffrement.
3. L'**aller-retour réseau réel**, donc la part du coût qui est vraiment du réseau (1,1 ms sur 19,8 sur le banc).
4. La **preuve par l'absence de paquet** que les deux segments non journalisés sont entièrement locaux au peer.
5. L'**instant exact du `SYN`**, donc l'étalement vrai des sollicitations.
6. La **durée d'inactivité** au bout de laquelle la tête ferme ses connexions.

### Modèle de demande

Rédigé pour être exécuté par une équipe qui ne connaît ni Splunk ni le dossier.

**Contexte.** On mesure la chronologie d'une recherche distribuée Splunk ; les journaux du produit donnent tout sauf ce qui se passe sur le fil, et seule une capture des **en-têtes** de paquets peut le donner.

**Machines** : **deux** suffisent. La tête de recherche qui lance la recherche étudiée, et un indexeur, n'importe lequel.

**Outil** : `tcpdump`. S'il n'est pas installé, l'installer puis le **retirer** après la capture.

**Sur la tête de recherche** (`<plage-des-indexeurs>` au format `a.b.c.0/24`, `<port-de-gestion>` : 8089 par défaut) :

```bash
timeout 300 tcpdump -i any -n -s 256 -B 16384 \
  -w "/var/tmp/chrono-tete-$(hostname -s)-$(date +%Y%m%d-%H%M%S).pcap" \
  'tcp and port <port-de-gestion> and net <plage-des-indexeurs>'
```

**Sur l'indexeur** :

```bash
timeout 300 tcpdump -i any -n -s 256 -B 16384 \
  -w "/var/tmp/chrono-peer-$(hostname -s)-$(date +%Y%m%d-%H%M%S).pcap" \
  'tcp and host <adresse-de-la-tete> and port <port-de-gestion>'
```

Les deux commandes tournent **en même temps** ; le demandeur joue ses recherches pendant la fenêtre.

| option | rôle | pourquoi elle est obligatoire |
| --- | --- | --- |
| `-i any` | toutes les interfaces | le chemin de retour peut être **asymétrique** ; sur une seule interface, on ne voit qu'une direction |
| `-s 256` | tronque chaque paquet à 256 octets | **aucune donnée applicative enregistrée**, seuls les en-têtes IP, TCP et TLS tiennent. C'est la garantie de confidentialité |
| `-n` | pas de résolution DNS inverse | la capture ne génère pas elle-même de trafic |
| `-B 16384` | tampon noyau de 16 Mo | pas de paquet perdu sous rafale |
| `timeout 300` | arrêt après 5 minutes | borne durée et volume sans intervention |

**Volume.** Repères du banc (24 indexeurs, trois recherches, un cycle de rafraîchissement) : 3 484 paquets et 577 Kio côté tête, 179 paquets et 29 Kio côté indexeur. Soit environ **7,5 Ko par connexion** côté tête (dérivé, pas mesuré par connexion) :

```text
volume cote tete  ~=  (indexeurs) x (recherches sur la fenetre) x 7,5 Ko
                   +  (indexeurs) x (minutes de capture) x 1,5 connexion x 7,5 Ko
```

Le second terme est le **rafraîchissement périodique de l'état des peers**, qui ouvre 1 à 2 connexions par indexeur toutes les 60 secondes, même si personne ne cherche. Exemple : 20 indexeurs, 5 minutes, 50 recherches → environ 7,5 Mo + 1,1 Mo, moins de 10 Mo. **Prévoir 50 Mo libres sur `/var/tmp`.**

**Confidentialité.** Le canal est intégralement chiffré en TLS, URL de requête comprises ; `-s 256` tronque de toute façon aux en-têtes. Sur le banc, les fichiers ont été passés au crible (`authorization`, `basic <base64>`, `password`, `pass4symmkey`, `cookie`, `session`, `HTTP/1.`, `POST /`, `GET /`) : zéro occurrence.

**Après la capture** :

```bash
tcpdump -r /var/tmp/chrono-*.pcap 2>/dev/null | wc -l   # lisible, nombre de paquets
sha256sum /var/tmp/chrono-*.pcap                        # empreinte a transmettre
command -v tcpdump || echo ABSENT                       # apres desinstallation eventuelle
```

Déposer les deux fichiers et leurs empreintes à l'emplacement convenu, **pas par messagerie**.

**Ce qui n'est pas demandé** : aucun redémarrage ni modification de configuration Splunk, aucune capture sur les autres indexeurs, aucune analyse, aucun déchiffrement, aucune clé privée.

### Lire les captures

Avec `tcpdump -nr`, `tshark` ou Wireshark, sans déchiffrement :

1. **Complète ou abrégée** : présence ou absence d'un `Certificate` serveur, dans un en-tête d'enregistrement TLS de 5 octets.
2. **Aller-retour réseau** : `SYN` → `SYN-ACK`.
3. **Segments non journalisés** : absence totale de paquet entre les deux instants déjà datés par le `search.log` distant.
4. **Seuil de fermeture** : délai entre le dernier octet utile et le `FIN` de la tête.

Pour rapprocher les deux captures, mesurer l'écart d'horloge entre les machines en appariant les paquets présents dans les deux fichiers (même quadruplet, mêmes `seq`/`ack`, mêmes drapeaux, même longueur) plutôt que de le supposer nul ; méthode dans la [chronologie de référence](./splunk-chronologie-recherche-distribuee.md#lécart-dhorloge-mesuré-et-non-supposé).

## Interpréter : dans cet ordre

### 1. Écarter le régime froid

**Signature** : `par_peer_ms_median` élevé sur **tous** les peers à la fois, `inactivite_s` grande, segment non journalisé n° 1 d'un ordre de grandeur au-dessus de sa valeur en rafale.

**Lecture** : le prix de la première recherche après un silence (sur le banc, facteur 2,1 à 2,6 sur la durée totale, 8,3 sur le coût par peer). En production, le régime réaliste est généralement le régime chaud, parce que les recherches s'enchaînent bien en deçà du seuil de fermeture. **Sauf si la plainte porte précisément sur des recherches isolées et espacées, refiltrer sur les recherches à `inactivite_s` faible et recommencer.**

### 2. Fan-out, peer lent ou contention ?

| ce qu'on voit | lecture | vérification |
| --- | --- | --- |
| `collecte_ms` croît avec le nombre de peers, `par_peer_ms_median` **stable** | **fan-out** : la collecte se termine avec le peer le plus lent, statistique d'ordre sur `n` durées, pas file d'attente | l'écart `par_peer_ms_max` / `par_peer_ms_median` se creuse avec `n` |
| **un seul** peer à `ecart_a_la_mediane ≥ 1,5`, stable | **peer lent** | charge machine et recherches simultanées sur ce peer |
| plusieurs peers lents **aux mêmes instants**, `charge_max` élevée sur leurs machines | **contention d'hôte** | `_introspection` ; en virtualisation partagée, chercher hors de Splunk |
| `etalement_ms` grand, `par_peer_ms_median` **faible** | goulet **sur la tête**, qui tarde à émettre ses sollicitations | `dispatchcreatedSearchResultInfrastructure` et charge de la tête |

### 3. Le fan-out coûte, et il est réductible

Le coût croît avec le nombre de peers **sollicités**. Sur le banc, restreindre une recherche à 12 peers sur 24 par une clause `splunk_server` rend **−40 % de `runDuration`** : la tête ne se connecte plus aux peers exclus, son `search.log` les déclare `optimized out`. Mais cette clause restreint aussi les données interrogées : ce n'est pas un réglage de déploiement.

**L'affinité de site ne produit pas cet effet, et c'est mesuré.** Une tête de recherche affectée à un site ne rend plus que les résultats des copies primaires de son site, et le résultat reste complet si ce site détient une copie interrogeable de chaque bucket. Mais elle **sollicite toujours tous les peers** : sur le banc, 24 connexions sous affinité comme sans, les peers de l'autre site exécutent leur part et ne rendent rien. `runDuration` : 0,3135 s sous affinité, 0,3125 s sans, écart nul. L'affinité change **qui rend** les résultats, pas **qui est sollicité**, et le coût du fan-out est payé par peer sollicité.

Deux conséquences :

- **Ne pas attendre de gain de latence de l'affinité de site.** Son intérêt est ailleurs (trafic inter-sites, tolérance à la perte d'un site).
- **Ne pas la combiner avec une restriction `splunk_server`** : les copies primaires du site affecté se trouvent aussi sur des peers exclus par la clause, et des événements disparaissent du résultat (33 sur 36 sur le banc).

Le seul moyen de réduire durablement le nombre de peers sollicités, sans réduire les données visibles, est de **découper les index par groupe de peers**, de sorte qu'une recherche sur un index ne concerne que les peers qui le portent. C'est une décision d'architecture, pas un réglage.


### 4. Ce que le diagnostic ne dira pas

Si le temps part dans les deux segments non journalisés (444 ms sur 704 d'écart froid/chaud sur le banc), le protocole a fait ce qu'il peut : il les a localisés, bornés, et, au niveau 3, établi qu'ils sont locaux au peer. **Il ne les explique pas.** Aucun réglage documenté n'a été identifié pour y agir. C'est une limite du produit, pas du protocole.

## Ce que cette méthode ne rend pas

| question | état |
| --- | --- |
| étalement **vrai** des sollicitations | niveau 1 : borne haute, écartée du vrai de 19,8 ms à froid et 1,9 ms à chaud sur le banc ; le vrai est au niveau 3 |
| seuil de fermeture des connexions | inférable au niveau 1 (coude), observable au niveau 3 ; aucun réglage documenté |
| *pourquoi* les segments non journalisés durent ce qu'ils durent | hors de portée des trois niveaux en l'état |
| charge réelle d'un hyperviseur portant plusieurs indexeurs | hors de Splunk |
| contenu applicatif d'une recherche distribuée | non lisible, délibérément |

## À lire ensuite

- [Chronologie d'une recherche distribuée : ce que le fil transporte, et quand](./splunk-chronologie-recherche-distribuee.md) : la chronologie de référence, établie par capture, et ses deux figures.
- [Latence de recherche et nombre de search peers](./splunk-latence-et-nombre-de-search-peers.md) : le coût du fan-out palier par palier, et pourquoi `startup.handoff` est un cumul.
- [Modèle temporel et instruments de mesure](../handbooks/splunk-search-performance-handbook/00-modele-temporel-et-mesure.md) : Job Inspector et journaux.
- [Cheat-sheet : décomposer un temps de recherche](../handbooks/splunk-search-performance-handbook/99-cheatsheet-decomposer-un-temps.md).

## Sources

- [Search Manual, Job Inspector](https://docs.splunk.com/Documentation/Splunk/9.4/Search/ViewsearchjobpropertieswiththeSearchJobInspector) : champs d'un job.
- [REST API Reference, Search endpoints](https://docs.splunk.com/Documentation/Splunk/9.4/RESTREF/RESTsearch) : `search/jobs`, `control`, `search.log`.
- [Admin Manual, limits.conf](https://docs.splunk.com/Documentation/Splunk/9.4/Admin/Limitsconf) : `ttl`, `remote_ttl`, `fetch_remote_search_log`.
- [Troubleshooting Manual, What Splunk logs about itself](https://docs.splunk.com/Documentation/Splunk/9.4/Troubleshooting/WhatSplunklogsaboutitself) : `_internal`, `_introspection`, `splunkd_access.log`.
- [tcpdump(8)](https://www.tcpdump.org/manpages/tcpdump.1.html) : options de capture.
