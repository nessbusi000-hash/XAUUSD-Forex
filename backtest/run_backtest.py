#!/usr/bin/env python3
"""Backtest des strategies SMC / ICT sur XAUUSD (execution M15, biais H4).

Exemples :
    python3 backtest/run_backtest.py --strategy both
    python3 backtest/run_backtest.py --strategy s3 --start 2018-01-01 --min-rr 3
    python3 backtest/run_backtest.py --strategy both --out backtest/results
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig,
    SweepConfig, SweepReversal, load_csv, slice_period,
)


def build(name: str, args) -> object:
    if name == "s2":
        return PoiContinuation(
            PoiConfig(
                min_rr=args.min_rr,
                max_rr=args.max_rr,
                use_mtf_poi=args.mtf_poi,
                confirm_window=args.confirm_window,
                fallback_fixed_rr=args.fallback_rr,
            )
        )
    if name == "s3":
        return SweepReversal(
            SweepConfig(
                min_rr=args.min_rr,
                max_rr=args.max_rr,
                sweep_window=args.confirm_window,
                htf_filter=args.htf_filter,
                fallback_fixed_rr=args.fallback_rr,
            )
        )
    raise ValueError(name)


def fmt_stats(name: str, res) -> str:
    s = res.stats
    if not s.get("trades"):
        return f"### {name}\nAucun trade genere.\n"

    lines = [
        f"### {name}",
        "",
        "| Metrique | Valeur |",
        "|---|---|",
        f"| Trades | {s['trades']} ({s['trades_per_year']:.0f}/an) |",
        f"| Win rate | {s['win_rate']:.1f}% |",
        f"| Profit factor | {s['profit_factor']:.2f} |",
        f"| Esperance | {s['expectancy_r']:+.3f} R / trade |",
        f"| Gain moyen | {s['avg_win_r']:+.2f} R |",
        f"| Perte moyenne | {s['avg_loss_r']:+.2f} R |",
        f"| Profit net | {s['net_profit']:+,.0f} $ ({s['return_pct']:+.1f}%) |",
        f"| CAGR | {s['cagr_pct']:+.1f}% |",
        f"| Equity finale | {s['final_equity']:,.0f} $ |",
        f"| Max drawdown | {s['max_dd']:,.0f} $ ({s['max_dd_pct']:.1f}%) |",
        f"| Pertes consecutives max | {s['max_consec_losses']} |",
        f"| Sorties TP / SL / temps | {s['tp_hits']} / {s['sl_hits']} / {s['time_stops']} |",
        f"| Duree moyenne | {s['avg_bars_held']:.0f} bougies M15 |",
        "",
        "| Annee | Trades | Win rate | P&L |",
        "|---|---|---|---|",
    ]
    for y, d in res.by_year().items():
        lines.append(f"| {y} | {d['trades']} | {d['win_rate']:.0f}% | {d['pnl']:+,.0f} $ |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv"))
    p.add_argument("--strategy", default="both", choices=["s2", "s3", "both"])
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--equity", type=float, default=10_000.0)
    p.add_argument("--risk", type=float, default=1.0, help="%% d'equity risque par trade")
    p.add_argument("--spread", type=float, default=0.30, help="spread en dollars")
    p.add_argument("--commission", type=float, default=7.0, help="$ par lot aller-retour")
    p.add_argument("--min-rr", type=float, default=3.0)
    p.add_argument("--max-rr", type=float, default=8.0)
    p.add_argument("--confirm-window", type=int, default=16)
    p.add_argument("--htf-filter", default="premium_discount", choices=["none", "bias", "premium_discount"])
    p.add_argument("--mtf-poi", action="store_true", help="ajoute les POI H1 aux POI H4")
    p.add_argument("--fallback-rr", action="store_true", help="TP a R:R fixe si aucune liquidite eligible")
    p.add_argument("--breakeven-at-r", type=float, default=0.0)
    p.add_argument("--out", default=None, help="dossier de sortie (rapport + trades CSV)")
    args = p.parse_args()

    if not os.path.exists(args.data):
        print(f"Donnees introuvables : {args.data}\nLancez d'abord backtest/fetch_data.sh", file=sys.stderr)
        return 1

    m15 = load_csv(args.data, "M15")
    if args.start or args.end:
        m15 = slice_period(m15, args.start, args.end)

    exec_cfg = ExecConfig(
        initial_equity=args.equity,
        risk_pct=args.risk,
        spread=args.spread,
        commission_per_lot=args.commission,
        breakeven_at_r=args.breakeven_at_r,
    )
    smc_cfg = SmcConfig()

    names = ["s2", "s3"] if args.strategy == "both" else [args.strategy]
    header = [
        "# Backtest SMC / ICT - XAUUSD",
        "",
        f"- Donnees : `{os.path.basename(args.data)}` M15, {len(m15):,} bougies",
        f"- Periode : {m15.time[0]} -> {m15.time[-1]}",
        f"- Capital initial : {args.equity:,.0f} $ | Risque : {args.risk}%/trade",
        f"- Spread : {args.spread:.2f} $ | Commission : {args.commission:.2f} $/lot A-R",
        f"- R:R minimum : 1:{args.min_rr:g} | Biais : H4 | Confirmation : M15",
        "",
    ]
    out_parts = ["\n".join(header)]
    results = {}

    for name in names:
        strat = build(name, args)
        bt = Backtester(m15, strat, exec_cfg, smc_cfg)
        res = bt.run()
        results[name] = res
        label = strat.name
        block = fmt_stats(label, res)
        print(block)
        out_parts.append(block)

        if args.out:
            os.makedirs(args.out, exist_ok=True)
            res.to_csv(os.path.join(args.out, f"trades_{name}.csv"))

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "report.md")
        with open(path, "w") as f:
            f.write("\n".join(out_parts))
        print(f"Rapport ecrit : {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
