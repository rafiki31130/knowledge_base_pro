# 06. Dimensionnement, conditions d'arrêt et retour arrière

## Dimensionnez depuis les mesures, pas depuis les pourcentages du banc

**Recommandation.** Séparez la capacité de la VM, le plafond du service, les plafonds de catégories et ceux des pools. Les gabarits de 2 vCPU et 2 Gio servent à éprouver les mécanismes. Ils ne dimensionnent pas une plateforme Splunk réelle.

1. Mesurez le besoin de l'instance sans plafonds métier serrés.
2. Mesurez la mémoire d'ingest, y compris le démon principal et les auxiliaires.
3. Mesurez les pics de recherche par famille et leur concurrence.
4. Mesurez les fichiers dispatch, la pagination et les files d'ingestion.
5. Définissez la marge OS et les contraintes des ancêtres systemd.
6. Retenez un plafond de service compatible avec ces besoins.
7. Calculez les plafonds par niveau.
8. Comparez les octets calculés aux octets réellement exposés par le noyau.
9. Rejouez les charges représentatives et leur mélange.

Le calcul compatible avec T11, pour une page de taille `P`, est :

```text
plafond catégorie = plancher(base service × poids catégorie / 100 / P) × P
plafond pool = plancher(plafond catégorie × poids pool / 100 / P) × P
```

Les essais reçus utilisent une page de 4096 octets. Ne supposez pas cette taille sur une autre cible. Le comportement exact d'une autre version reste à qualifier.

## Gardez ingest hors des essais ordinaires de serrage

**Observé en 10.4.5, T08.** `splunkd` appartient à ingest. Un plafond trop petit tue le démon principal, puis systemd le relance. Une réserve de RAM physique suffisante n'empêche pas cet OOM local de catégorie.

- Ne baissez pas ingest pour démontrer un OOM de recherche.
- Ne reprenez pas le seuil négatif de T08 en exploitation.
- Ne considérez pas un pool ingest à 100 comme une absence de plafond : sa catégorie et l'instance restent bornées.
- Ne considérez pas le swap comme une protection absolue si son espace peut s'épuiser.

Un essai OOM ingest exige un scénario destructif distinct, une portée explicitement admise et un accès de secours indépendant de Splunk. Aucun tel essai n'est requis pour lire les plafonds.

## Choisissez le modèle mémoire des pools

### Plafonds larges

Des pools search à 100 peuvent utiliser chacun toute la limite de search, sans réservation individuelle. Ce modèle évite de petits plafonds arbitraires. Il ne garantit pas qu'une recherche lourde ne mettra jamais les autres sous pression au niveau de la catégorie.

### Partition stricte

Une somme de poids mémoire égale à 100 crée des enveloppes étroites. Une recherche peut être tuée alors que la catégorie conserve de la mémoire libre. T05 le démontre sans swap sur le pair chargé.

Pour qualifier un témoin :

1. Exécutez-le seul dans un pool large.
2. Relevez son pic sur une durée et un corpus représentatifs.
3. Calculez un plafond supérieur à ce pic avec une marge explicite.
4. Vérifiez le plafond après arrondi.
5. Rejouez le même témoin avec la charge concurrente.
6. Comparez ses nouveaux événements OOM et sa progression.

Le protocole reçu exigeait au moins **1,5 fois** le pic mesuré. Ce facteur est une marge de protocole, pas une garantie de maximum universel. Le témoin à 10 % avait fait son propre OOM ; le témoin à 40 %, recalibré, est resté intact. Ne changez pas son profil pour gommer un échec.

Comparez les **deltas** de compteurs. Une valeur historique non nulle ne prouve pas un nouvel OOM. La calibration reçue avec swap ne démontre pas une empreinte maximale sans swap sur toutes les données.

## Calibrez le CPU sur une fenêtre

1. Identifiez les pools réellement demandeurs.
2. Vérifiez la demande sur les pairs, pas seulement sur le SH.
3. Mesurez les deltas pool, catégorie et instance.
4. Séparez montée en charge et fenêtre qualifiée.
5. Publiez la part intégrée et les excursions courtes.
6. Conservez les petits consommateurs de fond.

T02 et M2 n'autorisent pas une garantie de proportion à chaque intervalle de cinq secondes. Si le besoin métier impose une borne courte, définissez et testez cette borne séparément.

## Calibrez l'ingestion sans compter les copies deux fois

1. Fixez un débit offert et un volume maximal.
2. Vérifiez le budget de licence disponible.
3. Utilisez la même offre pour le témoin et la pression.
4. Maintenez chaque activité pendant toute la fenêtre retenue.
5. Rapprochez chaque séquence distincte offerte et reçue.
6. Mesurez retard, files, CPU et pagination sur tous les participants.
7. Séparez débit unique et débit de copies répliquées.

Une fenêtre dont un producteur ou une recherche attendue s'arrête n'est pas une référence mixte complète. Ne cumulez pas des durées disjointes pour atteindre une durée annoncée. T06 qualifie 330 s nominales sous pression CPU ; il ne qualifie ni le débit maximal ni une pression mémoire dédiée simultanée.

## Conditions d'arrêt

Fixez les valeurs applicables avant le changement. Les seuils numériques de laboratoire ne sont pas des seuils de production.

