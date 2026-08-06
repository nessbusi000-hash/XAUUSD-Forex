# Backtest SMC / ICT — XAUUSD (2006-2025)

Resultats **mesures**, pas estimes. Tout est reproductible :

```bash
./backtest/fetch_data.sh                 # telecharge, fusionne et audite l'historique
python3 backtest/run_backtest.py --strategy both --out backtest/results
python3 backtest/benchmark.py            # SMC vs entrees aleatoires
python3 backtest/robustness.py           # fenetres independantes + test t
python3 backtest/forward_test.py         # forward test sur source independante
python3 backtest/scan.py --strategy s3   # balayage parametrique IS / OOS
```

## Protocole

| Parametre | Valeur |
|---|---|
| Actif | XAUUSD, M15 (execution) / H1 (intermediaire) / H4 (biais) |
| Donnees | 424 996 bougies M15, 2006-11-27 -> 2025-03-21 (18,3 ans), heure serveur EET — authenticite verifiee, voir ci-dessous |
| Capital | 10 000 $, risque 1% par trade, 1 position a la fois |
| Frais | spread 0,30 $ paye en entier a l'entree + 7 $/lot de commission aller-retour |
| Execution | signal a la cloture de la bougie M15, execution a ce prix ; SL prioritaire sur TP si les deux sont dans la meme bougie |
| Look-ahead | aucun : les contextes H1/H4 ne recoivent une bougie qu'apres sa cloture, les fractales ne sont confirmees qu'apres `swing_right` bougies |

Le moteur est couvert par `backtest/tests/test_smc.py` (7 groupes de tests :
structure, FVG, liquidite, taille de position, P&L, priorite du SL, spread,
prise partielle).

## Authenticite des donnees (`backtest/verify_data.py`)

L'historique est fusionne a partir de deux depots publics par
`backtest/prepare_data.py` :

