# Réintégrer un license peer sans pic de charge sur le License Manager

Quand un license peer (typiquement un indexeur) reste coupé de son License Manager (LM),
il continue d'indexer et accumule son usage en attente. À la reconnexion, il remonte cet
usage d'un coup. Avec une forte cardinalité de sourcetypes, cette remontée coûte cher au LM :
plusieurs peers qui reviennent ensemble peuvent le saturer jusqu'à l'OOM.

Cette fiche mesure ce qui se passe réellement, et ce qui permet de réintégrer un peer
**sans que le LM traite l'usage accumulé**.

> Mesures sur **Splunk Enterprise 9.4.6**, lab d'un LM (2 vCPU, 4 Go) et d'un indexeur
> (2 vCPU, 8 Go), licence Developer de 10 Gio par jour, novembre 2026. Un seul peer : la
> charge cumulée de plusieurs peers n'est pas reproduite.

Voir aussi : [dernière synchro des license peers avec le LM](../cheat-sheets/splunk-license-peers-derniere-synchro.md).

---

## 1. Le mécanisme observé

```mermaid
sequenceDiagram
    participant P as license peer (indexer-01)
    participant D as table d'usage sur disque (peer)
    participant LM as license manager
    Note over P: usage du jour tenu en mémoire,<br/>une clé par (sourcetype, index...)
    loop toutes les 60 s (report_interval)
        P->>LM: POST /services/masterlm/usage (table cumulée du jour)
        LM-->>P: 200
        P->>D: réécrit la table (après remontée réussie)
    end
    Note over LM: le compteur du pool reflète<br/>la table remontée par le peer
    Note over P,LM: LM injoignable : usage en mémoire seulement,<br/>table non réécrite, une erreur LMTracker par minute
    P->>D: au démarrage : relit la table
```

- **Le coût suit la cardinalité, pas le volume.** À 1 M de sourcetypes, la première remontée
  coûte 9 à 15 s de traitement au LM. Ensuite, chaque remontée minute coûte encore environ
  2,6 s tant que la table du jour contient ces 1 M de clés, même sans nouvelle donnée. Multiplier
  le volume par 39 (10 Go au lieu de 256 Mo) n'aggrave pas ce coût de fond.
- **LM injoignable :** le peer garde l'usage en mémoire et journalise chaque minute
  `ERROR LMTracker - failed to send rows, reason='Unable to connect to license manager=...'`.
  Au retour du LM, il envoie **une seule** remontée agrégée : il ne rejoue pas les minutes
  d'absence.
- **Table d'usage sur disque :** un fichier CSV sous
  `$SPLUNK_HOME/var/lib/splunk/fishbucket/rawdata/`, d'en-tête
  `slaveId,slaveLabel,serializedTime,pool_suggestion,UsageKey,Bytes`, une ligne par clé
  (`"sourcetype::<st>",<octets>`), avec une copie `.old`. 33 Mo pour 1 M de sourcetypes. Il
  n'est réécrit qu'après une remontée réussie.
- **Délai côté peer :** au-delà de 30 s de traitement (`receive_timeout` par défaut), le peer
  compte la remontée comme échouée. Un peer seul n'a pas atteint ce seuil au lab (17 s au pire).

## 2. Protocole

- Fixture : événements de 256 octets `st=st_NNNNNNN seq=NNNNNNNN xxx...`, le sourcetype est
  attribué au parsing par `TRANSFORMS` (`DEST_KEY = MetaData:Sourcetype`). Lot de référence :
  1 M d'événements, 1 M de sourcetypes, 256 Mo.
- Chaque essai part du même instantané des deux VM.
- Relevés : durée de chaque `POST /services/masterlm/usage` (dernier champ, en ms, de
  `splunkd_access.log` du LM), CPU et RSS des splunkd toutes les 2 s, octets du pool
  (`/services/licenser/pools`), état côté peer (`/services/server/info`,
  `/services/licenser/localpeer`, `/services/licenser/messages`), recherche de contrôle
  `| tstats count where index=<index>`.
