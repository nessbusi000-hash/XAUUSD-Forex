# Backtest SMC / ICT — XAUUSD (2012-2022)

Resultats **mesures**, pas estimes. Tout est reproductible :

```bash
./backtest/fetch_data.sh
python3 backtest/run_backtest.py --strategy both --out backtest/results
python3 backtest/benchmark.py
python3 backtest/scan.py --strategy s2
python3 backtest/scan.py --strategy s3
```

## Protocole

| Parametre | Valeur |
|---|---|
| Actif | XAUUSD, M15 (execution) / H1 (intermediaire) / H4 (biais) |
| Donnees | 230 400 bougies M15, 2012-05-15 -> 2022-03-04 (~9,8 ans), export MetaTrader (heure serveur EET) — authenticite verifiee, voir ci-dessous |
| Capital | 10 000 $, risque 1% par trade, 1 position a la fois |
| Frais | spread 0,30 $ paye en entier a l'entree + 7 $/lot de commission aller-retour |
| Execution | signal a la cloture de la bougie M15, execution a ce prix ; SL prioritaire sur TP si les deux sont dans la meme bougie |
| Look-ahead | aucun : les contextes H1/H4 ne recoivent une bougie qu'apres sa cloture, les fractales ne sont confirmees qu'apres `swing_right` bougies |

Le moteur est couvert par `backtest/tests/test_smc.py` (7 groupes de tests :
structure, FVG, liquidite, taille de position, P&L, priorite du SL, spread,
prise partielle).

## Authenticite des donnees (`backtest/verify_data.py`)

Le dataset source est etiquete « Major Forex historical data ». XAU/USD *est*
une paire forex (l'once d'or contre le dollar, tradee en CFD chez les brokers
MT4/MT5), mais le fichier a ete confronte aux repere connus du marche de l'or —
`python3 backtest/verify_data.py`, sortie complete dans
[`backtest/results/verify_data.txt`](../backtest/results/verify_data.txt) :

| Repere | Fichier | Marche | Ecart |
|---|---|---|---|
| Krach des 12-15 avril 2013 | 1321,54 | ~1321 | 0,04% |
| Plus bas du cycle, 3 dec. 2015 | 1046,23 | ~1046 | 0,02% |
| Rebond post-Brexit, juillet 2016 | 1375,05 | ~1375 | 0,00% |
| Creux d'aout 2018 | 1160,07 | ~1160 | 0,01% |
| Sommet de septembre 2019 | 1556,98 | ~1557 | 0,00% |
| Krach COVID, mars 2020 | 1451,13 | ~1451 | 0,01% |
| Record du 7 aout 2020 | 2074,87 | ~2075 | 0,01% |

Le script controle aussi la coherence des bougies (High/Low englobant
Open/Close, horodatages uniques et tries, absence de bougies le week-end —
signature d'un instrument forex/CFD, sauts de cotation aberrants). Il renvoie 1
en cas d'echec, ce qui permet de l'utiliser comme garde-fou avant tout backtest
sur une nouvelle source de donnees.

Ce sont des cotations **bid d'un broker CFD**, pas le fixing spot de Londres :
c'est exactement ce que tradera l'EA sur MT4, mais les prix peuvent differer de
quelques dizaines de cents d'un broker a l'autre.

## Resultats — reglages par defaut, periode complete

| Metrique | #2 POI Continuation | #3 Liquidity Sweep |
|---|---|---|
| Trades | 606 (62/an) | 664 (68/an) |
| Win rate | 23,6% | 19,7% |
| Profit factor | **0,85** | **0,71** |
| Esperance | **-0,134 R** | **-0,215 R** |
| Gain moyen / perte moyenne | +2,65 R / -0,99 R | +3,02 R / -1,01 R |
| Resultat net | -5 898 $ (-59,0%) | -7 742 $ (-77,4%) |
| Max drawdown | 62,8% | 79,1% |
| Sorties TP / SL / temps | 87 / 450 / 69 | 111 / 529 / 24 |

Le detail annuel est dans [`backtest/results/report.md`](../backtest/results/report.md),
le journal de trades dans `backtest/results/trades_s2.csv` et `trades_s3.csv`.

**Lecture** : la mecanique fonctionne comme prevu (gain moyen ~3 R, perte moyenne
~1 R, donc le R:R 1:3 est bien respecte), mais le win rate reste sous le seuil de
rentabilite. A 1:3, il faut **plus de 25%** de reussite pour etre a l'equilibre
avant frais ; les deux strategies sont en dessous.

## Les filtres SMC apportent-ils un edge ? (`backtest/benchmark.py`)

Meme moteur, meme gestion du risque, entree **aleatoire** :

| Strategie | Trades | Win rate | PF | Esperance |
|---|---|---|---|---|
| #2 POI Continuation | 606 | 23,6% | 0,85 | -0,134 R |
| #3 Liquidity Sweep | 536 | 20,3% | 0,72 | -0,205 R |
| Entree aleatoire (graine 7) | 741 | 24,0% | 0,79 | -0,158 R |
| Entree aleatoire (graine 21) | 717 | 26,6% | 0,90 | -0,063 R |
| Aleatoire dans le sens du biais H4 | 757 | 25,1% | 0,81 | -0,129 R |
| Aleatoire contre le biais H4 | 739 | 23,8% | 0,78 | -0,166 R |

**Les setups SMC tombent dans la meme fourchette que le hasard.** L'ecart entre
deux graines aleatoires (-0,158 R vs -0,063 R) est plus grand que l'ecart entre
le hasard et les strategies SMC : sur cet echantillon, les filtres SMC ne
produisent pas d'edge mesurable.

Sans aucun frais, l'esperance remonte a -0,074 R (#2) et -0,133 R (#3) : les
frais expliquent une partie de la perte, pas sa totalite.

## In-sample / out-of-sample (`backtest/scan.py`)

- **IS** : 2012-05 -> 2018-12, 96 configurations testees pour #2, 144 pour #3.
- **OOS** : 2019-01 -> 2022-03, aucune influence sur le choix des reglages.

Strategie #2 — les 6 meilleures configurations IS, evaluees ensuite en OOS :

| Reglages | IS esperance | OOS esperance |
|---|---|---|
| rr=4 mtf_poi=True window=8 OB | +0,114 R | **-0,286 R** |
| rr=4 mtf_poi=False window=8 OB | +0,110 R | **-0,364 R** |
| rr=3 mtf_poi=False window=8 OB | +0,097 R | **-0,413 R** |
| rr=2 mtf_poi=False window=8 OB | +0,089 R | **-0,262 R** |
| rr=3 mtf_poi=True window=8 OB | +0,079 R | **-0,267 R** |
| rr=3 mtf_poi=False window=16 OB | +0,068 R | **-0,397 R** |

Strategie #3 :

| Reglages | IS esperance | OOS esperance |
|---|---|---|
| rr=4 htf=bias pools=2 window=12 | +0,078 R | **-0,208 R** |
| rr=4 htf=premium_discount pools=3 window=12 | +0,053 R | +0,180 R (n=60) |
| rr=4 htf=none pools=2 window=12 | +0,052 R | **-0,125 R** |
| rr=3 htf=bias pools=2 window=12 | +0,038 R | **-0,265 R** |
| rr=2 htf=bias pools=3 window=8 partiel | +0,033 R | **-0,060 R** |
| rr=3 htf=bias pools=3 window=8 partiel | +0,033 R | **-0,073 R** |

**11 configurations sur 12 s'effondrent hors echantillon.** La seule survivante
(#3 avec filtre Premium/Discount et clusters de 3 sommets) repose sur 60 trades
OOS : sur 144 configurations testees, en trouver une positive par hasard est
l'issue attendue, pas une preuve d'edge. A ne pas traiter comme un resultat
valide sans une validation independante (autre actif, autre periode, autre
broker).

## Limites connues

1. **Donnees** : un seul broker, prix bid uniquement, spread suppose constant a
   0,30 $ alors qu'il s'ecarte fortement sur les news (NFP, FOMC) — exactement
   les moments ou ces strategies se declenchent.
2. **Periode** : s'arrete en mars 2022. Ni 2022-2024, ni la hausse de 2025 ne
   sont couvertes.
3. **Intra-bougie** : le moteur ne connait que O/H/L/C en M15. L'ordre reel des
   evenements dans une bougie est inconnu ; l'hypothese retenue (SL avant TP)
   est pessimiste mais grossiere.
4. **Discretion** : un trader SMC humain filtre visuellement (qualite de l'OB,
   contexte des news, saisonnalite). Ce code applique des regles mecaniques —
   il teste *une* formalisation de la methode, pas la methode dans son ensemble.
5. **Une position a la fois**, pas de pyramidage, pas de trailing stop.

## Conclusion

En l'etat, ces deux strategies ne sont pas exploitables en reel sur XAUUSD.
Elles sont livrees comme **briques d'analyse et bancs d'essai** : le moteur
(structure, liquidite, OB/FVG) est teste et reutilisable, le protocole IS/OOS
et le benchmark aleatoire sont en place pour evaluer honnetement toute variante
future.

Pistes qui restent a tester avec ce meme protocole : entree limite au 50% de
l'OB plutot qu'a la cloture du CHoCH, filtre de news macro, exigence de
confluence OB + FVG, trailing sur structure M15, et validation sur un second
actif.
