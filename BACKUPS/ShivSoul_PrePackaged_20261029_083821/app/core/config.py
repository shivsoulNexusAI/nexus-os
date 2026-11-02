import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram Bot Secrets
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    BOT_TOKEN: Optional[str] = None
    ADMIN_TELEGRAM_ID: Optional[str] = None

    # AI / Vision APIs
    GEMINI_API_KEY: Optional[str] = None

    # MT5 Bridge Execution Endpoint
    MT5_BRIDGE_URL: str = "http://127.0.0.1:5000/webhook"

    # Allow extra fields without throwing ValidationError
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()