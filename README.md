# XAUUSD-Forex

Expert Advisors MetaTrader 4 pour XAUUSD.

## Contenu

| Fichier | Description |
|---|---|
| [`SPEC.md`](SPEC.md) | Spécification de la stratégie Order Block M15 |
| `OrderBlockM15.mq4` | EA implémentant cette stratégie |
| `Trader.mq4` | Ancien EA martingale — voir l'avertissement ci-dessous |

## OrderBlockM15.mq4

Order Block M15 filtré par un biais multi-timeframe D1/H4/H1 :

1. Biais directionnel calculé sur bougies **clôturées** de D1, H4 et H1 ;
2. Break of Structure sur M15 dans le sens du biais ;
3. identification de l'Order Block à l'origine de l'impulsion ;
4. entrée à la mitigation de la zone, avec stop loss et objectif en multiple de R.

Le lot est calculé pour risquer un pourcentage fixe de l'équité sur la distance au
stop. Une position à la fois, jamais d'ajout sur position perdante.

Les règles complètes et les paramètres sont dans [`SPEC.md`](SPEC.md).

### Installation

1. Copier `OrderBlockM15.mq4` dans `MQL4/Experts/` du dossier de données MT4 ;
2. compiler dans MetaEditor (F7) ;
3. attacher l'EA à un graphique **XAUUSD M15** et autoriser le trading automatisé.

> L'EA n'a pas été compilé lors de son écriture — MetaEditor n'est pas disponible dans
> cet environnement. Compiler et passer par le Strategy Tester avant tout usage.

## Statut

Aucun des deux EA n'a été validé en backtest ici. La courbe d'équité qui a motivé la
stratégie (×4 100 entre 2012 et 2022) n'est **pas reproduite** et reste à vérifier —
les réserves méthodologiques sont détaillées en section 7 de [`SPEC.md`](SPEC.md).

## Avertissement sur `Trader.mq4`

Cet EA est conservé pour référence historique. Il n'implémente pas la stratégie
Order Block : c'est une **martingale sans stop loss**, qui ajoute jusqu'à 10 positions
contre le marché. Cette structure est exposée à la ruine sur une tendance soutenue.
Il contient par ailleurs des défauts connus :

- `Ask`, `Bid` et `_Point` se réfèrent au symbole du graphique, pas à `mySymbol` ;
- `OrdersTotal()` compte les positions de tous les symboles, pas seulement XAUUSD ;
- les conditions d'achat et de vente peuvent se déclencher sur le même tick ;
- `maxPriceOfLastWeek` ignore `day7`, alors que la variable est calculée.

À ne pas exécuter sur un compte réel.
