---
title: Splunk | rest - /services ou /servicesNS, manifeste par type d'information
category: cheat-sheets
tags: [splunk, rest, servicesNS, namespace, acl, inventaire, shc, cheat-sheet]
created: 2026-09-30
---

# Splunk `| rest` : `/services` ou `/servicesNS`, manifeste par type d'information

Tout ce qui suit a été **mesuré** sur Splunk 9.4.6 (SHC de 3 membres, 2 indexeurs en cluster),
avec deux apps témoins, un compte admin et un compte restreint, et pour chaque type cinq objets
de portées différentes : privé, partagé app, global, dans une autre app, privé d'un autre compte.

## L'essentiel (3 minutes)

**1. `/services/` n'est pas « tout ».** `/services/<endpoint>` vaut
`/servicesNS/<compte courant>/search/<endpoint>`. Ni l'app d'où la recherche est lancée, ni l'app
par défaut du compte (`defaultApp`, `default_namespace`) ne changent ce contexte. On y voit donc :
les objets **globaux**, les objets de niveau app de **`search`**, et les objets **privés du compte
dans `search`**. Un objet partagé au niveau app ailleurs que dans `search` est **invisible**.
`/services/` ne sert jamais à inventorier.

**2. `/servicesNS/<owner>/<app>/` fixe la vue.** `-` est un joker.

| Chemin | Ce qui est rendu |
|---|---|
| `/servicesNS/-/-/` | tout ce que le compte peut lire : toutes apps, tous propriétaires, privés des autres comptes compris (pour un admin). **Le seul chemin d'inventaire.** |
| `/servicesNS/-/<app>/` | tout ce qui vit dans `<app>`, privés de tous les comptes compris |
| `/servicesNS/nobody/<app>/` | couche app de `<app>` + objets globaux de toutes les apps ; **aucun privé** |
| `/servicesNS/<user>/<app>/` | la vue de `<user>` dans `<app>` : ses privés + couche app + globaux ; un privé homonyme **masque** l'objet partagé |

**3. Le chemin ne donne aucun droit.** La visibilité suit toujours les ACL du compte qui exécute
la recherche (lecture de l'app et de l'objet). Un compte restreint ne voit ni les apps qu'il ne
peut pas lire, ni les privés des autres, ni les autres utilisateurs, ni les endpoints
`shcluster/*` et `cluster/*` (403, zéro ligne, aucune erreur bloquante).

**4. Le préfixe ne compte que pour les objets de connaissance.** Utilisateurs, rôles, apps, index,
état du serveur et des clusters rendent la même chose sous les cinq formes de chemin.

**5. `| rest` interroge aussi les pairs de recherche.** Sans `splunk_server`, la commande
s'exécute sur l'instance locale **et sur chaque indexeur** : lignes en double, et configuration
des indexeurs mêlée à celle du search head. Toujours `splunk_server=local` pour les objets du
search head ; `splunk_server=<motif>` pour viser des pairs. Un compte sans la capability
`dispatch_rest_to_indexers` est ramené en local, avec un simple message d'avertissement ; s'il
vise les pairs par `splunk_server=<motif>`, il obtient zéro ligne.

**6. `| rest` rend tout ; `curl` s'arrête à 30.** La commande SPL n'a pas de plafond par défaut
(`count=0` implicite). L'API appelée directement rend **30 entrées** par défaut : `count=0` est
obligatoire hors SPL.

