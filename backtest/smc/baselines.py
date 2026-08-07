"""Strategies de reference retail, pour situer les strategies SMC.

`benchmark.py` compare deja les setups SMC a des entrees aleatoires. Cette
famille ajoute un second point de comparaison : une strategie retail classique,
telle qu'on la trouve dans les bots publics.

`MacdPriceAction` reproduit [3aLaee/xauusd-trading-bot](https://github.com/3aLaee/xauusd-trading-bot)
(MACD 12/26/9 + niveaux des 10 dernieres bougies, M1, SL 15 pips / TP 10 pips).
Deux variantes, car le README et le code de ce depot ne decrivent pas la meme
strategie :

  * `variant="code"`   : ce que fait reellement `bot.py` (ligne 85) — achat si
    croisement haussier ET histogramme > 0 ET cloture au-dessus du **support**.
    Le support etant le plus bas des 10 dernieres bougies, bougie courante
    comprise, la condition est presque toujours vraie : le filtre ne filtre rien.
  * `variant="readme"` : ce que decrit le README — achat sur cassure de la
    **resistance**. Celle-ci etant le plus haut des 10 dernieres bougies, bougie
    courante comprise, une cloture ne peut jamais la depasser : zero trade.

Le MACD est calcule en flux (EMA recursives), sans lookback ni look-ahead.
"""

from __future__ import annotations

from .core import BULL, BEAR
from .engine import Signal

FAST, SLOW, SIGNAL = 12, 26, 9


class MacdPriceAction:
    name = "Baseline_MACD_PriceAction"

    def __init__(self, variant: str = "code", sl: float = 1.5, tp: float = 1.0,
                 lookback: int = 10, session_hours=None):
        if variant not in ("code", "readme"):
            raise ValueError(f"variante inconnue : {variant}")
        self.variant = variant
        self.sl = sl
        self.tp = tp
        self.lookback = lookback
        self.session_hours = session_hours
        self.ema_fast = self.ema_slow = self.signal = None
        self.prev_diff = None

    def on_bar(self, i, ltf, mtf, htf, series):
        close = ltf.close[i]
        kf, ks, kg = 2 / (FAST + 1), 2 / (SLOW + 1), 2 / (SIGNAL + 1)

        self.ema_fast = close if self.ema_fast is None else self.ema_fast + kf * (close - self.ema_fast)
        self.ema_slow = close if self.ema_slow is None else self.ema_slow + ks * (close - self.ema_slow)
        macd = self.ema_fast - self.ema_slow
        self.signal = macd if self.signal is None else self.signal + kg * (macd - self.signal)

        diff, prev = macd - self.signal, self.prev_diff
        self.prev_diff = diff
        if prev is None or i < self.lookback + SLOW + 5:
            return None

        cross_up = diff > 0 and prev <= 0
        cross_down = diff < 0 and prev >= 0
        if not (cross_up or cross_down):
            return None
        if self.session_hours and series.time[i].hour not in self.session_hours:
            return None

        window = slice(i - self.lookback + 1, i + 1)
        resistance = max(ltf.high[window])
        support = min(ltf.low[window])

        if self.variant == "code":
            if cross_up and close > support:
                return Signal(BULL, close - self.sl, close + self.tp, tag="macd")
            if cross_down and close < resistance:
                return Signal(BEAR, close + self.sl, close - self.tp, tag="macd")
        else:
            if cross_up and close > resistance:
                return Signal(BULL, close - self.sl, close + self.tp, tag="macd")
            if cross_down and close < support:
                return Signal(BEAR, close + self.sl, close - self.tp, tag="macd")
        return None
