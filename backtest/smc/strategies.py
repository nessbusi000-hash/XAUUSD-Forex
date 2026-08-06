"""Strategies Smart Money Concepts / ICT.

Strategie #2 : SMC POI Continuation
    Biais HTF (BOS/CHoCH) -> prix en Discount (achat) ou Premium (vente) ->
    atteinte d'un Order Block / FVG non mitige -> CHoCH M15 -> Sniper Entry.

Strategie #3 : Liquidity Sweep Reversal (Turtle Soup / Judas Swing)
    Chasse aux stops sur equal highs/lows -> rejet du niveau -> CHoCH M15 avec
    deplacement -> entree contre la liquidite balayee.

Les deux visent systematiquement la poche de liquidite opposee (BSL/SSL) et
n'ouvrent que si le R:R disponible atteint le minimum SMC (1:3 par defaut).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .core import BULL, BEAR, NEUTRAL, SmcContext, Zone
from .engine import Signal


# --------------------------------------------------------------------------- #
# Selection du Take Profit sur la liquidite opposee
# --------------------------------------------------------------------------- #
def pick_liquidity_tp(
    direction: int,
    entry: float,
    sl: float,
    contexts,
    min_rr: float,
    max_rr: float,
    fallback_fixed_rr: bool,
) -> Optional[float]:
    risk = abs(entry - sl)
    if risk <= 0:
        return None

    side = BULL if direction == BULL else BEAR
    levels = []
    for ctx in contexts:
        for p in ctx.liquidity_targets(side, entry):
            levels.append(p.level)
    levels = sorted(set(levels), reverse=(direction == BEAR))

    for lvl in levels:
        rr = (lvl - entry) / risk if direction == BULL else (entry - lvl) / risk
        if min_rr <= rr <= max_rr:
            return lvl

    if fallback_fixed_rr:
        return entry + min_rr * risk if direction == BULL else entry - min_rr * risk
    return None


def in_session(ts, hours) -> bool:
    return True if not hours else ts.hour in hours


# --------------------------------------------------------------------------- #
# Strategie #2 : SMC POI Continuation
# --------------------------------------------------------------------------- #
@dataclass
class PoiConfig:
    min_rr: float = 3.0
    max_rr: float = 8.0
    fallback_fixed_rr: bool = False
    equilibrium: float = 0.5  # frontiere Premium / Discount (Fib 50%)
    confirm_window: int = 16  # bougies M15 pour obtenir le CHoCH apres tap
    poi_kinds: tuple = ("OB", "FVG")
    confirm_events: tuple = ("CHoCH",)
    sl_buffer_atr: float = 0.5  # marge derriere le High/Low de l'OB
    use_mtf_poi: bool = False  # POI H1 en plus des POI H4
    session_hours: Optional[set] = None
    allow_long: bool = True
    allow_short: bool = True


class PoiContinuation:
    name = "S2_SMC_POI_Continuation"

    def __init__(self, cfg: PoiConfig | None = None):
        self.cfg = cfg or PoiConfig()
        self.armed = {BULL: None, BEAR: None}

    # ------------------------------------------------------------------ #
    def on_bar(self, i, ltf: SmcContext, mtf: SmcContext, htf: SmcContext, series):
        cfg = self.cfg
        if htf.bias == NEUTRAL or htf.n < 30 or ltf.n < 30:
            return None

        hi, lo, cl = ltf.high[i], ltf.low[i], ltf.close[i]
        frac = htf.premium_discount(cl)
        if frac is None:
            return None

        pools = [htf, mtf, ltf]
        poi_ctxs = [htf, mtf] if cfg.use_mtf_poi else [htf]

        # --- Armement : le prix atteint un POI institutionnel -------------- #
        if cfg.allow_long and htf.bias == BULL and frac <= cfg.equilibrium:
            z = self._tap(poi_ctxs, BULL, lo, cl)
            if z is not None and self.armed[BULL] is None:
                self.armed[BULL] = {"zone": z, "bar": i, "extreme": lo}

        if cfg.allow_short and htf.bias == BEAR and frac >= 1.0 - cfg.equilibrium:
            z = self._tap(poi_ctxs, BEAR, hi, cl)
            if z is not None and self.armed[BEAR] is None:
                self.armed[BEAR] = {"zone": z, "bar": i, "extreme": hi}

        # --- Suivi / peremption des setups armes -------------------------- #
        for d in (BULL, BEAR):
            a = self.armed[d]
            if a is None:
                continue
            a["extreme"] = min(a["extreme"], lo) if d == BULL else max(a["extreme"], hi)
            invalid = cl < a["zone"].low if d == BULL else cl > a["zone"].high
            if invalid or i - a["bar"] > cfg.confirm_window:
                self.armed[d] = None

        # --- Confirmation LTF : CHoCH sur M15 ----------------------------- #
        ev = ltf.last_event
        if ev is None or ev.idx != i or ev.kind not in cfg.confirm_events:
            return None
        if not in_session(series.time[i], cfg.session_hours):
            return None

        a = self.armed.get(ev.direction)
        if a is None:
            return None
        if htf.bias != ev.direction:
            return None

        buf = cfg.sl_buffer_atr * ltf.atr
        if ev.direction == BULL:
            sl = min(a["zone"].low, a["extreme"]) - buf
            entry_ref = cl
        else:
            sl = max(a["zone"].high, a["extreme"]) + buf
            entry_ref = cl

        tp = pick_liquidity_tp(
            ev.direction, entry_ref, sl, pools, cfg.min_rr, cfg.max_rr, cfg.fallback_fixed_rr
        )
        if tp is None:
            return None

        self.armed[BULL] = self.armed[BEAR] = None
        return Signal(
            direction=ev.direction,
            sl=sl,
            tp=tp,
            tag=f"{a['zone'].kind}-{a['zone'].origin or 'POI'}",
            meta={"frac": round(frac, 3)},
        )

    # ------------------------------------------------------------------ #
    def _tap(self, contexts, direction: int, extreme: float, close: float) -> Optional[Zone]:
        """Renvoie le POI non mitige le plus proche que le prix vient de toucher."""
        best = None
        for ctx in contexts:
            for z in ctx.zones:
                if z.dead or z.direction != direction or z.kind not in self.cfg.poi_kinds:
                    continue
                if direction == BULL:
                    if extreme <= z.high and close >= z.low:
                        if best is None or z.low > best.low:
                            best = z
                else:
                    if extreme >= z.low and close <= z.high:
                        if best is None or z.high < best.high:
                            best = z
        return best


# --------------------------------------------------------------------------- #
# Strategie #3 : Liquidity Sweep Reversal
# --------------------------------------------------------------------------- #
@dataclass
class SweepConfig:
    min_rr: float = 3.0
    max_rr: float = 8.0
    fallback_fixed_rr: bool = False
    min_pool_count: int = 2  # 2 = equal highs / equal lows stricts
    sweep_window: int = 12  # bougies M15 pour confirmer apres la chasse
    confirm_events: tuple = ("CHoCH", "BOS")
    require_displacement: bool = True
    displacement_atr: float = 1.0
    sl_buffer_atr: float = 0.3
    htf_filter: str = "premium_discount"  # "none" | "bias" | "premium_discount"
    equilibrium: float = 0.5
    session_hours: Optional[set] = None
    allow_long: bool = True
    allow_short: bool = True


class SweepReversal:
    name = "S3_SMC_Liquidity_Sweep"

    def __init__(self, cfg: SweepConfig | None = None):
        self.cfg = cfg or SweepConfig()
        self.armed = {BULL: None, BEAR: None}

    # ------------------------------------------------------------------ #
    def on_bar(self, i, ltf: SmcContext, mtf: SmcContext, htf: SmcContext, series):
        cfg = self.cfg
        if ltf.n < 40:
            return None

        hi, lo, cl = ltf.high[i], ltf.low[i], ltf.close[i]

        # --- Detection de la chasse aux stops (Liquidity Run) ------------- #
        for p in ltf.recent_sweeps[-8:]:
            if p.count < cfg.min_pool_count or i - p.swept_idx > cfg.sweep_window:
                continue
            k = p.swept_idx
            # Rejet : la bougie de balayage referme de l'autre cote du niveau.
            if p.side == BULL and ltf.close[k] < p.level and cfg.allow_short:
                if self.armed[BEAR] is None or self.armed[BEAR]["pool"] is not p:
                    self.armed[BEAR] = {"pool": p, "bar": k, "extreme": p.swept_extreme}
            elif p.side == BEAR and ltf.close[k] > p.level and cfg.allow_long:
                if self.armed[BULL] is None or self.armed[BULL]["pool"] is not p:
                    self.armed[BULL] = {"pool": p, "bar": k, "extreme": p.swept_extreme}

        for d in (BULL, BEAR):
            a = self.armed[d]
            if a is None:
                continue
            a["extreme"] = min(a["extreme"], lo) if d == BULL else max(a["extreme"], hi)
            if i - a["bar"] > cfg.sweep_window:
                self.armed[d] = None

        # --- Confirmation : CHoCH M15 avec deplacement -------------------- #
        ev = ltf.last_event
        if ev is None or ev.idx != i or ev.kind not in cfg.confirm_events:
            return None
        a = self.armed.get(ev.direction)
        if a is None:
            return None
        if not in_session(series.time[i], cfg.session_hours):
            return None
        if cfg.require_displacement and not self._displacement(i, ltf, ev.direction):
            return None

        frac = htf.premium_discount(cl)
        if cfg.htf_filter == "bias" and htf.bias != ev.direction:
            return None
        if cfg.htf_filter == "premium_discount" and frac is not None:
            if ev.direction == BULL and frac > cfg.equilibrium:
                return None
            if ev.direction == BEAR and frac < 1.0 - cfg.equilibrium:
                return None

        buf = cfg.sl_buffer_atr * ltf.atr
        sl = a["extreme"] - buf if ev.direction == BULL else a["extreme"] + buf

        tp = pick_liquidity_tp(
            ev.direction, cl, sl, [ltf, mtf, htf], cfg.min_rr, cfg.max_rr, cfg.fallback_fixed_rr
        )
        if tp is None:
            return None

        self.armed[BULL] = self.armed[BEAR] = None
        tag = "SweepEQH" if ev.direction == BEAR else "SweepEQL"
        return Signal(direction=ev.direction, sl=sl, tp=tp, tag=tag,
                      meta={"pool_count": a["pool"].count})

    # ------------------------------------------------------------------ #
    def _displacement(self, i: int, ltf: SmcContext, direction: int) -> bool:
        """Deplacement institutionnel = bougie large ou FVG frais dans le sens."""
        if ltf.atr > 0 and (ltf.high[i] - ltf.low[i]) >= self.cfg.displacement_atr * ltf.atr:
            return True
        for z in ltf.zones:
            if z.kind == "FVG" and z.direction == direction and i - z.idx <= 3:
                return True
        return False
