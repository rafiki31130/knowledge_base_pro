---
title: Splunk Lookup Editor - API REST
category: cheat-sheets
tags: [splunk, lookup, lookup-editor, rest, rbac, shc, cheat-sheet]
created: 2026-09-26
---

# Splunk Lookup Editor : ajouter, modifier, supprimer une lookup CSV par API REST

## À quoi ça sert

Piloter des lookups CSV depuis l'extérieur de Splunk (script, n8n, CI) sans accès disque
au search head, via l'API de l'add-on *Splunk App for Lookup File Editing* (`lookup_editor`).
L'add-on reçoit le contenu en JSON, écrit le fichier dans la zone de staging, puis appelle
l'endpoint natif `data/lookup-table-files` avec la session de l'appelant. En SHC, la lookup
est répliquée aux autres membres (moins de 10 s mesurées).

Mesuré sur Splunk 9.4.6 (SHC 3 membres), Lookup Editor 4.0.8, compte local authentifié par
jeton.

## Commandes de base

Variables communes :

```bash
SH=https://sh-01.example.com:8089
AUTH="Authorization: Bearer <token>"
APP=my_app          # app qui porte la lookup (namespace)
```

Toutes les requêtes `lookup_edit` sont des **POST en `application/x-www-form-urlencoded`**.
Un corps JSON ou multipart est refusé (403 ou 500). `contents` est une chaîne JSON :
tableau de lignes, **en-tête en première ligne**.

```bash
# Test de l'endpoint
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/ping          # -> Online

# AJOUTER : isNew=true refuse d'écraser une lookup existante (409)
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/lookup_contents \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv -d isNew=true \
  --data-urlencode 'contents=[["host","owner"],["srv01","team-a"]]'

# LIRE (renvoie le même format tableau de tableaux)
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/lookup_data \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv

# MODIFIER : remplacement COMPLET du fichier (pas de mise à jour partielle)
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/lookup_contents \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv \
  --data-urlencode 'contents=[["host","owner"],["srv01","team-b"],["srv02","team-a"]]'

# SUPPRIMER : l'add-on n'a pas d'endpoint de suppression -> endpoint natif
curl -sk -H "$AUTH" -X DELETE \
  $SH/servicesNS/nobody/$APP/data/lookup-table-files/assets.csv
```

Modifier une ligne = **lire, modifier, réécrire** le tableau entier.

`owner=nobody` crée une lookup de niveau app ; `owner=<compte appelant>` crée une lookup
privée (`etc/users/<compte>/<app>/lookups/`).

Sauvegardes (voir pièges avant de s'y fier) :

```bash
# Créer une sauvegarde : file_time doit contenir une décimale
curl -sk -H "$AUTH" $SH/services/data/lookup_backup/backup \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv -d file_time=$(date +%s).0
# Lister, puis lire une version
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/lookup_backups \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv
curl -sk -H "$AUTH" $SH/services/data/lookup_edit/lookup_data \
  -d namespace=$APP -d owner=nobody -d lookup_file=assets.csv -d version=<time>
```

## Droits indispensables

Rôle dédié sans héritage, app dédiée. Mesures faites en retirant un droit à la fois.

| Action | Capability | Droit sur l'app | Droit sur l'objet lookup |
|---|---|---|---|
| Lire | aucune | read | read |
| Ajouter (`owner=nobody`) | `upload_lookup_files` | **write** | - |
| Ajouter une lookup privée | `upload_lookup_files` | read | - |
| Modifier | `upload_lookup_files` | read | **write**, ou être owner de l'objet |
| Supprimer (`DELETE` natif) | aucune | **write** | ignoré |
| Sauvegarder / lister les versions | aucune | read | read |

Minimum pratique pour un compte de service : **`upload_lookup_files` + read/write sur l'app
dédiée**. Rien à accorder sur l'app `lookup_editor` elle-même : le handler exige seulement
l'authentification, et ce sont les ACL splunkd des appels internes qui tranchent.

Un rôle créé « vide » hérite quand même du stanza `[default]` d'`authorize.conf`
(`edit_own_objects`, `list_all_objects`, `run_collect`, `run_mcollect`,
`schedule_rtsearch`). Voir [Splunk RBAC](./splunk-rbac.md).

## Pièges fréquents

- **200 ne veut pas dire écrit.** Une création peut répondre `200` avec la charge `None`
  sans rien écrire (owner d'un autre utilisateur). Toujours relire (`lookup_data`) après
  une écriture.
- **Le droit de suppression est celui de l'app, pas de l'objet.** Avec write sur l'app, le
  compte supprime une lookup même si son ACL réserve l'écriture à `admin`. Avec read seul
  sur l'app, la suppression échoue (400 « cannot be deleted ») même si l'objet donne write
  au rôle. Ne pas donner write sur une app partagée à un compte d'automatisation.
- **L'owner piège la révocation.** Une lookup créée par le compte avec `owner=nobody` est
  enregistrée avec **owner = le compte** (sharing app). Il garde l'écriture même après
  retrait du write sur l'app. Réassigner après création :
  `POST .../data/lookup-table-files/<f>/acl` avec `sharing=app owner=nobody`.
- **Pas de mise à jour partielle** : chaque `lookup_contents` remplace le fichier entier.
  Deux écritures concurrentes : la dernière gagne.
- **Sauvegardes non fiables en SHC.** `backup=true` sur `lookup_contents` échoue en
  interne (500 côté splunkd) et l'écriture continue **sans** sauvegarde, sans erreur
  remontée. L'appel direct à `lookup_backup/backup` fonctionne mais la sauvegarde reste sur
  le membre appelé : `version=` renvoie 404 sur les autres.
- **`file_time` sans décimale est ignoré** (regex `[0-9]+\.[0-9]+`) : la sauvegarde prend
  alors un autre horodatage.
- **Lecture plafonnée à 10 Mo** (`MAXIMUM_EDITABLE_SIZE`), extension `.csv` obligatoire
  (403 sinon).
- **Appel de réplication en 403.** L'add-on appelle `replication/configuration/lookup-update-notify`,
  refusé pour un compte non admin ; l'erreur est avalée et la réplication SHC a lieu quand
  même via `lookup-table-files`.
- **`expires_on` à la création du jeton** : `+7d` et un epoch ont été refusés sur 9.4.6 ;
  sans paramètre, l'expiration par défaut de `tokens_auth` s'applique.
- **Tracer ce que fait l'add-on** : `index=_internal sourcetype=splunkd_access <compte>`
  montre les appels internes faits avec la session de l'appelant et leur code retour.

## Voir aussi

- [Intégration n8n](./n8n-splunk-lookup-editor.md) : piloter ces appels depuis un workflow n8n.
- [Splunk RBAC (rôles & héritage)](./splunk-rbac.md) : capabilities, stanza `[default]`.
- [Splunk (administration / CLI)](./splunk-admin.md) : `btool`, `_internal`.
