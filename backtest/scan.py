#!/usr/bin/env python3
"""Etude parametrique in-sample / out-of-sample des strategies SMC.

Le but n'est pas d'optimiser a outrance mais de verifier qu'une famille de
reglages coherents (R:R, killzones ICT, filtre Premium/Discount, prise
partielle) tient hors echantillon.

    IS  : 2012-05 -> 2018-12   (choix des reglages)
    OOS : 2019-01 -> 2025-03   (validation, jamais utilise pour choisir)

La fenetre IS est restee identique quand l'historique a ete etendu jusqu'en
2025 : les reglages ont donc ete choisis avant que ces annees existent dans le
projet, ce qui fait de 2022-2025 un vrai test en avant.

    python3 backtest/scan.py --strategy s3
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig,
    SweepConfig, SweepReversal, load_csv, slice_period,
)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")
IS = ("2012-05-15", "2018-12-31")
OOS = ("2019-01-01", "2025-03-21")

# Killzones ICT en heure serveur (donnees EET = UTC+2/+3) :
# London 09h-12h, New York 14h-18h.
KILLZONES = {9, 10, 11, 14, 15, 16, 17}

_SERIES = {}


def get_series(period):
    key = period
    if key not in _SERIES:
        full = load_csv(DATA, "M15")
        _SERIES[key] = slice_period(full, period[0], period[1])
    return _SERIES[key]


def make_strategy(kind: str, p: dict):
    session = KILLZONES if p["session"] == "killzone" else None
    if kind == "s2":
        return PoiContinuation(
            PoiConfig(
                min_rr=p["min_rr"],
                use_mtf_poi=p["mtf_poi"],
                confirm_window=p["window"],
                poi_kinds=p["poi_kinds"],
                session_hours=session,
            )
        )
    return SweepReversal(
        SweepConfig(
            min_rr=p["min_rr"],
            htf_filter=p["htf_filter"],
            min_pool_count=p["pool_count"],
            sweep_window=p["window"],
            session_hours=session,
        )
    )


def make_exec(p: dict) -> ExecConfig:
    return ExecConfig(
        partial_at_r=1.0 if p["partial"] else 0.0,
        partial_pct=0.5,
        be_on_partial=True,
    )


def run_one(job):
    kind, p, period = job
    series = get_series(period)
    bt = Backtester(series, make_strategy(kind, p), make_exec(p), SmcConfig())
    res = bt.run()
    s = res.stats
    out = dict(p)
    out.update(
        {
            "trades": s.get("trades", 0),
            "win_rate": round(s.get("win_rate", 0), 1),
            "pf": round(s.get("profit_factor", 0), 2) if s.get("trades") else 0,
            "exp_r": round(s.get("expectancy_r", 0), 3),
            "return_pct": round(s.get("return_pct", 0), 1),
            "max_dd_pct": round(s.get("max_dd_pct", 0), 1),
        }
    )
    return out


def grid(kind: str):
    if kind == "s2":
        keys = ["min_rr", "mtf_poi", "window", "poi_kinds", "session", "partial"]
        vals = [
            [2.0, 3.0, 4.0],
            [False, True],
            [8, 16],
            [("OB", "FVG"), ("OB",)],
            ["all", "killzone"],
            [False, True],
        ]
    else:
        keys = ["min_rr", "htf_filter", "pool_count", "window", "session", "partial"]
        vals = [
            [2.0, 3.0, 4.0],
            ["none", "bias", "premium_discount"],
            [2, 3],
            [8, 12],
            ["all", "killzone"],
            [False, True],
        ]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def fmt_row(r: dict, keys) -> str:
    cfg = " ".join(f"{k}={r[k]}" for k in keys)
    return (
        f"{cfg:<78} n={r['trades']:>4} wr={r['win_rate']:>5.1f}% "
        f"pf={r['pf']:>5.2f} E={r['exp_r']:>+6.3f}R ret={r['return_pct']:>+7.1f}% dd={r['max_dd_pct']:>5.1f}%"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="s3", choices=["s2", "s3"])
    ap.add_argument("--min-trades", type=int, default=60)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    params = grid(args.strategy)
    keys = list(params[0].keys())

    with ProcessPoolExecutor(max_workers=4) as ex:
        is_res = list(ex.map(run_one, [(args.strategy, p, IS) for p in params], chunksize=2))

    ranked = sorted(
        [r for r in is_res if r["trades"] >= args.min_trades],
        key=lambda r: r["exp_r"],
        reverse=True,
    )

    print(f"=== IN-SAMPLE {IS[0]} -> {IS[1]} ({len(ranked)}/{len(is_res)} configs retenues) ===")
    for r in ranked[: args.top]:
        print(fmt_row(r, keys))

    top = ranked[: args.top]
    with ProcessPoolExecutor(max_workers=4) as ex:
        oos_res = list(
            ex.map(run_one, [(args.strategy, {k: r[k] for k in keys}, OOS) for r in top], chunksize=1)
        )

    print(f"\n=== OUT-OF-SAMPLE {OOS[0]} -> {OOS[1]} (memes reglages) ===")
    for r in oos_res:
        print(fmt_row(r, keys))

    if args.out:
        with open(args.out, "w") as f:
            json.dump({"in_sample": ranked, "out_of_sample": oos_res}, f, indent=2, default=str)
        print(f"\nResultats bruts : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
