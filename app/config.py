"""
app/config.py — настройки приложения через pydantic-settings.
Читает из .env в корне проекта.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL (Neon или локальный)
    database_url: str = ""

    # Секрет Bearer-токена для API авторизации
    api_token: str = "dev-token-change-me"

    # Redis (опционально — кэш /stats)
    redis_url: str = ""           # redis://localhost:6379/0

    # Telegram бот (для /telegram/notify и алертов планировщика)
    telegram_bot_token: str = ""
    telegram_chat_id:   str = ""

    # Планировщик: время запуска morning_brief (HH:MM, UTC)
    scheduler_brief_time: str = "05:15"   # 08:15 Алматы = 05:15 UTC

    # ClickHouse (OLAP аналитика, опционально)
    clickhouse_url: str = ""    # clickhouse://user:pass@host:8123/analytics

    # Дополнительно
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
