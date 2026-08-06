#!/usr/bin/env python3
"""Robustesse : une configuration tient-elle sur des fenetres independantes ?

Un backtest positif sur une periode ne prouve rien s'il a ete choisi parmi des
dizaines de variantes. Ce script repond a deux questions :

  1. la configuration tient-elle sur quatre fenetres disjointes, dont deux qui
     n'ont jamais servi a choisir quoi que ce soit ;
  2. son esperance est-elle statistiquement distinguable de zero (test t sur la
     serie des resultats en R) ?

    python3 backtest/robustness.py
    python3 backtest/robustness.py --config s3_candidate
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig,
    SweepConfig, SweepReversal, load_csv, slice_period,
)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")

# Fenetres disjointes. "inedite" = n'a servi ni a choisir les reglages (IS),
# ni a les valider une premiere fois (OOS 1).
WINDOWS = [
    ("2006-11-27", "2012-05-14", "inedite (anterieure a l'etude)"),
    ("2012-05-15", "2018-12-31", "in-sample (choix des reglages)"),
    ("2019-01-01", "2022-03-04", "out-of-sample 1"),
    ("2022-03-05", "2025-03-21", "inedite (posterieure a l'etude)"),
]

CONFIGS = {
    "s2_default": ("S2 reglages par defaut", lambda: PoiContinuation(PoiConfig())),
    "s3_default": ("S3 reglages par defaut", lambda: SweepReversal(SweepConfig())),
    # Seule configuration du balayage parametrique restee non negative hors
    # echantillon : R:R 4, filtre Premium/Discount, clusters de 3 sommets.
    "s3_candidate": (
        "S3 candidate (rr=4, Premium/Discount, pools=3, window=12)",
        lambda: SweepReversal(
            SweepConfig(min_rr=4.0, htf_filter="premium_discount", min_pool_count=3, sweep_window=12)
        ),
    ),
}


def stats_line(res) -> str:
    s = res.stats
    if not s.get("trades"):
        return "aucun trade"
    return (
        f"n={s['trades']:>4} wr={s['win_rate']:>5.1f}% pf={s['profit_factor']:>5.2f} "
        f"E={s['expectancy_r']:>+6.3f}R ret={s['return_pct']:>+7.1f}% dd={s['max_dd_pct']:>5.1f}%"
    )


def t_statistic(res) -> tuple:
    rs = [t.r for t in res.trades]
    n = len(rs)
    if n < 3:
        return n, 0.0, 0.0, 0.0
    mean = sum(rs) / n
    sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    return n, mean, sd, t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--config", default=None, choices=sorted(CONFIGS), help="par defaut : toutes")
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print(f"Donnees introuvables : {args.data}\nLancez d'abord backtest/fetch_data.sh", file=sys.stderr)
        return 1

    full = load_csv(args.data, "M15")
    names = [args.config] if args.config else sorted(CONFIGS)
    exec_cfg, smc_cfg = ExecConfig(), SmcConfig()

    for name in names:
        label, build = CONFIGS[name]
        print(f"\n=== {label} ===")

        for start, end, tag in WINDOWS:
            try:
                series = slice_period(full, start, end)
            except ValueError:
                print(f"  {start} -> {end}  {tag:<32} hors de la periode couverte")
                continue
            res = Backtester(series, build(), exec_cfg, smc_cfg).run()
            print(f"  {start} -> {end}  {tag:<32} {stats_line(res)}")

        res = Backtester(full, build(), exec_cfg, smc_cfg).run()
        n, mean, sd, t = t_statistic(res)
        print(f"  {'periode complete':<56} {stats_line(res)}")
        print(f"  test t sur l'esperance : E={mean:+.3f}R, ecart-type={sd:.2f}, "
              f"n={n} -> t={t:+.2f} "
              f"({'significatif' if abs(t) >= 2 else 'INDISCERNABLE DE ZERO'} au seuil de 5%)")

    print("\nRappel : |t| < 2 signifie que le resultat est compatible avec le hasard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
