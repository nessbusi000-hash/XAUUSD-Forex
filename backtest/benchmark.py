#!/usr/bin/env python3
"""Diagnostics : les filtres SMC apportent-ils quelque chose ?

Trois questions :
  1. Une entree ALEATOIRE avec le meme R:R fait-elle mieux/pire que les setups
     SMC ? (si equivalent, les filtres SMC n'apportent pas d'edge)
  2. Quelle part du resultat vient des frais (spread + commission) ?
  3. Le sens du trade (avec ou contre le biais H4) change-t-il quelque chose ?

    python3 backtest/benchmark.py
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    BULL, BEAR, Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig,
    SweepConfig, SweepReversal, load_csv,
)
from smc.engine import Signal  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")


class RandomEntry:
    """Entree aleatoire, meme structure de risque (SL en ATR, TP = R:R fixe)."""

    name = "Benchmark_Random"

    def __init__(self, prob=0.0035, sl_atr=2.0, rr=3.0, seed=7, follow_bias=None):
        self.prob, self.sl_atr, self.rr = prob, sl_atr, rr
        self.rng = random.Random(seed)
        self.follow_bias = follow_bias  # None | True (avec H4) | False (contre H4)

    def on_bar(self, i, ltf, mtf, htf, series):
        if ltf.n < 50 or ltf.atr <= 0 or self.rng.random() > self.prob:
            return None
        if self.follow_bias is None:
            direction = BULL if self.rng.random() < 0.5 else BEAR
        else:
            if htf.bias == 0:
                return None
            direction = htf.bias if self.follow_bias else -htf.bias

        cl = ltf.close[i]
        dist = self.sl_atr * ltf.atr
        if direction == BULL:
            return Signal(BULL, cl - dist, cl + self.rr * dist, tag="random")
        return Signal(BEAR, cl + dist, cl - self.rr * dist, tag="random")


def run(series, strategy, exec_cfg=None, label=""):
    res = Backtester(series, strategy, exec_cfg or ExecConfig(), SmcConfig()).run()
    s = res.stats
    if not s.get("trades"):
        print(f"{label:<44} aucun trade")
        return res
    print(
        f"{label:<44} n={s['trades']:>4} wr={s['win_rate']:>5.1f}% pf={s['profit_factor']:>5.2f} "
        f"E={s['expectancy_r']:>+6.3f}R ret={s['return_pct']:>+7.1f}% dd={s['max_dd_pct']:>5.1f}%"
    )
    return res


def main() -> int:
    m15 = load_csv(DATA, "M15")
    print(f"Periode : {m15.time[0]} -> {m15.time[-1]} ({len(m15):,} bougies M15)\n")

    costs = ExecConfig()
    free = ExecConfig(spread=0.0, commission_per_lot=0.0)

    print("--- 1) Setups SMC vs entree aleatoire (R:R 1:3, frais reels) ---")
    run(m15, PoiContinuation(PoiConfig(min_rr=3.0)), costs, "S2 POI Continuation")
    run(m15, SweepReversal(SweepConfig(min_rr=3.0)), costs, "S3 Liquidity Sweep")
    run(m15, RandomEntry(rr=3.0, seed=7), costs, "Random (direction aleatoire)")
    run(m15, RandomEntry(rr=3.0, seed=21), costs, "Random (autre graine)")
    run(m15, RandomEntry(rr=3.0, seed=7, follow_bias=True), costs, "Random dans le sens du biais H4")
    run(m15, RandomEntry(rr=3.0, seed=7, follow_bias=False), costs, "Random contre le biais H4")

    print("\n--- 2) Poids des frais (memes strategies, spread et commission a 0) ---")
    run(m15, PoiContinuation(PoiConfig(min_rr=3.0)), free, "S2 POI Continuation - sans frais")
    run(m15, SweepReversal(SweepConfig(min_rr=3.0)), free, "S3 Liquidity Sweep - sans frais")
    run(m15, RandomEntry(rr=3.0, seed=7), free, "Random - sans frais")

    print("\n--- 3) Sensibilite au R:R vise (frais reels) ---")
    for rr in (1.5, 2.0, 3.0, 5.0):
        run(m15, SweepReversal(SweepConfig(min_rr=rr)), costs, f"S3 - R:R min 1:{rr:g}")
        run(m15, PoiContinuation(PoiConfig(min_rr=rr)), costs, f"S2 - R:R min 1:{rr:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
