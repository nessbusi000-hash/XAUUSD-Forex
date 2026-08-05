# Strategies SMC / ICT (Smart Money Concepts)

Documentation des strategies **#2** et **#3** du projet. Aucun indicateur retail
(RSI, MACD, supports/resistances classiques) n'intervient : seuls la structure de
marche, la liquidite et les zones institutionnelles sont utilises.

---

## 1. Architecture et biais du marche (Market Structure)

| Concept | Definition retenue dans le code |
|---|---|
| **Swing** | Fractale confirmee : `swing_left` bougies plus basses a gauche, `swing_right` a droite. Une fractale n'existe qu'apres confirmation (aucun look-ahead). |
| **BOS** (Break of Structure) | Cloture au-dela du dernier swing structurel **dans le sens du biais courant** -> continuation de l'order flow. |
| **CHoCH** (Change of Character) | Cloture au-dela du dernier swing structurel **contre le biais courant** -> premier signal de retournement. |
| **Dealing range** | Ancre sur l'origine du mouvement (dernier swing oppose au moment de la cassure), etendu au fil des bougies dans le sens de l'order flow. |
| **Premium / Discount** | `frac = (prix - range_low) / (range_high - range_low)`. `frac > 0.5` = Premium (zone de vente), `frac < 0.5` = Discount (zone d'achat). L'equilibrium est le Fib 50%. |
| **Phase** | Expansion si le prix est a moins de 25% du range de son extreme directionnel, sinon Retracement. |

Implementation : `backtest/smc/core.py` -> `SmcContext._update_structure()`,
`_update_range()`, `premium_discount()`.

## 2. Liquidite et chasse aux stops (Liquidity Pools)

- Chaque swing confirme depose une poche de liquidite : **BSL** au-dessus
  (stops des vendeurs), **SSL** en dessous (stops des acheteurs).
- Deux swings dans une tolerance de `0.35 x ATR` fusionnent en un cluster :
  c'est un **equal highs / equal lows** (`count >= 2`), la cible privilegiee des
  algorithmes.
- Un **Liquidity Run** n'est reconnu que si la penetration depasse
  `0.15 x ATR` : un depassement de quelques cents n'est pas une chasse aux stops,
  c'est la formation d'un equal high. *(Ce detail change materiellement les
  resultats : sans lui, les clusters d'equal highs sont detruits par le bruit.)*

Implementation : `_register_pool()`, `_update_pools()`, `liquidity_targets()`.

## 3. Zones d'interet institutionnelles (POI)

- **Order Block** : derniere bougie de couleur opposee avant le deplacement qui
  casse la structure, a condition que l'impulsion depasse `1.0 x ATR`
  (filtre de deplacement). Zone = high/low complet de la bougie, 50% = equilibrium
  de l'OB.
- **FVG / Imbalance** : `low[i] > high[i-2]` (haussier) ou `high[i] < low[i-2]`
  (baissier), taille minimale `0.10 x ATR`.
- Un POI est **mitige** des que le prix revient dedans, **invalide** des qu'une
  bougie cloture de l'autre cote, et **perime** apres `zone_expiry` bougies.

Implementation : `_create_order_block()`, `_detect_fvg()`, `_update_zones()`.

## 4. Plans d'execution

### Strategie #2 - `S2_SMC_POI_Continuation`

1. Biais H4 etabli (BOS/CHoCH) ;
2. prix en Discount (achat) ou Premium (vente) du dealing range H4 ;
3. mitigation d'un OB / FVG H4 non touche ;
4. **CHoCH M15** dans le sens du biais dans les `confirm_window` bougies -> Sniper Entry ;
5. SL derriere le High/Low de l'OB (+ `0.5 x ATR M15`) ;
6. TP sur la premiere poche de liquidite opposee offrant `R:R >= 1:3` (sinon le
   setup est ecarte).

### Strategie #3 - `S3_SMC_Liquidity_Sweep`

1. Cluster d'equal highs / equal lows identifie sur M15 ;
2. balayage franc du niveau puis cloture de l'autre cote (rejet) ;
3. **CHoCH M15 avec deplacement** (bougie > 1 ATR ou FVG frais) dans les
   `sweep_window` bougies ;
4. filtre HTF optionnel (`none` / `bias` / `premium_discount`) ;
5. SL au-dela de l'extreme du balayage (+ `0.3 x ATR`) ;
6. TP sur la poche de liquidite opposee, `R:R >= 1:3`.

---

## Utilisation

```bash
# 1. Recuperer l'historique XAUUSD M15 (2012-2022)
./backtest/fetch_data.sh

# 2. Tests unitaires du moteur
python3 backtest/tests/test_smc.py

# 3. Backtest des deux strategies
python3 backtest/run_backtest.py --strategy both --out backtest/results

# 4. Briefing SMC en 4 etapes sur la derniere bougie
python3 backtest/analyze.py

# 5. Etude in-sample / out-of-sample
python3 backtest/scan.py --strategy s3
```

L'EA MetaTrader 4 correspondant est `strategies/SMC_ICT_EA.mq4`
(`InpMode` = strategie #2, #3 ou les deux ; `InpEnableTrading = false` par
defaut : mode alerte uniquement).

## Resultats

Les resultats mesures sont dans **[BACKTEST_SMC.md](BACKTEST_SMC.md)** — a lire
avant toute mise en production : sur XAUUSD 2012-2022, **les deux strategies
sont perdantes** et ne se distinguent pas statistiquement d'entrees aleatoires
a R:R equivalent.
