# Skills personnels de `dobby`

Emplacement de priorité la plus haute (`<workspace>/skills`), visible de `dobby` seul, versionné dans
`Home/openclaw-workspace`. Aucune liste de skills ne restreint `dobby` (DAT §6.7) : un skill posé ici
et utilisable est vu au tour suivant.

## Conventions

- **Un dossier par skill** : `skills/<nom-du-skill>/SKILL.md`, nom en minuscules avec tirets, 2 à 4
  mots décrivant la classe de travail. Fichiers d'appui dans `references/`, `scripts/`, `templates/`
  ou `examples/` du même dossier.
- **La description déclenche** : aucun skill n'est préchargé ; seuls le nom, la description et le
  chemin sont injectés à chaque tour. Mettre en tête les situations et formulations qui doivent
  l'ouvrir.
- **Indépendant de l'hôte** (DAT §6.7, D-11) : pas de chemin `op`, de clé SSH, de variable locale ni
  de binaire supposé présent codés en dur ; les paramétrer.
- **Aucun secret** dans un skill : des références `op://` au plus, jamais de valeur.
- **Procédure, pas journal** : des étapes vérifiables ; les faits datés vont dans `memory/`.
- Ajout **ciblé**, puis commit et push (jamais `git add -A`).

Modèle : `_modele/SKILL.md.exemple` — l'extension `.exemple` l'empêche d'être chargé comme skill.
Autre voie : faire rédiger le skill par `dobby` avec `skill_workshop`, puis le committer.
