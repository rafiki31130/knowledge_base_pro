# Configurer et qualifier Splunk Workload Management

## Objet et limites du handbook

Ce handbook décrit la configuration WLM d'un déploiement distribué. Il explique les mécanismes CPU et mémoire. Il donne une procédure de mise en service, des contrôles et des retours ciblés. Il restitue une qualification sur **Splunk Enterprise 10.4.5**.

Ce n'est pas une certification de production. Ce n'est pas un guide d'installation de Splunk. Les exemples sont génériques. Ils ne constituent pas un dimensionnement prêt à appliquer.

Le handbook complète le [guide de gouvernance des usages Splunk](../gouvernance-utilisateurs-splunk/README.md). Il ne réécrit pas ses chapitres historiques. Pour les observations 10.4.5, utilisez les limites de preuve du présent livre. Ne combinez pas des étapes d'activation ou des conclusions de versions différentes.

## Lecteur et prérequis

Ce livre s'adresse à l'administrateur ou à l'architecte Splunk. Le lecteur connaît les bundles du cluster manager, les deployers de SHC, `btool`, REST, systemd et les cgroups Linux. Il dispose d'un accès de reprise indépendant de Splunk.

## Périmètre

- Splunk Enterprise **10.4.5**, WLM Advanced.
- RHEL **10.0**, cgroups v2 et systemd, pour les essais T01 à T18.
- AlmaLinux **8.10**, cgroups v1 et systemd, pour l'extension mixte M1 à M6.
- Une grappe d'indexeurs non multisite, deux SHC, leurs deployers, un cluster manager et une Monitoring Console.
- Des gabarits récents de **2 vCPU et 2 Gio nominaux**. Certains essais historiques utilisent 1 Gio.
- Une licence de laboratoire annoncée Developer/Enterprise. Le quota effectif est contrôlé, pas déduit du nom de la licence.

**Non vérifié :** Splunk 10.2, autres builds, production, multisite, perte de site, troisième SHC, retour arrière global et garantie statistique. Une passe par variante est la règle. Les exceptions sont indiquées dans les tableaux.

## Mode de lecture

Lisez les chapitres 00 à 02 avant un changement. Utilisez le chapitre 03 pour distinguer le résultat mesuré de la garantie supposée. Ajoutez le chapitre 04 pour une grappe mixte. Gardez les chapitres 05 et 06 ouverts pendant la réception et le retour.

## Sommaire

| Chapitre | Contenu |
| --- | --- |
| [00. Périmètre et méthode](./00-perimetre-et-preuves.md) | Topologie, gabarits, licence et limites expérimentales |
| [01. Modèle WLM](./01-modele-wlm.md) | Catégories, pools, CPU, mémoire, règles, admission et propagation |
| [02. Configurer pas à pas](./02-configurer-wlm.md) | Unité native, MemoryMax, fichiers de configuration, deployers et bundle CM |
| [03. Résultats T01 à T18 et M1 à M6](./03-resultats-qualification.md) | Verdicts, chiffres clés et parties non vérifiées |
| [04. Grappe mixte cgroups v1/v2](./04-cgroups-mixtes.md) | Unités adaptées, compteurs comparables et trou d'audit |
| [05. Exploitation et audit](./05-exploitation-et-audit.md) | SPL, état distribué, OOM, arrêts et incidents de bundle |
| [06. Dimensionnement, arrêt et retour](./06-dimensionnement-et-retour.md) | Méthode de calibration, gardes et retours ciblés |
| [07. Transposition vers 10.2](./07-transposition-102.md) | Contrat à relire et essais à rejouer, sans extrapolation |

## Conventions

### Niveaux de preuve

- **Documenté** : contrat décrit par une spécification ou une documentation identifiée. Ce mot ne signifie pas « exécuté ».
- **Observé en 10.4.5** : résultat reçu dans la fenêtre et les conditions décrites. Ce mot ne signifie pas « garanti sur toute charge ».
- **Non vérifié** : condition non exercée ou preuve insuffisante.
- **Recommandation** : choix de méthode proposé à partir des observations. Ce n'est pas une prescription universelle de l'éditeur.

Un PASS est toujours borné à son critère. Un essai négatif reste négatif après la restauration du service. Un changement de protocole n'efface pas les passes précédentes.

### Exemples

Les noms `idx-v2`, `idx-v1`, `sh-ops`, `sh-analytics`, `cm`, `mc`, `team_a_*` et `team_b_*` désignent des rôles génériques. Ils ne désignent pas des équipements réels. Les variables de commandes doivent être renseignées depuis l'inventaire cible. Aucune adresse ni identité de connexion n'est fournie.

Les blocs `ini` décrivent les fichiers Splunk ou les drop-ins. Les blocs `bash` contiennent une action ou une consultation identifiable. Les blocs `spl` contiennent des recherches. N'ajoutez pas de secret à une commande. Utilisez un canal d'authentification approuvé, sans secret en argument ou dans les journaux.

Chaque chapitre possède un H1 unique et une section Sources finale. Comme les handbooks français du dépôt, ce livre n'utilise pas de frontmatter YAML. Aucune traduction anglaise n'est requise par la convention du dépôt ; cette édition est française uniquement.

## Sources globales

La référence de syntaxe de cette édition est constituée des spécifications **livrées avec Splunk Enterprise 10.4.5** :

- `etc/system/README/workload_pools.conf.spec` ;
- `etc/system/README/workload_rules.conf.spec` ;
- `etc/system/README/workload_policy.conf.spec` ;
- les valeurs effectives, l'aide native et les journaux du même build.

Les résultats génériques sont consolidés dans le [chapitre 03](./03-resultats-qualification.md). Les preuves d'exploitation ne sont pas incorporées à ce livre public. Les chiffres sont des observations historiques, pas un état courant de machines.

Pointeurs documentaires complémentaires, déjà référencés dans la KB :

- [Fonctionnement WLM, documentation Splunk 10.0](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/10.0/workload-management-overview/how-workload-management-works).
- [Déploiement distribué, documentation Splunk 10.0](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/10.0/configure-workload-management/configure-workload-management-on-distributed-deployments).
- [Préparer Linux et cgroups v2, documentation Splunk 10.2](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/10.2/set-up-linux-for-workload-management/configure-cgroups-v2-in-splunk-enterprise).
- [Monitoring Console WLM, documentation Splunk 10.0](https://help.splunk.com/en/splunk-enterprise/administer/manage-workloads/10.0/monitor-workload-management).
- [Cgroups v2, documentation du noyau Linux](https://docs.kernel.org/admin-guide/cgroup-v2.html).
- [Contrôleur mémoire cgroups v1, documentation du noyau Linux](https://docs.kernel.org/admin-guide/cgroup-v1/memory.html).

Ces pages Web ne sont pas revérifiées par un accès réseau pour cette édition. Une référence 10.0 ou 10.2 ne valide pas un résultat 10.4.5. La documentation noyau en ligne peut évoluer ; confrontez-la au noyau installé.

## Version de cette édition

**Édition 1.0, 24 novembre 2026.** Les conclusions d'exécution portent uniquement sur Splunk Enterprise **10.4.5**, les deux environnements Linux décrits et les variantes reçues. Aucun résultat d'exécution **10.2** n'est disponible.
