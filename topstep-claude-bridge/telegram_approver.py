"""Validation manuelle des trades via Telegram (boutons Approuver / Rejeter).

Utilise l'API Bot Telegram en HTTP direct (pas de dépendance lourde) :
- envoi d'un message avec clavier inline,
- long-polling getUpdates en tâche de fond pour récupérer la décision.
"""
import asyncio
import itertools
import logging

import httpx

from config import settings

log = logging.getLogger(__name__)


class TelegramApprover:
    def __init__(self) -> None:
        self._api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._http = httpx.AsyncClient(timeout=40.0)
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._ids = itertools.count(1)
        self._offset = 0
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        await self._http.aclose()

    async def notify(self, text: str) -> None:
        """Message d'information simple, sans validation."""
        await self._http.post(
            f"{self._api}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text},
        )

    async def request_approval(self, text: str) -> bool:
        """Envoie le trade proposé et attend Approuver/Rejeter (ou timeout => rejet)."""
        request_id = f"trade-{next(self._ids)}"
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._http.post(
            f"{self._api}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "✅ Approuver", "callback_data": f"{request_id}:yes"},
                        {"text": "❌ Rejeter", "callback_data": f"{request_id}:no"},
                    ]]
                },
            },
        )
        try:
            return await asyncio.wait_for(future, timeout=settings.approval_timeout_seconds)
        except asyncio.TimeoutError:
            log.info("Validation expirée pour %s — trade rejeté", request_id)
            await self.notify(f"⏱ Signal {request_id} expiré sans validation — rejeté.")
            return False
        finally:
            self._pending.pop(request_id, None)

    async def _poll_loop(self) -> None:
        while True:
            try:
                resp = await self._http.get(
                    f"{self._api}/getUpdates",
                    params={"offset": self._offset, "timeout": 30,
                            "allowed_updates": '["callback_query"]'},
                )
                for update in resp.json().get("result", []):
                    self._offset = update["update_id"] + 1
                    callback = update.get("callback_query")
                    if not callback:
                        continue
                    request_id, _, answer = callback.get("data", "").partition(":")
                    future = self._pending.get(request_id)
                    if future and not future.done():
                        future.set_result(answer == "yes")
                    await self._http.post(
                        f"{self._api}/answerCallbackQuery",
                        json={"callback_query_id": callback["id"]},
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Erreur de polling Telegram — nouvelle tentative dans 5s")
                await asyncio.sleep(5)
