#!/usr/bin/env python3
"""Multiplier la frequence en changeant d'actif — et tester la generalisation.

Lever le plafond de positions ne donne que ~13% de trades en plus (voir
`frequency.py`). Le vrai multiplicateur est le nombre d'actifs : 12 instruments
a ~16 trades par an font ~190 trades par an, et surtout ils fournissent une
mesure que XAUUSD seul ne peut pas donner — la strategie generalise-t-elle ?

Un edge SMC repose sur un comportement d'acteurs institutionnels cense exister
sur tous les marches liquides. S'il n'apparait que sur l'or, c'est du bruit.

Mise a l'echelle entre actifs :
  * les statistiques sont comparees en **R** (multiples de risque), qui sont
    sans dimension : la taille de contrat n'influe pas ;
  * le spread est fixe a 1,5 point de base du prix median, soit ~0,27 $ sur l'or
    a 1800 et ~1,3 pip sur EURUSD — l'ordre de grandeur du retail ;
  * les bornes de stop (min/max) sont exprimees en pourcentage du prix, calees
    sur celles utilisees pour l'or.

    python3 backtest/multi_asset.py
    python3 backtest/multi_asset.py --config s3_default --data-dir /chemin/vers/paires
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig,
    SweepConfig, SweepReversal, load_csv,
)

# Facteur de mise a l'echelle des exports ejtrader : les cotations y sont
# stockees en unites entieres, soit 10^digits.
SYMBOLS = {
    "XAUUSD": (100.0, 100.0),      # (diviseur de prix, taille de contrat)
    "EURUSD": (100_000.0, 100_000.0),
    "GBPUSD": (100_000.0, 100_000.0),
    "AUDUSD": (100_000.0, 100_000.0),
    "USDCHF": (100_000.0, 100_000.0),
    "USDCAD": (100_000.0, 100_000.0),
    "EURGBP": (100_000.0, 100_000.0),
    "EURCHF": (100_000.0, 100_000.0),
    "USDJPY": (1_000.0, 100_000.0),
    "EURJPY": (1_000.0, 100_000.0),
    "GBPJPY": (1_000.0, 100_000.0),
    "AUDJPY": (1_000.0, 100_000.0),
}

SPREAD_BP = 1.5e-4     # 1,5 point de base du prix
MIN_SL_PCT = 7.0e-4    # 0,07% du prix
MAX_SL_PCT = 4.0e-2    # 4% du prix

CONFIGS = {
    "candidate": (
        "#3 candidate (rr=4, Premium/Discount, pools=3, window=12)",
        lambda: SweepReversal(
            SweepConfig(min_rr=4.0, htf_filter="premium_discount", min_pool_count=3, sweep_window=12)
        ),
    ),
    "s3_default": ("#3 reglages par defaut", lambda: SweepReversal(SweepConfig())),
    "s2_default": ("#2 reglages par defaut", lambda: PoiContinuation(PoiConfig())),
}


def t_of(rs) -> float:
    n = len(rs)
    if n < 3:
        return 0.0
    mean = sum(rs) / n
    sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5
    return mean / (sd / math.sqrt(n)) if sd > 0 else 0.0


def find_csv(data_dir: str, symbol: str) -> str | None:
    for candidate in (
        os.path.join(data_dir, symbol, f"{symbol}m15.csv"),
        os.path.join(data_dir, f"{symbol}m15.csv"),
        os.path.join(data_dir, f"{symbol}M15.csv"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pairs"))
    ap.add_argument("--config", default="candidate", choices=sorted(CONFIGS))
    ap.add_argument("--max-positions", type=int, default=2)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()

    label, build = CONFIGS[args.config]
    print(f"=== {label} ===")
    print(f"Repertoire : {args.data_dir}\n")
    print(f"{'actif':<8} {'bougies':>9} {'periode':<24} {'trades':>7} {'/an':>6} "
          f"{'wr':>6} {'pf':>6} {'esperance':>10} {'t':>6}")

    all_r = []
    total_years = 0.0
    rows = 0

    for symbol, (divisor, contract) in SYMBOLS.items():
        path = find_csv(args.data_dir, symbol)
        if path is None:
            print(f"{symbol:<8} absent du repertoire")
            continue

        series = load_csv(path, "M15", scale=divisor)
        if args.start or args.end:
            from smc import slice_period
            series = slice_period(series, args.start, args.end)

        median_price = sorted(series.close)[len(series) // 2]
        exec_cfg = ExecConfig(
            contract_size=contract,
            spread=SPREAD_BP * median_price,
            min_sl_dollars=MIN_SL_PCT * median_price,
            max_sl_dollars=MAX_SL_PCT * median_price,
            max_positions=args.max_positions,
        )

        res = Backtester(series, build(), exec_cfg, SmcConfig()).run()
        years = (series.time[-1] - series.time[0]).days / 365.25
        total_years += years
        s = res.stats
        period = f"{series.time[0].date()}->{series.time[-1].date()}"

        if not s.get("trades"):
            print(f"{symbol:<8} {len(series):>9,} {period:<24} {'0':>7}")
            continue

        rs = [t.r for t in res.trades]
        all_r.extend(rs)
        rows += 1
        print(f"{symbol:<8} {len(series):>9,} {period:<24} {s['trades']:>7} "
              f"{s['trades'] / years:>6.1f} {s['win_rate']:>5.1f}% {s['profit_factor']:>6.2f} "
              f"{s['expectancy_r']:>+9.3f}R {t_of(rs):>+6.2f}")

    if not all_r:
        print("\nAucun trade sur l'ensemble des actifs.")
        return 1

    n = len(all_r)
    mean = sum(all_r) / n
    sd = (sum((x - mean) ** 2 for x in all_r) / (n - 1)) ** 0.5
    t = t_of(all_r)
    wins = sum(1 for x in all_r if x > 0)
    gross_win = sum(x for x in all_r if x > 0)
    gross_loss = -sum(x for x in all_r if x <= 0)

    print(f"\n{'=' * 96}")
    print(f"POOL DES {rows} ACTIFS")
    print(f"  Trades           : {n:,} ({n / (total_years / rows):.0f} par an tous actifs confondus)")
    print(f"  Win rate         : {wins / n * 100:.1f}%")
    print(f"  Profit factor    : {gross_win / gross_loss:.2f}" if gross_loss else "  Profit factor    : inf")
    print(f"  Esperance        : {mean:+.3f} R (ecart-type {sd:.2f})")
    print(f"  Test t           : {t:+.2f} "
          f"({'significatif' if abs(t) >= 2 else 'indiscernable de zero'} au seuil de 5%)")
    if mean != 0:
        need = (2.0 * sd / abs(mean)) ** 2
        per_year = n / (total_years / rows)
        print(f"  Pour |t| = 2     : {need:.0f} trades, soit {need / per_year:.1f} ans "
              f"a la cadence du pool")
    print("\nLes trades de differents actifs ne sont pas independants (correlations")
    print("entre paires, sessions communes) : le t du pool est donc optimiste.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
