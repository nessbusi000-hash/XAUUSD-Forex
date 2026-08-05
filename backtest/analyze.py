#!/usr/bin/env python3
"""Briefing SMC / ICT en 4 etapes sur la derniere bougie disponible.

Reproduit la grille de lecture institutionnelle :
    1. Architecture et biais (BOS / CHoCH, Premium vs Discount)
    2. Liquidite et chasse aux stops (BSL / SSL, Liquidity Runs)
    3. Zones d'interet institutionnelles (Order Blocks, FVG)
    4. Plan d'execution (Sniper Entry, SL, TP, R:R)

    python3 backtest/analyze.py
    python3 backtest/analyze.py --at "2021-06-15 16:00" --htf H4 --ltf M15
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import BULL, BEAR, NEUTRAL, SmcConfig, SmcContext, load_csv, resample, slice_period  # noqa: E402
from smc.strategies import pick_liquidity_tp  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")

BIAS_TXT = {BULL: "BULLISH (order flow haussier)", BEAR: "BEARISH (order flow baissier)", NEUTRAL: "INDEFINI"}


def build(series, cfg) -> SmcContext:
    ctx = SmcContext(series.tf, cfg)
    for i in range(len(series)):
        ctx.on_bar(series.open[i], series.high[i], series.low[i], series.close[i], series.time[i])
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--at", default=None, help="date d'analyse (defaut : derniere bougie)")
    ap.add_argument("--htf", default="H4")
    ap.add_argument("--ltf", default="M15")
    ap.add_argument("--min-rr", type=float, default=3.0)
    args = ap.parse_args()

    m15 = load_csv(args.data, "M15")
    if args.at:
        m15 = slice_period(m15, None, args.at)

    cfg = SmcConfig()
    ltf = build(m15 if args.ltf == "M15" else resample(m15, args.ltf), cfg)
    htf = build(resample(m15, args.htf), cfg)
    mtf = build(resample(m15, "H1"), cfg)

    price = m15.close[-1]
    when = m15.time[-1]
    frac = htf.premium_discount(price)

    print("=" * 78)
    print(f"BRIEFING SMC / ICT - XAUUSD  |  {when}  |  prix {price:.2f}")
    print(f"Macro : {args.htf} (biais)   Micro : {args.ltf} (execution)")
    print("=" * 78)

    # --- 1. Architecture et biais ------------------------------------- #
    print("\n1. ARCHITECTURE ET BIAIS DU MARCHE (Market Structure)")
    print(f"  - Biais {args.htf} : {BIAS_TXT[htf.bias]}")
    for ev in htf.events[-3:]:
        d = "haussier" if ev.direction == BULL else "baissier"
        print(f"  - {ev.kind} {d} sur {ev.level:.2f} (bougie {args.htf} #{ev.idx})")
    if htf.range_low is not None:
        eq = (htf.range_low + htf.range_high) / 2
        zone = "PREMIUM (cher - zone de vente)" if frac and frac > 0.5 else "DISCOUNT (pas cher - zone d'achat)"
        print(f"  - Dealing range : {htf.range_low:.2f} -> {htf.range_high:.2f} | Equilibrium (Fib 50%) {eq:.2f}")
        print(f"  - Position du prix : {frac * 100:.1f}% du range => {zone}")
        depth = (htf.range_high - price) if htf.bias == BULL else (price - htf.range_low)
        span = htf.range_high - htf.range_low
        phase = "EXPANSION (impulsion en cours)" if span and depth / span < 0.25 else "RETRACEMENT (repli vers le POI)"
        print(f"  - Phase : {phase}")
    print(f"  - Biais H1 : {BIAS_TXT[mtf.bias]} | Biais {args.ltf} : {BIAS_TXT[ltf.bias]}")

    # --- 2. Liquidite -------------------------------------------------- #
    print("\n2. LIQUIDITE ET CHASSE AUX STOPS (Liquidity Pools)")
    bsl = htf.liquidity_targets(BULL, price)[:3]
    ssl = htf.liquidity_targets(BEAR, price)[:3]
    print("  - BSID / Buy-Side Liquidity (stops des vendeurs, au-dessus) :")
    for p in bsl:
        kind = f"equal highs x{p.count}" if p.is_equal else "sommet isole"
        print(f"      {p.level:.2f}  ({kind}, +{p.level - price:.2f} $)")
    if not bsl:
        print("      aucune poche intacte au-dessus")
    print("  - SSL / Sell-Side Liquidity (stops des acheteurs, en-dessous) :")
    for p in ssl:
        kind = f"equal lows x{p.count}" if p.is_equal else "creux isole"
        print(f"      {p.level:.2f}  ({kind}, -{price - p.level:.2f} $)")
    if not ssl:
        print("      aucune poche intacte en-dessous")
    runs = [p for p in ltf.recent_sweeps if p.swept_idx >= ltf.n - 96][-4:]
    print(f"  - Liquidity Runs recents ({args.ltf}, 24 dernieres heures) :")
    for p in runs:
        side = "BSL balayee" if p.side == BULL else "SSL balayee"
        print(f"      {side} {p.level:.2f} -> extreme {p.swept_extreme:.2f} (cluster x{p.count})")
    if not runs:
        print("      aucune chasse aux stops recente")

    # --- 3. POI --------------------------------------------------------- #
    print("\n3. ZONES D'INTERET INSTITUTIONNELLES (POI)")
    for ctx, label in ((htf, args.htf), (mtf, "H1")):
        for direction, name in ((BULL, "demande"), (BEAR, "offre")):
            zones = [z for z in ctx.active_pois(direction)][-3:]
            for z in zones:
                dist = z.mid - price
                print(
                    f"  - {label} {z.kind} {name} : {z.low:.2f} - {z.high:.2f} "
                    f"| 50% = {z.mid:.2f} ({dist:+.2f} $) {'[' + z.origin + ']' if z.origin else ''}"
                )

    # --- 4. Plan d'execution -------------------------------------------- #
    print("\n4. PLAN D'EXECUTION SMART MONEY")
    direction = htf.bias
    if direction == NEUTRAL or frac is None:
        print("  - Pas de biais HTF exploitable : rester flat (no trade).")
        return 0

    in_zone = (direction == BULL and frac <= 0.5) or (direction == BEAR and frac >= 0.5)
    pois = [z for z in htf.active_pois(direction)]
    if direction == BULL:
        pois = sorted([z for z in pois if z.high < price], key=lambda z: -z.high)
    else:
        pois = sorted([z for z in pois if z.low > price], key=lambda z: z.low)

    if not pois:
        print("  - Aucun POI non mitige dans le sens du biais : attendre la formation d'un nouvel OB/FVG.")
        return 0

    poi = pois[0]
    entry = poi.mid
    buf = 0.5 * ltf.atr
    sl = poi.low - buf if direction == BULL else poi.high + buf
    tp = pick_liquidity_tp(direction, entry, sl, [htf, mtf, ltf], args.min_rr, 12.0, False)
    side = "ACHAT" if direction == BULL else "VENTE"

    print(f"  - Sens : {side} (aligne sur le biais {args.htf})")
    print(f"  - Zone d'entree : {poi.kind} {poi.low:.2f}-{poi.high:.2f}, entree limite au 50% = {entry:.2f}")
    print(f"  - Declencheur : mitigation du POI puis CHoCH {args.ltf} dans le sens du trade (Sniper Entry)")
    print(f"  - Stop-Loss : {sl:.2f} (derriere le {'low' if direction == BULL else 'high'} de l'OB, {abs(entry - sl):.2f} $ de risque)")
    if tp is None:
        print(f"  - Take-Profit : aucune poche de liquidite n'offre 1:{args.min_rr:g} => setup ecarte (no trade)")
    else:
        rr = abs(tp - entry) / abs(entry - sl)
        print(f"  - Take-Profit : {tp:.2f} (poche de liquidite opposee) => R:R 1:{rr:.1f}")
    if not in_zone:
        z = "premium" if frac > 0.5 else "discount"
        print(f"  - ATTENTION : le prix est en {z}, contraire au sens du trade. Attendre le retour vers le POI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
