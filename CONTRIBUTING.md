# Règles de contribution

Ce dépôt est une **base de connaissances publiable**. Les règles ci-dessous
existent pour qu'il le reste, quel que soit le contributeur (humain ou
assistant).

## Principe directeur

> Si on ne pourrait pas publier la page sur un blog public, elle ne va pas ici.

En cas de doute : **anonymiser ou ne pas écrire**.

## Interdits explicites

- Noms d'environnements, de projets internes, de clients.
- Noms d'hôtes, de clusters, de sites, de zones réseau réels.
- IP, sous-réseaux, FQDN, URL internes.
- Comptes, identifiants, tokens, clés, hashs, mots de passe (même expirés).
- Chemins de fichiers contenant un identifiant interne.
- Captures d'écran non floutées.
- Références à des incidents, tickets, RUN, plannings, livrables clients.
- Détails d'architecture permettant d'identifier une infrastructure réelle.

## Bonnes pratiques

- Préférer des valeurs **génériques** : `indexer-01`, `10.0.0.0/24`,
  `example.com`, `user01`, `<tenant>`, `<region>`.
- Décrire des **principes** et des **patterns**, pas des configurations exactes
  copiées depuis un environnement.
- Pour une recherche / requête : montrer la **forme**, expliquer les champs,
  laisser les valeurs en placeholders.
- Citer ses sources officielles (docs vendeur, RFC, CVE…) quand pertinent.

## Style

- Markdown, une idée par fichier, titre H1 unique par page.
- Liens relatifs entre pages du dépôt.
- Blocs de code annotés (` ```spl `, ` ```bash `, etc.).
- Français par défaut ; anglais accepté pour un sujet déjà cadré en anglais.

## Workflow

- Commit direct sur `main`, pas de PR ni de revue obligatoire.
- Un commit = un sujet cohérent quand c'est possible.
- Si une page existante mélange du sensible et du générique, la corriger
  immédiatement (réécriture, pas seulement suppression — l'historique reste).

## Si du sensible a été commité par erreur

1. Réécrire la page pour purger le contenu.
2. Considérer que la donnée est **compromise** — la traiter comme telle dans
   l'environnement concerné (rotation, etc.).
3. Le simple `git revert` ne suffit pas : l'historique public garde la trace.
   Faire remonter pour décider d'une réécriture d'historique si nécessaire.
