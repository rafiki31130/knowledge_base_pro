---
title: n8n
category: cheat-sheets
tags: [n8n, automatisation, workflow, no-code, webhook, cheat-sheet]
created: 2026-07-06
---

# n8n — Cheat-sheet

## À quoi ça sert

n8n automatise des **workflows** en reliant visuellement des services : un
déclencheur (webhook, cron…) lance une suite de nœuds qui appellent des API,
transforment des données, écrivent en base, notifient. Cette fiche couvre
l'**usage courant** — syntaxe des expressions, nœuds clés, déploiement Docker
self-hosted, CLI et patterns fréquents. Pour comprendre *comment les données
circulent* (items, exécution par item, credentials) →
[fiche conceptuelle n8n](../concepts/n8n-modele-mental.md).

## Expressions (`{{ }}`)

Tout champ peut passer en mode *Expression* : du JavaScript évalué à l'exécution.

```javascript
{{ $json.email }}                       // champ de l'item courant
{{ $json.user.name }}                   // accès imbriqué
{{ $json["clé avec espace"] }}          // clé non-identifiant → crochets
{{ $json.total * 1.2 }}                 // calcul
{{ $json.nom ?? "inconnu" }}            // valeur par défaut si null/undefined
{{ $json.tags.join(", ") }}             // méthodes JS standard dispo
```

Variables de contexte les plus utilisées :

```javascript
{{ $json }}                    // JSON de l'item courant (entrée du nœud)
{{ $input.all() }}             // tous les items entrants (tableau)
{{ $input.first().json.id }}   // premier item entrant
{{ $('Webhook').item.json.x }} // sortie d'un AUTRE nœud, item lié à l'item courant
{{ $('Set').all() }}           // tous les items d'un nœud nommé
{{ $itemIndex }}               // index de l'item courant (0-based)
{{ $runIndex }}                // n° d'itération (boucles)
{{ $execution.id }}            // id de l'exécution en cours
{{ $workflow.name }}           // nom du workflow
{{ $env.MA_VAR }}              // variable d'environnement (si autorisée)
```

Dates (objet Luxon `DateTime`, pas une string) :

```javascript
{{ $now.toISO() }}                         // 2026-07-06T12:34:56.000+02:00
{{ $now.toFormat('yyyy-LL-dd') }}          // 2026-07-06
{{ $now.minus({ days: 7 }).toISO() }}      // il y a 7 jours
{{ $today }}                               // minuit aujourd'hui
{{ DateTime.fromISO($json.date).toFormat('dd/LL/yyyy') }}
```

> Piège : `$json.date` est souvent une **string**. Pour la manipuler comme date,
> la parser (`DateTime.fromISO(...)`), ne pas concaténer bêtement.

## Nœuds à connaître (le noyau)

| Nœud | Rôle |
|---|---|
| **Manual Trigger** | lancer à la main pour tester |
| **Schedule Trigger** | déclenchement récurrent (cron / interval) |
| **Webhook** | reçoit une requête HTTP entrante (URL test + prod) |
| **HTTP Request** | appelle une API sortante (le couteau suisse) |
| **Set / Edit Fields** | définir / renommer / nettoyer des champs |
| **IF** | brancher en deux (true / false) selon une condition |
| **Switch** | brancher en N selon une valeur |
| **Filter** | ne laisser passer que les items qui matchent |
| **Merge** | recombiner deux branches (append, merge par clé…) |
| **Split Out** | éclater un tableau en plusieurs items |
| **Aggregate** | regrouper plusieurs items en un seul |
| **Loop Over Items (Split in Batches)** | traiter par lots |
| **Code** | JavaScript/Python arbitraire quand un nœud ne suffit pas |
| **Execute Workflow** | appeler un sous-workflow (réutilisation) |
| **NoOp** | ne rien faire (utile comme point de jonction / fin de branche) |

### Nœud Code (échappatoire quand aucun nœud ne convient)

```javascript
// Mode "Run Once for All Items" : reçoit tous les items, retourne un tableau
const items = $input.all();
return items.map(i => ({
  json: { id: i.json.id, nomMaj: i.json.nom.toUpperCase() }
}));
```

```javascript
// Mode "Run Once for Each Item" : $json = item courant
return { json: { ...$json, traite: true } };
```

## Webhook — l'essentiel

- **Deux URL** : `/webhook-test/...` (écoute un seul appel quand l'éditeur est
  ouvert, pour tester) et `/webhook/...` (**production**, active en permanence
  **seulement si le workflow est Active**).
- Répondre au caller : nœud **Respond to Webhook** (sinon réponse par défaut).
- Récupérer le contenu entrant dans les nœuds suivants :

```javascript
{{ $json.body }}      // corps de la requête (POST JSON)
{{ $json.query }}     // paramètres d'URL (?a=1)
{{ $json.headers }}   // en-têtes HTTP
```

Test rapide en ligne de commande :

