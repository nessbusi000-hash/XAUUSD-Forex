"""Analyse des signaux TradingView par Claude, avec sortie structurée validée."""
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel

from config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es l'analyste de risque d'un trader sur compte Topstep (prop firm futures).
Tu reçois un signal d'alerte TradingView et l'état actuel du compte.

Ton rôle : évaluer si ce trade doit être proposé au trader pour validation.
Tu n'exécutes rien toi-même — le trader garde la décision finale.

Règles Topstep à respecter impérativement :
- Ne jamais recommander un trade qui pourrait franchir la perte journalière maximale.
- Respecter la taille de position maximale configurée.
- Éviter d'empiler des positions dans la même direction quand une position est déjà ouverte.
- Être prudent autour des annonces macro majeures (NFP, FOMC, CPI).

Sois direct et concis. Réponds en français dans le champ reasoning.
"""


class TradeDecision(BaseModel):
    action: Literal["recommend", "skip"]
    confidence: int  # 0-100
    position_size: int  # contrats recommandés (0 si skip)
    reasoning: str  # 2-3 phrases en français


class ClaudeAnalyst:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze(self, signal: dict, account_state: dict) -> TradeDecision:
        user_message = (
            f"Signal TradingView reçu :\n{signal}\n\n"
            f"État du compte Topstep :\n{account_state}\n\n"
            f"Limites configurées : perte journalière max {settings.max_daily_loss}$, "
            f"taille max {settings.max_position_size} contrat(s), "
            f"max {settings.max_open_positions} position(s) ouverte(s).\n\n"
            "Évalue ce signal et rends ta décision."
        )
        response = await self._client.messages.parse(
            model="claude-opus-4-8",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=TradeDecision,
        )
        decision = response.parsed_output
        if decision is None:
            log.warning("Sortie Claude non parsable, signal ignoré par sécurité")
            return TradeDecision(
                action="skip",
                confidence=0,
                position_size=0,
                reasoning="Analyse illisible — signal ignoré par précaution.",
            )
        log.info("Décision Claude: %s (confiance %d%%)", decision.action, decision.confidence)
        return decision