- Piège de fixture : deux fichiers dont les 256 premiers octets sont identiques ont le même CRC
  pour le monitor, qui prend le second pour un fichier déjà lu. Le second lot décale donc son
  champ `seq=`.

## 3. Résultats

| Essai | Séquence | Remontée la plus lourde au retour | Coût de fond ensuite | Octets comptés par le LM |
|---|---|---|---|---|
| 1. Témoin | LM éteint, lot de référence, LM rallumé | **14,8 s** | 2,5 à 2,9 s par minute | 255 Mo |
| 2. Restart du peer | LM éteint, lot de référence, restart du peer, LM rallumé | 1 ms | 0 à 1 ms | **0** |
| 3. 10 Go puis restart | LM éteint, 39 M d'événements (1 M de sourcetypes, 9,98 Go), restart du peer, lot de référence, LM rallumé | 14,5 s | 3,0 s | 255 Mo (le second lot seul) |
| 4a. Restart, table conservée | LM allumé, lot de référence, restart du peer | pas de pic | 2,6 s par minute | 255 Mo |
| 4b. Restart, table retirée | LM allumé, lot de référence, table déplacée pendant l'arrêt, restart du peer | pas de pic | 0 ms | **0** : l'usage déjà compté est effacé |
| 5a. LM coupé entre deux remontées, restart | `report_interval = 15m`, LM allumé, 10 Go ingérés juste après une remontée, LM coupé avant la suivante, restart du peer, LM rallumé | 1 ms | 0 à 1 ms | **0** |
| 5b. LM coupé entre deux remontées, table retirée à chaud | comme 5a, mais table déplacée splunkd en marche, sans restart | 242 ms, puis **14,9 s** à l'intervalle suivant | non mesuré | 4,1 Mo, puis **9,945 Go** (tout) |

Les octets comptés valent 255 par événement : le saut de ligne n'est pas compté.

### Essai 1 : témoin

![Témoin](./img/splunk-lm-reintegration-1-temoin.png)

Au retour du LM : une remontée de 525 ms, puis une seule remontée lourde de 14,8 s, puis le coût
de fond. Tout l'usage de la coupure est compté.

### Essai 2 : restart du peer pendant la coupure

![Restart du peer](./img/splunk-lm-reintegration-2-restart-peer.png)

Le splunkd du peer redémarre alors que le LM est toujours injoignable. Au retour du LM : 16
remontées à 0 ou 1 ms en 15 min, 0 octet compté, table d'usage vide. L'usage en attente, tenu en
mémoire, a disparu avec le processus.

### Essai 3 : 10 Go accumulés, restart, puis nouvelle ingestion

![10 Go puis restart](./img/splunk-lm-reintegration-3-10go-restart.png)

Tout ce qui a été ingéré **avant** le restart (9,98 Go) est purgé. Ce qui est ingéré **après**
(256 Mo, 1 M de sourcetypes) est remonté et compté normalement, avec son propre coût : 14,5 s,
comme au témoin. Le pic au retour ne dépend donc que de ce que le peer a ingéré depuis son
dernier démarrage.

### Essai 4a : restart avec la table conservée

![Table conservée](./img/splunk-lm-reintegration-4a-table-conservee.png)

Au démarrage, le peer relit sa table de 33 Mo et la remonte aussitôt. Il n'y a pas de pic, et
le compteur ne double pas, mais le coût de fond reprend à 2,6 s par minute. **Redémarrer un peer
ne fait pas disparaître le coût de fond** d'une journée déjà synchronisée.

### Essai 4b : restart avec la table retirée

![Table retirée](./img/splunk-lm-reintegration-4b-table-retiree.png)

Le peer repart avec une table vide et le coût de fond tombe à 0 ms. Mais le pool du LM passe
de 255 Mo à **0 octet** dans la même minute : le LM remplace l'usage du peer par la table que
celui-ci remonte. Ce n'est pas une optimisation, c'est **une altération du comptage de licence**
(usage du jour effacé). À exclure.

### Essai 5a : LM coupé entre deux remontées, puis restart du peer

![LM coupé, restart](./img/splunk-lm-reintegration-5a-lm-coupe-restart.png)

Cas de la panne en pleine collecte : le LM est allumé pendant toute l'ingestion, et il tombe
avant que le peer ait remonté. `report_interval` passe à 15 min pour laisser le temps d'ingérer
10 Go entre deux remontées. Le journal d'accès du LM confirme qu'aucune remontée n'a lieu entre
la fin de l'ingestion et l'arrêt du LM. Le restart du peer (avec retour de l'intervalle par
défaut) purge l'usage en attente : 0 octet compté, aucun pic au retour.

### Essai 5b : LM coupé entre deux remontées, table retirée à chaud

![LM coupé, table retirée](./img/splunk-lm-reintegration-5b-lm-coupe-table-retiree.png)

Même séquence, mais sans restart : la table d'usage est déplacée pendant que splunkd tourne.
Ça ne purge rien. L'usage en attente vit en mémoire, et la table sur disque n'a aucun rôle à
son égard. Deux points à noter :

- la première remontée après l'ingestion (+15 min) ne porte que 4,1 Mo, soit les 16 123
  premiers événements du fichier ;
- la suivante (+30 min) porte tout le reste : 14,9 s de traitement, et 9,945 Go comptés.

Avec un intervalle long, l'usage arrive donc avec un décalage d'un intervalle, sans perte. Le
mécanisme de ce découpage n'est pas établi.

## 4. État de licence du peer pendant la coupure

Relevé après le restart du peer, LM toujours injoignable (essais 2, 3 et 5a) :

- `licenseState=OK`, et `licenser/messages` vide ;
- `last_manager_contact_success_time` **conservé** à travers le restart : il n'est ni remis à
  zéro ni avancé. Le décompte des 72 h repart donc probablement de ce point, et non du
  redémarrage (déduction, non vérifiée sur une coupure longue) ;
- `last_manager_contact_attempt_time` avance : le peer retente dès son démarrage ;
- la recherche fonctionne, et une ingestion faite après le restart est indexée et cherchable ;
- `activeLicenseGroup` est vide et le peer expose un jeu de fonctions par défaut (33 entrées,
  toutes `ENABLED`, contre 39 avec le LM). Le jeu normal revient à la reconnexion.

```bash
# Sur le peer : contact avec le LM et état de licence
curl -sk -u admin "https://localhost:8089/services/licenser/localpeer?output_mode=json" \
  | jq '.entry[0].content | {manager_uri, last_manager_contact_success_time, last_manager_contact_attempt_time}'
curl -sk -u admin "https://localhost:8089/services/server/info?output_mode=json" \
  | jq '.entry[0].content | {licenseState, activeLicenseGroup}'
curl -sk -u admin "https://localhost:8089/services/licenser/messages?output_mode=json" | jq '.entry | length'
```

## 5. Ce qu'on en retient

- **Redémarrer le splunkd du peer juste avant sa reconnexion au LM** purge l'usage accumulé
  pendant la coupure, quel qu'en soit le volume (testé jusqu'à 39 M d'événements). Le LM ne
  voit pas de pic au retour. Ça vaut aussi quand le LM tombe en pleine collecte, avant que le
  peer ait remonté (essai 5a).
- **Retirer la table à chaud ne purge rien** (essai 5b) : seul le restart vide l'usage en
  attente, qui vit en mémoire.
- **Redémarrer au plus près de la reconnexion :** tout ce qui est ingéré entre le restart et le
  retour du LM est remonté normalement.
- **Contrepartie :** l'usage de la coupure n'est jamais compté. À faire valider au regard des
  obligations de licence avant tout usage en production.
- **En cluster d'indexeurs,** ce restart suit la procédure habituelle d'un peer (maintenance
  mode). Non testé ici.
- **Ne pas toucher à la table d'usage sur disque :** la retirer efface l'usage du jour déjà
  compté (essai 4b).
- **Le coût de fond n'est pas traité par un restart :** il dépend de la cardinalité du jour. Les
  leviers restent la réduction du nombre de sourcetypes dès le parsing et, côté peers,
  `[license] report_interval` (de 1 min à 1 h, prévu par `server.conf.spec` pour les grands
  déploiements) pour espacer les remontées. À 15 min, la remontée lourde n'est pas allégée
  (14,9 s pour 1 M de sourcetypes, comme à 1 min), et l'usage arrive avec un intervalle de
  retard (essai 5b). En régime établi, le coût par remontée ne change pas, mais il n'est payé
  qu'une fois par intervalle : 24 remontées de 2,4 à 3,3 s (médiane 2,7 s) en près de 6 h, au
  lieu d'une par minute.

## 6. Mesurer le temps de traitement par client

Le LM trace chaque remontée dans `splunkd_access.log`. Le champ `spent`, extrait nativement
pour `sourcetype=splunkd_access`, donne sa durée de traitement en ms. Un client est identifié
par son IP (`clientip`) ; son nom vient de la résolution DNS inverse, s'il existe un
enregistrement PTR.

Synthèse par client, à lancer sur le LM ou sur une instance qui cherche dans son `_internal`.
Les plus coûteux remontent en tête :

```spl
index=_internal host=<license-manager> sourcetype=splunkd_access
    TERM(/services/masterlm/usage) method=POST uri_path="/services/masterlm/usage"
| stats count AS remontees count(eval(status!=200)) AS echecs
        avg(spent) AS moy_ms perc95(spent) AS p95_ms max(spent) AS max_ms
        sum(spent) AS total_ms latest(_time) AS derniere BY clientip
| lookup dnslookup clientip OUTPUT clienthost
| eval moy_ms=round(moy_ms), total_s=round(total_ms/1000,1),
       etat=case(max_ms>=30000,"TIMEOUT", max_ms>=20000,"PROCHE TIMEOUT", true(),"OK"),
       derniere=strftime(derniere,"%F %T %z")
| sort - total_ms
| table clientip clienthost remontees echecs moy_ms p95_ms max_ms total_s etat derniere
```

- `total_s` est le temps de traitement cumulé que le client a coûté au LM sur la période :
  c'est la colonne qui désigne les peers à forte cardinalité.
- `etat` compare le pire cas aux 30 s du `receive_timeout` par défaut côté peer : au-delà, le
  peer compte la remontée comme échouée.
- Sur le lab, sur 24 h, la recherche rend 30 remontées pour l'unique peer : moyenne 2 710 ms,
  p95 3 258 ms, max 14 944 ms, 81,3 s cumulées.

Évolution dans le temps, une série par client :

```spl
index=_internal host=<license-manager> sourcetype=splunkd_access
    TERM(/services/masterlm/usage) method=POST uri_path="/services/masterlm/usage"
| timechart span=1m max(spent) AS remontee_ms BY clientip
```

Avec un `report_interval` supérieur à 1 min, prendre `span` égal à l'intervalle.

## 7. Limites

- Un seul peer. La concurrence entre peers, cause probable de l'OOM sur un grand parc, n'est
  pas reproduite.
- La grâce de 72 h n'est pas mesurée (coupures de 40 s à 14 min).
- Journée compressée : 1 M de sourcetypes actifs à chaque minute, ce qu'un trafic étalé sur
  24 h ne produit pas forcément.
- À cette cardinalité, `license_usage.log` du LM tourne plus vite qu'il n'est lu (6 fichiers de
  25 Mo) : 663 683 lignes `Usage` lisibles pour 1 M attendues. Les rapports d'usage
  construits sur `license_usage.log` sont alors incomplets.
- Le remplacement du compteur par la table remontée est observé, pas documenté. La remise à
  zéro de la table au changement de jour n'est pas mesurée.
