# Splunk — Concepts

Fiches expliquant le fonctionnement interne de Splunk. Cibles typiques :

- Indexers, search heads, cluster master / manager node, deployer, deployment
  server : rôles et interactions.
- **Buckets** : hot / warm / cold / frozen / thawed, transitions, nommage,
  rolling, replication factor, search factor.
- **Clustering** : cluster d'indexers, cluster de search heads, captain.
- **Multisite** : sites, replication/search factor par site, affinity de
  recherche, bascule.
- **SmartStore** : cache local, remote store, eviction, particularités vs
  stockage classique.
- Gestion du cycle de vie des données, rétention, archivage.
- Licensing, pools, fairness.

Une fiche par concept, focalisée sur les principes et les pièges, sans détail
de configuration spécifique à un environnement.
