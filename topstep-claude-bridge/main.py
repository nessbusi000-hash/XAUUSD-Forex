"""Point d'entrée : serveur FastAPI recevant les webhooks TradingView.

Pipeline par signal :
  1. Vérification du secret partagé
  2. Garde-fous de risque Topstep (codés en dur, non négociables)
  3. Analyse du signal par Claude (recommandation structurée)
  4. Validation manuelle via Telegram (conformité règles Topstep)
  5. Exécution de l'ordre via l'API ProjectX (TopstepX)

Lancement :  uvicorn main:app --host 0.0.0.0 --port 8080
"""
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from claude_analyst import ClaudeAnalyst
from config import settings
from projectx_client import SIDE_BUY, SIDE_SELL, ProjectXClient
from risk_manager import RiskManager
from telegram_approver import TelegramApprover

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("bridge")


class TradingViewAlert(BaseModel):
    """Corps JSON attendu depuis l'alerte TradingView.

    Exemple de message d'alerte à configurer dans TradingView :
    {"secret": "...", "symbol": "MGC", "side": "buy", "price": {{close}},
     "strategy": "breakout-h1", "comment": "cassure du plus haut hebdo"}
    """
    secret: str
    symbol: str
    side: str  # "buy" | "sell"
    price: float | None = None
    strategy: str | None = None
    comment: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.px = ProjectXClient(
        settings.projectx_base_url,
        settings.projectx_username,
        settings.projectx_api_key,
    )
    if settings.projectx_account_id:
        account_id = int(settings.projectx_account_id)
    else:
        accounts = await app.state.px.search_accounts()
        if not accounts:
            raise RuntimeError("Aucun compte Topstep actif trouvé via l'API ProjectX")
        account_id = accounts[0]["id"]
        log.info("Compte sélectionné automatiquement: %s", account_id)
    app.state.account_id = account_id
    app.state.risk = RiskManager(app.state.px, account_id)
    app.state.analyst = ClaudeAnalyst()
    app.state.telegram = TelegramApprover()
    await app.state.telegram.start()
    await app.state.telegram.notify("🟢 Bridge Topstep ↔ TradingView ↔ Claude démarré.")
    yield
    await app.state.telegram.stop()
    await app.state.px.close()


app = FastAPI(title="topstep-claude-bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/tradingview")
async def tradingview_webhook(alert: TradingViewAlert, background: BackgroundTasks):
    if not settings.webhook_secret or not hmac.compare_digest(
        alert.secret, settings.webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Secret invalide")
    if alert.side.lower() not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="side doit être 'buy' ou 'sell'")

    # Traitement en tâche de fond : TradingView attend une réponse rapide (<3s).
    background.add_task(process_signal, alert)
    return {"status": "accepted"}


async def process_signal(alert: TradingViewAlert) -> None:
    telegram: TelegramApprover = app.state.telegram
    signal = alert.model_dump(exclude={"secret"})
    log.info("Signal reçu: %s", signal)

    # 2. Garde-fous de risque — bloquants, avant toute analyse
    check = await app.state.risk.check()
    if not check.allowed:
        log.info("Signal bloqué par le risk manager: %s", check.reason)
        await telegram.notify(f"🚫 Signal {alert.symbol} {alert.side} bloqué : {check.reason}")
        return

    # 3. Analyse Claude
    decision = await app.state.analyst.analyze(signal, check.account_state)
    if decision.action == "skip":
        await telegram.notify(
            f"⏭ Claude écarte le signal {alert.symbol} {alert.side} "
            f"(confiance {decision.confidence}%) : {decision.reasoning}"
        )
        return

    size = app.state.risk.clamp_size(decision.position_size)

    # 4. Validation manuelle — obligatoire (conformité Topstep : pas de full-auto)
    approved = await telegram.request_approval(
        f"📊 Trade proposé\n"
        f"Symbole : {alert.symbol}\n"
        f"Sens : {alert.side.upper()}  |  Taille : {size} contrat(s)\n"
        f"Stratégie : {alert.strategy or 'n/a'}\n"
        f"PnL du jour : {check.account_state['daily_pnl']}$\n\n"
        f"🧠 Claude (confiance {decision.confidence}%) : {decision.reasoning}"
    )
    if not approved:
        log.info("Trade rejeté par le trader")
        return

    # 5. Exécution
    try:
        contract = await app.state.px.search_contract(alert.symbol)
        if contract is None:
            await telegram.notify(f"⚠️ Contrat introuvable pour '{alert.symbol}'.")
            return
        side = SIDE_BUY if alert.side.lower() == "buy" else SIDE_SELL
        result = await app.state.px.place_market_order(
            app.state.account_id, contract["id"], side, size
        )
        await telegram.notify(
            f"✅ Ordre exécuté : {alert.side.upper()} {size}x {contract.get('name', alert.symbol)} "
            f"(ordre #{result.get('orderId', '?')})"
        )
    except Exception as exc:
        log.exception("Échec d'exécution de l'ordre")
        await telegram.notify(f"❌ Échec d'exécution : {exc}")
