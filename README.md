# XAUUSD-Forex

Bot de trading pour XAUUSD (or) et bancs d'essai associes.

## Strategies

| # | Nom | Fichier | Logique | Statut |
|---|---|---|---|---|
| 1 | Weekly Grid | [`Trader.mq4`](Trader.mq4) | Moyenne 7 jours + plus haut de la semaine, grille d'ordres espaces de 100 points (MT4, timer 5 s) | historique, non backteste |
| 2 | SMC POI Continuation | [`strategies/SMC_ICT_EA.mq4`](strategies/SMC_ICT_EA.mq4) | Biais H4 (BOS/CHoCH) + Discount/Premium + Order Block / FVG non mitige + CHoCH M15 | backteste — **perdante en l'etat** |
| 3 | SMC Liquidity Sweep | [`strategies/SMC_ICT_EA.mq4`](strategies/SMC_ICT_EA.mq4) | Chasse aux stops sur equal highs/lows + rejet + CHoCH M15 avec deplacement | backteste — **perdante en l'etat** |

Les strategies 2 et 3 partagent le meme EA MetaTrader 4 (`InpMode` selectionne
l'une, l'autre ou les deux) et le meme moteur Python de backtest.

- Methodologie detaillee : [`docs/SMC_ICT.md`](docs/SMC_ICT.md)
- Resultats mesures et limites : [`docs/BACKTEST_SMC.md`](docs/BACKTEST_SMC.md)

> Sur 2012-2022, les strategies 2 et 3 sont perdantes et ne se distinguent pas
> d'entrees aleatoires a R:R equivalent. L'EA demarre donc en mode alerte
> (`InpEnableTrading = false`).

## Backtest et analyse

```bash
./backtest/fetch_data.sh                                   # historique XAUUSD M15 2012-2022
python3 -m pip install pandas                              # seule dependance
python3 backtest/tests/test_smc.py                         # tests du moteur
python3 backtest/run_backtest.py --strategy both --out backtest/results
python3 backtest/analyze.py                                # briefing SMC en 4 etapes
python3 backtest/benchmark.py                              # SMC vs entrees aleatoires
python3 backtest/scan.py --strategy s3                     # etude in-sample / out-of-sample
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
backtest/tests/test_smc.py  tests unitaires
backtest/results/           rapports et journaux de trades
docs/                       methodologie et resultats
```
