---
name: obsidian-notes
description: Interagir avec le vault Obsidian de l'utilisateur via le serveur MCP — lire, écrire, retrouver et capitaliser tout type de note (pages libres, projets, fleeting notes, tâches, checklists, listes `#list/`, logs et journal). Déclenche ce skill dès que l'utilisateur demande de noter, consigner, capturer, mettre à jour, retrouver ou synthétiser quelque chose dans ses notes / son vault / Obsidian, y compris implicitement ("mets ça dans la note", "on en est où sur X", "ajoute une tâche", "note cette idée", "ajoute ça à ma liste", "qu'est-ce que j'ai sur Y"), et aussi quand une conversation produit des décisions ou des informations durables qui mériteraient d'être écrites quelque part. À utiliser avant toute lecture ou écriture dans le vault pour choisir le bon objet, le bon outil et le bon emplacement.
---

# Vault Obsidian via MCP

Vault à schéma contraint, synchronisé en continu par LiveSync (desktop + mobile). Les
descriptions des outils MCP couvrent déjà quel outil correspond à quel objet et quels chemins
sont refusés. Ce skill couvre ce qu'elles ne disent pas : **quel objet choisir, avec quelle
granularité, et dans quel ordre opérer pour ne rien écraser**.

Source de vérité du vault : `r_templates/CONVENTIONS.md` (lisible via MCP). En cas de doute
sur une convention non couverte ici, va la lire — mais méfie-toi de sa section MCP, partielle-
ment datée (elle déclare `vault_get_document_map` non supporté alors qu'il fonctionne).

Organisation : partie générale, puis une section autosuffisante par type d'objet.

---

## Partie générale

### Choisir l'objet avant l'outil

La question n'est pas « quel outil appeler » mais « quelle est la nature de cette
information ». Le mauvais objet coûte plus cher que le mauvais outil : une décision noyée dans
un log est perdue, un inventaire éclaté en cinq fleeting notes devient inexploitable.

| Nature de l'information | Objet | Section |
|---|---|---|
| Périmètre, décision, avancement d'un projet | Page projet | [Page projet](#page-projet) |
| Documentation, note de fond hors projet | Page libre | [Page libre](#page-libre) |
| Capture rapide, inventaire, relevé, idée à trier | Fleeting note | [Fleeting note](#fleeting-note) |
| Action à faire, avec suivi ou échéance | Tâche `#Todo` | [Tâche](#tâche) |
| Étapes locales d'une note, sans suivi global | Checklist locale | [Checklist locale](#checklist-locale) |
| Item réutilisable par contexte (courses, matos) | Liste `#list/` | [Liste #list/](#liste-list) |
| Sujet durable sans fin (domaine, pièce, thème) ; « qu'est-ce qu'il reste à faire ici ? » | Page Topic | [Page Topic](#page-topic) |
| Événement daté, observation ponctuelle | Log | [Log du journal](#log-du-journal) |

### Destination par défaut : le journal du jour

Ce vault n'a **pas d'inbox**. Quand aucun hub ne s'impose — pas de projet identifié, note trop
mince pour justifier une page — le journal du jour est le bon endroit par défaut : tâche via
`create_task`, observation via `log_to_daily`, item via `add_to_list`. Une information dans le
journal est datée et retrouvable ; une information nulle part est perdue.

Ne crée pas un projet ou une page uniquement pour « ranger » une phrase.

### Principe hub / satellites

Une page projet est un **hub**, pas un journal. Ce qui s'y écrit doit rester vrai dans six
mois. Le reste vit dans un satellite relié au hub par wikilink `[[Nom de la page]]`. La page
est relue à froid pour reprendre le travail : si elle accumule l'historique de la
conversation, l'information utile s'y noie.

Corollaire : un satellite non relié est un satellite perdu. Fleeting note → `page_path` ;
tâche → `project`.

### Rattachement : `parent`, `topic`, `relations`

Trois propriétés, trois sens distincts. Ne les interchange pas, même quand une vue affiche
le même résultat avec l'une ou l'autre.

| Propriété | Sens | Exemple |
|---|---|---|
| `parent` (ou titre `Parent @ Enfant`) | Hiérarchie structurelle : sous-projet, sous-page | `Travaux @ SDB @ Plafond spots` → parent `Travaux @ SDB` |
| `topic` | Domaine d'appartenance : « où vit ce sujet ». Réponse à « qu'est-ce que j'ai en cours dans ce domaine ? » | Projet SDB → `topic: ["[[Maison]]", "[[Maison @ SalleDeBain]]"]` |
| `relations` | Lien transversal entre deux sujets qui se touchent : à traiter ensemble, achat groupé, impact croisé | Peinture SDB ↔ peinture cage d'escalier ; carrelage SDB ↔ crédence cuisine |

Règles :
- **`topic` liste toujours le Topic enfant ET ses Topics parents** (`[[Maison]]` +
  `[[Maison @ SalleDeBain]]`) : chaque niveau affiche alors le projet dans sa vue
  `Relations.base`.
- **`relations` n'exprime jamais l'appartenance à un domaine.** Pointer un projet vers sa pièce
  via `relations` est une erreur de sens : migre-le vers `topic`. Une relation se pose dans les
  deux sens (les deux projets se citent).
- Contre-exemple : « en peignant la SDB, je toucherai à l'entrée » n'est pas une relation entre
  projets mais un rappel : une ligne de checklist dans le lot concerné, qui renvoie par wikilink
  vers l'item source (écrit à un seul endroit).

Mécanique utile : `Relations.base` (corps des Topics) se fonde sur `topic` ; le bloc dataviewjs
`related-projects` se fonde sur `parent` / nommage `@` et `relations`, pas sur `topic`.

### Séquence de travail

1. **Situer avant d'écrire.** `get_active_projects` donne les projets et leur statut exact —
   ce basename est la clé de `create_task`, `get_project_tasks` et des wikilinks.
   `search_simple` si le nom est incertain, `search_query` pour un filtre sur frontmatter.
2. **Cartographier avant de patcher.** `vault_get_document_map` renvoie headings, block IDs et
   champs de frontmatter sans charger le fichier. C'est la bonne préparation d'un
   `vault_patch` : `vault_read` ramène tout le fichier et devient lent, voire inexploitable,
   sur les pages longues.
3. **Écrire au plus étroit.** Patch ciblé plutôt que réécriture complète.

Le troisième point est la protection principale contre le lost-update : sous LiveSync, un PUT
complet écrase silencieusement une édition faite en parallèle sur le téléphone ou le desktop.
Plus l'écriture est étroite, plus la fenêtre de collision est courte.

### Vérifier avant de créer

Presque tous les outils de création sont non idempotents : rejouer produit un doublon, pas une
mise à jour. Avant de créer, vérifie l'existant (`get_active_projects`, `get_project_tasks`,
`list_query`, `search_simple`) et préfère mettre à jour. Deux notes divergentes sur le même
sujet coûtent plus cher qu'une note imparfaite.

Seul `journal_open_or_create` est idempotent : il ouvre la page existante sans l'écraser.

### Ne jamais écrire de frontmatter à la main

Les templates sont la source de vérité du frontmatter, et les valeurs autorisées vivent sous
`r_templates/properties/`. Templater s'exécute à la création via l'interface Obsidian, mais
**pas** sur une écriture REST : un fichier créé par `vault_write` n'obtient ni template ni
frontmatter, même correctement titré. Passe donc par l'outil métier qui déclenche Templater
(`create_project`, `journal_open_or_create`), ou par `patch_frontmatter` pour modifier un
champ existant.

Deux exceptions, où le frontmatter s'écrit à la main **en recopiant le template de type**
(`r_templates/templates/type_*.md`) et les valeurs de `r_templates/properties/` :
- **Page Topic** : aucun outil métier ne la crée (cf. [Page Topic](#page-topic)).
- **Échec de `create_project`** (cf. [Page projet](#page-projet)).

Quel que soit l'outil, la **première ligne du corps reste vide** après le `---` de fermeture :
le curseur s'y place à l'ouverture et masquerait sinon le premier callout.

### Après écriture : signaler la sync

LiveSync ne détecte pas les écritures faites via l'API REST (inotify non déclenché depuis
l'extérieur du conteneur). Les commandes de sync (`obsidian-livesync:livesync-scan-files`,
`livesync-replicate`) ne sont pas exposées comme outils MCP : signale à l'utilisateur, après
une écriture, qu'une sync manuelle peut être nécessaire pour voir le changement sur mobile.

### Rendre compte

Après écriture, dis en une ligne ce qui a été écrit et où, avec un lien ouvrable :

```
obsidian://open?file=pages/Mon%20projet.md
```

Le chemin est URL-encodé (espaces en `%20`, extension `.md` incluse). Cette forme, sans
paramètre `vault`, s'ouvre dans le vault courant et fonctionne aussi bien sous Windows que sur
Android. Si plusieurs vaults sont ouverts, ajoute `&vault=<nom>`.

Savoir quel fichier vient de bouger évite un conflit de synchro et permet une vérification
immédiate.

---

## Page projet

**Ce que c'est** — une page sous `pages/` avec le frontmatter `type: Projet` et un `statut`.
Hub de son écosystème : tâches, fleeting notes et sous-pages s'y relient par `[[Nom]]`.

**Statuts** (valeurs sous `r_templates/properties/statut/`) : `1. A cadrer`, `2. A démarrer`,
`3. En cours`, `4. Bloqué`, `5. En pause`, `6. Recette`, `7. Lotit`, `8. Terminé`,
`9. Abandonné`.

`get_active_projects` renvoie **tous** les statuts, y compris terminés et abandonnés. Un
projet en `8. Terminé` ou `9. Abandonné` est hors périmètre : ne le propose pas comme
rattachement, ne l'inclus pas dans un état des lieux, ne lui ajoute pas de tâche. Sauf si
l'utilisateur demande explicitement de le rouvrir ou de le consulter — auquel cas remets
d'abord le statut à jour via `patch_frontmatter`.

**Créer** — `create_project(name, parent=...)`. `name` est le basename, sans extension ni
chemin ; `parent` produit `Parent @ Enfant.md`. L'outil applique le template Templater
`type_Props-Projet` ; le statut reste vide à la création, à renseigner ensuite via
`patch_frontmatter`. Ne crée jamais une page projet par `vault_write` : sans template, elle
n'apparaît ni dans `get_active_projects` ni dans la base `🛠️Projets`.

**Échec de `create_project`** — si la commande Templater répond 404, le fichier est quand même
créé, vide (`# <name>`), à la racine de `pages/`. Ne relance pas (doublon) : complète ce même
fichier par `vault_write` avec le frontmatter projet (`type: Projet`, `statut`, `parent`,
`topic`, `relations`) et les blocs standard du corps (ci-dessous). L'outil n'écrit jamais dans
`pages/1. Projets/` et aucun outil ne déplace un fichier entre dossiers : signale-le à
l'utilisateur, qui le rangera lui-même.

**Rattachement** — tout projet porte `topic:` (Topic enfant + Topics parents) en plus de son
`parent` éventuel. Cf. [Rattachement](#rattachement--parent-topic-relations).

**Champs Operon** (`status: Project.*`, `operonId`, `parentTask`, `taskType`, compteurs
`*SubtaskCount`, `progress`) — test de plugin, considérés comme du bruit : ne pas s'en servir
comme statut, ne pas les supprimer non plus. `type: Projet` + `statut` font foi. Une page créée
par Operon n'a souvent ni `type: Projet` ni `statut` : elle est invisible dans
`get_active_projects` et dans les vues des Topics tant qu'on ne les ajoute pas par
`patch_frontmatter`.

**Projet ou checklist ?** — un projet seulement pour un lot à plusieurs étapes avec une fin
identifiable. Une finition unitaire (poser une prise, changer un joint de porte) est une ligne
de checklist dans le `Reste à faire` du Topic concerné, pas un projet.

**Structure du corps** — le corps type (projets et Topics) enchaîne, après la ligne vide :
`` `button-applytype` `button-archive` ``, les trois callouts dataviewjs
(`r_templates/scripts/related-projects`, `child-pages`, `related-tasks`), puis `## Notes`.
Recopie-les d'une page existante quand tu écris un corps à la main. Au-delà, le corps est
libre : n'impose pas un canevas, lis les headings existants avec
`vault_get_document_map` et écris dans la section qui convient. Si aucune ne convient, crée un
heading de niveau 2 au nom parlant plutôt que d'entasser en fin de page.

**Mettre à jour le corps** — `vault_patch` avec `target_type: "heading"` et le texte exact du
heading tel que renvoyé par le map. Le MCP custom applique un read-modify-write côté serveur
pour cette cible, ce qui corrige le bug d'insertion du plugin natif v4.1.0.

**Mettre à jour les propriétés** — `patch_frontmatter(path, {statut: "3. En cours"})`, jamais
`vault_patch(target_type="frontmatter")` ni une réécriture complète. Le merge est idempotent.

**Granularité** — les décisions s'empilent (`append`), l'état d'avancement se remplace
(`replace`). Un avancement empilé devient un journal et perd sa fonction de réponse à « où
j'en suis ».

**Lire** — `get_active_projects` pour la liste et les statuts, `get_project_tasks` pour ce qui
gravite autour. Ne lis la page entière que si le contenu rédactionnel est nécessaire.

---

## Page Topic

**Ce que c'est** — un sujet entretenu sans date de fin : domaine (`Maison`, `Santé`) sous
`pages/2. Domaines/`, ou sous-domaine / objet (`Maison @ Cuisine`) sous `pages/3. Ressources/`.
Les Topics s'emboîtent : une pièce est un Topic enfant du Topic `Maison` (`parent: "[[Maison]]"`).
C'est la page qu'on ouvre pour savoir **ce qu'il y a à faire à un endroit** ; la page projet
dit **où on en est** sur un chantier.

**Frontmatter** — `type: Topic`, `topic:` = la page elle-même **puis** ses Topics parents
(`["[[Maison @ Cuisine]]", "[[Maison]]"]`), `parent` si enfant.

**Corps** — ligne vide, `![[Relations.base]]`, blocs standard, puis trois sections :
- `## Notes` : contexte stable, renvoi vers le projet hub du sujet s'il existe ;
- `## Reste à faire` : checklist locale des finitions unitaires du lieu (pas de `#Todo`) ;
  un item suivi dans un projet y figure en renvoi (`→ [[Projet]]`), pas en double ;
- `## Idées / plus tard` : sous-projets envisagés mais non lancés, une ligne chacun. Une idée
  lancée devient un projet (`topic` vers ce Topic) et sa ligne disparaît.

**Créer** — pas d'outil métier : `vault_write` avec le frontmatter recopié de
`r_templates/templates/type_Topic.md` complété comme ci-dessus. **Convertir** une page
existante : `patch_frontmatter` (`type`, `topic`), puis ajout des sections.

---

## Page libre

**Ce que c'est** — une note sous `pages/` sans `type: Projet` : documentation, note de fond,
référence. Pas de frontmatter obligatoire — seulement ce qui est utile (`tags`, `relations`).

**Créer** — `vault_write("pages/<titre>.md", content)`. Rappel : Templater ne tournera pas,
donc pas de frontmatter généré ; c'est acceptable pour une page libre, contrairement à un
projet.

**Hiérarchie** — `pages/` est rangé par grands types (`1. Projets/`, `2. Domaines/`,
`3. Ressources/`, `4. Archives/`), sans arborescence de sujet : la hiérarchie s'exprime par le titre
`Parent @ Enfant` ou par le frontmatter `parent: "[[Parent]]"`. L'une ou l'autre forme suffit.
Via MCP, pose-la toi-même dans le titre du fichier au moment de la création.

**Mettre à jour** — `vault_patch` après `vault_get_document_map`, ou `vault_append` pour un
ajout en fin de fichier. Évite `vault_write` sur un fichier existant : il écrase tout.

---

## Fleeting note

**Ce que c'est** — un fichier horodaté `fleeting/FLT-YYYY.MM.DDThh.mm.ss.md` avec un alias
liable en frontmatter. Support de tout ce qui est trop détaillé ou trop mouvant pour une page :
inventaires, relevés, idées à trier, captures brutes.

**Créer** — `create_fleeting_note(alias, content, page_path=..., tags=[...])`. L'alias doit
être parlant : c'est lui qui sert de wikilink, le nom de fichier étant illisible. `page_path`
pointe vers la page hôte et y dépose le lien retour — renseigne-le dès qu'un hub existe.

**Mettre à jour** — `vault_patch` ou `vault_append` sur le chemin de la note. Une note
d'inventaire s'enrichit, elle ne se recrée pas : `create_fleeting_note` rappelé produit un
nouveau fichier horodaté, donc un doublon silencieux.

**Retrouver** — `search_simple` sur l'alias ou un terme du contenu, ou le wikilink depuis la
page hôte. C'est précisément pourquoi le lien retour compte.

**Granularité** — un sujet, une note. Un inventaire de chantier reste une note unique qu'on
enrichit, pas une note par passage en magasin.

---

## Tâche

**Ce que c'est** — une ligne `- [ ] #Todo ...` du plugin Tasks, toujours dans le journal du
jour, jamais dans la page projet. Visible dans les vues Tasks globales.

**Créer** — `create_task(description, project=..., due_date=...)`.
- `project` : basename d'un projet **existant et actif**, sans `[[ ]]`. Vérifie avec
  `get_active_projects` plutôt que d'inventer un nom. **Sans `project`, la tâche est une tâche
  simple, sans lien** : c'est le comportement attendu quand rien ne s'y rattache — ne force
  pas un rattachement approximatif.
- `due_date` : ISO `YYYY-MM-DD` strict. « demain » est refusé ; convertis toi-même en date
  absolue à partir de la date du jour.
- `tags` : **ne renseigne pas ce paramètre**. Le seul tag convenu sur une tâche est `#Todo`,
  posé automatiquement. Toute autre étiquette encombre les vues sans être exploitée.

**Piège principal** — non idempotent : un second appel crée une seconde tâche. Si tu ignores
si un appel a abouti (timeout, connecteur instable), vérifie avec `get_project_tasks` avant de
rejouer.

**Lire** — `get_project_tasks(project_name)` pour les tâches ouvertes d'un projet,
`get_overdue_tasks` pour les échéances dépassées. Ces outils appliquent le schéma métier, là
où `search_simple("[[projet]]")` ramène du plein-texte approximatif.

**Ne jamais** écrire une tâche via `vault_append` : hors schéma (placement avant
`### Overdued`, date en fin de ligne), elle n'apparaît dans aucune requête.

---

## Checklist locale

**Ce que c'est** — des lignes `- [ ]` **sans** `#Todo`, dans le corps d'une note : étapes d'un
mode opératoire, points à vérifier. Reste locale, n'apparaît pas dans les vues Tasks.

**Quand la préférer à une tâche** — quand les items n'ont ni échéance ni suivi individuel et
n'ont de sens que dans le contexte de leur note. Verser une procédure en douze étapes dans les
vues Tasks les noierait.

**Écrire** — `vault_patch` sur le heading concerné de la note. N'ajoute jamais `#Todo` à ces
lignes, et n'utilise pas `create_task` pour les créer.

---

## Liste `#list/`

**Ce que c'est** — des items à cocher taggés `#list/<Contexte>` (`#list/MatosCamping`,
`#list/LeroyMerlin`), regroupables depuis plusieurs notes. Pour l'interchangeable et le
réutilisable : courses, matériel à emporter.

**Ajouter** — `add_to_list`, qui écrit dans le journal du jour. **C'est la destination par
défaut** : sauf indication explicite de l'utilisateur, un item de liste va au journal du jour,
pas dans une page projet. Si une autre destination est demandée, écris la ligne dans la note
cible avec le tag `#list/<Contexte>` — le regroupement fonctionne quel que soit l'emplacement.

**Lire** — `list_query(name=...)` ; `include_done=True` pour voir aussi les items cochés.

**Distinction avec une tâche** — une liste porte des items interchangeables sans échéance ; une
tâche porte un suivi. Les périmètres sont disjoints : `list_query` ignore les `#Todo`,
`get_project_tasks` ignore les `#list/`.

---

## Log du journal

**Ce que c'est** — une entrée horodatée `- \`HH:MM\` - ...` dans la section `## Logs` du journal
du jour, insérée en LIFO juste après le bouton `button-addlog`.

**Créer** — `log_to_daily(content)`. L'outil gère le placement, l'heure (Europe/Paris) et les
lignes vides.

**Quand l'utiliser** — pour ce qui est daté et ponctuel : une observation, un appel passé, un
constat terrain. Pas pour une décision de projet, qui doit rester retrouvable sans connaître
sa date.

**Ne jamais** l'écrire via `vault_append` : l'ordre LIFO et le rendu du bouton seraient cassés.

---

## Page de journal

**Ce que c'est** — `journals/<YYYY-MM-DD>.md`, structure `## Logs` / `## Tasks` avec le bouton
`button-addlog` et les rubriques `### Overdued` / `### Next`. **Aucun frontmatter** : le
dossier identifie le type.

**Créer / ouvrir** — `journal_open_or_create(date_str)` (défaut : aujourd'hui). Idempotent.
Utile pour préparer une date à l'avance.

**Écriture** — en append uniquement, et via les outils métier (`log_to_daily`, `create_task`,
`add_to_list`). `vault_write` sur un journal casserait la structure dont ils dépendent.

---

## Placement et zones d'écriture

Racine du vault : `pages/`, `journals/`, `fleeting/`, `attachments/`, `bases/`, `briefings/`,
`r_wiki/`, `r_knowledge_base_pro/`, `r_templates/`.

| Zone | Écriture MCP |
|---|---|
| `pages/` | Créer, modifier — zone principale |
| `journals/` | Append via outils métier uniquement |
| `fleeting/` | Créer via `create_fleeting_note`, retoucher ensuite |
| `attachments/`, `r_wiki/`, `bases/`, `briefings/` | Possible selon le besoin |
| `r_templates/` | **Lecture seule** — refusé en écriture |

Garde-fous du serveur : pas de fichier à la racine, pas de nouveau dossier de premier niveau,
et seul `r_wiki/` accepte de nouveaux sous-dossiers — pas `pages/`, dont les sous-dossiers
existants (`1. Projets/` … `4. Archives/`) restent utilisables (la hiérarchie de sujet passe par le
nommage `Parent @ Enfant`). Ailleurs, le dossier parent
doit déjà exister.