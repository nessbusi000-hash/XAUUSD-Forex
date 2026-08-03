# Stratégie Order Block M15 — XAUUSD

Spécification de la stratégie « Order Block M15 avec biais multi-timeframe D1/H4/H1 ».

Ce document fait autorité sur le code : si `OrderBlockM15.mq4` diverge de ce qui suit,
c'est le code qui est en tort.

---

## 1. Principe

Trader la **mitigation d'un Order Block M15**, uniquement dans le sens du biais
directionnel des timeframes supérieurs (D1, H4, H1).

Un cycle complet se déroule en quatre temps :

1. **Biais** — les timeframes supérieurs disent long, short, ou rien.
2. **Structure** — le M15 casse une structure (BOS) dans ce sens.
3. **Order Block** — on identifie la bougie à l'origine de l'impulsion.
4. **Mitigation** — le prix revient dans la zone, on entre.

Pas de moyenne à la baisse, pas de martingale, pas de grille. Une position à la fois
par défaut, avec un stop loss systématique.

---

## 2. Biais multi-timeframe

Pour chaque timeframe T ∈ {D1, H4, H1}, le biais est calculé **sur bougies clôturées
uniquement** (décalage ≥ 1) :

```
EMA_T(n)  = EMA(close, InpBiasMAPeriod) sur T

biais_T = +1  si  close_T[1] > EMA_T[1]  ET  EMA_T[1] > EMA_T[2]
biais_T = -1  si  close_T[1] < EMA_T[1]  ET  EMA_T[1] < EMA_T[2]
biais_T =  0  sinon
```

Le biais global est **+1** si au moins `InpMinBiasAgreement` timeframes sont à +1 et
qu'aucun n'est à −1. Symétriquement pour −1. Sinon **0**, et on ne trade pas.

L'exigence « aucun en contradiction » est délibérée : elle coûte des trades mais évite
d'acheter un repli M15 pendant que le D1 se retourne.

> **Note anti-look-ahead.** L'usage du décalage 1 partout est le point critique.
> Lire `close_D1[0]` en cours de journée revient à connaître le futur intrabar et
> produit des backtests spectaculaires mais faux.

---

## 3. Structure M15

### 3.1 Points de swing

Un swing haut est confirmé au bar `k` si `high[k]` est le maximum strict de la fenêtre
`[k − F, k + F]`, avec `F = InpFractalBars`. Symétriquement pour un swing bas.

Conséquence : un swing n'est **confirmé qu'avec F bougies de retard**. Le code ne
considère jamais un swing avant que ses F bougies de droite existent.

### 3.2 Break of Structure (BOS)

- **BOS haussier** au bar `i` : `close[i] > ` dernier swing haut confirmé avant `i`.
- **BOS baissier** au bar `i` : `close[i] < ` dernier swing bas confirmé avant `i`.

Le scan couvre les `InpStructureLookback` dernières bougies M15 et retient le **BOS le
plus récent**.

---

## 4. Order Block

À partir du bar de BOS `i`, on remonte jusqu'à `InpOBSearchBars` bougies vers le passé :

- **OB haussier** : première bougie `j > i` avec `close[j] < open[j]` (dernière bougie
  baissière avant l'impulsion). Zone = `[low[j], high[j]]`.
- **OB baissier** : première bougie `j > i` avec `close[j] > open[j]`. Zone =
  `[low[j], high[j]]`.

### 4.1 Validité

L'OB est écarté si l'une de ces conditions est vraie :

| Condition | Motif |
|---|---|
| `age > InpMaxOBAgeBars` | zone périmée |
| OB haussier : une bougie a clôturé sous `low[j]` depuis la formation | structure invalidée |
| OB baissier : une bougie a clôturé au-dessus de `high[j]` depuis la formation | structure invalidée |
| l'OB a déjà servi à une entrée | pas de ré-entrée sur la même zone |

### 4.2 Déclencheur d'entrée

Entrée au marché dès que le prix courant pénètre la zone :

- **Achat** : `Ask ≤ high[j]` et `Ask ≥ low[j]`
- **Vente** : `Bid ≥ low[j]` et `Bid ≤ high[j]`

---

## 5. Risque

| Élément | Règle |
|---|---|
| Stop loss (achat) | `low[j] − InpOBBufferATR × ATR(14) M15` |
| Stop loss (vente) | `high[j] + InpOBBufferATR × ATR(14) M15` |
| Take profit | `entrée ± InpRewardRatio × distance_stop` |
| Taille | risque fixe de `InpRiskPercent` % de l'équité sur la distance au stop |
| Break-even | déplacement du stop à l'entrée à `InpBreakEvenR` × R (0 = désactivé) |
| Positions | `InpOneTradeAtATime` → une seule position ouverte sur le symbole/magic |
| Filtre spread | pas d'entrée si spread > `InpMaxSpreadPoints` |

Le lot est calculé, jamais fixe : c'est la distance au stop qui varie, pas le risque.

---

## 6. Ce que la stratégie ne fait pas

- Aucune moyenne à la baisse, aucun ajout sur position perdante.
- Aucune position sans stop loss.
- Aucune lecture de bougie non clôturée sur D1/H4/H1.

---

## 7. Sur le backtest de référence

La courbe d'équité qui a motivé ce travail affiche 100 → ~412 000 entre 2012 et 2022,
soit ×4 100 (~110 % annualisés composés). Ce chiffre n'a pas été reproduit ici et doit
être considéré comme **non vérifié** tant que les points suivants ne sont pas établis :

1. **Coûts de transaction** — spread, commission et swap effectivement déduits ?
   Sur XAUUSD M15, quelques milliers d'allers-retours à ~30 cents de spread suffisent à
   absorber la totalité du gain.
2. **Look-ahead multi-timeframe** — le biais D1/H4 était-il calculé sur bougie clôturée
   (décalage ≥ 1) ou sur la bougie en cours ? C'est la cause n°1 des courbes trop lisses.
3. **Ordre de remplissage intrabar** — quand SL et TP tombent dans la même bougie M15,
   lequel était réputé touché en premier ?
4. **Composition** — la forme exponentielle vient-elle du signal ou du sizing ?

Métriques à produire avant toute mise en production : max drawdown, nombre de trades,
profit factor, et une équité en **échelle logarithmique** (en linéaire, la comparaison
Buy & Hold est illisible).

---

## 8. Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `InpSymbol` | `""` | vide = symbole du graphique |
| `InpMagic` | `20260803` | identifiant des ordres de l'EA |
| `InpBiasMAPeriod` | `50` | période EMA du biais |
| `InpMinBiasAgreement` | `3` | timeframes devant s'accorder (1–3) |
| `InpFractalBars` | `2` | bougies de chaque côté pour un swing |
| `InpStructureLookback` | `200` | profondeur de scan M15 |
| `InpOBSearchBars` | `30` | recherche de l'OB en amont du BOS |
| `InpMaxOBAgeBars` | `96` | péremption de l'OB (24 h en M15) |
| `InpOBBufferATR` | `0.2` | marge du stop en ATR |
| `InpRiskPercent` | `0.5` | risque par trade, en % de l'équité |
| `InpRewardRatio` | `2.0` | multiple de R visé |
| `InpBreakEvenR` | `1.0` | seuil de mise à break-even (0 = off) |
| `InpMaxSpreadPoints` | `50` | spread maximum toléré |
| `InpOneTradeAtATime` | `true` | une position à la fois |
