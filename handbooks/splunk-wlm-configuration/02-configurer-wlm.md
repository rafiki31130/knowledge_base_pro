# 02. Configurer WLM pas à pas

## 1. Préparez la fenêtre

1. Relevez le build exact de chaque rôle.
2. Lisez les trois spécifications WLM livrées avec ce build.
3. Identifiez l'unité systemd réellement utilisée par chaque instance.
4. Associez chaque SHC à son deployer.
5. Associez chaque pair à son cluster manager.
6. Vérifiez la santé des SHC, les pairs recherchables et RF/SF.
7. Vérifiez l'absence d'opération de cluster concurrente.
8. Mesurez les marges mémoire, swap, disque et dispatch.
9. Fixez les seuils d'arrêt et les délais de convergence.
10. Sauvegardez les sources et les unités qui changeront.
11. Vérifiez les empreintes des sauvegardes.
12. Exécutez une recherche de référence depuis chaque SHC.
13. Conservez ses résultats et les contributions des pairs.

Utilisez les consultations suivantes sur chaque hôte concerné. Elles ne modifient pas l'état.

```bash
# Lecture seule : relever le build installé.
/opt/splunk/bin/splunk version
```

```bash
# Lecture seule : relever le montage des contrôleurs cgroups.
stat -fc %T /sys/fs/cgroup
findmnt -t cgroup,cgroup2
```

```bash
# Lecture seule : relever le plafond, la délégation et l'incarnation de l'unité cible.
systemctl show Splunkd.service -p FragmentPath -p DropInPaths -p ControlGroup -p Delegate -p MemoryMax -p MainPID -p NRestarts -p Restart -p OOMPolicy
```

Remplacez `Splunkd.service` si l'instance utilise un autre nom. Ne démarrez pas une unité alternative pour obtenir un état actif.

## 2. Préparez l'unité native sur chaque hôte

**Observé en 10.4.5.** Copier une unité v2 sur AlmaLinux v1 laisse un post-hook vers un chemin absent. WLM ne s'active pas, même si `splunkd` fonctionne. La génération native sur l'hôte corrige ce défaut sans changer le bundle de pools.

1. Vérifiez l'arrêt propre du membre à traiter.
2. Sauvegardez son unité et ses drop-ins.
3. Générez l'unité avec le lanceur du build installé.
4. Comparez l'unité générée au mode cgroups réel.
5. Conservez les réglages d'exploitation nécessaires.
6. Conservez explicitement la politique de démarrage au boot prévue.

Commande de génération utilisée sur le build qualifié, service arrêté :

```bash
# Générer l'unité Splunk locale ; sauvegarder l'existante et conserver sa politique de boot.
sudo /opt/splunk/bin/splunk enable boot-start -systemd-managed 1 -user splunk -group splunk -systemd-unit-file-name Splunkd -create-polkit-rules 0
```

Le choix de ne pas créer de règles polkit appartient à cette recette. Préservez les droits et le canal d'administration déjà prévus. Ne changez pas les contrôles d'accès pour faire passer une commande.

L'unité native reçoit notamment `Delegate=true`. En v1, ses post-hooks préparent les contrôleurs `cpu` et `memory` séparés. En v2, le chemin appartient à la hiérarchie unifiée. **Ne remplacez pas ces post-hooks par un bloc copié d'un autre OS.**

## 3. Fixez le plafond du service

Le profil qualifié fixe :

```text
MemoryMax en octets = MemTotal Linux en Kio × 1024
```

C'est le choix du banc, pas une recommandation générale de capacité. Pour l'exploitation, faites valider la réserve de l'OS, les autres services et le besoin Splunk avant de retenir ce plafond.

1. Relevez `MemTotal` sur l'hôte cible.
2. Calculez le plafond en octets.
3. Comparez-le au besoin de l'instance et à ses ancêtres.
4. Écrivez un drop-in dédié sans toucher aux réglages sans rapport.
5. Rechargez systemd.
6. Démarrez le membre dans la fenêtre prévue.
7. Relisez le plafond effectif du noyau.
8. Relisez les plafonds WLM après activation.

Gabarit de `/etc/systemd/system/Splunkd.service.d/99-wlm-memory.conf` :

```ini
# Gabarit : remplacer la valeur entre chevrons par les octets validés pour cet hôte.
[Service]
Delegate=true
MemoryMax=<OCTETS_VALIDES_POUR_CET_HOTE>
```

