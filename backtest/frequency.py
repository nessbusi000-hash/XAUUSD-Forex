#!/usr/bin/env python3
"""Augmenter la frequence des signaux sans toucher aux regles d'entree.

Le verrou identifie par le forward test est la rareté des trades : a ~16 par an,
la configuration candidate demanderait 89 ans pour prouver son edge. Ce script
mesure le premier levier, celui qui ne change **aucune** regle d'entree : le
plafond de positions simultanees.

Quand une position est ouverte, tout nouveau signal est refuse. Le moteur les
compte desormais (`BacktestResult.skipped_signals`), ce qui donne la frequence
reelle de la strategie par opposition a sa frequence executee.

Attention : N positions simultanees a 1% de risque chacune, c'est jusqu'a N% de
risque en meme temps. L'esperance en R reste comparable, pas la courbe d'equity.

    python3 backtest/frequency.py
    python3 backtest/frequency.py --config candidate --max 10
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

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")

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


def t_stat(trades) -> float:
    rs = [t.r for t in trades]
    n = len(rs)
    if n < 3:
        return 0.0
    mean = sum(rs) / n
    sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5
    return mean / (sd / math.sqrt(n)) if sd > 0 else 0.0


def years_to_prove(trades, per_year: float) -> float:
    """Annees necessaires pour atteindre |t| = 2 a cette esperance et cadence."""
    rs = [t.r for t in trades]
    n = len(rs)
    if n < 3 or per_year <= 0:
        return float("inf")
    mean = sum(rs) / n
    sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5
    if mean == 0 or sd == 0:
        return float("inf")
    return ((2.0 * sd / abs(mean)) ** 2) / per_year


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--config", default=None, choices=sorted(CONFIGS))
    ap.add_argument("--max", type=int, default=10, help="plafond maximal teste")
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print(f"Donnees introuvables : {args.data}", file=sys.stderr)
        return 1

    series = load_csv(args.data, "M15")
    span_years = (series.time[-1] - series.time[0]).days / 365.25
    print(f"Donnees : {len(series):,} bougies M15, {series.time[0].date()} -> "
          f"{series.time[-1].date()} ({span_years:.1f} ans)\n")

    caps = [c for c in (1, 2, 3, 5, 10, 20) if c <= args.max]
    names = [args.config] if args.config else list(CONFIGS)

    for name in names:
        label, build = CONFIGS[name]
        print(f"=== {label} ===")
        print(f"  {'plafond':>8} {'trades':>7} {'/an':>6} {'refuses':>8} {'wr':>6} "
              f"{'pf':>6} {'esperance':>10} {'t':>6} {'DD':>7} {'ans pour |t|=2':>15}")

        for cap in caps:
            cfg = ExecConfig(max_positions=cap)
            res = Backtester(series, build(), cfg, SmcConfig()).run()
            s = res.stats
            if not s.get("trades"):
                print(f"  {cap:>8} aucun trade")
                continue
            per_year = s["trades"] / span_years
            need = years_to_prove(res.trades, per_year)
            print(f"  {cap:>8} {s['trades']:>7} {per_year:>6.1f} {res.skipped_signals:>8} "
                  f"{s['win_rate']:>5.1f}% {s['profit_factor']:>6.2f} "
                  f"{s['expectancy_r']:>+9.3f}R {t_stat(res.trades):>+6.2f} "
                  f"{s['max_dd_pct']:>6.1f}% {need:>14.1f}")
        print()

    print("Lecture : 'refuses' = signaux valides ecartes parce que le plafond etait")
    print("atteint. Si lever le plafond multiplie les trades sans degrader l'esperance,")
    print("la frequence gagnee est gratuite ; si l'esperance s'effondre, les trades")
    print("supplementaires etaient de moins bonne qualite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
