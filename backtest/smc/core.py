"""Moteur SMC / ICT : structure de marche, liquidite, Order Blocks, FVG.

Tout est calcule en flux (streaming) : chaque bougie est fournie une seule fois
via `SmcContext.on_bar()` et l'etat interne ne regarde jamais vers l'avenir.
C'est ce qui garantit qu'un backtest construit dessus est exempt de look-ahead.

Terminologie (ICT / Smart Money Concepts) :
  BOS   : Break of Structure       -> continuation de l'order flow
  CHoCH : Change of Character      -> premier signal de retournement
  OB    : Order Block              -> derniere bougie opposee avant deplacement
  FVG   : Fair Value Gap           -> desequilibre a 3 bougies
  BSL   : Buy-Side Liquidity       -> stops au-dessus des sommets (equal highs)
  SSL   : Sell-Side Liquidity      -> stops sous les creux (equal lows)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

BULL = 1
BEAR = -1
NEUTRAL = 0


# --------------------------------------------------------------------------- #
# Structures de donnees
# --------------------------------------------------------------------------- #
@dataclass
class Swing:
    idx: int
    price: float
    kind: int  # BULL = swing high, BEAR = swing low


@dataclass
class StructureEvent:
    idx: int
    kind: str  # "BOS" ou "CHoCH"
    direction: int
    level: float  # niveau structurel casse


@dataclass
class Zone:
    """Order Block ou Fair Value Gap (POI = Point Of Interest)."""

    kind: str  # "OB" ou "FVG"
    direction: int  # BULL = zone de demande, BEAR = zone d'offre
    low: float
    high: float
    idx: int  # bougie de creation
    origin: str = ""  # "BOS" / "CHoCH" a l'origine de l'OB
    touched: bool = False
    touched_idx: int = -1
    dead: bool = False  # mitigee integralement / invalidee

    @property
    def mid(self) -> float:
        """Equilibre du POI : le fameux "50% de l'Order Block"."""
        return (self.low + self.high) / 2.0

    @property
    def size(self) -> float:
        return self.high - self.low


@dataclass
class LiquidityPool:
    """Poche de liquidite retail : BSL au-dessus, SSL en-dessous."""

    side: int  # BULL = BSL (au-dessus), BEAR = SSL (en-dessous)
    level: float
    idx: int
    count: int = 1  # 2+ = equal highs / equal lows
    swept: bool = False
    swept_idx: int = -1
    swept_extreme: float = 0.0

    @property
    def is_equal(self) -> bool:
        return self.count >= 2


@dataclass
class SmcConfig:
    swing_left: int = 2
    swing_right: int = 2
    atr_period: int = 14
    ob_lookback: int = 12  # profondeur de recherche de l'OB avant le deplacement
    displacement_atr: float = 1.0  # amplitude mini du deplacement (en ATR)
    fvg_min_atr: float = 0.10  # taille mini d'un FVG (en ATR)
    pool_tol_atr: float = 0.35  # tolerance de regroupement des equal highs/lows
    sweep_tol_atr: float = 0.15  # penetration mini pour parler de balayage reel
    max_zones: int = 40  # nb de POI conserves par direction
    max_pools: int = 40
    zone_expiry: int = 500  # bougies avant peremption d'un POI


# --------------------------------------------------------------------------- #
# Contexte SMC d'un timeframe
# --------------------------------------------------------------------------- #
class SmcContext:
    """Etat SMC complet d'un timeframe (structure + liquidite + POI)."""

    def __init__(self, tf: str, cfg: SmcConfig | None = None):
        self.tf = tf
        self.cfg = cfg or SmcConfig()

        self.n = 0
        self.high: List[float] = []
        self.low: List[float] = []
        self.open: List[float] = []
        self.close: List[float] = []
        self.time: List[object] = []

        self.atr: float = 0.0
        self._tr_window: List[float] = []

        self.swings: List[Swing] = []
        self.last_swing_high: Optional[Swing] = None
        self.last_swing_low: Optional[Swing] = None
        # Extremes protégés : dernier sommet/creux structurel casse.
        self.bias: int = NEUTRAL
        self.last_event: Optional[StructureEvent] = None
        self.events: List[StructureEvent] = []

        # Dealing range servant au calcul Premium / Discount (Fibonacci 50%).
        self.range_low: Optional[float] = None
        self.range_high: Optional[float] = None

        self.zones: List[Zone] = []  # OB + FVG vivants
        self.pools: List[LiquidityPool] = []
        self.recent_sweeps: List[LiquidityPool] = []

    # ------------------------------------------------------------------ #
    # Entree principale
    # ------------------------------------------------------------------ #
    def on_bar(self, o: float, h: float, l: float, c: float, t=None) -> None:
        i = self.n
        self.open.append(o)
        self.high.append(h)
        self.low.append(l)
        self.close.append(c)
        self.time.append(t)
        self.n += 1

        self._update_atr(i)
        self._detect_swing(i)
        self._update_structure(i)
        self._update_range(i)
        self._detect_fvg(i)
        self._update_zones(i)
        self._update_pools(i)

    # ------------------------------------------------------------------ #
    # ATR (volatilite de reference pour les seuils de deplacement)
    # ------------------------------------------------------------------ #
    def _update_atr(self, i: int) -> None:
        if i == 0:
            tr = self.high[0] - self.low[0]
        else:
            pc = self.close[i - 1]
            tr = max(self.high[i] - self.low[i], abs(self.high[i] - pc), abs(self.low[i] - pc))
        self._tr_window.append(tr)
        if len(self._tr_window) > self.cfg.atr_period:
            self._tr_window.pop(0)
        self.atr = sum(self._tr_window) / len(self._tr_window)

    # ------------------------------------------------------------------ #
    # Swings (fractales confirmees)
    # ------------------------------------------------------------------ #
    def _detect_swing(self, i: int) -> None:
        L, R = self.cfg.swing_left, self.cfg.swing_right
        k = i - R
        if k - L < 0:
            return

        hs, ls = self.high, self.low
        left = range(k - L, k)
        right = range(k + 1, k + R + 1)

        if all(hs[k] > hs[j] for j in left) and all(hs[k] >= hs[j] for j in right):
            sw = Swing(k, hs[k], BULL)
            self.swings.append(sw)
            self.last_swing_high = sw
            self._register_pool(BULL, hs[k], k)

        if all(ls[k] < ls[j] for j in left) and all(ls[k] <= ls[j] for j in right):
            sw = Swing(k, ls[k], BEAR)
            self.swings.append(sw)
            self.last_swing_low = sw
            self._register_pool(BEAR, ls[k], k)

        if len(self.swings) > 200:
            self.swings = self.swings[-200:]

    # ------------------------------------------------------------------ #
    # Structure : BOS / CHoCH
    # ------------------------------------------------------------------ #
    def _update_structure(self, i: int) -> None:
        c = self.close[i]

        if self.last_swing_high is not None and c > self.last_swing_high.price:
            kind = "BOS" if self.bias == BULL else "CHoCH"
            ev = StructureEvent(i, kind, BULL, self.last_swing_high.price)
            self._commit_event(ev, i)
            self.last_swing_high = None
            return

        if self.last_swing_low is not None and c < self.last_swing_low.price:
            kind = "BOS" if self.bias == BEAR else "CHoCH"
            ev = StructureEvent(i, kind, BEAR, self.last_swing_low.price)
            self._commit_event(ev, i)
            self.last_swing_low = None

    def _commit_event(self, ev: StructureEvent, i: int) -> None:
        self.bias = ev.direction
        self.last_event = ev
        self.events.append(ev)
        if len(self.events) > 200:
            self.events = self.events[-200:]

        # Nouveau dealing range ancre sur l'origine du mouvement.
        if ev.direction == BULL:
            anchor = self.last_swing_low.price if self.last_swing_low else min(self.low[max(0, i - 50) : i + 1])
            self.range_low = anchor
            self.range_high = max(self.high[max(0, i - 50) : i + 1])
        else:
            anchor = self.last_swing_high.price if self.last_swing_high else max(self.high[max(0, i - 50) : i + 1])
            self.range_high = anchor
            self.range_low = min(self.low[max(0, i - 50) : i + 1])

        self._create_order_block(ev, i)

    def _update_range(self, i: int) -> None:
        if self.range_high is None or self.range_low is None:
            return
        if self.bias == BULL:
            self.range_high = max(self.range_high, self.high[i])
        elif self.bias == BEAR:
            self.range_low = min(self.range_low, self.low[i])

    def premium_discount(self, price: float) -> Optional[float]:
        """0 = bas du range (discount profond), 1 = haut du range (premium)."""
        if self.range_high is None or self.range_low is None:
            return None
        span = self.range_high - self.range_low
        if span <= 0:
            return None
        return (price - self.range_low) / span

    # ------------------------------------------------------------------ #
    # Order Blocks
    # ------------------------------------------------------------------ #
    def _create_order_block(self, ev: StructureEvent, i: int) -> None:
        cfg = self.cfg
        start = max(0, i - cfg.ob_lookback)

        if ev.direction == BULL:
            # Derniere bougie baissiere avant le deplacement haussier.
            k = -1
            for j in range(i, start - 1, -1):
                if self.close[j] < self.open[j]:
                    k = j
                    break
            if k < 0:
                return
            impulse = max(self.high[k : i + 1]) - self.low[k]
            if self.atr > 0 and impulse < cfg.displacement_atr * self.atr:
                return
            self.zones.append(
                Zone("OB", BULL, self.low[k], self.high[k], k, origin=ev.kind)
            )
        else:
            k = -1
            for j in range(i, start - 1, -1):
                if self.close[j] > self.open[j]:
                    k = j
                    break
            if k < 0:
                return
            impulse = self.high[k] - min(self.low[k : i + 1])
            if self.atr > 0 and impulse < cfg.displacement_atr * self.atr:
                return
            self.zones.append(
                Zone("OB", BEAR, self.low[k], self.high[k], k, origin=ev.kind)
            )

    # ------------------------------------------------------------------ #
    # Fair Value Gaps
    # ------------------------------------------------------------------ #
    def _detect_fvg(self, i: int) -> None:
        if i < 2:
            return
        min_gap = self.cfg.fvg_min_atr * self.atr

        # FVG haussier : le low actuel est au-dessus du high de i-2.
        if self.low[i] > self.high[i - 2]:
            gap = self.low[i] - self.high[i - 2]
            if gap >= min_gap:
                self.zones.append(Zone("FVG", BULL, self.high[i - 2], self.low[i], i))

        # FVG baissier : le high actuel est sous le low de i-2.
        if self.high[i] < self.low[i - 2]:
            gap = self.low[i - 2] - self.high[i]
            if gap >= min_gap:
                self.zones.append(Zone("FVG", BEAR, self.high[i], self.low[i - 2], i))

    def _update_zones(self, i: int) -> None:
        h, l, c = self.high[i], self.low[i], self.close[i]
        for z in self.zones:
            if z.dead or z.idx >= i:
                continue
            if z.direction == BULL:
                if l <= z.high:  # le prix revient dans le POI -> mitigation
                    if not z.touched:
                        z.touched, z.touched_idx = True, i
                if c < z.low:  # POI traverse -> invalide
                    z.dead = True
            else:
                if h >= z.low:
                    if not z.touched:
                        z.touched, z.touched_idx = True, i
                if c > z.high:
                    z.dead = True
            if i - z.idx > self.cfg.zone_expiry:
                z.dead = True

        self.zones = [z for z in self.zones if not z.dead][-self.cfg.max_zones * 2 :]

    def unmitigated(self, direction: int, kind: str | None = None) -> List[Zone]:
        return [
            z
            for z in self.zones
            if z.direction == direction and not z.touched and (kind is None or z.kind == kind)
        ]

    def active_pois(self, direction: int) -> List[Zone]:
        """POI exploitables : non invalides, non encore mitiges."""
        return [z for z in self.zones if z.direction == direction and not z.dead and not z.touched]

    # ------------------------------------------------------------------ #
    # Liquidite
    # ------------------------------------------------------------------ #
    def _register_pool(self, side: int, level: float, idx: int) -> None:
        tol = max(self.cfg.pool_tol_atr * self.atr, level * 0.00025)
        for p in self.pools:
            if p.side == side and not p.swept and abs(p.level - level) <= tol:
                p.count += 1
                p.idx = idx
                # Les stops se logent derriere l'extreme du cluster.
                p.level = max(p.level, level) if side == BULL else min(p.level, level)
                return
        self.pools.append(LiquidityPool(side, level, idx))
        if len(self.pools) > self.cfg.max_pools * 3:
            self.pools = self.pools[-self.cfg.max_pools * 2 :]

    def _update_pools(self, i: int) -> None:
        h, l = self.high[i], self.low[i]
        # Un depassement d'un ou deux cents n'est pas une chasse aux stops : on
        # exige une penetration significative, sinon le niveau reste un equal
        # high / equal low en formation.
        for p in self.pools:
            if p.swept:
                continue
            tol = max(self.cfg.sweep_tol_atr * self.atr, p.level * 0.0001)
            if p.side == BULL and h > p.level + tol:
                p.swept, p.swept_idx, p.swept_extreme = True, i, h
                self.recent_sweeps.append(p)
            elif p.side == BEAR and l < p.level - tol:
                p.swept, p.swept_idx, p.swept_extreme = True, i, l
                self.recent_sweeps.append(p)
        if len(self.recent_sweeps) > 50:
            self.recent_sweeps = self.recent_sweeps[-50:]

    def liquidity_targets(self, side: int, price: float) -> List[LiquidityPool]:
        """Poches de liquidite intactes, triees de la plus proche a la plus loin."""
        if side == BULL:
            pools = [p for p in self.pools if p.side == BULL and not p.swept and p.level > price]
            return sorted(pools, key=lambda p: p.level)
        pools = [p for p in self.pools if p.side == BEAR and not p.swept and p.level < price]
        return sorted(pools, key=lambda p: -p.level)
