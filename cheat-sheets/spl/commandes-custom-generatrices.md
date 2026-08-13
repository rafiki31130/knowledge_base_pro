---
title: Commandes de recherche personnalisées — une génératrice doit rendre des résultats, pas des événements
category: cheat-sheets
tags: [splunk, spl, custom-search-command, generating-command, sdk, chunked, reporting, cheat-sheet]
created: 2026-08-13
---

# Commandes personnalisées — génératrice, résultats et événements

> **Version** : mesuré sur **Splunk Enterprise 9.4.6**, SDK Python `splunk-sdk` 2.1.1
> vendorisé, protocole **chunked** (`chunked = true` dans `commands.conf`). Le mécanisme
> décrit tient au SDK autant qu'à la plateforme : re-vérifier sur une autre version majeure
> du SDK.

## Le défaut, et pourquoi il passe inaperçu

Une commande de recherche personnalisée **génératrice** — celle qui ouvre le pipeline et ne
consomme aucune entrée — doit rendre des **résultats**, comme toutes les natives de sa
famille. Écrite avec le SDK sans précaution, elle rend des **événements** : l'interface
ouvre l'onglet *Events* au lieu de *Statistics*, et l'utilisateur reçoit une table qui se
comporte comme un flux de logs.

Rien ne le signale. Aucune erreur, aucun avertissement, tous les tests hors Splunk passent —
ils ne voient que les lignes produites, jamais leur classement par la plateforme. Le défaut
n'apparaît qu'en ouvrant l'interface, ce que les campagnes de tests automatisés ne font pas.

## Le comportement, mesuré

`GeneratingCommand` du SDK laisse la configuration `type` à `streaming`. À la sérialisation
des métadonnées, le SDK réécrit cette valeur en `stateful` — et Splunk classe alors la
sortie comme des **événements**.

| Commande | `eventCount` | `reportSearch` | endpoint `/events` |
|---|---|---|---|
| Génératrice sans `type` | **9** | vide | **9 lignes** |
| `\| rest /services/apps/local` | 0 | renseigné | vide |
| `\| metadata type=sourcetypes` | 0 | renseigné | vide |
| Même génératrice, `type="reporting"` | 0 | renseigné | vide |

Les deux natives donnent la **signature d'un rendu correct**, et la corrigée la reproduit
sans perdre une ligne.

## Le correctif

```python
@Configuration(type="reporting", local=True)
class MyInventoryCommand(GeneratingCommand):
    ...
```

**`type` passé au décorateur `@Configuration` est la seule voie qui fonctionne.**

> **Piège mesuré : la clé `type` de `commands.conf` est sans effet** sur une commande
> déclarée `chunked = true`, y compris après redémarrage de `splunkd`. Sous le protocole
> chunked, la configuration transmise à chaque exécution est celle que la commande **annonce
> elle-même** dans son échange de métadonnées ; le fichier de configuration ne la surcharge
> pas. Éditer `commands.conf` en croyant corriger le rendu est un aller-retour perdu.

## Ce que le correctif ne touche pas

Les commandes **streaming**, qui reçoivent des événements d'un pipeline amont, ne sont pas
concernées : `type` y est en lecture seule sur `StreamingCommand`, et une chaîne
`générative | streaming` rend le même nombre de lignes et les mêmes champs dans les deux
configurations. La question ne se pose que pour la commande qui **ouvre** le pipeline.

## Comment le vérifier soi-même

Le compteur d'événements du job discrimine sans ambiguïté, et il se lit sans interface :

```bash
# après avoir lancé la recherche, sur le job créé
curl -sk -u <user> "https://<sh>:8089/services/search/jobs/<sid>" \
  | grep -E 'eventCount|reportSearch'
```

**Pose toujours un témoin de contrôle** dans la même mesure — `| makeresults` ou
`| rest /services/apps/local`, dont on sait qu'elles rendent `eventCount = 0`. Sans témoin,
un compteur à zéro ne distingue pas « rendu correct » de « je n'ai rien mesuré ».

## La leçon de méthode, qui vaut au-delà de Splunk

Un socle de tests exécuté **hors** de la plateforme est **structurellement aveugle** à tout
ce que la plateforme décide : le classement de la sortie, l'analyse du nom de la commande,
le rendu de l'interface. Il peut être vert, exhaustif et honnête tout en ne disant rien de
ce que l'utilisateur voit.

La contrepartie tient en une phrase : **avant de livrer une commande, ouvrir l'interface et
la lancer**. Une seule exécution réelle, regardée par un humain, attrape ce qu'aucun nombre
de tests hors plateforme ne verra.

## Voir aussi

- [`tstats-summariesonly.md`](tstats-summariesonly.md) — une autre génératrice native, et
  son rendu de référence.
- [`splunk-admin.md`](../splunk-admin.md) — déclaration et déploiement d'apps.
