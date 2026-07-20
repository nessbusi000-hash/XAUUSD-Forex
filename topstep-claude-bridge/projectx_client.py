"""Client asynchrone pour l'API ProjectX Gateway (TopstepX).

Documentation officielle : https://gateway.docs.projectx.com
Les chemins d'endpoints ci-dessous suivent la doc publique ProjectX ;
vérifiez-les contre votre abonnement API avant de passer en réel.
"""
import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

SIDE_BUY = 0
SIDE_SELL = 1
ORDER_TYPE_LIMIT = 1
ORDER_TYPE_MARKET = 2


class ProjectXError(Exception):
    pass


class ProjectXClient:
    def __init__(self, base_url: str, username: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._api_key = api_key
        self._token: str | None = None
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=20.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _login(self) -> None:
        resp = await self._http.post(
            "/api/Auth/loginKey",
            json={"userName": self._username, "apiKey": self._api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False) or not data.get("token"):
            raise ProjectXError(f"Échec d'authentification ProjectX: {data}")
        self._token = data["token"]
        log.info("Authentifié auprès de ProjectX Gateway")

    async def _post(self, path: str, payload: dict) -> dict:
        async with self._lock:
            if self._token is None:
                await self._login()
        for attempt in range(2):
            resp = await self._http.post(
                path,
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            if resp.status_code == 401 and attempt == 0:
                async with self._lock:
                    await self._login()
                continue
            resp.raise_for_status()
            return resp.json()
        raise ProjectXError(f"Requête refusée après ré-authentification: {path}")

    async def search_accounts(self, only_active: bool = True) -> list[dict]:
        data = await self._post("/api/Account/search", {"onlyActiveAccounts": only_active})
        return data.get("accounts", [])

    async def search_contract(self, search_text: str, live: bool = False) -> dict | None:
        data = await self._post(
            "/api/Contract/search", {"searchText": search_text, "live": live}
        )
        contracts = data.get("contracts", [])
        return contracts[0] if contracts else None

    async def open_positions(self, account_id: int) -> list[dict]:
        data = await self._post("/api/Position/searchOpen", {"accountId": account_id})
        return data.get("positions", [])

    async def place_market_order(
        self, account_id: int, contract_id: str, side: int, size: int
    ) -> dict:
        payload = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": ORDER_TYPE_MARKET,
            "side": side,
            "size": size,
        }
        data = await self._post("/api/Order/place", payload)
        if not data.get("success", False):
            raise ProjectXError(f"Ordre refusé: {data}")
        return data