```bash
curl -X POST https://n8n.example.com/webhook/mon-hook \
  -H "Content-Type: application/json" \
  -d '{"nom":"Alice","action":"create"}'
```

## Déploiement self-hosted (Docker)

Lancement minimal (données en volume nommé) :

```bash
docker run -d --name n8n \
  -p 5678:5678 \
  -e GENERIC_TIMEZONE="Europe/Paris" \
  -e N8N_ENCRYPTION_KEY="<clé-longue-aléatoire-à-sauvegarder>" \
  -v n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

Docker Compose (patron typique avec base Postgres) :

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=n8n.example.com
      - N8N_PROTOCOL=https
      - WEBHOOK_URL=https://n8n.example.com/   # indispensable derrière un reverse-proxy
      - GENERIC_TIMEZONE=Europe/Paris
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n
      - DB_POSTGRESDB_PASSWORD=${DB_PASSWORD}
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      - postgres
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  n8n_data:
  pg_data:
```

Variables d'environnement courantes :

```bash
N8N_ENCRYPTION_KEY   # chiffre les credentials — À SAUVEGARDER (perte = credentials illisibles)
WEBHOOK_URL          # URL publique ; obligatoire derrière un reverse-proxy pour des webhooks corrects
N8N_HOST / N8N_PROTOCOL / N8N_PORT
GENERIC_TIMEZONE     # fuseau pour les Schedule Trigger et $now
DB_TYPE=postgresdb   # base externe recommandée en prod (défaut = SQLite)
N8N_BASIC_AUTH_ACTIVE / _USER / _PASSWORD   # auth simple (anciennes versions)
N8N_SECURE_COOKIE=false   # seulement en HTTP local, jamais en prod
```

## CLI (`n8n`)

Dans le conteneur (`docker exec -it n8n n8n <cmd>`) ou en install locale :

```bash
n8n start                                  # démarrer l'instance
n8n export:workflow --all --output=./wf/   # exporter tous les workflows en JSON
n8n export:workflow --id=42 --output=w.json
n8n import:workflow --input=w.json         # importer un workflow
n8n export:credentials --all --decrypted --output=creds.json  # SENSIBLE (secrets en clair)
n8n import:credentials --input=creds.json
n8n execute --id=42                         # exécuter un workflow en CLI (batch/cron)
n8n update:workflow --id=42 --active=true   # activer/désactiver
n8n user-management:reset                   # réinitialiser l'accès owner (dépannage)
```

> `export:credentials --decrypted` écrit les **secrets en clair** : fichier à
> traiter comme un secret, ne jamais committer.

## Debug — le réflexe

1. Ouvrir l'onglet **Executions** du workflow.
2. Cliquer l'exécution (souvent la dernière en erreur).
3. Lire la **sortie réelle de chaque nœud** : c'est là que l'expression cassée ou
   la structure inattendue devient visible.
4. Rejouer avec **Retry** / *Copy to editor* une fois corrigé.

Bonnes pratiques fiabilité :

```
Settings du workflow → Error Workflow   : router les échecs vers une notif
Réglage d'un nœud → "Continue On Fail"  : ne pas stopper tout le workflow sur une erreur
Réglage d'un nœud → "Retry On Fail"     : relancer N fois avant d'échouer
```

## Pièges fréquents

| Symptôme | Cause probable | Réflexe |
|---|---|---|
| Le nœud « tourne plusieurs fois » | plusieurs **items** en entrée (1 exécution / item) | agréger/filtrer en amont ; c'est le modèle, pas un bug |
| Expression → `undefined` | chemin `$json.x` ≠ structure réelle | lire la vraie sortie du nœud amont dans l'**execution** |
| Webhook muet en prod | workflow non **Active**, ou URL **test** au lieu de **prod** | activer le workflow, utiliser `/webhook/...` |
| Webhooks cassés derrière proxy | `WEBHOOK_URL` non défini | fixer `WEBHOOK_URL=https://domaine/` |
| Credentials illisibles après restore | `N8N_ENCRYPTION_KEY` différente/perdue | restaurer **la même** clé de chiffrement |
| Données perdues au redéploiement | pas de volume sur `/home/node/.n8n` (+ SQLite par défaut) | volume persistant, Postgres externe en prod |
| Date qui s'affiche mal / calcul faux | `$json.date` est une **string** | parser via `DateTime.fromISO(...)` |
| Secret visible dans un champ | mis en dur dans le nœud | déplacer dans une **credential** |
| `$now` décalé | mauvais `GENERIC_TIMEZONE` | fixer le fuseau au niveau instance |

## Voir aussi

- [Fiche conceptuelle n8n](../concepts/n8n-modele-mental.md) — items, exécution par item, credentials, executions (le *pourquoi*).
- [Docker](./docker.md) — exploitation des conteneurs pour le self-hosted.
- [HAProxy & TLS](./haproxy-tls.md) — publier n8n derrière un reverse-proxy TLS.
- [Secrets & SSH](./secrets-ssh.md) — gérer clés et secrets autour de l'instance.
