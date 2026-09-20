"""Central config — env-driven, safe defaults. No secrets hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, str(default)).strip().lower()
    return val in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class Settings:
    dhan_client_id: str = ""
    dhan_access_token: str = ""
    dhan_pin: str = ""
    dhan_totp_secret: str = ""
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    telegram_admin_chat_id: str = ""
    owner_id: str = ""  # your Telegram user id — only this user may /template
    chart_url: str = "https://web.dhan.co"  # blue [[numbers]] link target (no preview)
    group_window_sec: int = 120
    only_traded: bool = True
    dry_run: bool = True
    db_path: str = "data/state.db"
    token_json: str = "data/token.json"
    order_ws_url: str = "wss://api-order-update.dhan.co"


def load_settings() -> Settings:
    return Settings(
        dhan_client_id=_get("DHAN_CLIENT_ID"),
        dhan_access_token=_get("DHAN_ACCESS_TOKEN"),
        dhan_pin=_get("DHAN_PIN"),
        dhan_totp_secret=_get("DHAN_TOTP_SECRET"),
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
        telegram_channel_id=_get("TELEGRAM_CHANNEL_ID"),
        telegram_admin_chat_id=_get("TELEGRAM_ADMIN_CHAT_ID"),
        owner_id=_get("OWNER_ID"),
        chart_url=_get("CHART_URL", "https://web.dhan.co"),
        group_window_sec=_get_int("GROUP_WINDOW_SEC", 120),
        only_traded=_get_bool("ONLY_TRADED", True),
        dry_run=_get_bool("DRY_RUN", True),
        db_path=_get("DB_PATH", "data/state.db"),
        token_json=_get("TOKEN_JSON", "data/token.json"),
    )