Le gabarit n'est pas directement installable avec ses chevrons. Ne recopiez pas une ancienne valeur numérique parce que deux VM ont la même RAM nominale. Vérifiez la précédence de tous les drop-ins.

```bash
# Recharger les définitions de l'unité après l'édition autorisée ; aucun démarrage implicite.
sudo systemctl daemon-reload
```

```bash
# Démarrer le seul membre préparé dans la fenêtre prévue ; vérifier sa réintégration ensuite.
sudo systemctl start Splunkd.service
```

En v2, relisez `memory.max` au chemin indiqué par `ControlGroup`. En v1, relisez `memory.limit_in_bytes` dans le contrôleur mémoire de cette unité. Ne lisez pas la racine si `ControlGroup` est vide.

**Observé en 10.4.5, T11.** Une modification à chaud de MemoryMax ne recalcule pas les catégories et les pools. Après une modification sur une instance déjà activée, prévoyez son redémarrage, puis recevez chaque plafond. Le retour à la valeur initiale exige le même contrôle.

## 4. Conservez le swap prévu

1. Relevez les espaces swap et leur priorité.
2. Relevez `vm.swappiness`.
3. Comparez les hôtes avant la mise en service.
4. Conservez la configuration prévue pendant l'activation.

```bash
# Lecture seule : relever les espaces swap et le réglage de pagination.
swapon --show --bytes
sysctl vm.swappiness
```

La désactivation du swap n'est **pas** un prérequis WLM. Elle appartient seulement aux essais OOM dédiés. La garde physique de ces essais ne protège pas le démon contre un plafond `ingest` trop petit.

## 5. Préparez les fichiers de pools

Les exemples suivants sont reformulés avec des noms génériques. Les valeurs reprennent le **profil large de qualification**, pas un dimensionnement de production. Les stanzas de chaque fichier forment un ensemble ; ne les ajoutez pas aveuglément à un existant.

### Search heads du SHC A

Préparez `etc/shcluster/apps/wlm_search_a/local/workload_pools.conf` sur le deployer A :

```ini
[general]
enabled = 1
default_pool = team_a_interactive
ingest_pool = ingest_default
workload_pool_base_dir_name = splunk

[workload_category:search]
cpu_weight = 70
mem_weight = 70

[workload_category:ingest]
cpu_weight = 20
mem_weight = 100

[workload_category:misc]
cpu_weight = 10
mem_weight = 10

[workload_pool:team_a_interactive]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 1

[workload_pool:team_a_scheduled]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_a_accel]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_a_bulk]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:ingest_default]
category = ingest
cpu_weight = 100
mem_weight = 100
default_category_pool = 1

[workload_pool:misc_default]
category = misc
cpu_weight = 100
mem_weight = 100
default_category_pool = 1
```

Pour le SHC B, préparez une app distincte sur son deployer. Remplacez `team_a_` par `team_b_` dans les pools et les règles. Vérifiez son défaut indépendamment. Ne distribuez pas les deux sources au même SHC.

### Indexeurs : union des pools des deux SHC

Préparez `etc/manager-apps/wlm_peers/local/workload_pools.conf` sur le CM :

```ini
[general]
enabled = 1
default_pool = unmapped
ingest_pool = ingest_default
workload_pool_base_dir_name = splunk

[workload_category:search]
cpu_weight = 60
mem_weight = 70

[workload_category:ingest]
cpu_weight = 30
mem_weight = 100

[workload_category:misc]
cpu_weight = 10
mem_weight = 10

[workload_pool:unmapped]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 1

[workload_pool:team_a_interactive]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_a_scheduled]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_a_accel]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_a_bulk]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_b_interactive]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_b_scheduled]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_b_accel]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:team_b_bulk]
category = search
cpu_weight = 10
mem_weight = 100
default_category_pool = 0

[workload_pool:ingest_default]
category = ingest
cpu_weight = 100
mem_weight = 100
default_category_pool = 1

[workload_pool:misc_default]
category = misc
cpu_weight = 100
mem_weight = 100
default_category_pool = 1
```

**Piège de syntaxe.** `default_pool` sous `[workload_category:*]` est hors spécification et sans effet sur le build reçu. Le défaut actuel se définit par `default_category_pool` dans la stanza du pool. Les clés `default_pool` et `ingest_pool` conservées sous `[general]` sont des clés historiques de compatibilité du contrat 10.4.5. Ne les confondez pas avec la clé invalide de catégorie.

