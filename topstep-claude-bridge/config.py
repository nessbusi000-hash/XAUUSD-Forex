"""Configuration centralisée, chargée depuis les variables d'environnement."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")

    projectx_base_url: str = os.environ.get("PROJECTX_BASE_URL", "https://api.topstepx.com")
    projectx_username: str = os.environ.get("PROJECTX_USERNAME", "")
    projectx_api_key: str = os.environ.get("PROJECTX_API_KEY", "")
    projectx_account_id: str = os.environ.get("PROJECTX_ACCOUNT_ID", "")

    webhook_secret: str = os.environ.get("WEBHOOK_SECRET", "")

    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")

    max_daily_loss: float = float(os.environ.get("RISK_MAX_DAILY_LOSS", "1000"))
    max_position_size: int = int(os.environ.get("RISK_MAX_POSITION_SIZE", "2"))
    max_open_positions: int = int(os.environ.get("RISK_MAX_OPEN_POSITIONS", "1"))
    approval_timeout_seconds: int = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "300"))


settings = Settings()
