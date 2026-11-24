# 03. Résultats de qualification : T01 à T18, puis M1 à M6

## Portée des tableaux

**Tous les résultats d'exécution de ce chapitre sont observés en Splunk Enterprise 10.4.5.** Aucun n'est qualifié en 10.2. Les conditions communes sont celles du [chapitre 00](./00-perimetre-et-preuves.md).

Un PASS confirme un critère borné. Il ne signifie pas que tous les critères initiaux ont été satisfaits sans adaptation. Les passes interrompues, les changements de population et les échecs de témoin restent signalés.

## Essais du socle cgroups v2

| Essai et objet | Verdict et résultat observé en 10.4.5 | Conditions et chiffres clés | Garantie à ne pas en déduire ou partie non vérifiée |
| --- | --- | --- | --- |
| **T01. Emprunt CPU dans search** | **PASS borné.** Un seul pool fortement demandeur utilise presque tout le CPU de search. | Environ 70 s sur trois pairs ; part du pool dans search de 99,985 à 99,993 %. Search consomme environ 1,87 à 1,89 vCPU. Swap actif. | Ce pourcentage ne porte pas sur tout le CPU de la VM. Aucun débit ni résultat sans pagination garanti. |
| **T02. Partage CPU** | **PASS intégré 1:1. FAIL pour une exigence à chaque intervalle.** | Environ 95 s ; parts intégrées d'un pool de 50,05 %, 50,26 % et 50,09 %. Deux des 57 intervalles-pair de 5 s sortent de la bande 45 à 55 %, correspondant à ±10 % relatif autour de la cible 50 %. | Pas de partage instantané garanti. Poids inégaux non testés. |
| **T03. Emprunt entre catégories** | **PASS borné.** Search dépasse son poids CPU de 60 lorsque les autres catégories demandent peu. | Environ 80 s ; search de 1,877 à 1,897 vCPU, soit environ 94 % de deux vCPU. Ingest et misc restent positifs. | Pas de partage garanti lorsque toutes les catégories saturent simultanément. |
| **T04. OOM de pool** | **PASS sans swap pour le kill local d'un worker. Avec swap : plafond RAM atteint, pagination et aucun OOM.** | Pool à 20 %, limite de 240 734 208 octets. Swap désactivé sur le seul pair chargé. Témoin d'un autre pool intact ; démon principal conservé. | Le seuil est distribué aux trois pairs, pas isolé en configuration à un pair. Le pool utilisé diffère du scénario initial. Aucun OOM affiché dans une vue MC qualifié. DONE ne garantit pas les résultats. |
| **T05. Partition mémoire stricte** | **PASS borné après calibration du témoin. La passe précédente reste FAIL.** | Sans swap sur le pair chargé. CPU=mémoire et somme 100, défaut inclus. Pool sollicité à 20 %, témoin à 40 %. Pic du témoin seul : 279 691 264 octets ; plafond retenu : 481 468 416. Marge de catégorie positive dans les deux clichés encadrant le kill. | Le témoin à 10 % avait subi son propre OOM. Marge au kill encadrée à environ 0,5 s, pas mesure atomique. Poids diffusés aux trois pairs. Pas de maximum mémoire universel. |
| **T06. Ingestion sous pression search** | **PASS borné à la tenue nominale sous pression CPU.** | Fenêtre qualifiée de 330 s ; offre de 288 Kio/s. Rapprochement complet de 112 320 événements et 115 015 680 octets sur l'exécution. Files observées au plus à 2 %, retard maximal de 6 s. Search à environ 1,89 vCPU par pair. | Deux SH émetteurs, aucun job mémoire dédié. Swap actif et pagination persistante. Témoin de 30 s qualifiées issu d'une passe antérieure. Pic 3×, pression mémoire dédiée simultanée et débit maximal non qualifiés. Deux interruptions antérieures restent non concluantes. |
| **T07. Pool absent sur les pairs** | **PASS borné.** Repli vers le pool par défaut des pairs, autre famille inchangée. | Trois pairs ; six associations recherche/pair relues. Deux recherches rendent chacune 1 036 800 événements, comme leurs témoins. Retour des pools sans restart. Profil historique de 1 Gio. | Aucun partage de ressources sous saturation testé. La seule vue agrégée MC ne prouve pas le pool effectif d'un pair. |
| **T08. OOM ingest et démon principal** | **FAIL pour la survie du démon. Risque confirmé.** | Plafond ingest à 19 %, soit 326 709 248 octets, commun aux trois pairs. Pendant swapoff sur un seul pair, le noyau tue le MainPID. Systemd le relance ; NRestarts augmente de 1. Aucun nouveau générateur synthétique lancé. | Pas de débit ni de perte d'événements mesuré dans T08. Pas de régime stabilisé à swap nul : du swap est encore compté pendant la transition. La garde de RAM physique ne protège pas contre un plafond de catégorie trop bas. |
| **T09. Visibilité d'alert** | **PASS borné pour la visibilité propriétaire et la journalisation.** | Un job admin avec capacités WLM, puis un job user sans capacité WLM, sur le même SH. Message constaté dans le menu « Tâche ». Première journalisation vers 123 et 126 s depuis le début audité ; 13 et 18 entrées alert. | Le Job Inspector ouvert est rapporté par l'opérateur, pas montré par les captures du menu. Pas de vue native MC affichée, pas de visibilité par un tiers, pas de nécessité individuelle de chaque capacité démontrée. Les entrées répétées ne sont pas des messages Web distincts. |
| **T10. Précédence move/abort** | **PASS borné.** La règle de gauche l'emporte au franchissement étudié. | Un job temps réel par ordre, même prédicat. Move en tête : changement de pool et fin normale. Abort en tête : marqueur, message et fin des processus, sans move. | Le premier job finit moins d'une minute après son move. Aucun abort ultérieur après une nouvelle minute démontré. Déplacement sur chaque pair non relevé. |
| **T11. Base des plafonds** | **PASS après complément discriminant à froid.** Plafonds dérivés du MemoryMax du service, calculés au démarrage. | MemTotal constant ; plafond abaissé à chaud, restart, retour à chaud, second restart. Les valeurs détaillées figurent ci-dessous. Aucun OOM provoqué. | La première passe, où MemoryMax égale MemTotal converti, ne départageait pas les bases. Une seule passe discriminante, un seul pair, poids inchangés. Autre build et autre taille de page non testés. |
| **T12. Activation globale de l'admission** | **PASS borné pour le contraste effectif 0/1.** | Même filtre : six soumissions acceptées en OFF ; trois refus 400 sans recherche créée sur le prédicat en ON ; trois témoins hors prédicat réussis. Réception sur trois SH. Profil historique. | Clé entièrement absente non testée. Ce n'est pas un test de visibilité Web d'alert. |
| **T13. Alltime et exclusion d'app** | **PASS borné.** Filtre alltime et exclusion d'app conformes aux soumissions testées. | Après neuf acceptations de référence, six témoins acceptés et trois refus sans recherche créée. Profil historique. La restriction user=nobody reste documentaire. | Pas d'inventaire exhaustif des recherches internes touchées. Aucun compte réservé utilisé pour un essai runtime. |
| **T14. Prédicat index littéral** | **PASS admin, puis PASS borné non-admin en complément.** | La chaîne littérale index=* reçoit le pool de la règle ; une recherche nommant un index explicite reste dans le pool ad hoc. Deux jobs qualifiés par population. Preuve PID, dispatch et cgroup sur le SH. | Les passes non-admin avec erreurs distantes sont non concluantes. Droit temps réel temporaire et convergence des droits sur les pairs nécessaires au protocole. Pas de qualification de toutes les syntaxes SPL équivalentes. |
| **T15. Héritage des rôles** | **PASS pour les chaînes testées.** | Quatre jobs : parent direct contre enfant seul, admin et non-admin. Le parent est reconnu dans chaque placement. Champ REST de pool absent pour les non-admin, preuve cgroup positive. | Toutes les profondeurs, conflits de rôles et visibilité REST uniforme non vérifiés. |
| **T16. Retrait propre et retour d'un pair** | **PASS borné à un arrêt propre, avec offre réduite.** | Offre de 192 Kio/s sur deux producteurs survivants pendant 390 s. 74 880 événements rapprochés sans manque ni doublon. RF/SF satisfaits dans 40 clichés. Retour observé entre 4,773 et 14,404 s après soumission du start. | Ni crash brutal, ni perte de site, ni offre initiale à trois producteurs. L'intervalle de retour n'est pas toute l'indisponibilité ni un engagement de délai. |
| **T17. Délai des règles** | **PASS borné pour la durée native et l'effet abort.** | Seuil runtime>1m, recherches temps réel. Trois jobs ad hoc : runDuration de 62,410 à 62,440 s. Trois jobs planifiés : de 65,792 à 67,908 s. Borne murale haute observée de 68,782 s. | Pas de timestamp interne séparant décision résidente et action. Les trois jobs concurrents par mode ne sont pas trois campagnes indépendantes. Aucun SLA. |
| **T18. Cycles systemd/cgroups v2** | **PASS pour les 50 cycles à vide.** Aucun blocage reproduit. | Dix cycles sur un représentant de chacune des classes CM, pair, SH non-capitaine, deployer et MC. Nouveaux PID et débuts d'incarnation reçus. Profil historique de 1 Gio. | Avertissements cgroup conservés. SF inconnu pendant l'arrêt CM, temporairement non satisfait pendant les arrêts du pair, puis restauré. Aucun défaut sous charge exclu. |