Les neuf pools search des pairs ont ici le même poids. Ils ne disposent pas chacun de 10 % garantis à toute charge. Comparez les poids relatifs des pools effectivement demandeurs. Les pools mémoire à 100 se recouvrent sous leur catégorie et sous l'instance.

## 6. Préparez règles et policy sur les deployers

Exemple de `workload_rules.conf` pour le SHC A :

```ini
[workload_rule:observe_long]
predicate = runtime>2m
action = alert
user_message = Duree attendue depassee ; examinez la recherche.

[workload_rule:place_accel]
predicate = search_type=datamodel_acceleration
workload_pool = team_a_accel

[workload_rule:place_scheduled]
predicate = search_type=scheduled
workload_pool = team_a_scheduled

[workload_rule:place_interactive]
predicate = search_type=adhoc
workload_pool = team_a_interactive

[workload_rules_order]
rules = observe_long,place_accel,place_scheduled,place_interactive
```

Le placement n'utilise pas de clé `action`. La trace peut le nommer `place`. L'exemple d'accélération ne couvre que les datamodels ; ajoutez les autres types après inventaire et qualification.

Exemple de `workload_policy.conf` initial :

```ini
[search_admission_control]
admission_rules_enabled = 0
```

Ajoutez une règle d'admission seulement après étude d'impact. L'exemple suivant illustre la syntaxe ; il n'appartient pas à la première bascule :

```ini
[search_filter_rule:filter_alltime]
predicate = app=search AND search_time_range=alltime
action = filter
user_message = Utilisez une plage temporelle bornee.
disabled = true
```

Pour l'activer ultérieurement, vérifiez les exclusions d'apps techniques, activez le filtre retenu et passez la policy à 1. Ne mettez pas `filter_alltime` dans `workload_rules_order`.

### Actions contraignantes, à qualifier séparément

Les deux exemples suivants sont **désactivés**. Ils montrent la syntaxe, pas une politique prête à appliquer :

```ini
[workload_rule:abort_long]
predicate = app=search AND runtime>1m
action = abort
user_message = Recherche arretee par la politique de duree.
disabled = true

[workload_rule:move_long]
predicate = app=search AND runtime>1m
action = move
workload_pool = team_a_bulk
user_message = Recherche deplacee dans le pool differe.
disabled = true
```

Avant leur activation, incluez leurs noms dans l'ordre et qualifiez cet ordre. `abort_long,move_long,...` donne priorité à abort ; l'ordre inverse donne priorité à move pour le franchissement testé. Prévoyez un essai distinct si le comportement après déplacement fait partie du besoin.

**Piège de prédicat.** Une règle `index=*` ne sélectionne pas universellement toute recherche. T14 observe une correspondance avec la chaîne littérale `index=*`. Testez aussi une recherche nommant explicitement un index.

## 7. Contrôlez les sources

1. Vérifiez un défaut valide par catégorie.
2. Vérifiez l'union des noms de pools sur les pairs.
3. Vérifiez les règles et leurs références de pool.
4. Vérifiez l'ordre effectif des règles.
5. Vérifiez la policy effective.
6. Comparez les différences à la sauvegarde.

```bash
# Lecture seule : contrôler la fusion de configuration et sa provenance.
/opt/splunk/bin/splunk btool workload_pools list --debug
/opt/splunk/bin/splunk btool workload_rules list --debug
/opt/splunk/bin/splunk btool workload_policy list --debug
/opt/splunk/bin/splunk btool check
```

Sur le deployer ou le CM, inspectez aussi les fichiers du répertoire de distribution. Un `btool` local à cette autorité ne prouve pas la configuration future de ses destinataires. Refaites la lecture sur chaque membre après distribution.

## 8. Activez les SHC avant les pairs

La séquence retenue dans cette qualification est **SHC A, SHC B, puis pairs**. La comparaison documentaire disponible pour 10.2/10.4 rapporte aussi l'activation des search heads avant les pairs. Cette édition ne constitue pas une nouvelle qualification de l'ordre en 10.2.

L'ancien guide de gouvernance propose une activation des pairs appelée observation. Cette phase active pourtant les plafonds Linux : ce n'est pas un audit sans effet. N'utilisez pas cette appellation pour inverser la séquence du présent profil.

Pour chaque SHC :