**7. Une exception de namespace : le KV store.** Les collections KV store exigent l'utilisateur `nobody`
(`/services/` et `/servicesNS/<user>/` : HTTP 400 ; `| rest` n'affiche que `code=400, Bad
Request`, l'appel direct donne la cause, *Must use user context of 'nobody'*). Utiliser
`/servicesNS/nobody/<app>/` ou `/servicesNS/-/-/`.

**8. Endpoint typé ou `configs/conf-*`.** Les deux rendent les mêmes objets avec les mêmes ACL.
L'endpoint typé ajoute des champs calculés (`next_scheduled_time`, `qualifiedSearch`,
`fields_list`…) ; `configs/conf-<fichier>` rend les clés brutes et **toutes** les stanzas du
fichier (`conf-transforms` = lookups + extractions).

**9. Lire l'origine d'une ligne.** `eai:acl.app`, `eai:acl.sharing` (`user`, `app`, `global`,
`system`) et `eai:acl.owner` disent où vit l'objet ; le chemin du champ `id` porte le namespace
exact (`/servicesNS/nobody/...` ou `/servicesNS/<user>/...`) et départage deux homonymes. Comparer
le chemin, pas l'URL entière : la partie hôte varie selon l'endpoint.

**10. Filtrer côté serveur.** `search="eai:acl.app=my_app"` filtre avant le rapatriement ;
`f=<champ>` ne garde que les champs nommés : ajouter `f=eai:acl` pour conserver les ACL.

Squelette d'inventaire sûr :

```spl
| rest /servicesNS/-/-/<endpoint> splunk_server=local
| table title eai:acl.app eai:acl.sharing eai:acl.owner id
```

## Manifestes par type d'information

### Lookups

| Information | Endpoint |
|---|---|
| Fichiers CSV | `data/lookup-table-files` |
| Définitions (`transforms.conf`) | `data/transforms/lookups` |
| Lookups automatiques (`LOOKUP-` de `props.conf`) | `data/props/lookups` |
| Définitions, clés brutes | `configs/conf-transforms` |

- `/services/` ne rend aucun fichier d'une autre app que `search` : un fichier créé par
  `outputlookup` dans une app est partagé **app** (propriétaire `nobody`), même lancé par un
  compte non admin.
- `eai:data` de `lookup-table-files` donne le **chemin disque** du fichier
  (`.../etc/apps/<app>/lookups/<fichier>` pour un fichier de niveau app).
- `data/transforms/lookups` ajoute `type` et `fields_list` ; `configs/conf-transforms` mélange
  définitions de lookup et transformations d'extraction.
- `data/props/lookups` : un objet par attribut, titre `<stanza> : LOOKUP-<nom>`.

```spl
| rest /servicesNS/-/-/data/lookup-table-files splunk_server=local
| table title eai:acl.app eai:acl.sharing eai:acl.owner eai:data
```

### Recherches sauvegardées et alertes

| Information | Endpoint |
|---|---|
| Recherches, rapports, alertes | `saved/searches` |
| Clés brutes | `configs/conf-savedsearches` |
| Alertes déclenchées | `alerts/fired_alerts` |

- Seul `/servicesNS/-/-/` rend l'ensemble (131 objets contre 8 sous `/services/` sur le banc).
- `saved/searches` ajoute `next_scheduled_time`, `qualifiedSearch`, `is_scheduled`, `actions`,
  `alert_type` ; `conf-savedsearches` rend les clés brutes (`enableSched`, `counttype`,
  `relation`, `quantity`).
- Sans `splunk_server=local`, les indexeurs renvoient leurs propres recherches sauvegardées
  (397 lignes au lieu de 131).

```spl
| rest /servicesNS/-/-/saved/searches splunk_server=local search="is_scheduled=1"
| table title eai:acl.app eai:acl.owner cron_schedule next_scheduled_time
```

### Macros

| Information | Endpoint |
|---|---|
| Macros | `admin/macros` |
| Clés brutes | `configs/conf-macros` |

- `admin/macros` et `configs/conf-macros` rendent exactement les mêmes champs : l'un vaut l'autre.
- `/servicesNS/<user>/<app>/` montre la macro **effective** pour cet utilisateur : un privé
  homonyme masque la version partagée.

### Tableaux de bord et navigation

| Information | Endpoint |
|---|---|
| Vues (Simple XML, Dashboard Studio) | `data/ui/views` |
| Menus de navigation | `data/ui/nav` |

- `eai:data` porte la source XML ; `isDashboard`, `rootNode`, `version` distinguent les types.
- `/servicesNS/nobody/<app>/` inclut les vues **globales** des autres apps : compter par
  `eai:acl.app` avant de conclure qu'une app contient N vues.
- `data/ui/nav` ne rend rien pour une app sans menu propre.

### Extractions de champs, alias, champs calculés

| Information | Endpoint |
|---|---|
| `EXTRACT-` / `REPORT-` | `data/props/extractions` |
| Transformations d'extraction | `data/transforms/extractions` |
| `FIELDALIAS-` | `data/props/fieldaliases` |
| `EVAL-` | `data/props/calcfields` |
| Stanzas `props.conf` complètes | `configs/conf-props` |

- Les endpoints `data/props/*` rendent un objet **par attribut** (`<stanza> : EXTRACT-<nom>`),
  avec `stanza`, `type`, `value`. `configs/conf-props` rend une ligne **par stanza**, attributs
  en colonnes.
- Sous `/services/`, un attribut défini dans une app non exportée n'apparaît pas.

### Types d'événements et tags

| Information | Endpoint |
|---|---|
| Types d'événements | `saved/eventtypes` |
| Tags | `saved/fvtags` (titre `<champ>=<valeur>`, ex. `eventtype=<nom>`) |

### Collections KV store

| Information | Endpoint |
|---|---|
| Définitions de collections | `storage/collections/config` |

- `/services/` et `/servicesNS/<user>/...` : **HTTP 400**, zéro ligne ; `| rest` affiche
  seulement `code=400, Bad Request`. Utiliser `nobody` ou `-/-`.
- Conséquence de l'obligation de `nobody` : pas de collection privée, une collection est de
  niveau app ou globale.

### Utilisateurs, rôles, capabilities

| Information | Endpoint |
|---|---|
| Comptes | `authentication/users` |
| Compte courant | `authentication/current-context` |
| Rôles | `authorization/roles` |
| Capabilities existantes | `authorization/capabilities` |

- Le chemin est indifférent. Le compte restreint ne voit **que lui-même** et **ses** rôles.
- Sans `splunk_server=local`, chaque indexeur ajoute ses comptes locaux.

### Apps

| Information | Endpoint |
|---|---|
| Apps installées | `apps/local` |

- Le chemin est indifférent ; une app non lisible par le compte est absente de la liste.
- Sur un SHC, sans `splunk_server=local`, les indexeurs ajoutent leurs propres apps.

### Index

| Information | Endpoint |
|---|---|
| Index et volumétrie | `data/indexes` |

- Sur un search head, `data/indexes` décrit **ses** index locaux, pas les données : la volumétrie
  réelle se lit sur les pairs (`splunk_server=<motif des indexeurs>`).
- Le compte restreint voit **tous** les index de la liste, y compris ceux qu'il ne peut pas
  chercher (`_audit`, `_internal`) : la liste n'est pas un contrôle d'accès aux données.
- Les index **metrics** sont exclus par défaut : ajouter `datatype=all` (13 index par défaut
  contre 15 avec `datatype=all` sur le banc).

```spl
| rest /services/data/indexes datatype=all splunk_server=<motif des indexeurs>
| stats sum(currentDBSizeMB) as mb by title
```

### État de l'instance et des clusters

| Information | Endpoint | Où il répond |
|---|---|---|
| Version, rôles, OS | `server/info` | partout |
| Membre SHC courant | `shcluster/member/info` | membres SHC |
| Membres du SHC | `shcluster/member/members` | membres SHC |
| Captain | `shcluster/captain/info` | membres SHC |
| État du SHC | `shcluster/status` | membres SHC |
| Génération et pairs vus du SH | `cluster/searchhead/generation` | search heads |
| Configuration de clustering | `cluster/config` | partout |
| Pairs de recherche | `search/distributed/peers` | search heads |

- Le chemin est indifférent. Admin requis, sauf pour `server/info` : sur les autres, le compte
  restreint reçoit 403 et zéro ligne.
- `shcluster/*` interrogé sans `splunk_server=local` : les indexeurs répondent 503, seule la ligne
  du membre local reste.
- `cluster/manager/*` n'est **pas** joignable par `| rest` depuis un search head (503 partout) :
  le cluster manager n'est pas un pair de recherche. L'interroger directement, ou via une console
  de supervision qui l'a en pair.

## Pièges fréquents

- **Inventaire faux par `/services/`** : il ne montre que `search` et les globaux. Toujours
  `/servicesNS/-/-/`.
- **Doublons silencieux** : oublier `splunk_server=local` multiplie les lignes par le nombre de
  pairs et mêle leur configuration.
- **Homonymes** : un objet privé et un objet partagé de même nom coexistent ; `-/-` rend les deux,
  seul `id` les distingue.
- **Recherche lancée dans une app absente des pairs** : juste après le déploiement d'une app, les
  pairs répondent *Application does not exist* tant que le bundle ne l'a pas encore portée ;
  `splunk_server=local` évite la question.
- **Écrire une ACL par le mauvais namespace** : après passage en `sharing=app`, l'objet vit sous
  `nobody`. Un `POST .../servicesNS/<user>/<app>/<endpoint>` du même nom **crée un second objet
  privé** au lieu de modifier le premier, et un `POST .../acl` par ce chemin répond 409
  *Cannot overwrite existing app object*.
- **`f=` est une liste blanche** : `f=title` seul fait disparaître les ACL ; ajouter `f=eai:acl`,
  ou filtrer par `| fields` après la commande.

## Voir aussi

- [Splunk RBAC (rôles & héritage)](./splunk-rbac.md) : capabilities, dont celles qui ouvrent la
  lecture des objets.
- [Splunk : nettoyer une configuration locale](./splunk-nettoyage-config-locale.md) : `removable`,
  couches `default`/`local`.
- [Splunk Lookup Editor : API REST](./splunk-lookup-editor-api.md) : écrire une lookup par API.
