# Concepts transverses

Connaissances utiles à plusieurs sujets, qui ne sont pas spécifiques à un
outil.

Cibles typiques :

- **Logs** : formats courants (syslog, CEF, LEEF, JSON, Windows Event, Sysmon,
  audit Linux…), champs typiques, pièges de parsing.
- **Regex** : référence rapide, pièges (greedy, anchors, lookaround).
- **Réseau** : rappels TCP/IP, DNS, TLS, HTTP, proxies — vu sous l'angle
  « qu'est-ce qu'on voit dans les logs ».
- **Time** : timezones, epoch, formats ISO, drift d'horloge.
- **Encodages** : base64, URL, hex, unicode — détection et décodage.
- **Identités** : SID, UPN, sAMAccountName, OAuth/OIDC notions de base.

Chaque fiche reste générique et publiable.

## Fiches existantes

- [Formats de logs courants et leurs pièges de parsing](./formats-logs-et-pieges-parsing.md)
- [Regex pour les logs : greedy, ancres, lookaround](./regex-pour-logs.md)
- [Temps dans les logs : timezones, epoch, drift d'horloge](./temps-dans-les-logs.md)
- [Encodages à reconnaître et décoder : base64, URL, hex](./encodages-courants.md)
- [Identités dans les logs : SID, UPN, sAMAccountName, notions OIDC](./identites-dans-les-logs.md)
- [Git : modèle mental, vocabulaire et principes (HEAD, tree, worktree, prune…)](./git-modele-mental.md)
- [n8n : modèle mental (workflow, nœuds, items, expressions, credentials, executions)](./n8n-modele-mental.md)
- [Patrons de CI/CD pour déploiement Splunk](./cicd-deployment-patterns.md)
- [Cycle de vie d'un évènement Splunk : input → parsing → index → search](./splunk-cycle-de-vie-evenement.md)
- [Parsing phase : ce qui s'exécute où (UF vs HF)](./splunk-parsing-phase-uf-vs-hf.md)
- [Deployment Server](./splunk-deployment-server.md)
- [Comptes de service Splunk créés par fichiers de configuration, sans API](./splunk-comptes-de-service-par-fichiers.md)
- [`btool` est une vue normalisée, pas un écho des fichiers source](./splunk-btool-vue-normalisee.md)
- [Commande de recherche *chunked* : le décorateur ne dit pas ce que splunkd reçoit](./splunk-commande-chunked-metadonnees.md)
- [Diagnostiquer une commande de recherche custom : ni le code de retour ni le message ne sont fiables](./splunk-commande-custom-diagnostic-cli.md)
- [Historique de recherche Splunk : deux magasins, une bascule à sens unique](./splunk-search-history-storage.md)
- [Déclencheurs de rolling restart — SHC & cluster d'indexers](./splunk-rolling-restart-triggers.md)
- [Le bouton « Add Data » : quelles capabilities, et pourquoi il est masqué en SHC](./splunk-add-data-capabilities.md)
- [`splunk.secret` dans un Search Head Cluster — propagation à l'ajout de membre](./shc-splunk-secret-propagation.md)
- [Cycle de vie des buckets en cluster multisite](./splunk-buckets-multisite-lifecycle.md)
- [Rebalance d'un cluster d'indexeurs (multisite)](./splunk-rebalance-multisite.md)
- [ITSI + Federated Search](./splunk-itsi-federated-search.md)
