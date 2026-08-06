#!/usr/bin/env python3
"""Fusionne une ou plusieurs sources brutes en un historique M15 exploitable.

Le pipeline :
  1. charge chaque source (separateur, colonnes et format de date auto-detectes) ;
  2. fusionne par horodatage, la premiere source citee faisant autorite en cas
     de conflit ;
  3. coupe l'historique au dernier segment continu : au-dela du premier trou
     superieur a `--max-gap-days`, les donnees sont trop lacunaires pour un
     backtest honnete (un trou de 3 semaines fabrique de faux gaps de prix) ;
  4. ecrit le CSV canonique `Date,open,high,low,close,tick_volume`.

    python3 backtest/prepare_data.py raw1.csv raw2.csv -o backtest/data/XAUUSDm15.csv
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import load_csv  # noqa: E402


def to_frame(path: str) -> pd.DataFrame:
    s = load_csv(path, "M15")
    return pd.DataFrame(
        {
            "time": s.time,
            "open": s.open,
            "high": s.high,
            "low": s.low,
            "close": s.close,
            "tick_volume": s.volume,
        }
    ).set_index("time")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", help="CSV bruts, par ordre de priorite decroissante")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-gap-days", type=float, default=4.0,
                    help="trou maximal tolere avant de couper (week-ends et feries : ~3 jours)")
    ap.add_argument("--start", default=None, help="date de debut imposee")
    args = ap.parse_args()

    frames = []
    for path in args.sources:
        if not os.path.exists(path):
            print(f"  source absente, ignoree : {path}")
            continue
        df = to_frame(path)
        print(f"  {os.path.basename(path):<28} {len(df):>8,} bougies  {df.index[0]} -> {df.index[-1]}")
        frames.append(df)

    if not frames:
        print("Aucune source exploitable.", file=sys.stderr)
        return 1

    merged = pd.concat(frames)
    merged = merged[~merged.index.duplicated(keep="first")].sort_index()
    print(f"\n  fusion                       {len(merged):>8,} bougies  "
          f"{merged.index[0]} -> {merged.index[-1]}")

    if args.start:
        merged = merged.loc[pd.Timestamp(args.start):]

    # Decoupe aux trous anormaux et garde le plus long segment continu : une
    # serie trouee fabrique de faux gaps de prix que le moteur SMC lirait
    # comme des FVG geants.
    gaps = merged.index.to_series().diff()
    limit = pd.Timedelta(days=args.max_gap_days)
    breaks = [merged.index.get_loc(t) for t in gaps[gaps > limit].index]

    if breaks:
        bounds = [0] + breaks + [len(merged)]
        segments = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        print(f"\n  {len(breaks)} trou(s) > {args.max_gap_days:g} jours, "
              f"{len(segments)} segment(s) continu(s) :")
        for a, b in segments:
            mark = ""
            print(f"    {merged.index[a]} -> {merged.index[b - 1]}  {b - a:>8,} bougies{mark}")

        a, b = max(segments, key=lambda s: s[1] - s[0])
        dropped = len(merged) - (b - a)
        merged = merged.iloc[a:b]
        print(f"  segment retenu (le plus long) : {merged.index[0]} -> {merged.index[-1]}, "
              f"{dropped:,} bougies ecartees")

    out = merged.reset_index().rename(columns={"time": "Date"})
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out.to_csv(args.out, index=False)

    span_days = (merged.index[-1] - merged.index[0]).days
    print(f"\n  ecrit {args.out} : {len(out):,} bougies, "
          f"{merged.index[0]} -> {merged.index[-1]} ({span_days / 365.25:.1f} ans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
