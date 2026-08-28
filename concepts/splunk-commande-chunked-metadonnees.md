# Commande de recherche *chunked* : le décorateur ne dit pas ce que splunkd reçoit

Une commande de recherche personnalisée écrite avec le SDK Python Splunk
(protocole *chunked*, SCP v2) déclare son comportement par un décorateur :

```python
@Configuration(type="events", distributed=False)
class MaCommande(GeneratingCommand):
    ...
```

On lit ce décorateur, on en déduit que la commande n'est pas distribuée et
qu'elle produit des événements, et on l'écrit dans une spec. **La conclusion est
fausse une fois sur deux** : ce que le décorateur écrit et ce que splunkd reçoit
ne coïncident pas.

> Mesuré sur **Splunk Enterprise 9.4.x** avec le SDK Python Splunk vendorisé.
> La procédure de sonde plus bas permet de re-vérifier sur toute autre version —
> c'est elle qui fait foi, pas la table.

---

## 1. Ce que le SDK fait réellement

Dans `splunklib/searchcommands/generating_command.py`,
`ConfigurationSettings.iteritems()` :

- sous le protocole v2, le réglage **`distributed` est retiré** de la charge
  utile, **toujours**, quel que soit le type. Il ne circule jamais jusqu'à
  splunkd ;
- si `distributed` est faux **et** que le type vaut `streaming`, le type émis
  devient `stateful`.

D'où la correspondance réelle :

| Décorateur | Métadonnée émise | Distribuable ? | Sortie classée par Splunk comme |
|---|---|---|---|
| `@Configuration(distributed=True)` | `{"generating":true,"type":"streaming"}` | **oui** | événements |
| `@Configuration(distributed=False)` (ou rien) | `{"generating":true,"type":"stateful"}` | non | **événements** |
| `@Configuration(type="events")` | `{"generating":true,"type":"events"}` | non | événements |
| `@Configuration(type="reporting", …)` | `{"generating":true,"type":"reporting"}` | non | **résultats** |

Deux conséquences contre-intuitives :

1. **Un `distributed=False` ne se voit pas dans la métadonnée.** Ce qui porte la
   non-distribution est le **type**. Corollaire dangereux : une commande dont la
   non-distribution est « garantie » par son type la perd silencieusement le jour
   où le type change. Déclarer `distributed=False` explicitement **en plus** ne
   coûte rien et survit au changement de type.
2. **Retirer `type="events"` ne suffit pas à cesser de produire des événements.**
   Avec le défaut du SDK (`stateful`), le job rapporte toujours
   `eventCount = resultCount` et `/search/jobs/<sid>/events` sert les lignes.
   Seul `type="reporting"` donne `eventCount = 0` et un `/events` vide — le
   comportement des commandes génératives natives qui produisent des résultats.

---

## 2. Lire la métadonnée réelle : la sonde `getinfo`

On présente une poignée de main `getinfo` sur l'entrée standard du script
**déployé**, exécuté par l'interpréteur de Splunk, et on lit le premier chunk
qu'il rend. C'est littéralement ce que splunkd reçoit.

```python
# sonde.py — à exécuter sur l'instance, sous l'utilisateur qui fait tourner Splunk
import json, os, subprocess, tempfile

APP = os.path.join(os.environ["SPLUNK_HOME"], "etc", "apps", "<VOTRE_APP>")
dispatch = tempfile.mkdtemp(prefix="probe-")
searchinfo = {
    "args": [], "raw_args": [], "dispatch_dir": dispatch,
    "earliest_time": "0", "latest_time": "0",
    "search": "%7C%20macommande", "command": "macommande",
    "sid": "probe", "app": "search", "owner": "admin", "username": "admin",
    "session_key": "", "splunkd_uri": "https://127.0.0.1:8089",
    "splunkd_protocol": "https", "splunkd_host": "127.0.0.1",
    "splunkd_port": 8089, "maxresultrows": 50000,
    "splunk_version": "9.4.6",                 # obligatoire, cf. pièges
}
meta = json.dumps({"action": "getinfo", "preview": False,
                   "searchinfo": searchinfo}).encode()
payload = b"chunked 1.0," + str(len(meta)).encode() + b",0\n" + meta

# `splunk cmd python3` règle LD_LIBRARY_PATH tout seul — c'est le plus simple.
proc = subprocess.run(
    [os.path.join(os.environ["SPLUNK_HOME"], "bin", "splunk"), "cmd", "python3",
     os.path.join(APP, "bin", "macommande.py")],
    input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=dispatch, timeout=180)                  # PAS d'argument "__EXECUTE__", cf. pièges

header, _, rest = proc.stdout.partition(b"\n")
print(header.decode(), rest[:int(header.decode().split(",")[1])].decode())
```

