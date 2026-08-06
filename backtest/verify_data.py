#!/usr/bin/env python3
"""Audit du fichier de donnees : est-ce vraiment du XAUUSD, et est-il propre ?

Le dataset utilise par defaut provient d'un depot etiquete "forex". XAU/USD est
bien une paire forex (l'once d'or contre le dollar, tradee en CFD chez les
brokers MT4/MT5), mais mieux vaut le verifier que le supposer : ce script
confronte le fichier aux repere connus du marche de l'or et controle la
coherence des bougies.

    python3 backtest/verify_data.py
    python3 backtest/verify_data.py --data backtest/data/XAUUSDh1.csv --tf H1

Code de sortie 0 si tous les controles passent, 1 sinon.
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smc import load_csv  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "XAUUSDm15.csv")

# Reperes historiques de l'or (cours spot). Un broker CFD peut s'en ecarter de
# quelques dixiemes de pourcent, d'ou la tolerance par defaut de 1,5%.
#   (debut, fin, "high"|"low", niveau attendu, description)
REFERENCES = [
    ("2011-09-05", "2011-09-07", "high", 1920.0, "Sommet de septembre 2011"),
    ("2013-04-12", "2013-04-16", "low", 1321.0, "Krach des 12-15 avril 2013"),
    ("2015-12-01", "2015-12-05", "low", 1046.0, "Plus bas du cycle, 3 decembre 2015"),
    ("2016-06-24", "2016-07-08", "high", 1375.0, "Rebond post-Brexit"),
    ("2018-08-13", "2018-08-17", "low", 1160.0, "Creux d'aout 2018"),
    ("2019-09-01", "2019-09-05", "high", 1557.0, "Sommet de septembre 2019"),
    ("2020-03-15", "2020-03-20", "low", 1451.0, "Krach COVID de mars 2020"),
    ("2020-08-06", "2020-08-08", "high", 2075.0, "Record du 7 aout 2020"),
    ("2022-03-07", "2022-03-09", "high", 2070.0, "Pic du 8 mars 2022 (Ukraine)"),
    ("2024-10-29", "2024-11-01", "high", 2790.0, "Sommet de fin octobre 2024"),
]

OK, KO, SKIP = "  ok  ", " ECHEC", " passe"


class Report:
    def __init__(self):
        self.failures = 0

    def line(self, status: str, text: str) -> None:
        if status == KO:
            self.failures += 1
        print(f"[{status}] {text}")


def check_references(df: pd.DataFrame, rep: Report, tol_pct: float) -> None:
    print("\n--- Reperes historiques du marche de l'or ---")
    first, last = df.index[0], df.index[-1]
    checked = 0

    for start, end, kind, expected, label in REFERENCES:
        a = pd.Timestamp(start)
        # La fenetre couvre la journee de fin en entier, bougies intraday comprises.
        b = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        if a < first or b > last:
            rep.line(SKIP, f"{label} : hors de la periode couverte")
            continue

        window = df.loc[a:b]
        if window.empty:
            rep.line(SKIP, f"{label} : aucune bougie dans la fenetre")
            continue

        found = window["h"].max() if kind == "high" else window["l"].min()
        gap_pct = abs(found - expected) / expected * 100.0
        checked += 1
        status = OK if gap_pct <= tol_pct else KO
        rep.line(
            status,
            f"{label} : {kind} du fichier {found:.2f} vs reference {expected:.0f} "
            f"(ecart {gap_pct:.2f}%)",
        )

    if checked == 0:
        rep.line(KO, "Aucun repere verifiable : impossible d'authentifier l'instrument")
    else:
        print(f"      {checked} repere(s) confronte(s), tolerance {tol_pct:.1f}%")


def check_integrity(df: pd.DataFrame, rep: Report) -> None:
    print("\n--- Coherence des bougies ---")

    bad_hl = int((df["h"] < df["l"]).sum())
    rep.line(OK if bad_hl == 0 else KO, f"High >= Low : {bad_hl} violation(s)")

    bad_h = int((df["h"] < df[["o", "c"]].max(axis=1) - 1e-9).sum())
    bad_l = int((df["l"] > df[["o", "c"]].min(axis=1) + 1e-9).sum())
    rep.line(OK if bad_h == 0 else KO, f"High englobe Open/Close : {bad_h} violation(s)")
    rep.line(OK if bad_l == 0 else KO, f"Low englobe Open/Close : {bad_l} violation(s)")

    nonpos = int((df[["o", "h", "l", "c"]] <= 0).sum().sum())
    rep.line(OK if nonpos == 0 else KO, f"Prix strictement positifs : {nonpos} violation(s)")

    dups = int(df.index.duplicated().sum())
    rep.line(OK if dups == 0 else KO, f"Horodatages uniques : {dups} doublon(s)")

    rep.line(
        OK if df.index.is_monotonic_increasing else KO,
        "Horodatages tries par ordre croissant",
    )

    weekend = int(df.index.dayofweek.isin([5, 6]).sum())
    share = weekend / len(df) * 100.0
    rep.line(
        OK if share < 1.0 else KO,
        f"Instrument forex/CFD (pas de week-end) : {weekend} bougie(s) samedi/dimanche ({share:.2f}%)",
    )

    # Un saut de cotation aberrant trahit un raccord de series mal fait.
    jumps = (df["o"] / df["c"].shift(1) - 1.0).abs().dropna()
    worst = jumps.max() * 100.0 if len(jumps) else 0.0
    rep.line(
        OK if worst < 10.0 else KO,
        f"Plus grand ecart de cotation entre bougies : {worst:.2f}% le {jumps.idxmax()}"
        if len(jumps) else "Pas assez de bougies pour mesurer les sauts",
    )


def describe(df: pd.DataFrame, tf: str) -> None:
    print("--- Fichier ---")
    print(f"  Bougies      : {len(df):,} ({tf})")
    print(f"  Periode      : {df.index[0]} -> {df.index[-1]}")
    print(f"  Prix         : min {df['l'].min():.2f} / max {df['h'].max():.2f}")
    print(f"  Plus haut le : {df['h'].idxmax()}")
    print(f"  Plus bas le  : {df['l'].idxmin()}")

    gaps = df.index.to_series().diff().dt.total_seconds().div(60).dropna()
    if len(gaps):
        expected = gaps.mode().iloc[0]
        print(
            f"  Continuite   : {int((gaps == expected).sum()):,} pas de {expected:.0f} min, "
            f"{int((gaps > expected).sum()):,} interruptions (week-ends/feries), "
            f"la plus longue {gaps.max() / 60 / 24:.1f} jours"
        )
    counts = df.groupby(df.index.dayofweek).size()
    jours = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
    print("  Repartition  : " + ", ".join(f"{jours[d]} {n:,}" for d, n in counts.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--tolerance", type=float, default=1.5, help="ecart tolere en %% sur les reperes")
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print(f"Donnees introuvables : {args.data}\nLancez d'abord backtest/fetch_data.sh", file=sys.stderr)
        return 1

    s = load_csv(args.data, args.tf)
    df = pd.DataFrame(
        {"t": s.time, "o": s.open, "h": s.high, "l": s.low, "c": s.close}
    ).set_index("t")

    print(f"Audit de {os.path.basename(args.data)}\n")
    describe(df, args.tf)

    rep = Report()
    check_references(df, rep, args.tolerance)
    check_integrity(df, rep)

    print()
    if rep.failures:
        print(f"{rep.failures} controle(s) en echec : ces donnees ne sont pas fiables telles quelles.")
        return 1
    print("Tous les controles passent : le fichier contient bien du XAUUSD exploitable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
