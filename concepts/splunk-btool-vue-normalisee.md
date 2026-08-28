# `btool` est une vue normalisée, pas un écho des fichiers source

`splunk btool <conf> list --debug` est l'oracle de référence pour savoir **quelle
définition gagne** dans l'empilement des couches de configuration. Il est
tentant de s'en servir aussi comme **inventaire des origines** : quel fichier
déclare quoi, quelles clés sont héritées, quelles stanzas existent.

C'est là que ça casse. La sortie de `btool` est **normalisée** : elle résout,
déséchappe, réécrit et parfois escamote. Toute comparaison littérale entre cette
sortie et les fichiers `.conf` que l'on parse soi-même produit du faux positif —
et les écarts ne sont documentés nulle part.

> Comportements relevés sur **Splunk Enterprise 9.4.x**. La **méthode** de sonde
> plus bas reste valable pour re-vérifier sur une autre version : c'est elle qui
> compte, pas la liste d'exceptions, qui peut bouger.

---

## 1. Le cas qui coûte le plus cher : l'en-tête `[default]`

Un outil qui identifie les définitions héritées par la **présence de l'en-tête de
stanza `[default]`** dans la sortie fonctionne sur la quasi-totalité des confs, et
part en vrille sur `inputs` : chaque clé héritée dans chaque stanza est prise pour
une définition propre.

```sh
splunk btool authorize list --debug | grep -c '\[default\]'   # -> 1
splunk btool inputs    list --debug | grep -c '\[default\]'   # -> 0
```

`etc/system/default/inputs.conf` déclare pourtant bien un `[default]`, et
l'héritage **est** expansé dans chaque stanza de la sortie. Seul l'**en-tête**
manque.

### La règle, mesurée

> `btool <conf> list --debug` émet un en-tête `[default]` **si et seulement si**
> un fichier source de la conf en déclare un — **à l'exception de `inputs`**,
> seule conf sur 77 sondées où l'en-tête est supprimé alors que l'expansion a
> bien lieu.

La règle vaut dans les deux sens : aucun en-tête n'apparaît sans déclaration
source. Elle ne dépend ni de la couche (`system` / app, `local` / `default`), ni
du nombre de stanzas, ni du nombre de clés, ni de la redéfinition des clés
héritées.

Le mécanisme interne n'est pas observable depuis `btool`. **Rien ne garantit que
l'exception reste unique d'une version à l'autre** — et c'est ce qui condamne
toute stratégie fondée sur l'en-tête, pas seulement sur `inputs`.

### Sonde causale, pour vérifier sur son propre socle

Une corrélation descriptive ne suffit pas : il faut **injecter** un `[default]`
inerte, conf par conf, et observer.

```sh
mkdir -p "$SPLUNK_HOME/etc/apps/zz_probe/local"
printf '[default]\nzzprobe = 1\n' > "$SPLUNK_HOME/etc/apps/zz_probe/local/<conf>.conf"
splunk btool <conf> list --debug | grep -E '\.conf +\[default\]$'   # en-tête émis ?
splunk btool <conf> list --debug | grep -c 'zzprobe = 1'            # expansion : > 0 même sans en-tête
rm -rf "$SPLUNK_HOME/etc/apps/zz_probe"
```

---

## 2. Les autres normalisations

Même famille de piège, mêmes conséquences sur un comparateur littéral :

| Ce que fait `btool` | Conséquence sur une comparaison naïve |
|---|---|
| **Résout les variables et les chemins relatifs** dans les noms de stanza — `[batch://$SPLUNK_HOME/…]` sort en chemin absolu | La stanza de la sortie n'est pas celle du fichier : aucun rapprochement par égalité de chaîne |
| **Déséchappe les antislashs doublés** dans les noms de clé | Idem, sur les clés — fréquent sur les confs Windows |
| **Émet des définitions sans préfixe de chemin** : valeurs synthétisées, sans fichier d'origine | Un parseur qui suppose « une ligne = un fichier » produit des entrées orphelines ou plante |
| **Expanse l'héritage `[default]`** dans chaque stanza héritière | Sans l'en-tête, impossible de distinguer l'héritée de la propre |

Ajouter que la sortie n'est **pas** « une ligne = un enregistrement » : une
définition peut s'étaler, et le chemin affiché pour une ligne d'héritage est
celui du **porteur**, pas celui de l'héritier.

---

## 3. Le remède

**Ne jamais dériver les origines de la sortie `btool`.** Deux sources, deux rôles :

- **Les fichiers `.conf`, parsés soi-même** → l'inventaire des définitions et de
  leurs origines. C'est la seule source qui dit littéralement ce qui est écrit où.
- **`btool --debug`** → l'oracle du **verdict de précédence**, et rien d'autre.
  On lui demande « qui gagne », jamais « qui a déclaré ».

Quand il faut confronter les deux — par exemple pour vérifier qu'un parseur
maison reproduit bien la précédence — **normaliser des deux côtés avant de
comparer**, et garder l'émission littérale côté sortie. Normaliser pour comparer
et émettre littéralement sont deux opérations distinctes ; les confondre fait
perdre l'origine réelle.

---

## 4. La leçon transposable

Un outil de l'éditeur qui **affiche** un état interne n'est pas une API. Sa
sortie est faite pour être lue par un humain : elle simplifie, elle résout, elle
escamote ce qui n'aide pas à la lecture. Trois occurrences de la même famille sur
un seul projet ont suffi à établir la règle.

Corollaire pratique : quand un outil sert d'oracle dans une chaîne automatisée,
écrire noir sur blanc **ce qu'on lui demande exactement**, et tester ce contrat
avec une entrée qui doit le faire échouer. Un comparateur qui ne signale jamais
d'écart n'a pas prouvé qu'il n'y en a pas.

---

## Voir aussi

- [Métadonnée d'une commande de recherche *chunked*](./splunk-commande-chunked-metadonnees.md)
  — même famille : ce que le code déclare n'est pas ce que splunkd reçoit.
- [Diagnostiquer une commande de recherche custom en ligne de commande](./splunk-commande-custom-diagnostic-cli.md)
