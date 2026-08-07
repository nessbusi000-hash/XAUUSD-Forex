#!/usr/bin/env python3
"""Mesure une strategie retail classique (MACD) avec le meme protocole que SMC.

Porte la strategie de https://github.com/3aLaee/xauusd-trading-bot dans notre
moteur et la mesure sur son timeframe natif, le M1, reconstruit a partir de
ticks (voir `backtest/ticks_to_m1.py`). A defaut de M1, retombe sur le M15.

Le depot laisse deux ambiguites que ce script tranche par la mesure :
  * `PIP_SIZE` vaut 0,10 dans le README mais 0,01 par defaut dans le code — a
    0,01 le stop est plus petit que le spread ;
  * le README annonce de meilleurs resultats en session de Londres.

    python3 backtest/baseline_macd.py
    python3 backtest/baseline_macd.py --data backtest/data/XAUUSDm15.csv --tf M15
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import Backtester, ExecConfig, SmcConfig, load_csv  # noqa: E402
from smc.baselines import MacdPriceAction  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
M1_DATA = os.path.join(HERE, "data", "XAUUSDm1_2018.csv")
M15_DATA = os.path.join(HERE, "data", "XAUUSDm15.csv")

# Spread moyen mesure sur les 18,8 M de ticks de 2018 (ticks_to_m1.py).
MEASURED_SPREAD = 0.226
KILLZONES = {9, 10, 11, 14, 15, 16, 17}


def t_of(rs) -> float:
    n = len(rs)
    if n < 3:
        return 0.0
    m = sum(rs) / n
    sd = (sum((x - m) ** 2 for x in rs) / (n - 1)) ** 0.5
    return m / (sd / math.sqrt(n)) if sd else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    ap.add_argument("--tf", default=None)
    ap.add_argument("--spread", type=float, default=MEASURED_SPREAD)
    args = ap.parse_args()

    path = args.data or (M1_DATA if os.path.exists(M1_DATA) else M15_DATA)
    tf = args.tf or ("M1" if path.endswith("m1_2018.csv") else "M15")
    if not os.path.exists(path):
        print(f"Donnees introuvables : {path}", file=sys.stderr)
        return 1

    series = load_csv(path, tf)
    days = (series.time[-1] - series.time[0]).days
    # 5 jours calendaires, exprimes dans le pas de temps courant.
    hold = int(5 * 24 * 60 / {"M1": 1, "M5": 5, "M15": 15}.get(tf, 15))

    print(f"{os.path.basename(path)} ({tf}) : {len(series):,} bougies, "
          f"{series.time[0].date()} -> {series.time[-1].date()} ({days} jours)")
    print(f"Spread applique : {args.spread:.3f} $\n")

    def cfg(**kw):
        base = dict(spread=args.spread, commission_per_lot=7.0, min_sl_dollars=0.05,
                    max_sl_dollars=60.0, max_hold_bars=hold)
        base.update(kw)
        return ExecConfig(**base)

    def run(strat, label, exec_cfg):
        res = Backtester(series, strat, exec_cfg, SmcConfig()).run()
        s = res.stats
        if not s.get("trades"):
            print(f"{label:<52} aucun trade")
            return
        rs = [t.r for t in res.trades]
        print(f"{label:<52} n={s['trades']:>6} wr={s['win_rate']:>5.1f}% "
              f"pf={s['profit_factor']:>5.2f} E={s['expectancy_r']:>+6.3f}R "
              f"ret={s['return_pct']:>+8.1f}% t={t_of(rs):>+8.2f}")

    print("--- Les deux conventions de pip du depot ---")
    run(MacdPriceAction("code", sl=1.5, tp=1.0), "PIP_SIZE=0,10 (README) : SL 1,50 / TP 1,00", cfg())
    run(MacdPriceAction("code", sl=0.15, tp=0.10), "PIP_SIZE=0,01 (defaut du code) : SL 0,15 / TP 0,10", cfg())

    print("\n--- Sans aucun frais, pour isoler leur poids ---")
    free = cfg(spread=0.0, commission_per_lot=0.0)
    run(MacdPriceAction("code", sl=1.5, tp=1.0), "PIP_SIZE=0,10, sans frais", free)
    run(MacdPriceAction("code", sl=0.15, tp=0.10), "PIP_SIZE=0,01, sans frais", free)

    print("\n--- Variante decrite par le README (cassure de niveau) ---")
    run(MacdPriceAction("readme", sl=1.5, tp=1.0), "variante README", cfg())

    print("\n--- Filtre de session ('better results during London session') ---")
    run(MacdPriceAction("code", sl=1.5, tp=1.0, session_hours=KILLZONES),
        "PIP_SIZE=0,10, sessions Londres + New York", cfg())

    print("\n--- Le filtre 'price action' retire-t-il des signaux ? ---")
    probe = MacdPriceAction("code")
    crossings = kept_code = kept_readme = 0
    for i in range(len(series)):
        before = probe.prev_diff
        sig = probe.on_bar(i, series, series, series, series)
        after = probe.prev_diff
        if before is None or i < probe.lookback + 31:
            continue
        if not ((after > 0 and before <= 0) or (after < 0 and before >= 0)):
            continue
        crossings += 1
        kept_code += 1 if sig is not None else 0
        window = slice(i - probe.lookback + 1, i + 1)
        res_l, sup_l = max(series.high[window]), min(series.low[window])
        c = series.close[i]
        if (after > 0 and c > res_l) or (after < 0 and c < sup_l):
            kept_readme += 1
    print(f"  croisements MACD                {crossings:>7}")
    print(f"  retenus par le filtre du code   {kept_code:>7}")
    print(f"  retenus par le filtre du README {kept_readme:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