| Source | Couverture | Role |
|---|---|---|
| [BaseMax/XAUUSD-LSTM](https://github.com/BaseMax/XAUUSD-LSTM) (`XAU_15m_data.csv`) | 2004 -> 2025 | source principale |
| [ejtraderLabs/historical-data](https://github.com/ejtraderLabs/historical-data) (`XAUUSD/XAUUSDm15.csv`) | 2012 -> 2022 | recoupement et secours |

Les deux series se recouvrent sur 230 398 bougies et **coincident a 100% au cent
pres** (open, high, low, close), sans decalage horaire : meme lignee de donnees,
meme fuseau serveur EET. Au-dela du 21 mars 2025 la source principale devient
lacunaire (trous de 10, 17, 26 puis 81 jours) ; `prepare_data.py` conserve
automatiquement le plus long segment continu et coupe la.

Le fichier a ete confronte aux repere connus du marche de l'or — sortie complete
dans [`backtest/results/verify_data.txt`](../backtest/results/verify_data.txt) :

| Repere | Fichier | Marche | Ecart |
|---|---|---|---|
| Sommet de septembre 2011 | 1920,61 | ~1920 | 0,03% |
| Krach des 12-15 avril 2013 | 1321,54 | ~1321 | 0,04% |
| Plus bas du cycle, 3 dec. 2015 | 1046,23 | ~1046 | 0,02% |
| Creux d'aout 2018 | 1160,07 | ~1160 | 0,01% |
| Krach COVID, mars 2020 | 1451,13 | ~1451 | 0,01% |
| Record du 7 aout 2020 | 2074,87 | ~2075 | 0,01% |
| Pic du 8 mars 2022 (Ukraine) | 2070,30 | ~2070 | 0,01% |
| Sommet de fin octobre 2024 | 2790,09 | ~2790 | 0,00% |

Les 10 reperes passent, ainsi que les 8 controles de coherence (High/Low
englobant Open/Close, horodatages uniques et tries, absence de bougies le
week-end, sauts de cotation). Ce sont des cotations **bid d'un broker CFD**,
pas le fixing spot de Londres.

## Resultats — reglages par defaut, periode complete

| Metrique | #2 POI Continuation | #3 Liquidity Sweep |
|---|---|---|
| Trades | 1122 (61/an) | 957 (52/an) |
| Win rate | 23,6% | 21,6% |
| Profit factor | **0,82** | **0,80** |
| Esperance | **-0,147 R** | **-0,136 R** |
| Gain moyen / perte moyenne | +2,59 R / -0,99 R | +3,04 R / -1,01 R |
| Resultat net | -8 234 $ (-82,3%) | -7 700 $ (-77,0%) |
| Max drawdown | 85,0% | 82,4% |
| Test t sur l'esperance | **t = -3,01** | **t = -2,44** |

Le detail annuel est dans [`backtest/results/report.md`](../backtest/results/report.md),
le journal de trades dans `backtest/results/trades_s2.csv` et `trades_s3.csv`.

**Lecture** : le R:R est bien respecte (gain moyen ~2,6 a 3 R contre une perte
moyenne de 1 R), mais le win rate reste sous le seuil de rentabilite — a 1:3 il
faut plus de 25% de reussite pour etre a l'equilibre avant frais. Avec |t| > 2,
la perte n'est pas un accident d'echantillon : elle est statistiquement etablie
sur 18 ans.

## Test en avant : les 3 annees qui n'existaient pas dans l'etude initiale

L'etude precedente s'arretait au 4 mars 2022 et c'est sur elle que les reglages
par defaut ont ete figes. L'extension des donnees fournit donc un vrai test en
avant sur 2022-03-05 -> 2025-03-21, resultats dans
[`backtest/results/oos_2022_2025/report.md`](../backtest/results/oos_2022_2025/report.md) :

| Metrique | #2 POI Continuation | #3 Liquidity Sweep |
|---|---|---|
| Trades | 193 | 224 |
| Win rate | 23,8% | 22,8% |
| Profit factor | 0,77 | 0,94 |
| Esperance | -0,151 R | -0,025 R |
| Resultat | -27,4% | -8,9% |

Verdict inchange : les deux strategies restent perdantes sur des donnees
totalement inedites. La #3 s'ameliore nettement (PF 0,94 contre 0,80 sur la
periode complete) mais ne passe pas au-dessus de 1.

*Controle de non-regression : rejouee sur son ancienne fenetre 2012-2022 avec le
nouveau fichier de donnees, la #2 redonne 606 trades / PF 0,85 / -0,133 R et la
#3 663 trades / PF 0,71 — identique a l'etude precedente au trade pres.*

## Les filtres SMC apportent-ils un edge ? (`backtest/benchmark.py`)

Meme moteur, meme gestion du risque, entree **aleatoire** :

| Strategie | Trades | Win rate | PF | Esperance |
|---|---|---|---|---|
| #2 POI Continuation | 1122 | 23,6% | 0,82 | -0,147 R |
| #3 Liquidity Sweep | 957 | 21,6% | 0,80 | -0,136 R |
| Entree aleatoire (graine 7) | 1351 | 25,2% | 0,79 | -0,115 R |
| Entree aleatoire (graine 21) | 1305 | 24,1% | 0,78 | -0,154 R |
| Aleatoire dans le sens du biais H4 | 1328 | 25,2% | 0,81 | -0,117 R |
| Aleatoire contre le biais H4 | 1340 | 24,0% | 0,84 | -0,152 R |

**Les setups SMC tombent dans la fourchette du hasard**, et l'ecart entre deux
graines aleatoires (-0,115 R vs -0,154 R) depasse l'ecart entre le hasard et les
strategies SMC. Le filtre de biais H4 lui-meme ne separe pas : entrer dans son
sens (-0,117 R) ou contre (-0,152 R) donne des resultats du meme ordre.

Sans frais, l'esperance remonte a -0,095 R (#2) et -0,060 R (#3), contre
-0,003 R pour le hasard : les frais pesent, mais ne sont pas la cause de l'ecart.

## In-sample / out-of-sample (`backtest/scan.py`)

- **IS** : 2012-05 -> 2018-12, 96 configurations testees pour #2, 144 pour #3.
- **OOS** : 2019-01 -> 2025-03, sans aucune influence sur le choix des reglages.
  La fenetre IS n'a pas bouge quand les donnees ont ete etendues : les reglages
  classes ci-dessous ont donc ete choisis avant que 2022-2025 n'existe dans le
  projet.

Strategie #2 — les 6 meilleures configurations IS, evaluees ensuite en OOS :

| Reglages | IS esperance | OOS esperance |
|---|---|---|
| rr=4 mtf_poi=True window=8 OB | +0,114 R | **-0,129 R** |
| rr=4 mtf_poi=False window=8 OB | +0,091 R | **-0,241 R** |
| rr=3 mtf_poi=True window=8 OB | +0,086 R | **-0,054 R** |
| rr=2 mtf_poi=False window=8 OB | +0,080 R | **-0,105 R** |
| rr=3 mtf_poi=False window=8 OB | +0,079 R | **-0,230 R** |
| rr=3 mtf_poi=False window=16 OB | +0,067 R | **-0,224 R** |

Strategie #3 :

| Reglages | IS esperance | OOS esperance |
|---|---|---|
| rr=4 htf=bias pools=2 window=12 | +0,059 R | **-0,084 R** |
| rr=4 htf=premium_discount pools=3 window=12 | +0,053 R | +0,211 R |
| rr=4 htf=none pools=2 window=12 | +0,052 R | **-0,012 R** |
| rr=2 htf=bias pools=3 window=8 partiel | +0,033 R | **-0,052 R** |
| rr=3 htf=bias pools=3 window=8 partiel | +0,031 R | **-0,017 R** |
| rr=2 htf=premium_discount pools=3 window=12 killzone | +0,028 R | +0,077 R |

10 configurations sur 12 restent negatives hors echantillon.

## La configuration candidate (`backtest/robustness.py`)

Une seule configuration tient sur les quatre fenetres, dont deux qui n'ont
jamais servi a choisir quoi que ce soit — **#3 avec R:R 1:4, filtre
Premium/Discount et clusters de 3 sommets** :

| Fenetre | Statut | Trades | PF | Esperance |
|---|---|---|---|---|
| 2006-11 -> 2012-05 | inedite (anterieure) | 58 | 0,96 | -0,009 R |
| 2012-05 -> 2018-12 | in-sample | 112 | 1,04 | +0,053 R |
| 2019-01 -> 2022-03 | out-of-sample 1 | 60 | 1,20 | +0,180 R |
| 2022-03 -> 2025-03 | inedite (posterieure) | 60 | 1,27 | +0,221 R |
| **Periode complete** | | **287** | **1,13** | **+0,114 R** |

Resultat cumule : +31,5% en 18,3 ans pour 22,1% de drawdown maximal, soit
~16 trades par an.

**A ne pas surinterpreter.** Le test t sur les 287 trades donne **t = +0,91** :
l'esperance est *indiscernable de zero* au seuil de 5%. Cette configuration a
ete retenue parmi 144 candidates ; en trouver une de ce profil par hasard est
l'issue attendue. Ce qui la rend interessante, c'est la coherence du classement
(la fenetre la plus recente, jamais vue, est aussi la meilleure) — pas sa
significativite, qui n'est pas atteinte. Statut : **candidate a surveiller**,
pas strategie validee.

## Forward test de la configuration candidate (`backtest/forward_test.py`)

La candidate a ete retenue sur un historique s'arretant au **21 mars 2025**.
Elle a ensuite ete rejouee sur des bougies posterieures a cette date, issues
d'une **source independante** obtenue apres coup —
[ilahuerta-IA/backtrader-pullback-window-xauusd](https://github.com/ilahuerta-IA/backtrader-pullback-window-xauusd)
(`XAUUSD_5m_5Yea.csv`, bougies 5 min en UTC, converties vers l'heure serveur
EET/EEST ; ecart median residuel de 0,11 $ contre notre flux, soit la difference
normale entre deux brokers).

L'historique du projet sert de periode de chauffe — structure, POI et poches de
liquidite sont alimentes, mais aucun trade n'y est compte (`ExecConfig.trade_from`).

Fenetre : **2025-03-24 -> 2025-08-01**, 130 jours, 8 612 bougies M15.

| Strategie | Trades attendus | Trades observes | Win rate | PF | Esperance | Reference 2006-2025 |
|---|---|---|---|---|---|---|
| #3 candidate | ~5,6 | **2** | 100% | inf | +4,144 R | +0,114 R |
| #3 par defaut | ~18,6 | 21 | 29% | 1,38 | +0,243 R | -0,136 R |
| #2 par defaut | ~21,8 | 26 | 15% | 0,50 | -0,369 R | -0,147 R |

**Rien de concluant, et c'est le resultat le plus utile.** La candidate n'a
declenche que 2 trades en quatre mois — deux gagnants, mais deux trades ne
disent rien. Les reglages par defaut, eux, partent dans des directions
opposees sur la meme fenetre : la #3 ressort positive (+0,243 R alors qu'elle
vaut -0,136 R sur 18 ans) et la #2 nettement pire que son historique. Une
fenetre de quatre mois est domine par le bruit, exactement comme le benchmark
aleatoire le laissait prevoir.

### Combien de temps faudrait-il pour trancher ?

Avec l'esperance et la dispersion mesurees sur 18 ans, le nombre de trades
necessaire pour atteindre `|t| = 2` :

| Strategie | Trades requis | A la cadence observee |
|---|---|---|
| #3 candidate (E=+0,114 R, ecart-type 2,13) | 1 396 | **88,9 ans** |
| #3 par defaut (E=-0,136 R, ecart-type 1,73) | 647 | 12,4 ans |
| #2 par defaut (E=-0,147 R, ecart-type 1,64) | 498 | 8,1 ans |

C'est la conclusion pratique : meme si l'edge de la candidate etait reel, il est
**indetectable a l'echelle d'une vie de trading** a 16 trades par an. Le
protocole ne peut pas la valider ; seule une augmentation massive de la
frequence (autres actifs, timeframe inferieur, regles moins restrictives)
rendrait la question decidable.

## Limites connues

1. **Donnees** : un seul broker, prix bid uniquement, spread suppose constant a
   0,30 $ alors qu'il s'ecarte fortement sur les news (NFP, FOMC) — exactement
   les moments ou ces strategies se declenchent.
2. **Periode** : s'arrete au 21 mars 2025. Au-dela, aucune source M15 publique
   accessible depuis cet environnement ; pour prolonger, exporter depuis un
   terminal MetaTrader (script `FetchAllData.mq4` de
   [nvn01/MQL4-Script-fetching-XAUUSD-price-history](https://github.com/nvn01/MQL4-Script-fetching-XAUUSD-price-history))
   et passer le CSV a `backtest/prepare_data.py`.
3. **Intra-bougie** : le moteur ne connait que O/H/L/C en M15. L'ordre reel des
   evenements dans une bougie est inconnu ; l'hypothese retenue (SL avant TP)
   est pessimiste mais grossiere.
4. **Discretion** : un trader SMC humain filtre visuellement (qualite de l'OB,
   contexte des news, saisonnalite). Ce code applique des regles mecaniques —
   il teste *une* formalisation de la methode, pas la methode dans son ensemble.
5. **Une position a la fois**, pas de pyramidage, pas de trailing stop.

## Conclusion

Avec 18 ans de donnees et un test en avant sur trois annees inedites, le verdict
de l'etude initiale se confirme et se renforce : **les reglages par defaut des
strategies #2 et #3 sont perdants de facon statistiquement etablie**, et ne se
distinguent pas d'entrees aleatoires a R:R equivalent.

La seule piste non refutee est la #3 filtree par Premium/Discount sur des
clusters de 3 sommets, positive sur quatre fenetres consecutives puis sur un
forward test de quatre mois (2 trades, 2 gagnants) — mais sans significativite
statistique, et le calcul de puissance donne **89 ans** de trading avant de
pouvoir trancher a sa cadence. Autrement dit : cette piste n'est pas
verifiable en pratique telle quelle. C'est precisement pour cela que l'EA
demarre en mode alerte.

Pistes qui restent a tester avec ce meme protocole : entree limite au 50% de
l'OB plutot qu'a la cloture du CHoCH, filtre de news macro, exigence de
confluence OB + FVG, trailing sur structure M15, et validation sur un second
actif.
