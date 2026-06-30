"""
app/main.py — точка входа FastAPI-приложения.

Запуск:
  python -m uvicorn app.main:app --reload --port 8000

Swagger UI:  http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.cache import close_cache, init_cache
from app.config import settings
from app.database import engine
from app.exceptions import AppError, app_error_handler
from app.middleware import AccessLogMiddleware, setup_access_log
from app.routers import brief, freelance, health, stats, vacancies
from app.routers import telegram as tg_router
from app.scheduler import create_scheduler
from app.ws import router as ws_router

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # ── Startup ──
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    setup_access_log("access.log")

    # PostgreSQL
    if engine is not None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL: connection established")
        except Exception as exc:
            logger.warning("PostgreSQL unavailable at startup: %s", exc)

    # Redis
    try:
        await init_cache(settings.redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable at startup: %s", exc)

    # Планировщик
    scheduler = None
    try:
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("Scheduler started (brief @ %s UTC)", settings.scheduler_brief_time)
    except Exception as exc:
        logger.warning("Scheduler not started: %s", exc)

    yield

    # ── Shutdown ──
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
    await close_cache()
    if engine is not None:
        await engine.dispose()
    logger.info("Connections closed")


# ── Приложение ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Job Search API",
    description=(
        "REST API для системы поиска работы.\n\n"
        "**Авторизация:** Bearer token (`API_TOKEN` из .env).\n"
        "Нажмите 🔒 Authorize → введите токен.\n\n"
        "**WebSocket:** `wss://host/ws/updates?token=<API_TOKEN>`"
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# ── Exception handlers ───────────────────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)

# ── Middleware ────────────────────────────────────────────────────────────
app.add_middleware(AccessLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:5173", "http://localhost:8080",
        "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Роутеры ───────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(vacancies.router)
a