"""
app/routers/health.py

GET /health — статус сервиса и подключения к БД.
Не требует авторизации. Всегда возвращает HTTP 200.
"""
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status:    str
    db:        str
    timestamp: str
    version:   str = "1.0.0"


@router.get("/health", response_model=HealthOut)
async def health():
    """Проверяет доступность сервиса и БД."""
    from app.database import AsyncSessionLocal

    db_status = "ok"
    if AsyncSessionLocal is None:
        db_status = "no DATABASE_URL"
    else:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        except Exception as e:
            db_status = f"error: {e}"

    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        timestamp=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )
