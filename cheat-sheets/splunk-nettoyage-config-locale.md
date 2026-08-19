---
title: Splunk — nettoyer une configuration locale (REST, purge, suppression, reload)
category: cheat-sheets
tags: [splunk, rest-api, configuration, local, purge, reload, acl, metadata, cheat-sheet]
created: 2026-08-14
---

# Splunk — nettoyer une configuration locale — Cheat-sheet

> **Version** : établi empiriquement sur **Splunk Enterprise 9.4.6**, instance
> **standalone**, onze familles de configuration et trois chemins d'écriture REST.
> **Le comportement en search head cluster n'a pas été mesuré** et n'est pas
> inféré ici : la propagation d'une suppression et l'effet d'un deployer restent
> hors périmètre.

## À quoi ça sert

Retirer une surcharge posée dans `local/` — une clé modifiée, un objet créé, une
ACL — paraît trivial et ne l'est pas. L'API REST **ne sait pas tout nettoyer**, et
surtout **elle ne le signale pas** : elle répond `HTTP 200` à des opérations qui
n'ont rien retiré, parfois en écrivant l'inverse de l'intention. Cette fiche donne
le geste correct par situation, le moyen de savoir à l'avance ce qui va marcher, et
les pièges qui font échouer silencieusement un script de nettoyage.

## 1. Deux gestes, pas un

La confusion la plus coûteuse du sujet : « nettoyer » recouvre deux opérations qui
**ne s'appliquent pas aux mêmes objets**.

| | **Purger une clé** | **Supprimer un objet** |
|---|---|---|
| Objet visé | défini en `default/`, surchargé en `local/` | n'existe **qu'en** `local/` |
| Geste | `POST` de la valeur `default` | `DELETE` |
| Effet | la clé disparaît de `local/`, l'objet retombe sur la couche inférieure | l'objet disparaît |
| Réversible | oui | **non — destructif** |

On purge ce qui existe dessous ; on supprime ce qui n'existe que dessus.

## 2. Décider avant d'agir

Un seul `GET` sur l'objet, **deux signaux à lire** :

```bash
curl -k -u <compte> \
  "https://<host>:8089/servicesNS/nobody/<app>/<handler>/<objet>?output_mode=json"
```

```
DELETE réussira  ⟺  eai:acl.removable == true  ET  lien "remove" exposé
```

Les deux sont **orthogonaux** : `removable` décrit l'objet au regard de ses couches,
le lien `remove` décrit ce que le handler sait faire. Un objet peut annoncer
`removable=true` et résister parce que son handler n'expose pas `remove` ; un autre
peut exposer le lien et échouer parce qu'il est `removable=false`.

**`removable=false` a deux causes suffisantes et indépendantes** — l'une **ou**
l'autre suffit :

1. la **définition** de l'objet existe dans une couche `default/<conf>.conf` ;
2. une **stanza `.meta` à son nom** existe dans `default.meta`.

> **Décider ≠ diagnostiquer.** `removable` dit *si* le `DELETE` passera, jamais
> **laquelle** des deux causes bloque — donc jamais quoi corriger. Le diagnostic
> exige la lecture de fichier : `btool --debug` ne suffit pas, il est **aveugle aux
> `.meta`** (il n'existe pas de `btool metadata`).

## 3. Purger une clé — le geste

Contre-intuitif : **ce n'est pas `DELETE`, c'est `POST`.**

```bash
# 1. relever la valeur exacte servie par la couche default
splunk btool <conf> list <stanza> --debug | grep <cle>

# 2. la reposter : la cle disparait de local/
curl -k -X POST "https://<host>:8089/servicesNS/nobody/<app>/<handler>/<objet>" \
     -d "<cle>=<valeur-default-exacte>"
```

**Mécanisme** : splunkd compare la valeur postée aux couches inférieures et n'écrit
en `local/` que ce qui en **diffère**. Poster une valeur identique au `default`
revient à écrire « rien ».

Trois propriétés vérifiées : la clé disparaît réellement, les autres clés de la
stanza survivent, et **modifier ensuite le `default/` fait suivre la valeur
servie** — c'est une purge, pas un gel.

## 4. Ce qui purge, et ce qui ne purge pas

**La purge est portée par le handler, pas par le moteur de configuration.** Sur onze
familles mesurées, **quatre purgent, par cinq handlers** :

| Famille | Handler qui purge |
|---|---|
| `savedsearches` | `saved/searches` |
| `transforms` | `data/transforms/extractions` **et** `data/transforms/lookups` |
| `workflow_actions` | `data/ui/workflow-actions` |
| `datamodels` | `datamodel/model` — **clés `.conf` seulement**, pas la charge utile JSON |

**Sept familles ne purgent par aucune méthode** : `eventtypes`, `tags`, `props`,
`alert_actions`, `data/ui/views`, `data/ui/nav`, et **tout `.conf` sans handler
dédié**. Elles répondent `HTTP 200` **en réécrivant** la valeur postée.

Les trois chemins d'écriture REST ne se valent pas :

| Chemin | Purge ? | Supprime ? |
|---|---|---|
| **Handler dédié** | oui, sur 4 familles | oui, si l'objet est purement local |
| **`configs/conf-<nom>`** — couverture universelle | **jamais** | oui, si l'objet est purement local |
| **`properties/<conf>/<stanza>`** | **jamais** | non (`Key deletion is not supported`) |

> **Couverture universelle et capacité de purge sont incompatibles par REST** : le
> seul chemin qui couvre tout ne purge rien. C'est la limite structurante de toute
> automatisation fondée sur l'API.

**Rien de ce qui n'est pas une clé de `.conf` n'est purgeable.** Reposter le contenu
exact de `default/` pour un data model (JSON) **crée** le fichier `local/` même
absent ; pour une vue ou une nav (XML), il **laisse en place** l'existant.

`alert_actions` n'a **aucune suppression REST**, ni création : le refus est au niveau
du handler.

## 5. Les ACL — fermées par REST

**Aucun chemin REST ne retire une stanza d'ACL d'un `local.meta`** : douze candidats
épuisés (`DELETE` sur l'objet, sur la famille, sur l'ACL d'app ; arguments `remove`,
`delete`, `reset`, `inherit`, `restore`, `remove_stanza`…), sur les trois
granularités — stanza de même nom dans les deux couches, entête de famille en
`default.meta` avec stanza fine en `local.meta`, stanza uniquement locale. Le
redémarrage ne purge pas non plus les stanzas redondantes.

> **Le piège que le geste fabrique** : poster des permissions **égales à celles du
> `default`** — le geste qui *purge* un `.conf` — **gèle** un `.meta`. La stanza est
> réécrite, pas retirée ; la valeur servie devient celle du `default` et **rien dans
> REST ne distingue ce gel d'un héritage réel**.

Le sort d'une ACL après suppression de son objet dépend de sa couche :

| ACL portée par | Après suppression | Objet recréé du même nom |
|---|---|---|
| `local.meta` | disparaît avec l'objet | revient à l'**héritage** |
| `default.meta` | **survit** | **hérite de l'ACL orpheline** et **devient non supprimable** |

## 6. L'alternative : éditer le fichier, puis recharger

Là où REST bute, l'édition directe suivie d'un rechargement passe — **y compris pour
les ACL**, que l'API ne sait pas retirer.

| Configuration | Rechargeable à chaud ? | Appel |
|---|---|---|
| `savedsearches`, `macros`, `props`, `transforms`, `eventtypes`, `tags`, `alert_actions`, `data/ui/views`, `indexes` | **oui** | `_reload` du **handler dédié** |
| **`metadata` (`.meta`)** | **oui** | `_reload` du **handler de la famille** qu'ils gouvernent |
| **`authorize.conf`, `web.conf`** | **non** | **redémarrage obligatoire** |

Le retrait fonctionne partout où le rechargement fonctionne : l'objet retombe sur
`default/`, l'objet purement local disparaît en `404`.

**Trois mécanismes, à ne pas confondre** :

| Mécanisme | Où | Ce qu'il fait |
|---|---|---|
| **`_reload` par handler** | splunkd (`:8089`) | Recharge la famille — **le seul à utiliser pour du nettoyage** |
| **`debug/refresh`** | **SplunkWeb** (`:8089` rend `404`) | Sans argument, rafraîchit toutes les entités **et dit ce qu'il a fait**. **N'ajoute aucune couverture** |
| **`_bump`** | **SplunkWeb** | Expire le cache d'**assets statiques**. **Ne recharge aucune configuration** |

**Après rechargement, aucune divergence entre vues** : handler dédié,
`configs/conf-*`, `properties/`, `btool` et le comportement réel s'accordent.
**Avant** rechargement, `btool` diverge des autres — c'est le **signal d'un
rechargement en attente**, et un contrôle exploitable.

> **Réserve majeure en search head cluster** : une écriture directe dans un fichier
> **n'est pas répliquée** entre membres — le cluster ne propage que ce qui passe par
> splunkd. Cette voie crée donc une divergence silencieuse si elle est appliquée au
> `local/` des membres. Non mesuré, mais structurant.

## 7. Les pièges — le cœur de la fiche

| # | Piège | Règle |
|---|---|---|
| **1** | **`DELETE` non idempotent selon le namespace** — deux appels identiques suppriment **deux objets différents**, `200` chacun. Entre les deux, le `GET` de contrôle répond `200` (retombée sur la couche inférieure), ce qui **se lit comme un échec et invite au rejeu destructeur** | **Ne jamais rejouer un `DELETE`** sur la foi d'un `GET`. Résoudre le namespace explicitement |
| **2** | **`configs/conf-<x>/_reload` répond `200` pour tout** — y compris les familles qui exigent un redémarrage, **et pour une configuration qui n'existe pas** | **Toujours le `_reload` du handler dédié**, dont le `404` est informatif |
| **3** | **`POST` sur `saved/eventtypes` désactive tous les tags** de l'eventtype, sans qu'aucun argument `tag` ne soit fourni | Traiter les tags séparément et contrôler après coup |
| **4** | **`DELETE /properties/<conf>/<stanza>`** répond `200` + *« Successfully modified 1 key(s) »* **sans rien supprimer** : il **ajoute `disabled = true`** | Ne jamais l'employer comme mécanisme de retrait |
| **5** | **Poster une valeur vide** sur une clé dont le `default` est non vide **masque** ce `default` et le fait disparaître de `btool` | Poster la **valeur `default`**, jamais une valeur vide |
| **6** | **Le `DELETE` vide le fichier `local/`** au lieu de le supprimer (0 octet, répertoire conservé) | **La présence d'un fichier `local/` ne prouve aucune surcharge** — lire le contenu |
| **7** | **Une stanza posée à la main est invisible par REST avant rechargement**, alors que `btool` la sert immédiatement | L'écart entre les deux vues **est** le signal de dérive |
| **8** | Le segment `<owner>` de l'URI **choisit le fichier écrit** : avec un compte nommé, l'écriture atterrit dans un `local.meta` **privé**, en `200` silencieux | Imposer `nobody` en dur dans le namespace |

## 8. Prouver qu'on a nettoyé

**Aucun moyen par REST.** Le code HTTP ment ; le `GET` de contrôle ne distingue pas
une purge d'une réécriture, puisque dans les deux cas la valeur servie est celle du
`default` ; et `_configtracker` **ne distingue pas une clé retirée d'une clé mise à
vide** — les deux ressortent en `new_value: ""`.

**La seule preuve est la relecture du fichier `local/<conf>.conf`.** Toute
automatisation qui prétend garantir une purge sans accès au filesystem promet ce
qu'elle ne peut pas tenir.

Pour tracer **qui** a fait quoi, les deux index sont complémentaires et **disjoints** :

| Index | Porte | Ne porte pas |
|---|---|---|
| `_audit` | l'utilisateur, l'action, l'issue, **les refus** | le chemin de fichier |
| `_configtracker` | le chemin, la stanza, le diff, **les dérives posées à la main** | l'utilisateur |

La jointure temporelle se fait **à ± 3 s**, pas à la seconde : la suppression d'un
objet **privé** décale `_configtracker` d'environ 2 secondes derrière `_audit`, là où
un objet partagé tient en quelques millisecondes. Un `bin span=1s` casse le couple.

## 9. Mémo — quel geste pour quelle situation

| Situation | Geste |
|---|---|
| Rendre une clé à sa valeur d'origine (4 familles purgeables) | `POST` de la valeur `default` sur le **handler dédié** |
| Supprimer un objet purement local | `DELETE` — **une seule fois** |
| Savoir lequel des deux | `GET` : `removable=true` **et** lien `remove` |
| ACL, familles non purgeables, JSON/XML | **Édition du fichier** + `_reload` du handler dédié |
| Vérifier le résultat | **Relire le fichier** |
| `authorize.conf` / `authentication.conf` | Édition + **redémarrage** — aucun rechargement à chaud |

## Sources

- `docs.splunk.com` — REST API Reference (`configs/conf-*`, `properties/`, endpoints
  `_reload`), *About configuration files* (précédence des couches), *Manage
  configuration file changes*.
- Spécifications locales : `authorize.conf.spec`, `restmap.conf.spec`,
  `metadata`/`.meta` (précédence `default.meta` / `local.meta`).
- Comportements de cette fiche : **mesurés sur 9.4.6**, chaque verdict adossé à une
  preuve fonctionnelle (comportement observé) et non à un code de retour.