1. Poussez une seule fois depuis son deployer.
2. Conservez la réponse native.
3. Attendez la fin du rolling restart.
4. Attendez tous les membres prêts vus du capitaine.
5. Relisez les fichiers et leur provenance sur chaque membre.
6. Relisez l'état WLM et les plafonds sur chaque membre.
7. Vérifiez les cohortes témoins avant le SHC suivant.

Contrat REST observé pour le push du deployer :

```text
POST /services/apps/deploy
 target=<MGMT_URI_D_UN_MEMBRE_DU_SHC>
 action=all
 preserve-lookups=true
 output_mode=json
```

Sans DNS, utilisez le **`mgmt_uri` exprimé en IP et réellement déclaré par le membre** dans `server.conf [shclustering]`. Ne fabriquez pas une URI depuis le nom affiché. L'identité TLS doit rester vérifiée pour l'adresse utilisée.

**Observé en 10.4.5.** Les pushes de règles ou de pools reçus ont déclenché un rolling restart, d'environ quatre à cinq minutes dans cette topologie. La spec du fichier de règles indique qu'une modification ne nécessite pas en elle-même de restart. Le workflow du deployer et le contrat du fichier sont deux objets distincts.

Une réponse JSON de type liste est possible. Une erreur du lecteur après le push ne justifie pas un second push. Relisez d'abord l'effet sur les membres. Un drapeau `rolling_restart=false` ne suffit pas si un membre reste `Restarting`.

## 9. Validez puis appliquez le bundle CM

Les indexeurs reçoivent les **pools** par le CM. N'y ajoutez pas les règles de placement des SHC ni leur policy d'admission. N'éditez pas les fichiers actifs des pairs à la main.

1. Validez le bundle depuis le CM.
2. Relisez son verdict et la prévision de redémarrage.
3. Vérifiez le même bundle valide sur tous les pairs.
4. Arrêtez si le redémarrage annoncé dépasse la fenêtre autorisée.
5. Appliquez une seule fois le bundle validé.
6. Attendez sa convergence sur tous les pairs.
7. Relisez les fichiers actifs et leurs plafonds.
8. Vérifiez l'état WLM de chaque pair.
9. Vérifiez RF/SF, données recherchables et SHC prêts.

Équivalents CLI à confronter à l'aide du build installé :

```bash
# Valider le bundle depuis le CM et obtenir la prévision de redémarrage avant application.
/opt/splunk/bin/splunk validate cluster-bundle --check-restart
```

```bash
# Lecture seule : examiner le résultat natif et le même bundle sur les pairs.
/opt/splunk/bin/splunk show cluster-bundle-status
```

```bash
# Appliquer une seule fois le bundle validé lorsque tous les critères de réception sont satisfaits.
/opt/splunk/bin/splunk apply cluster-bundle
```

N'utilisez pas de saut de validation. Certaines modifications de poids mémoire ont été reçues sans restart sur ce build. Cela ne dispense pas de lire la prévision à chaque variante. Un bundle commun ne qualifie pas un seuil individuel par pair.

## 10. Recevez l'activation

1. Interrogez le statut WLM sur tous les membres attendus.
2. Comparez la liste retournée à l'inventaire du CM et des SHC.
3. Vérifiez `enabled=1`, le support et l'absence d'erreur.
4. Vérifiez les cgroups et les plafonds effectifs.
5. Rejouez la recherche de référence depuis chaque SHC.
6. Comparez résultats et contributions des pairs.
7. Inspectez les messages de recherche.
8. Reliez les processus au pool attendu sur SH et pairs.
9. Conservez deux lectures stables après convergence.

Un fichier distribué n'est pas une activation reçue. Un pair Up n'est pas une preuve WLM. Un job DONE n'est pas une preuve de complétude. Utilisez les [contrôles d'audit](./05-exploitation-et-audit.md) avant de clore la fenêtre.

## Sources

- Splunk Enterprise 10.4.5 : spécifications livrées `workload_pools.conf.spec`, `workload_rules.conf.spec`, `workload_policy.conf.spec`, aide native des bundles et générateur natif d'unité.
- [Modèle et sémantique des paramètres](./01-modele-wlm.md).
- [Résultats T07, T10 à T15, T18 et M5](./03-resultats-qualification.md).
- [Conditions d'arrêt et retours](./06-dimensionnement-et-retour.md).
- [Sources documentaires complémentaires](./README.md).
