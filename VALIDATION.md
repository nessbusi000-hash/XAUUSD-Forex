# Protocole de validation — Order Block M15 XAUUSD

Checklist anti-biais appliquée à la stratégie décrite dans [`SPEC.md`](SPEC.md).

Aucune de ces cases n'est cochée à ce jour. Tant qu'elles ne le sont pas, la courbe
d'équité de référence (100 → ~412 000 entre 2012 et 2022) reste **non vérifiée**.

---

## 1. Les cinq biais

| Biais | Applicable ? | Statut | Traitement retenu |
|---|---|---|---|
| Look-ahead | **Oui, critique** | ⬜ à tester | Données point-in-time, décalage ≥ 1 sur tous les TF |
| Survivorship | Non | ✅ sans objet | Instrument unique et continu — XAUUSD ne « disparaît » pas |
| Overfitting | **Oui, fort** | ⬜ à tester | Walk-forward + réduction du nombre de paramètres |
| Sélection | Oui | 🟡 partiel | `SPEC.md` écrit avant toute optimisation — pré-enregistrement de fait |
| Coûts de transaction | **Oui, critique** | ⬜ à tester | Spread + commission + swap modélisés |

Le biais de survivance est le seul qui tombe naturellement ici. Les quatre autres
demandent un travail explicite.

---

## 2. Look-ahead — le test qui tranche

C'est le suspect n°1 pour une courbe aussi lisse.

**Invariant à vérifier** : à l'instant `t`, aucune décision ne doit dépendre d'une
donnée postérieure à `t`.

Points de contrôle dans `OrderBlockM15.mq4` :

- [ ] `TimeframeBias()` n'utilise que les décalages 1 et 2 — jamais 0. La bougie D1
      en cours ne doit pas être lue.
- [ ] `IsSwingHigh()` / `IsSwingLow()` refusent tout pivot dont les `F` bougies de
      droite n'existent pas encore (garde `shift - InpFractalBars < 0`).
- [ ] Le balayage de `FindActiveOrderBlock()` ne lit jamais un décalage < 1.
- [ ] Le déclenchement d'entrée n'utilise que Bid/Ask courants, pas le haut ou le bas
      de la bougie M15 en cours.

**Test de non-régression** : rejouer le backtest en décalant artificiellement tous les
signaux d'une bougie supplémentaire. Une stratégie saine perd un peu de performance.
Une stratégie qui lit le futur s'effondre.

---

## 3. Coûts de transaction

À modéliser, dans cet ordre d'importance sur XAUUSD M15 :

| Poste | Ordre de grandeur | Effet |
|---|---|---|
| Spread | 20–35 cents, très variable | Le poste dominant |
| Commission | ~7 $/lot A-R sur compte ECN | Proportionnel au nombre de trades |
| Swap | négatif des deux côtés | Marginal — les positions ne passent pas la nuit |
| Slippage | 1–3 points en conditions normales | Explose sur news (NFP, FOMC, CPI) |

- [ ] Spread **variable** (issu des données tick), pas une constante optimiste.
- [ ] Élargissement du spread modélisé sur les news et à l'ouverture asiatique.
- [ ] Test de sensibilité : refaire tourner à spread × 1,5 et × 2. Une stratégie
      viable survit à × 1,5.

**Test de rentabilité brute** : `gain_moyen_par_trade` doit rester nettement supérieur
au coût aller-retour. Si l'espérance par trade est de 40 cents pour 30 cents de coûts,
la stratégie n'a pas de marge — elle est un artefact de backtest sans frais.

---

## 4. Overfitting et walk-forward

`SPEC.md` définit **13 paramètres**. C'est beaucoup pour ~10 ans de données : chaque
paramètre libre est un degré de liberté supplémentaire pour coller au passé.

- [ ] Geler les paramètres structurels (`InpFractalBars`, `InpBiasMAPeriod`) sur des
      valeurs conventionnelles plutôt que de les optimiser.
- [ ] N'optimiser que `InpRewardRatio` et `InpMinBiasAgreement`, sur la fenêtre
      d'entraînement uniquement.

### Découpage walk-forward proposé

Entraînement de 24 mois, test de 12 mois, glissement de 12 mois :

```
F1: train 2012-2013 → test 2014
F2: train 2013-2014 → test 2015
F3: train 2014-2015 → test 2016
F4: train 2015-2016 → test 2017
F5: train 2016-2017 → test 2018
F6: train 2017-2018 → test 2019
F7: train 2018-2019 → test 2020
F8: train 2019-2020 → test 2021
F9: train 2020-2021 → test 2022
```

L'équité rapportée est la **concaténation des seules fenêtres de test**. Une courbe
tracée sur l'historique complet après optimisation sur ce même historique ne prouve
rien.

- [ ] Efficacité walk-forward (perf hors échantillon / perf en échantillon) > 0,5.
- [ ] Les paramètres retenus sont stables d'une fenêtre à l'autre. S'ils sautent à
      chaque refit, le signal n'existe pas.

---

## 5. Métriques à produire

La courbe d'équité seule ne suffit pas. Le minimum publiable :

- [ ] Nombre de trades (en dessous de ~200, rien n'est significatif)
- [ ] Profit factor
- [ ] Max drawdown, en % et en durée
- [ ] Espérance par trade, **nette de frais**
- [ ] Ratio de Sharpe ou de Sortino
- [ ] Équité en **échelle logarithmique** — en linéaire, la comparaison Buy & Hold est
      illisible, ce qui est précisément le défaut du graphique de référence
- [ ] Répartition des trades dans le temps : un gain concentré sur 2020 n'est pas une
      stratégie, c'est une position sur le COVID

---

## 6. Monte Carlo

- [ ] Rééchantillonnage de l'ordre des trades (1 000 tirages) → distribution du max
      drawdown. Le drawdown historique est un tirage parmi d'autres, presque toujours
      optimiste.
- [ ] Risque de ruine sur l'horizon visé.
- [ ] Suppression aléatoire de 10 % des trades → la performance doit tenir. Si elle
      s'effondre, tout repose sur une poignée de coups.

---

## 7. Critères de passage en réel

Aucune exécution sur compte réel avant que **tout** ce qui suit soit vrai :

1. Les quatre biais applicables sont traités et documentés ;
2. l'efficacité walk-forward dépasse 0,5 sur les fenêtres de test ;
3. la stratégie reste rentable à spread × 1,5 ;
4. le max drawdown Monte Carlo au 95e percentile est tolérable ;
5. au moins 3 mois de forward-test sur compte démo, cohérents avec le backtest.

---

*Checklist dérivée de la skill `backtesting-frameworks`
([wshobson/agents](https://github.com/wshobson/agents)), appliquée au cas XAUUSD.*
