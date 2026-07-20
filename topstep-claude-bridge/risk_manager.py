"""Garde-fous de risque Topstep, appliqués AVANT l'analyse Claude et AVANT l'exécution.

Ces vérifications sont volontairement codées en dur (pas déléguées au LLM) :
un signal ne peut jamais contourner la perte journalière max ni la taille max.
"""
import datetime as dt
import logging
from dataclasses import dataclass

from config import settings
from projectx_client import ProjectXClient

log = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    allowed: bool
    reason: str
    account_state: dict


class RiskManager:
    def __init__(self, client: ProjectXClient, account_id: int):
        self._client = client
        self._account_id = account_id
        self._day_anchor_balance: float | None = None
        self._day_anchor_date: dt.date | None = None

    async def check(self) -> RiskCheck:
        accounts = await self._client.search_accounts()
        account = next(
            (a for a in accounts if a.get("id") == self._account_id), None
        )
        if account is None:
            return RiskCheck(False, "Compte introuvable ou inactif.", {})

        balance = float(account.get("balance", 0))
        today = dt.date.today()
        if self._day_anchor_date != today:
            self._day_anchor_date = today
            self._day_anchor_balance = balance
            log.info("Ancrage journalier: balance de départ %.2f$", balance)

        daily_pnl = balance - (self._day_anchor_balance or balance)
        positions = await self._client.open_positions(self._account_id)

        state = {
            "balance": balance,
            "daily_pnl": round(daily_pnl, 2),
            "open_positions": len(positions),
            "positions": positions,
        }

        if daily_pnl <= -settings.max_daily_loss:
            return RiskCheck(
                False,
                f"Perte journalière max atteinte ({daily_pnl:.2f}$). Trading stoppé pour aujourd'hui.",
                state,
            )
        if len(positions) >= settings.max_open_positions:
            return RiskCheck(
                False,
                f"Déjà {len(positions)} position(s) ouverte(s) (max {settings.max_open_positions}).",
                state,
            )
        return RiskCheck(True, "OK", state)

    def clamp_size(self, size: int) -> int:
        return max(1, min(size, settings.max_position_size))
