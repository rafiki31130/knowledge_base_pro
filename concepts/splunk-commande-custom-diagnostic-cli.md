# Diagnostiquer une commande de recherche custom : ni le code de retour ni le message ne sont fiables

Deux pannes de diagnostic distinctes autour de `splunk search` et des commandes
de recherche personnalisées. Elles se combinent mal, et surtout **elles vont en
sens inverse** : dans un cas le message passe et le code de retour ment, dans
l'autre le code de retour est juste et le message disparaît.

> Mesuré sur **Splunk Enterprise 9.4.x**, avec un témoin par ligne du tableau.
> La procédure de rejeu en fin de fiche permet de re-vérifier sur une autre
> version.

---

## 1. La matrice

Même instance, même session, `splunk search "<recherche>" -maxout N` :

| Situation | Ce que l'utilisateur voit | Code de retour |
|---|---|---|
| Recherche valide | les résultats | `0` |
| Commande **inconnue de la plateforme** (`\| commandequinexistepas`) | `Unknown search command '…'.` | **`1`** |
| **Erreur de syntaxe SPL** (`\| eval x=(`) | `FATAL: Error in 'EvalCommand': The expression is malformed.` | **`17`** |
| Erreur émise par une commande **custom** en phase **`execute`** | `ERROR: <le message exact de la commande>` | **`0`** ⚠️ |
| Refus d'une commande **custom** en phase **`getinfo`** (option non reconnue) | un message générique, sans la cause | `17` |

### 1.1 Le message passe, le code ne suit pas

Une commande custom qui appelle `error_exit()` / `write_error()` pendant la phase
`execute` voit son message correctement rendu à l'utilisateur — mais le job
**n'est pas marqué en échec** : `splunk search` sort en `0`.

Conséquence directe : **un script de recette qui teste `$?` ne verra jamais un
refus applicatif.** Il est vert parce qu'il mesure son propre silence.

### 1.2 Le code est juste, le message se perd

Un refus émis pendant la phase `getinfo` — typiquement une option d'appel non
reconnue — produit ceci dans le `search.log` du dispatch :

```
WARN  ChunkedExternProcessor - Error adding inspector message: invalid level or message already exists
ERROR ChunkedExternProcessor - EOF while attempting to read transport header read_size=0
ERROR ChunkedExternProcessor - Error in '<cmd>' command: External search command exited unexpectedly with non-zero error code 1.
```

splunkd **rejette** le message d'inspecteur émis à ce stade, puis ne rapporte que
la mort du processus. La commande a bien dit pourquoi elle refusait ; personne ne
l'entend. Rien n'apparaît non plus dans le log applicatif de l'app, ni dans
`splunkd.log`.

---

## 2. Ce que le message générique veut vraiment dire

> `External search command exited unexpectedly with non-zero error code 1`

**Ne veut pas dire que la commande a planté.** Il veut dire : *la commande est
sortie en non-zéro et je n'ai pas su transmettre ce qu'elle disait*. Un refus
d'argument parfaitement propre produit exactement ce texte.

Diagnostiquer l'application sur cette phrase mène droit à chercher un défaut qui
n'existe pas. **Vérifier d'abord la syntaxe d'appel** — en particulier la
distinction entre options nommées (`option=valeur`) et arguments **positionnels**,
que le SDK traite très différemment : un argument positionnel écrit comme une
option inexistante déclenche ce refus, et donc ce message opaque.

Cas vécu : une commande dont les cibles sont positionnelles, appelée
`| macommande cible=x` au lieu de `| macommande x`. Refus légitime, message jeté,
et une heure passée à instruire un faux défaut sur une version fraîchement
publiée.

---

## 3. Récupérer le vrai message : sonde `getinfo`

Le seul moyen de lire ce que la commande a réellement répondu est de lui parler
directement, sans splunkd. Sur l'instance, **sous l'utilisateur qui fait tourner
Splunk** :

