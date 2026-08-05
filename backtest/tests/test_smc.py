#!/usr/bin/env python3
"""Tests unitaires du moteur SMC et du backtester (aucune dependance externe).

    python3 backtest/tests/test_smc.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from smc import BULL, BEAR, Backtester, ExecConfig, SmcConfig, SmcContext  # noqa: E402
from smc.data import Series  # noqa: E402
from smc.engine import Signal  # noqa: E402

FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {detail}")


def make_series(bars) -> Series:
    t0 = pd.Timestamp("2020-01-01 00:00:00")
    times = [t0 + pd.Timedelta(minutes=15 * i) for i in range(len(bars))]
    return Series(
        tf="M15",
        time=times,
        open=[b[0] for b in bars],
        high=[b[1] for b in bars],
        low=[b[2] for b in bars],
        close=[b[3] for b in bars],
        volume=[1.0] * len(bars),
        close_time=[t + pd.Timedelta(minutes=15) for t in times],
    )


# --------------------------------------------------------------------------- #
def test_structure():
    """Montee -> creux -> cassure du sommet = BOS haussier."""
    ctx = SmcContext("M15", SmcConfig(swing_left=2, swing_right=2, atr_period=5))
    # Prix montant, repli, puis cassure du sommet precedent.
    path = [100, 101, 103, 106, 105, 104, 103, 104, 106, 108, 110]
    for p in path:
        ctx.on_bar(p, p + 0.5, p - 0.5, p)

    check("structure: biais haussier detecte", ctx.bias == BULL, f"bias={ctx.bias}")
    check("structure: au moins un evenement", len(ctx.events) >= 1)
    check(
        "structure: dealing range defini",
        ctx.range_low is not None and ctx.range_high is not None and ctx.range_high > ctx.range_low,
    )
    frac = ctx.premium_discount(ctx.range_high)
    check("structure: haut du range = premium (1.0)", abs(frac - 1.0) < 1e-9, f"frac={frac}")
    frac = ctx.premium_discount(ctx.range_low)
    check("structure: bas du range = discount (0.0)", abs(frac) < 1e-9, f"frac={frac}")


def test_fvg():
    """Trois bougies avec un gap : low[i] > high[i-2] => FVG haussier."""
    ctx = SmcContext("M15", SmcConfig(atr_period=3, fvg_min_atr=0.0))
    ctx.on_bar(100, 101, 99, 100)
    ctx.on_bar(100, 106, 100, 105)  # bougie de deplacement
    ctx.on_bar(105, 108, 103, 107)  # low=103 > high[0]=101 => FVG 101-103
    fvgs = [z for z in ctx.zones if z.kind == "FVG" and z.direction == BULL]
    check("fvg: un FVG haussier detecte", len(fvgs) == 1, f"n={len(fvgs)}")
    if fvgs:
        z = fvgs[0]
        check("fvg: bornes correctes", abs(z.low - 101) < 1e-9 and abs(z.high - 103) < 1e-9,
              f"{z.low}-{z.high}")
        check("fvg: milieu = 50%", abs(z.mid - 102) < 1e-9)


def test_liquidity_pool():
    """Deux sommets au meme niveau = equal highs, puis balayage."""
    cfg = SmcConfig(swing_left=1, swing_right=1, atr_period=3, pool_tol_atr=1.0)
    ctx = SmcContext("M15", cfg)
    seq = [(100, 100.2, 99.8), (101, 105.0, 100.5), (100, 100.5, 99.5),
           (100, 105.05, 99.9), (99, 99.5, 98.0), (99, 99.4, 98.5)]
    for o, h, l in seq:
        ctx.on_bar(o, h, l, (h + l) / 2)
    eqh = [p for p in ctx.pools if p.side == BULL and p.count >= 2]
    check("liquidite: equal highs regroupes", len(eqh) >= 1, f"pools={[(p.level, p.count) for p in ctx.pools]}")

    ctx.on_bar(99, 106.0, 99, 99.5)  # balayage au-dessus des equal highs
    swept = [p for p in ctx.pools if p.side == BULL and p.swept]
    check("liquidite: balayage detecte", len(swept) >= 1)


class _StubStrategy:
    """Ouvre un unique trade a la bougie `at` avec SL/TP imposes."""

    def __init__(self, at, direction, sl, tp):
        self.at, self.direction, self.sl, self.tp = at, direction, sl, tp
        self.done = False

    def on_bar(self, i, ltf, mtf, htf, series):
        if i == self.at and not self.done:
            self.done = True
            return Signal(self.direction, self.sl, self.tp, tag="stub")
        return None


def test_engine_pnl():
    """1 lot XAUUSD = 100 onces : +10 $ de mouvement = +1000 $ par lot."""
    bars = [(1800, 1801, 1799, 1800)] * 5
    bars += [(1800, 1815, 1799, 1810)]  # touche le TP a 1810
    bars += [(1810, 1812, 1808, 1810)] * 3
    s = make_series(bars)

    cfg = ExecConfig(
        initial_equity=10_000, risk_pct=1.0, spread=0.0, commission_per_lot=0.0,
        min_sl_dollars=0.5, max_sl_dollars=100,
    )
    bt = Backtester(s, _StubStrategy(4, BULL, 1795.0, 1810.0), cfg, SmcConfig())
    res = bt.run()

    check("engine: un trade ferme", len(res.trades) == 1, f"n={len(res.trades)}")
    t = res.trades[0]
    check("engine: entree a la cloture du signal", abs(t.entry - 1800) < 1e-9, f"entry={t.entry}")
    check("engine: sortie au TP", t.reason == "TP" and abs(t.exit - 1810) < 1e-9, f"{t.reason}@{t.exit}")
    # Risque 1% de 10 000 = 100 $ ; SL a 5 $ => 100 / (5 * 100) = 0.20 lot
    check("engine: taille de position", abs(t.lots - 0.20) < 1e-9, f"lots={t.lots}")
    # 10 $ de gain * 0.20 lot * 100 = 200 $ ; R = 200 / 100 = 2
    check("engine: P&L", abs(t.pnl - 200.0) < 1e-6, f"pnl={t.pnl}")
    check("engine: multiple R", abs(t.r - 2.0) < 1e-6, f"r={t.r}")
    check("engine: equity mise a jour", abs(res.stats["final_equity"] - 10_200) < 1e-6)


def test_engine_sl_priority():
    """Si SL et TP sont dans la meme bougie, le SL doit primer (pessimiste)."""
    bars = [(1800, 1801, 1799, 1800)] * 5
    bars += [(1800, 1815, 1790, 1800)]  # touche SL (1795) ET TP (1810)
    bars += [(1800, 1801, 1799, 1800)] * 2
    s = make_series(bars)

    cfg = ExecConfig(initial_equity=10_000, spread=0.0, commission_per_lot=0.0,
                     min_sl_dollars=0.5, max_sl_dollars=100)
    res = Backtester(s, _StubStrategy(4, BULL, 1795.0, 1810.0), cfg, SmcConfig()).run()
    check("engine: SL prioritaire sur TP", res.trades[0].reason == "SL", res.trades[0].reason)
    check("engine: perte = -1R", abs(res.trades[0].r + 1.0) < 1e-6, f"r={res.trades[0].r}")


def test_engine_spread_and_partial():
    """Spread paye a l'entree + prise partielle a 1R avec passage au point mort."""
    bars = [(1800, 1801, 1799, 1800)] * 5
    bars += [(1800, 1806, 1799, 1805)]  # atteint 1R (1805.3 -> 1805.5 ? cf. ci-dessous)
    bars += [(1805, 1806, 1794, 1800)]  # revient sur le point mort (SL = entree)
    s = make_series(bars)

    cfg = ExecConfig(
        initial_equity=10_000, spread=0.30, commission_per_lot=0.0,
        partial_at_r=1.0, partial_pct=0.5, be_on_partial=True,
        min_sl_dollars=0.5, max_sl_dollars=100,
    )
    res = Backtester(s, _StubStrategy(4, BULL, 1795.3, 1830.0), cfg, SmcConfig()).run()
    t = res.trades[0]
    check("engine: spread paye a l'entree", abs(t.entry - 1800.30) < 1e-9, f"entry={t.entry}")
    check("engine: prise partielle effectuee", t.partial_done, "")
    check("engine: SL remonte au point mort", abs(t.sl - t.entry) < 1e-9, f"sl={t.sl}")
    # Moitie fermee a +1R (+0.5R), moitie au point mort (0) => environ +0.5R
    check("engine: resultat ~ +0.5R", 0.4 < t.r < 0.6, f"r={t.r}")


def test_no_lookahead():
    """Le contexte ne doit connaitre que les bougies deja fournies."""
    ctx = SmcContext("M15", SmcConfig())
    for p in [100, 102, 101, 103, 105]:
        ctx.on_bar(p, p + 1, p - 1, p)
    check("no-lookahead: nb de bougies vues", ctx.n == 5, f"n={ctx.n}")
    check("no-lookahead: dernier close connu", ctx.close[-1] == 105)
    check("no-lookahead: pas de bougie future", len(ctx.high) == 5)


def main() -> int:
    for fn in [
        test_structure, test_fvg, test_liquidity_pool, test_engine_pnl,
        test_engine_sl_priority, test_engine_spread_and_partial, test_no_lookahead,
    ]:
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} test(s) en echec : {', '.join(FAILED)}")
        return 1
    print("Tous les tests passent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