| Condition | Action |
| --- | --- |
| Build, identité ou portée inconnue | Suspendez la mutation |
| Échec de validation native ou restart non couvert | N'appliquez pas le bundle |
| Garde mémoire, swap, disque, licence ou durée franchie | Annulez immédiatement la charge concernée |
| Pair ou SH disparu hors scénario | Suspendez l'enchaînement et recevez l'état |
| RF/SF ou données recherchables non conformes au contrat | Arrêtez l'essai et engagez le retour prévu |
| Témoin tué, contribution manquante ou résultats incomplets | Conservez la passe comme négative ou non concluante |
| Réponse de push/apply ambiguë | Relisez l'effet avant toute nouvelle soumission |
| Retour non reçu dans le délai prévu | Conservez les preuves et utilisez l'accès de reprise |

Pendant un essai sans swap admis, le banc exigeait `MemAvailable > swap utilisé + 200 Mio` avant swapoff. T08 montre que cette garde physique ne couvre pas un manque de marge dans ingest. Elle ne doit pas être présentée comme une garantie de sûreté.

N'attendez pas la fin d'une sonde longue pour annuler une charge qui franchit une garde. Un HTTP 404 sur le SH ne prouve pas la disparition instantanée de tous les workers distants.

## Retour 1. Arrêtez les charges du changement

1. Arrêtez les producteurs temporaires.
2. Annulez les recherches du changement sur leurs SH émetteurs.
3. Relisez leur fin ou leur HTTP 404.
4. Vérifiez les références de dispatch sur SH et pairs.
5. Vérifiez le retour du CPU au repos.
6. Retirez les seules entrées d'ingestion temporaires prévues.
7. Conservez les données nécessaires au rapprochement.

Ne tuez pas les lanceurs réutilisables et ne purgez pas les preuves pour obtenir un contrôle vide.

## Retour 2. Restaurez l'objet modifié

### Pools des indexeurs

1. Restaurez la source CM sauvegardée.
2. Validez le bundle de retour et sa prévision de restart.
3. Appliquez une seule fois le bundle validé.
4. Relisez l'identité du bundle actif sur chaque pair.
5. Comparez les fichiers actifs à la source attendue.
6. Relisez les catégories, pools et plafonds effectifs.

Les archives `peer-apps.old*` et `default.old.*` tournent nativement. Ne les confondez pas avec les fichiers actifs et ne les restaurez pas manuellement pour égaliser un inventaire.

### Règles ou pools des SHC

1. Restaurez la source du deployer concerné.
2. Poussez une seule fois.
3. Attendez la fin du rolling restart.
4. Vérifiez tous les membres prêts.
5. Relisez la configuration et l'état WLM de chaque membre.

### Unité ou MemoryMax

1. Identifiez la seule unité à restaurer.
2. Recevez l'arrêt propre du membre.
3. Restaurez les réglages sauvegardés encore admissibles.
4. Rechargez systemd.
5. Démarrez le membre.
6. Relisez le plafond du service et du noyau.
7. Relisez les plafonds WLM.
8. Recevez la réintégration.

**Observé en 10.4.5.** Revenir à chaud à l'ancien MemoryMax laisse les plafonds WLM calculés au démarrage précédent. Le redémarrage reçu rétablit leur base. N'utilisez pas un `systemctl revert` aveugle qui pourrait retirer des drop-ins sans rapport.

### Swap d'essai

1. Rétablissez les espaces swap prévus.
2. Comparez périphérique, type, taille et priorité.
3. Comparez fstab et swappiness à la référence.
4. Vérifiez les marges et la santé.

Le volume Used évolue avec la charge. Il n'a pas à revenir à sa valeur initiale.

## Retour 3. Distinguez désactivation ciblée et retour global

**Observé en 10.4.5.** Un cycle OFF puis ON des seuls pairs a été reçu par bundle CM, les SHC restant actifs. Des retours de règles, de poids et d'unité ont aussi été reçus dans leurs lots.

**Non vérifié.** Retour arrière global de tous les rôles et tout retour 10.2. N'inversez pas mécaniquement l'ordre d'activation. Définissez les états intermédiaires attendus et la réception de chaque palier.

Si le workflow CM est bloqué après une mort de pair, appliquez la branche de diagnostic du [chapitre 05](./05-exploitation-et-audit.md), pas une suite de resets improvisés.

## Fermez la fenêtre sur des preuves distinctes

1. Vérifiez les fichiers actifs et leurs sources.
2. Vérifiez les plafonds de service, catégories et pools.
3. Vérifiez WLM sur chaque membre attendu.
4. Vérifiez RF/SF et données recherchables.
5. Vérifiez les SHC prêts.
6. Vérifiez l'absence de charge et de maintenance résiduelles.
7. Consignez les écarts et les retours non exercés.

Une grappe saine ne prouve pas la restauration des plafonds. La remise WLM ne retire pas automatiquement des comptes d'essai, des accès Web ou une app de restitution. Traitez leur sort séparément, sans les confondre avec la réussite technique de WLM.

## Sources

- [Résultats T02, T04 à T06, T08, T11, T16 et M2/M3](./03-resultats-qualification.md).
- Spécification `workload_pools.conf.spec` de Splunk Enterprise 10.4.5 et plafonds noyau observés.
- [Contrôles de terminaison et récupération CM](./05-exploitation-et-audit.md).
- [Transposition et contrôles restant à rejouer](./07-transposition-102.md).