## T11 : la démonstration discriminante

Les chiffres suivants sont des observations en octets, pas des valeurs à recopier. `MemTotal` reste à **1 719 537 664 octets** pendant toute la comparaison.

| État reçu | Plafond effectif de l'instance | ingest | misc | search |
| --- | ---: | ---: | ---: | ---: |
| Initial | 1 719 537 664 | 1 719 537 664 | 171 950 080 | 1 203 675 136 |
| Baisse à chaud, sans restart | 1 288 486 912 | 1 719 537 664 | 171 950 080 | 1 203 675 136 |
| Après restart au plafond abaissé | 1 288 486 912 | 1 288 486 912 | 128 847 872 | 901 939 200 |
| Retour à chaud, sans restart | 1 719 537 664 | 1 288 486 912 | 128 847 872 | 901 939 200 |
| Après restart à la référence | 1 719 537 664 | 1 719 537 664 | 171 950 080 | 1 203 675 136 |

La valeur systemd abaissée est **1 288 490 188**. Le noyau expose **1 288 486 912**, après arrondi à une page de 4096 octets. La baisse à chaud ne change pas les quatorze plafonds WLM pendant environ 30 s. Le démarrage suivant les recalcule. Les neuf pools search à 100 suivent leur catégorie.

**Conclusion observée en 10.4.5 :** après toute modification de MemoryMax, prévoyez le redémarrage de `splunkd`, puis recevez les plafonds. Appliquez le même contrôle au retour. L'essai ne distingue pas le nombre systemd brut du nombre noyau arrondi lorsque les poids choisis conduisent au même résultat final.