```python
import json, os, subprocess

APP = os.path.join(os.environ["SPLUNK_HOME"], "etc", "apps", "<VOTRE_APP>")
meta = {"action": "getinfo", "preview": False, "searchinfo": {
    "args": ["<arg1>"], "raw_args": ["<arg1>"],
    "dispatch_dir": "/tmp/probe", "sid": "probe", "app": "search",
    "owner": "admin", "username": "admin",
    "session_key": open("/tmp/sk.txt").read().strip(),
    "splunkd_uri": "https://127.0.0.1:8089", "splunk_version": "9.4.6",
    "search": "| <cmd> <arg1>", "earliest_time": "0", "latest_time": "0"}}
body = json.dumps(meta).encode()
p = subprocess.Popen(
    [os.path.join(os.environ["SPLUNK_HOME"], "bin", "splunk"), "cmd", "python3",
     os.path.join(APP, "bin", "<cmd>.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
out, err = p.communicate(b"chunked 1.0,%d,0\n" % len(body) + body, timeout=120)
print(p.returncode, out[:600].decode(), err.decode()[-2000:])
```

La réponse rend le message **verbatim**, celui que splunkd a jeté :

```
chunked 1.0,113,0
{"generating":true,"type":"reporting","inspector":{"messages":[["ERROR","Unrecognized option: cible=x"]]}}
```

### Obtenir la `session_key` sans exposer de mot de passe

Ne jamais passer un mot de passe en `argv` (visible dans `/proc` et dans
l'historique). Le faire lire depuis un fichier à droits restreints :

```sh
umask 077; printf '%s' "$PASSWORD" > /tmp/pw          # $PASSWORD hérité, jamais en argv
curl -sk -d username=admin --data-urlencode "password@/tmp/pw" \
  https://127.0.0.1:8089/services/auth/login \
  | sed -n 's:.*<sessionKey>\(.*\)</sessionKey>.*:\1:p' > /tmp/sk.txt
rm -f /tmp/pw
```

Pour le CLI lui-même, `SPLUNK_USERNAME` et `SPLUNK_PASSWORD` en variables
d'environnement sont acceptés — c'est l'alternative propre à `-auth user:pass`,
qui expose le mot de passe en ligne de commande. À noter au passage :
`splunk login` lit son prompt sur le terminal, pas sur l'entrée standard — le
scripter par un tube échoue.

Les trois pièges de la sonde (protocole v1 déclenché par tout argument
supplémentaire, bibliothèques de l'interpréteur, `splunk_version` obligatoire)
sont détaillés dans
[Métadonnée d'une commande de recherche *chunked*](./splunk-commande-chunked-metadonnees.md).

---

## 4. Ce qu'il faut en retenir

- **Ne jamais recetter une recherche sur `$?`.** Le code de retour distingue une
  erreur *de la plateforme* d'un succès ; il ne distingue pas un succès d'un refus
  *applicatif*. Contrôler la **sortie** — nombre de lignes attendu, absence de
  ligne `ERROR:` — ou interroger le statut du job par REST (`dispatchState`,
  `messages`).
- **Un contrôle qui ne rapporte jamais d'échec doit être éprouvé avec une entrée
  qui DOIT le faire échouer.** C'est la seule façon de distinguer « rien à
  signaler » de « je ne regarde pas ».
- **Le message générique n'accuse pas l'application.** Avant de suspecter un
  défaut, rejouer l'appel avec la syntaxe documentée, puis sonder en chunked si le
  doute persiste.

---

## 5. Rejeu

Sur une instance portant une commande custom, avec `SPLUNK_USERNAME` /
`SPLUNK_PASSWORD` en variables d'environnement :

```sh
splunk search '| <cmd> <arg-valide>'                  ; echo "rc=$?"   # 0, résultats
splunk search '| <cmd> <option-inexistante>=1'        ; echo "rc=$?"   # 17, message perdu
splunk search '| <cmd> <arg-valide> <filtre-invalide>'; echo "rc=$?"   # 0, message rendu
splunk search '| commandequinexistepas'               ; echo "rc=$?"   # 1
```

---

## Voir aussi

- [Métadonnée d'une commande de recherche *chunked*](./splunk-commande-chunked-metadonnees.md)
- [`btool` est une vue normalisée](./splunk-btool-vue-normalisee.md)
