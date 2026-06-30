"""
app/database.py — асинхронный движок SQLAlchemy (asyncpg).

Neon URL: postgresql://user:pass@host/db?sslmode=require
→ преобразуется в: postgresql+asyncpg://user:pass@host/db
с connect_args={"ssl": "require"}

Если DATABASE_URL не задан — движок не создаётся, приложение стартует
в режиме "без БД" и отдаёт degraded на /health (не крашится).
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _make_async_url(dsn: str) -> tuple[str, dict]:
    """Конвертирует postgresql:// → postgresql+asyncpg://, извлекает ssl."""
    connect_args: dict = {}
    url = dsn

    if "sslmode=require" in url:
        connect_args["ssl"] = "require"
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")

    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url, connect_args


_DB_URL = (settings.database_url or "").strip()

if _DB_URL:
    _async_url, _connect_args = _make_async_url(_DB_URL)
    engine = create_async_engine(
        _async_url,
        connect_args=_connect_args,
        echo=settings.debug,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
else:
    # DATABASE_URL не задан — движок-заглушка
    engine = None           # type: ignore[assignment]
    AsyncSessionLocal = None  # type: ignore[assignment]


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — поставляет сессию БД в роутер."""
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL не задан — БД недоступна")
    async with AsyncSessionLocal() as session:
        yield session
