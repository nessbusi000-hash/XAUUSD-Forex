# XAUUSD-Forex

Bot de trading pour XAUUSD (or) et bancs d'essai associes.

## Strategies

| # | Nom | Fichier | Logique | Statut |
|---|---|---|---|---|
| 1 | Weekly Grid | [`Trader.mq4`](Trader.mq4) | Moyenne 7 jours + plus haut de la semaine, grille d'ordres espaces de 100 points (MT4, timer 5 s) | historique, non backteste |
| 2 | SMC POI Continuation | [`strategies/SMC_ICT_EA.mq4`](strategies/SMC_ICT_EA.mq4) | Biais H4 (BOS/CHoCH) + Discount/Premium + Order Block / FVG non mitige + CHoCH M15 | backteste 2006-2025 — **perdante en l'etat** |
| 3 | SMC Liquidity Sweep | [`strategies/SMC_ICT_EA.mq4`](strategies/SMC_ICT_EA.mq4) | Chasse aux stops sur equal highs/lows + rejet + CHoCH M15 avec deplacement | backteste 2006-2025 sur 12 instruments — **perdante en l'etat** |

Les strategies 2 et 3 partagent le meme EA MetaTrader 4 (`InpMode` selectionne
l'une, l'autre ou les deux) et le meme moteur Python de backtest.

- Methodologie detaillee : [`docs/SMC_ICT.md`](docs/SMC_ICT.md)
- Resultats mesures et limites : [`docs/BACKTEST_SMC.md`](docs/BACKTEST_SMC.md)

> Sur 18 ans (2006-2025), les strategies 2 et 3 sont perdantes de facon
> statistiquement etablie (t = -2,9 et -2,4) et ne se distinguent pas d'entrees
> aleatoires a R:R equivalent — y compris sur les trois annees inedites
> 2022-2025. Portee sur 12 instruments (3 024 trades), la seule variante
> candidate ressort a -0,097 R avec t = -2,80 : son edge n'existait que sur
> l'or. L'EA demarre donc en mode alerte (`InpEnableTrading = false`).

## Backtest et analyse

```bash
./backtest/fetch_data.sh                                   # historique XAUUSD M15 2006-2025 (telecharge, fusionne, audite)
python3 -m pip install pandas                              # seule dependance
python3 backtest/tests/test_smc.py                         # tests du moteur
python3 backtest/run_backtest.py --strategy both --out backtest/results
python3 backtest/analyze.py                                # briefing SMC en 4 etapes
python3 backtest/benchmark.py                              # SMC vs entrees aleatoires
python3 backtest/robustness.py                             # fenetres independantes + test t
python3 backtest/forward_test.py                           # forward test sur source independante
python3 backtest/frequency.py                              # plafond de positions et signaux refuses
python3 backtest/multi_asset.py                            # meme config sur 12 instruments
python3 backtest/scan.py --strategy s3                     # etude in-sample / out-of-sample
python3 backtest/verify_data.py                            # audit des donnees (authenticite + coherence)
```

## Arborescence

```
Trader.mq4                  strategie #1 (grille hebdomadaire)
strategies/SMC_ICT_EA.mq4   strategies #2 et #3 pour MetaTrader 4
backtest/smc/core.py        moteur SMC : structure, liquidite, Order Blocks, FVG
backtest/smc/strategies.py  strategies #2 et #3
backtest/smc/engine.py      backtester (risque, frais, statistiques)
backtest/run_backtest.py    lancement d'un backtest
backtest/analyze.py         briefing SMC/ICT en 4 etapes
backtest/benchmark.py       comparaison avec des entrees aleatoires
backtest/scan.py            balayage parametrique in-sample / out-of-sample
backtest/robustness.py      tenue sur fenetres independantes + significativite (test t)
backtest/forward_test.py    forward test post-selection sur une source de donnees independante
backtest/frequency.py       frequence reelle des signaux et cout du plafond de positions
backtest/multi_asset.py     meme strategie sur 12 instruments (frequence + generalisation)
backtest/prepare_data.py    fusion des sources brutes en historique M15 canonique
backtest/verify_data.py     audit du fichier de donnees (reperes de marche + coherence)
backtest/tests/test_smc.py  tests unitaires
backtest/results/           rapports et journaux de trades
docs/                       methodologie et resultats
```
