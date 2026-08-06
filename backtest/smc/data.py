"""Chargement et resampling des donnees XAUUSD pour le moteur SMC/ICT.

Les CSV sources sont au format MetaTrader exporte :
    Date,open,high,low,close,tick_volume
    2012-05-15 08:00:00,155408.0,155463.0,155397.0,155450.0,595

Les prix sont exprimes en centiemes (155408.0 => 1554.08). La detection est
automatique : si la mediane des cloture depasse 20000, on divise par 100.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import pandas as pd

# Un pas de temps M15 en minutes, utilise pour dater la cloture des bougies HTF.
TF_MINUTES = {
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

PANDAS_RULE = {
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1D",
}


@dataclass(frozen=True)
class Series:
    """Serie OHLC d'un timeframe donne, en listes paralleles (rapide a iterer)."""

    tf: str
    time: List[pd.Timestamp]
    open: List[float]
    high: List[float]
    low: List[float]
    close: List[float]
    volume: List[float]
    # Horodatage de cloture de chaque bougie : c'est le seul instant ou la
    # bougie HTF est exploitable sans look-ahead.
    close_time: List[pd.Timestamp]

    def __len__(self) -> int:
        return len(self.time)


TIME_ALIASES = ("date", "time", "datetime", "timestamp", "gmt time", "local time")
VOLUME_ALIASES = ("tick_volume", "volume", "vol", "tickvol")
DATE_FORMATS = ("%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d %H:%M",
                "%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M")


def load_csv(path: str, tf: str = "M15") -> Series:
    """Charge un CSV OHLC. Tolerant sur le separateur, les noms de colonnes et
    le format de date : les exports MetaTrader varient d'une source a l'autre."""
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Certains exports separent la date et l'heure en deux colonnes.
    if "date" in df.columns and "time" in df.columns:
        df["date"] = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
        df = df.drop(columns=["time"])

    time_col = next((c for c in df.columns if c in TIME_ALIASES), None)
    if time_col is None:
        raise ValueError(f"{path} : aucune colonne de date reconnue parmi {list(df.columns)}")
    vol_col = next((c for c in df.columns if c in VOLUME_ALIASES), None)

    rename = {time_col: "time"}
    if vol_col:
        rename[vol_col] = "volume"
    df = df.rename(columns=rename)

    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"{path} : colonnes OHLC manquantes {sorted(missing)}")
    if "volume" not in df.columns:
        df["volume"] = 0.0

    df["time"] = _parse_times(df["time"])
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df = df.dropna().drop_duplicates("time").sort_values("time").reset_index(drop=True)

    if df["close"].median() > 20000:  # prix exprimes en centiemes
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] / 100.0

    return _to_series(df, tf)


def series_from_frame(df: pd.DataFrame, tf: str = "M15") -> Series:
    """Construit une Series a partir d'un DataFrame indexe par le temps.

    Colonnes attendues : open, high, low, close (volume optionnel)."""
    out = df.reset_index()
    out = out.rename(columns={out.columns[0]: "time"})
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return _to_series(out.sort_values("time").reset_index(drop=True), tf)


def _parse_times(col: pd.Series) -> pd.Series:
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(col, format=fmt, errors="coerce")
        if parsed.notna().mean() > 0.99:
            return parsed
    return pd.to_datetime(col, errors="coerce")


def resample(src: Series, tf: str) -> Series:
    """Agrege une serie vers un timeframe superieur (H1, H4, D1...)."""
    df = pd.DataFrame(
        {
            "time": src.time,
            "open": src.open,
            "high": src.high,
            "low": src.low,
            "close": src.close,
            "volume": src.volume,
        }
    ).set_index("time")

    agg = df.resample(PANDAS_RULE[tf], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    agg = agg.dropna().reset_index()
    return _to_series(agg, tf)


def _to_series(df: pd.DataFrame, tf: str) -> Series:
    delta = pd.Timedelta(minutes=TF_MINUTES[tf])
    times = list(df["time"])
    return Series(
        tf=tf,
        time=times,
        open=[float(x) for x in df["open"]],
        high=[float(x) for x in df["high"]],
        low=[float(x) for x in df["low"]],
        close=[float(x) for x in df["close"]],
        volume=[float(x) for x in df["volume"]],
        close_time=[t + delta for t in times],
    )


def slice_period(s: Series, start: str | None = None, end: str | None = None) -> Series:
    lo = pd.Timestamp(start) if start else s.time[0]
    hi = pd.Timestamp(end) if end else s.time[-1]
    idx = [i for i, t in enumerate(s.time) if lo <= t <= hi]
    if not idx:
        raise ValueError(f"Aucune bougie entre {lo} et {hi}")
    a, b = idx[0], idx[-1] + 1
    return Series(
        tf=s.tf,
        time=s.time[a:b],
        open=s.open[a:b],
        high=s.high[a:b],
        low=s.low[a:b],
        close=s.close[a:b],
        volume=s.volume[a:b],
        close_time=s.close_time[a:b],
    )


def default_data_path(symbol: str = "XAUUSD", tf: str = "m15") -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "data", f"{symbol}{tf}.csv")
