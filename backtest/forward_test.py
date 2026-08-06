#!/usr/bin/env python3
"""Forward test : la configuration candidate tient-elle apres sa selection ?

La configuration candidate (#3, R:R 1:4, filtre Premium/Discount, clusters de 3
sommets) a ete retenue sur un historique s'arretant au 21 mars 2025. Ce script
la rejoue sur des bougies **posterieures a cette date**, issues d'une **source
independante** obtenue apres coup :

  source du forward : ilahuerta-IA/backtrader-pullback-window-xauusd
                      (`data/XAUUSD_5m_5Yea.csv`, bougies 5 min en UTC)

Deux precautions :
  * l'historique du projet sert de periode de chauffe (structure, POI, poches de
    liquidite) mais aucun trade n'y est compte : `ExecConfig.trade_from` ;
  * la source du forward est convertie d'UTC vers l'heure serveur EET/EEST pour
    coller au reste de la serie (ecart median residuel ~0,11 $, soit la
    difference normale entre deux flux de brokers).

    python3 backtest/forward_test.py
    python3 backtest/forward_test.py --cutoff 2025-03-21 --tz Europe/Athens
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import (  # noqa: E402
    Backtester, ExecConfig, PoiConfig, PoiContinuation, SmcConfig, SweepConfig,
    SweepReversal, load_csv, resample, series_from_frame,
)

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_DATA = os.path.join(HERE, "data", "XAUUSDm15.csv")
FORWARD_DATA = os.path.join(HERE, "data", "XAUUSD_5m_forward.csv")

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

# Cadence historique mesuree sur 2006-2025, pour situer la taille d'echantillon.
HIST_TRADES_PER_YEAR = {"candidate": 15.7, "s3_default": 52.3, "s2_default": 61.3}
HIST_EXPECTANCY = {"candidate": +0.114, "s3_default": -0.136, "s2_default": -0.147}
# Ecart-type des resultats en R, mesure sur 2006-2025 (voir robustness.py).
HIST_SD = {"candidate": 2.13, "s3_default": 1.73, "s2_default": 1.64}


def build_series(main_path: str, forward_path: str, cutoff: pd.Timestamp, tz: str):
    """Recolle l'historique du projet et les bougies du forward."""
    main = load_csv(main_path, "M15")
    hist = pd.DataFrame(
        {"time": main.time, "open": main.open, "high": main.high,
         "low": main.low, "close": main.close, "volume": main.volume}
    ).set_index("time")
    hist = hist.loc[:cutoff]

    fwd_m5 = load_csv(forward_path, "M5")
    fwd = resample(fwd_m5, "M15")
    fut = pd.DataFrame(
        {"time": fwd.time, "open": fwd.open, "high": fwd.high,
         "low": fwd.low, "close": fwd.close, "volume": fwd.volume}
    ).set_index("time")
    # UTC -> heure serveur, en respectant les changements d'heure.
    fut.index = fut.index.tz_localize("UTC").tz_convert(tz).tz_localize(None)
    fut = fut[fut.index > cutoff].sort_index()

    spliced = pd.concat([hist, fut])
    spliced = spliced[~spliced.index.duplicated(keep="first")].sort_index()
    return series_from_frame(spliced, "M15"), hist, fut


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=MAIN_DATA)
    ap.add_argument("--forward-data", default=FORWARD_DATA)
    ap.add_argument("--cutoff", default="2025-03-21 23:59", help="fin de l'historique de selection")
    ap.add_argument("--tz", default="Europe/Athens", help="fuseau serveur cible")
    args = ap.parse_args()

    for path in (args.data, args.forward_data):
        if not os.path.exists(path):
            print(f"Donnees introuvables : {path}\nLancez d'abord backtest/fetch_data.sh", file=sys.stderr)
            return 1

    cutoff = pd.Timestamp(args.cutoff)
    series, hist, fut = build_series(args.data, args.forward_data, cutoff, args.tz)

    if fut.empty:
        print("Aucune bougie posterieure a la date de coupure : rien a tester en avant.")
        return 1

    span_days = (fut.index[-1] - fut.index[0]).days
    years = span_days / 365.25
    print("=" * 96)
    print("FORWARD TEST - XAUUSD")
    print(f"  Chauffe (aucun trade compte) : {hist.index[0]} -> {cutoff}   {len(hist):,} bougies")
    print(f"  Fenetre de forward           : {fut.index[0]} -> {fut.index[-1]}   "
          f"{len(fut):,} bougies ({span_days} jours)")
    print(f"  Source du forward            : {os.path.basename(args.forward_data)} (5 min, UTC -> {args.tz})")
    print("=" * 96)

    exec_cfg = ExecConfig(trade_from=cutoff)
    smc_cfg = SmcConfig()

    for key, (label, build) in CONFIGS.items():
        res = Backtester(series, build(), exec_cfg, smc_cfg).run()
        trades = res.trades
        expected = HIST_TRADES_PER_YEAR[key] * years

        print(f"\n--- {label} ---")
        print(f"  Trades attendus sur {span_days} jours (cadence historique) : ~{expected:.1f}")
        if not trades:
            print("  Aucun trade declenche sur la fenetre.")
            continue

        s = res.stats
        print(f"  Trades observes : {s['trades']} | win rate {s['win_rate']:.0f}% | "
              f"PF {s['profit_factor']:.2f} | esperance {s['expectancy_r']:+.3f} R | "
              f"resultat {s['return_pct']:+.1f}%")
        print(f"  Reference historique 2006-2025 : esperance {HIST_EXPECTANCY[key]:+.3f} R")

        rs = [t.r for t in trades]
        n = len(rs)
        if n >= 3:
            mean = sum(rs) / n
            sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5
            t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
            print(f"  Test t sur la fenetre : t = {t_stat:+.2f} "
                  f"({'significatif' if abs(t_stat) >= 2 else 'non significatif'} — "
                  f"n={n}, trop peu pour conclure)")

        print("  Journal :")
        for t in trades:
            print(f"    {t.time_in}  {t.side:<4} entree {t.entry:8.2f}  SL {t.sl0:8.2f}  "
                  f"TP {t.tp:8.2f}  -> {t.reason:<9} {t.r:+5.2f} R  ({t.pnl:+8.2f} $)")

    print("\n" + "=" * 96)
    print("COMBIEN DE TEMPS FAUDRAIT-IL POUR TRANCHER ?")
    print("  Nombre de trades necessaires pour atteindre |t| = 2, en supposant que")
    print("  l'esperance et la dispersion historiques se maintiennent :")
    for key, (label, _) in CONFIGS.items():
        e, sd = HIST_EXPECTANCY[key], HIST_SD[key]
        if e == 0:
            continue
        needed = (2.0 * sd / abs(e)) ** 2
        print(f"    {label:<52} n = {needed:>6.0f} trades  "
              f"-> {needed / HIST_TRADES_PER_YEAR[key]:>5.1f} ans a la cadence observee")
    print("\nUn forward test de quelques mois ne valide ni n'invalide une strategie a ~16")
    print("trades par an : il sert a verifier qu'elle se comporte comme prevu, pas a trancher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