## Extension mixte cgroups v1/v2

M1 à M6 utilisent trois pairs RHEL v2 et deux pairs AlmaLinux v1. Les comparaisons détaillées portent sur un témoin v2 et un pair v1, sauf M5 et M6. Le second SHC est arrêté. Les unités v1 ont été régénérées nativement avant les essais.

| Essai et objet | Verdict et résultat observé en 10.4.5 | Chiffres et limites |
| --- | --- | --- |
| **M1. Placement et abort** | **PASS borné.** Même recherche placée dans le pool attendu sur v2 et v1, puis abort WLM. | Liens dispatch/PID et contrôleurs natifs concordants. Durée native de 60,928 s au cliché d'action. REST reste RUNNING avec isDone/isFailed vrais. Une exécution, pas tous les modes. |
| **M2. Emprunt et partage CPU** | **PASS intégré, pas de garantie à 5 s.** | Solo : 1,876 vCPU sur v2 et 1,909 sur v1, environ 56 s. Contention : part d'un pool dans search de 50,33 % sur v2 et 49,30 % sur v1, environ 76 s. Sur quinze intervalles par pair, un intervalle v2 et quatre v1 sortent de 45 à 55 %. Passe finale sans nouvel OOM. Les passes avec expansion mémoire restent invalidées pour qualifier le CPU. |
| **M3. Mémoire et OOM local** | **PASS pour le mécanisme, pas pour la complétude SPL.** Avec swap : pagination sans kill sur les deux modes. Sans swap sur le seul pair v1 : worker tué dans son pool, MainPID intact. | Pool v2 à 240 734 208 octets ; v1 à 251 113 472. Pics swap échantillonnés d'environ 689 et 503 millions d'octets, non supposés simultanés aux pics RAM. Compteur v1 oom_kill augmente de 1. DONE/isFailed=false masque l'échec distant. mvexpand tronque la sortie à 39 700 résultats. Le témoin v2 conserve le swap pendant la sous-phase sans swap v1. |
| **M4. Offline et retour v1** | **PASS pour un cycle propre.** | Offline arrête le service sans relance observée. Après start, le pair revient Up, WLM enabled=1/advanced, contrôleurs CPU et mémoire v1 et plafonds présents. Aucun délai garanti ni test de démarrage automatique au boot. |
| **M5. Défaut d'unité et audit** | **Trou d'audit confirmé.** Un pair sans WLM appliqué reste Up et sert les recherches. | Unité v2 copiée sur un pair v1 : WLM enabled=0, isSupported=1, mode=advanced, erreur de création des catégories. CM : cinq pairs Up, RF/SF satisfaits. Aucun signal WLM du CM, du job ordinaire ou de wlm_monitor dans la fenêtre. REST distribué explicite détecte le défaut. Unité v1 restaurée et enabled=1 reçu. |
| **M6. Cohérence des plafonds** | **PASS arithmétique.** | Soixante-dix comparaisons catégorie/pool sur cinq pairs conformes au plafond de service et à l'arrondi page. Aucun contraste de base exclusive dans ce lot. Le contraste discriminant reste celui de T11 sur v2. |

## Quatre conclusions opérationnelles

1. **Le CPU est empruntable.** Le partage doit se mesurer sur une fenêtre et par niveau. Une moyenne juste n'efface pas une excursion courte.
2. **Le swap change l'épreuve mémoire.** Un plafond RAM atteint n'est pas une preuve d'OOM. Un OOM de pool n'est pas forcément un abort WLM.
3. **La santé du cluster ne suffit pas.** Un pair Up peut ne pas appliquer WLM. Un job DONE peut manquer une contribution.
4. **La version fait partie du résultat.** Un fonctionnement sur le mélange testé ne certifie ni sa supportabilité ni son comportement en 10.2.

## Sources

- Résultats génériques consolidés de la qualification Splunk Enterprise 10.4.5 : séries CPU, compteurs cgroups, journaux noyau, messages de recherche, états systemd et contrôles natifs de cluster.
- Spécifications du même build pour distinguer contrat de configuration et observation : `workload_pools.conf.spec`, `workload_rules.conf.spec`, `workload_policy.conf.spec`.
- [Périmètre et méthode](./00-perimetre-et-preuves.md).
- [Contrôles d'exploitation associés aux conclusions](./05-exploitation-et-audit.md).
