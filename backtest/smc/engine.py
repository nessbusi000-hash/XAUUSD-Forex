"""Moteur de backtest bougie par bougie (execution sur M15).

Regles d'execution volontairement conservatrices :
  * un signal genere a la cloture de la bougie i n'est execute qu'a ce prix de
    cloture, jamais avec les meches de la bougie i ;
  * si SL et TP sont touches dans la meme bougie, on considere que le SL part
    en premier (hypothese pessimiste) ;
  * le spread est integralement paye a l'entree, la commission a l'aller-retour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .core import BULL, BEAR, SmcConfig, SmcContext
from .data import Series, resample


@dataclass
class Signal:
    direction: int
    sl: float
    tp: float
    tag: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Trade:
    idx_in: int
    time_in: object
    direction: int
    entry: float
    sl: float
    sl0: float  # SL initial : sert de reference pour le calcul du R
    tp: float
    lots: float
    risk_amount: float
    tag: str
    idx_out: int = -1
    time_out: object = None
    exit: float = 0.0
    pnl: float = 0.0
    r: float = 0.0
    reason: str = ""
    mae_r: float = 0.0  # excursion adverse maximale, en R
    equity_after: float = 0.0
    partial_pnl: float = 0.0  # gain deja securise par la prise partielle
    lots_open: float = 0.0  # lots restants apres prise partielle
    partial_done: bool = False

    @property
    def side(self) -> str:
        return "BUY" if self.direction == BULL else "SELL"


@dataclass
class ExecConfig:
    initial_equity: float = 10_000.0
    risk_pct: float = 1.0  # % de l'equity risque par trade
    contract_size: float = 100.0  # XAUUSD : 1 lot = 100 onces => 1$ = 100$/lot
    spread: float = 0.30  # en dollars (30 cents)
    commission_per_lot: float = 7.0  # aller-retour
    min_lot: float = 0.01
    max_lot: float = 50.0
    lot_step: float = 0.01
    max_hold_bars: int = 480  # 5 jours en M15
    breakeven_at_r: float = 0.0  # 0 = desactive
    partial_at_r: float = 0.0  # prise partielle a X R (0 = desactive)
    partial_pct: float = 0.5  # fraction du lot fermee a la prise partielle
    be_on_partial: bool = True  # SL au point mort apres la partielle
    min_sl_dollars: float = 1.0
    max_sl_dollars: float = 60.0


class Backtester:
    def __init__(
        self,
        m15: Series,
        strategy,
        exec_cfg: ExecConfig | None = None,
        smc_cfg: SmcConfig | None = None,
        htf: str = "H4",
        mtf: str = "H1",
    ):
        self.m15 = m15
        self.strategy = strategy
        self.cfg = exec_cfg or ExecConfig()
        self.smc_cfg = smc_cfg or SmcConfig()
        self.htf_name = htf
        self.mtf_name = mtf

        self.ctx_ltf = SmcContext("M15", self.smc_cfg)
        self.ctx_mtf = SmcContext(mtf, self.smc_cfg)
        self.ctx_htf = SmcContext(htf, self.smc_cfg)

        self.trades: List[Trade] = []
        self.equity = self.cfg.initial_equity
        self.equity_curve: List[tuple] = []
        self.open_trade: Optional[Trade] = None

    # ------------------------------------------------------------------ #
    def run(self) -> "BacktestResult":
        m15 = self.m15
        htf_bars = resample(m15, self.htf_name)
        mtf_bars = resample(m15, self.mtf_name)
        h_ptr = m_ptr = 0

        for i in range(len(m15)):
            now = m15.close_time[i]
            hi, lo, cl = m15.high[i], m15.low[i], m15.close[i]

            # 1) Gestion de la position ouverte avec le range de la bougie.
            if self.open_trade is not None:
                self._manage(i, hi, lo, cl)

            # 2) Alimentation des contextes HTF puis LTF (aucun look-ahead).
            while h_ptr < len(htf_bars) and htf_bars.close_time[h_ptr] <= now:
                self.ctx_htf.on_bar(
                    htf_bars.open[h_ptr], htf_bars.high[h_ptr], htf_bars.low[h_ptr],
                    htf_bars.close[h_ptr], htf_bars.time[h_ptr],
                )
                h_ptr += 1
            while m_ptr < len(mtf_bars) and mtf_bars.close_time[m_ptr] <= now:
                self.ctx_mtf.on_bar(
                    mtf_bars.open[m_ptr], mtf_bars.high[m_ptr], mtf_bars.low[m_ptr],
                    mtf_bars.close[m_ptr], mtf_bars.time[m_ptr],
                )
                m_ptr += 1

            self.ctx_ltf.on_bar(m15.open[i], hi, lo, cl, m15.time[i])

            # 3) Recherche de signal a la cloture.
            if self.open_trade is None:
                sig = self.strategy.on_bar(i, self.ctx_ltf, self.ctx_mtf, self.ctx_htf, m15)
                if sig is not None:
                    self._open(i, sig, cl)

        # Cloture de la position residuelle en fin de periode.
        if self.open_trade is not None:
            self._close(len(m15) - 1, self.m15.close[-1], "end_of_data")

        return BacktestResult(self.trades, self.cfg.initial_equity, self.equity_curve, self.m15)

    # ------------------------------------------------------------------ #
    def _open(self, i: int, sig: Signal, price: float) -> None:
        cfg = self.cfg
        half = cfg.spread
        entry = price + half if sig.direction == BULL else price - half
        sl_dist = abs(entry - sig.sl)
        if sl_dist < cfg.min_sl_dollars or sl_dist > cfg.max_sl_dollars:
            return

        risk_amount = self.equity * cfg.risk_pct / 100.0
        lots = risk_amount / (sl_dist * cfg.contract_size)
        lots = max(cfg.min_lot, min(cfg.max_lot, round(lots / cfg.lot_step) * cfg.lot_step))

        self.open_trade = Trade(
            idx_in=i,
            time_in=self.m15.time[i],
            direction=sig.direction,
            entry=entry,
            sl=sig.sl,
            sl0=sig.sl,
            tp=sig.tp,
            lots=round(lots, 2),
            risk_amount=risk_amount,
            tag=sig.tag,
        )
        self.open_trade.lots_open = self.open_trade.lots

    def _manage(self, i: int, hi: float, lo: float, cl: float) -> None:
        t = self.open_trade
        cfg = self.cfg
        risk = abs(t.entry - t.sl0)

        if t.direction == BULL:
            t.mae_r = max(t.mae_r, (t.entry - lo) / risk)
            if lo <= t.sl:  # hypothese pessimiste : le SL passe avant le TP
                self._close(i, t.sl, "SL")
                return
            if hi >= t.tp:
                self._close(i, t.tp, "TP")
                return
            if cfg.partial_at_r > 0 and not t.partial_done:
                lvl = t.entry + cfg.partial_at_r * risk
                if hi >= lvl:
                    self._take_partial(lvl)
            if cfg.breakeven_at_r > 0 and hi >= t.entry + cfg.breakeven_at_r * risk:
                t.sl = max(t.sl, t.entry)
        else:
            t.mae_r = max(t.mae_r, (hi - t.entry) / risk)
            if hi >= t.sl:
                self._close(i, t.sl, "SL")
                return
            if lo <= t.tp:
                self._close(i, t.tp, "TP")
                return
            if cfg.partial_at_r > 0 and not t.partial_done:
                lvl = t.entry - cfg.partial_at_r * risk
                if lo <= lvl:
                    self._take_partial(lvl)
            if cfg.breakeven_at_r > 0 and lo <= t.entry - cfg.breakeven_at_r * risk:
                t.sl = min(t.sl, t.entry)

        if i - t.idx_in >= self.cfg.max_hold_bars:
            self._close(i, cl, "time_stop")

    def _take_partial(self, price: float) -> None:
        """Securise une fraction de la position (gestion classique SMC)."""
        t = self.open_trade
        cfg = self.cfg
        closed = round(t.lots * cfg.partial_pct / cfg.lot_step) * cfg.lot_step
        closed = min(max(closed, cfg.min_lot), t.lots_open)
        if closed <= 0:
            return
        t.partial_pnl += (price - t.entry) * t.direction * closed * cfg.contract_size
        t.lots_open = round(t.lots_open - closed, 2)
        t.partial_done = True
        if cfg.be_on_partial:
            t.sl = t.entry

    def _close(self, i: int, price: float, reason: str) -> None:
        t = self.open_trade
        gross = (price - t.entry) * t.direction * t.lots_open * self.cfg.contract_size
        gross += t.partial_pnl
        cost = t.lots * self.cfg.commission_per_lot
        t.pnl = gross - cost
        t.exit = price
        t.idx_out = i
        t.time_out = self.m15.time[i]
        t.reason = reason
        risk_money = abs(t.entry - t.sl0) * t.lots * self.cfg.contract_size
        t.r = t.pnl / risk_money if risk_money else 0.0

        self.equity += t.pnl
        t.equity_after = self.equity
        self.trades.append(t)
        self.equity_curve.append((t.time_out, self.equity))
        self.open_trade = None


# --------------------------------------------------------------------------- #
# Statistiques
# --------------------------------------------------------------------------- #
class BacktestResult:
    def __init__(self, trades: List[Trade], initial_equity: float, curve, m15: Series):
        self.trades = trades
        self.initial_equity = initial_equity
        self.curve = curve
        self.m15 = m15

    @property
    def stats(self) -> dict:
        t = self.trades
        n = len(t)
        if n == 0:
            return {"trades": 0}

        wins = [x for x in t if x.pnl > 0]
        losses = [x for x in t if x.pnl <= 0]
        gross_win = sum(x.pnl for x in wins)
        gross_loss = -sum(x.pnl for x in losses)
        net = sum(x.pnl for x in t)
        final = self.initial_equity + net

        peak, max_dd, max_dd_pct = self.initial_equity, 0.0, 0.0
        eq = self.initial_equity
        for x in t:
            eq += x.pnl
            peak = max(peak, eq)
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd / peak * 100.0

        # Serie de pertes consecutives.
        streak = worst_streak = 0
        for x in t:
            if x.pnl <= 0:
                streak += 1
                worst_streak = max(worst_streak, streak)
            else:
                streak = 0

        rs = [x.r for x in t]
        days = max(1, (self.m15.time[-1] - self.m15.time[0]).days)
        years = days / 365.25

        return {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / n * 100.0,
            "net_profit": net,
            "return_pct": net / self.initial_equity * 100.0,
            "cagr_pct": ((final / self.initial_equity) ** (1 / years) - 1) * 100.0 if final > 0 else -100.0,
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            "expectancy_r": sum(rs) / n,
            "avg_win_r": sum(x.r for x in wins) / len(wins) if wins else 0.0,
            "avg_loss_r": sum(x.r for x in losses) / len(losses) if losses else 0.0,
            "max_dd": max_dd,
            "max_dd_pct": max_dd_pct,
            "max_consec_losses": worst_streak,
            "final_equity": final,
            "trades_per_year": n / years,
            "years": years,
            "avg_bars_held": sum(x.idx_out - x.idx_in for x in t) / n,
            "tp_hits": sum(1 for x in t if x.reason == "TP"),
            "sl_hits": sum(1 for x in t if x.reason == "SL"),
            "time_stops": sum(1 for x in t if x.reason == "time_stop"),
        }

    def by_year(self) -> dict:
        out: dict = {}
        for x in self.trades:
            y = x.time_out.year
            d = out.setdefault(y, {"trades": 0, "pnl": 0.0, "wins": 0})
            d["trades"] += 1
            d["pnl"] += x.pnl
            d["wins"] += 1 if x.pnl > 0 else 0
        for y, d in out.items():
            d["win_rate"] = d["wins"] / d["trades"] * 100.0
        return dict(sorted(out.items()))

    def to_csv(self, path: str) -> None:
        import csv

        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                ["time_in", "time_out", "side", "tag", "entry", "sl", "tp", "exit",
                 "lots", "pnl", "r", "reason", "mae_r", "equity_after"]
            )
            for t in self.trades:
                w.writerow(
                    [t.time_in, t.time_out, t.side, t.tag, round(t.entry, 2), round(t.sl, 2),
                     round(t.tp, 2), round(t.exit, 2), t.lots, round(t.pnl, 2), round(t.r, 3),
                     t.reason, round(t.mae_r, 2), round(t.equity_after, 2)]
                )
