---
title: Splunk — détecter les erreurs d'authentification et d'autorisation en SHC
category: cheat-sheets
tags: [splunk, shc, authorize, authentication, rbac, troubleshooting, spl, audit, cheat-sheet]
created: 2026-08-14
---

# Splunk — détecter les erreurs d'auth en search head cluster — Cheat-sheet

> **Version** : recherches validées syntaxiquement et exécutées sur **Splunk
> Enterprise 9.4.6**. Les champs employés (`log_level`, `component`, `host`,
> `action`, `info`) sont stables sur les branches 9.x.

## À quoi ça sert

Après une modification d'`authorize.conf` ou d'`authentication.conf` — refonte de
rôles, mapping SAML/LDAP, retrait d'une capability —, les symptômes arrivent
**dispersés** : un utilisateur sans rôle à la connexion, des recherches qui rendent
zéro résultat, des refus de permission, parfois seulement sur *certains* search
heads. Ces trois recherches disent **combien**, **où**, et **qui subit**.

## 1. Combien, où, de quel type

```spl
index=_internal sourcetype=splunkd log_level IN (ERROR,WARN,FATAL)
  (role OR authorization OR authentication OR capability OR permission)
| eval categorie=case(
    match(_raw,"(?i)(no roles|rolemap|importRoles|defaultRolesIfMissing|role .*not)"), "1-rolemapping",
    match(_raw,"(?i)(not authorized|insufficient|permission|capabilit)"),              "2-autorisation",
    match(_raw,"(?i)authentic"),                                                        "3-authentification",
    match(_raw,"(?i)(authorize\.conf|authentication\.conf|invalid key|bad stanza|Invalid value)"), "4-parse-conf",
    true(), "5-autre")
| stats count as erreurs by host categorie component
| sort - erreurs
```

**Le `by host` n'est pas décoratif — c'est lui qui porte le diagnostic** (§4).

## 2. L'asymétrie entre membres, d'un coup d'œil

```spl
index=_internal sourcetype=splunkd log_level IN (ERROR,WARN,FATAL)
  (role OR authorization OR authentication OR capability OR permission)
| timechart span=15m count by host limit=20
```

Une courbe qui décolle **sur un seul membre** à une heure précise : édition locale
non répliquée. Le décrochage donne l'heure du fait générateur.

## 3. Ce que les utilisateurs subissent

```spl
index=_audit (action=login OR action=search) (info=failed OR info=denied OR info=canceled)
| stats count as evenements dc(user) as utilisateurs by action info host
| sort - evenements
```

`_internal` dit ce que Splunk a refusé, `_audit` dit **qui** l'a subi : les deux index
sont **disjoints** — l'un porte l'utilisateur sans le chemin de fichier, l'autre
l'inverse.

## 4. Lire le résultat

| Répartition par `host` | Interprétation |
|---|---|
| **Uniforme sur tous les membres** | Le bundle poussé est fautif — la configuration est cohérente, mais fausse |
| **Concentrée sur un membre** | **Dérive locale** : le fichier a été modifié sur ce membre seul, ou le redémarrage n'y a pas eu lieu |
| **Un membre sain, les autres en erreur** | Le membre sain est celui qui a redémarré — voir §5 |

| Signal croisé | Interprétation |
|---|---|
| `dc(user)` monte, erreurs `_internal` stables | **Rolemapping** : les comptes arrivent sans rôle |
| Erreurs `2-autorisation` en hausse, connexions normales | **Capability** retirée ou `srchIndexesAllowed` trop étroit |
| Catégorie `4-parse-conf` non vide | Fichier syntaxiquement invalide — la stanza en cause est nommée dans le message |

## 5. Le piège propre à ces deux fichiers

**`authorize.conf` et `authentication.conf` ne se rechargent pas à chaud** : ils
exigent un **redémarrage**. Conséquence directe en cluster — après une modification,
**l'écart entre membres persiste jusqu'au redémarrage de chacun**. Un membre
redémarré et deux qui ne le sont pas, c'est un même utilisateur avec des droits
différents selon le search head qui le sert, et le `timechart by host` du §2 le montre
immédiatement.

> **Ne pas se fier à un `configs/conf-authorize/_reload` qui répond `200`** : cet
> endpoint répond `200` à tout, y compris à une configuration inexistante. Le
> `_reload` du **handler dédié**, lui, est informatif — il rend `404` quand aucun
> rechargement n'est possible, ce qui est justement le cas ici.

## 6. Contrôles complémentaires

```spl
# le rôle attendu existe-t-il vraiment, et sur quel membre ?
| rest /services/authorization/roles splunk_server=*
| stats values(splunk_server) as membres by title
| where mvcount(membres) < <nombre_de_membres_du_cluster>
```

Un rôle absent d'un seul membre est une divergence de configuration, invisible tant
qu'aucun utilisateur ne s'y connecte.

```spl
# les comptes sans aucun rôle
| rest /services/authentication/users splunk_server=*
| where isnull(roles) OR roles=""
| table title splunk_server
```

## Voir aussi

- [Splunk RBAC (rôles, capabilities, héritage)](./splunk-rbac.md) — ce que chaque
  droit accorde, comment ils se composent, et comment en retirer un proprement.
- [Splunk — nettoyer une configuration locale](./splunk-nettoyage-config-locale.md) —
  les endpoints de rechargement, ce qui se recharge à chaud et ce qui exige un
  redémarrage.