Sortie attendue :

```
chunked 1.0,38,0 {"generating":true,"type":"reporting"}
```

**Faire aussi le témoin négatif** : copier le `bin/` ailleurs, basculer le
décorateur, relancer la sonde. Si le type rendu ne change pas, ce n'est pas le
décorateur qui le commande et la preuve ne vaut rien.

---

## 3. Les trois pièges de la sonde

### 3.1 Ne pas passer `__EXECUTE__` en argument

`SearchCommand.process()` choisit le protocole ainsi :

```python
if len(argv) > 1:
    self._process_protocol_v1(argv, ifile, ofile)
else:
    self._process_protocol_v2(argv, ifile, ofile)
```

**Tout** argument supplémentaire bascule sur le protocole **v1**, y compris le
`__EXECUTE__` que la documentation du SDK laisse croire nécessaire. Symptôme : la
sonde rend `error_message=unknown url type: '/services/server/info…'` suivi de
`\r\n\r\n`, jamais un chunk.

### 3.2 L'interpréteur a besoin des bibliothèques de Splunk

Appelé directement, le Python livré avec Splunk échoue à l'`import ssl` — les
`libssl` / `libcrypto` sont dans le `lib/` de Splunk — donc à l'import de
`splunklib.binding`. Symptôme : un traceback qui s'arrête sur `import ssl` et
laisse croire à un problème de `PYTHONPATH`. Passer par `splunk cmd python3`
règle l'environnement ; sinon, exporter `LD_LIBRARY_PATH` vers le `lib/` de
Splunk.

### 3.3 `searchinfo.splunk_version` est obligatoire

Absent, le SDK lève
`AttributeError: 'ObjectView' object has no attribute 'splunk_version'` — mais
**après** avoir écrit un chunk de métadonnée qui ne contient que l'inspecteur
d'erreurs, ce qui donne l'illusion d'une métadonnée vide. Ajouter la clé.

---

## 4. Vérification côté job (complémentaire, non substituable)

Depuis le contexte d'usage réel
(`POST /servicesNS/<user>/<app>/search/jobs`), sur le job terminé :

| Champ | Commande produisant des résultats | Commande produisant des événements |
|---|---|---|
| `eventCount` | `0` | `= resultCount` |
| `/search/jobs/<sid>/events` | vide | sert les lignes |
| `reportSearch` | rempli | vide |
| `isRemoteTimeline` / `searchProviders` | `False` / `[]` | idem sur standalone |

⚠️ Les deux dernières lignes **ne prouvent rien sur une instance standalone** :
sans pair, aucune distribution n'est observable. C'est la métadonnée qui fait foi.

⚠️ Le JSON d'une ligne de résultat **omet les champs à valeur vide**. Pour
énumérer les champs d'une sortie, lire le tableau `fields` de la réponse
`/results`, pas les clés d'une ligne.

Témoin de contrôle utile : `| makeresults count=3` rapporte `eventCount = 0`. Si
votre commande rapporte un `eventCount` peuplé, elle est bien dans le pipeline
des événements.

---

## Voir aussi

- [Diagnostiquer une commande de recherche custom en ligne de commande](./splunk-commande-custom-diagnostic-cli.md)
  — la même sonde sert à récupérer un message d'erreur que splunkd a jeté.
- [`btool` est une vue normalisée](./splunk-btool-vue-normalisee.md) — même
  famille : ce qu'un outil affiche n'est pas ce qui est écrit.
