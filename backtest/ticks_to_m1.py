#!/usr/bin/env python3
"""Construit des bougies M1 a partir de ticks bid/ask.

Source attendue : FX-Data/FX-Data-XAUUSD-DS, un fichier CSV par heure,
    2018.01.02 01:00:00.155,13.06291,13.06522,0.00,0.00
    (horodatage, bid, ask, volume bid, volume ask)

Les prix y sont stockes au centieme : 13.06291 vaut 1306,29 $. Les bougies OHLC
sont construites sur le **bid**, comme le reste des donnees du projet, et le
spread reel (ask - bid) est mesure au passage — il n'a plus a etre suppose.

    python3 backtest/ticks_to_m1.py /chemin/vers/XAUUSD/2018 -o backtest/data/XAUUSDm1_2018.csv
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

PRICE_SCALE = 100.0  # 13.06291 -> 1306.291


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tick_dir", help="repertoire contenant les *_ticks.csv (recursif)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--scale", type=float, default=PRICE_SCALE)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.tick_dir, "**", "*_ticks.csv"), recursive=True))
    if not files:
        print(f"Aucun fichier de ticks sous {args.tick_dir}", file=sys.stderr)
        return 1
    print(f"{len(files):,} fichiers horaires a traiter")

    bars = []
    spread_sum = spread_n = 0.0
    total_ticks = 0

    for k, path in enumerate(files, 1):
        try:
            df = pd.read_csv(path, header=None, names=["t", "bid", "ask", "vb", "va"])
        except Exception as exc:  # fichier vide ou tronque : on l'ignore en le signalant
            print(f"  ignore {os.path.basename(path)} : {exc}")
            continue
        if df.empty:
            continue

        df["t"] = pd.to_datetime(df["t"], format="%Y.%m.%d %H:%M:%S.%f", errors="coerce")
        df = df.dropna(subset=["t"])
        if df.empty:
            continue

        df["bid"] = df["bid"] * args.scale
        df["ask"] = df["ask"] * args.scale
        total_ticks += len(df)
        spread_sum += float((df["ask"] - df["bid"]).sum())
        spread_n += len(df)

        agg = df.set_index("t")["bid"].resample("1min").agg(["first", "max", "min", "last", "count"])
        agg = agg.dropna()
        agg.columns = ["open", "high", "low", "close", "tick_volume"]
        bars.append(agg)

        if k % 500 == 0:
            print(f"  {k:,}/{len(files):,} fichiers, {total_ticks:,} ticks")

    if not bars:
        print("Aucune bougie produite.", file=sys.stderr)
        return 1

    out = pd.concat(bars)
    out = out[~out.index.duplicated(keep="first")].sort_index()
    out.index.name = "Date"

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out.to_csv(args.out)

    avg_spread = spread_sum / spread_n if spread_n else 0.0
    print(f"\n{len(out):,} bougies M1 : {out.index[0]} -> {out.index[-1]}")
    print(f"{total_ticks:,} ticks agreges")
    print(f"Spread moyen mesure : {avg_spread:.3f} $ "
          f"(l'etude XAUUSD utilisait 0,30 $ par hypothese)")
    print(f"Ecrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
