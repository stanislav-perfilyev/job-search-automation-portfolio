"""
app/middleware.py — Middleware логирования HTTP запросов в access.log.

Формат записи:
    2026-06-29T07:15:00Z  POST /vacancies  201  45ms  127.0.0.1
"""
import logging
import time
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Отдельный логгер → access.log
_access_log = logging.getLogger("access")


def setup_access_log(log_file: str = "access.log") -> None:
    """Настраивает файловый хэндлер для access.log."""
    if _access_log.handlers:
        return   # уже настроен
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    _access_log.addHandler(handler)
    _access_log.setLevel(logging.INFO)
    _access_log.propagate = False


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Логирует каждый HTTP-запрос в access.log."""

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            _log(request, 500, elapsed)
            raise
        elapsed = int((time.monotonic() - t0) * 1000)
        _log(request, response.status_code, elapsed)
        return response


def _log(request: Request, status: int, elapsed_ms: int) -> None:
    ip  = request.client.host if request.client else "-"
    ts  = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _access_log.info(
        "%s  %-6s %-40s  %d  %dms  %s",
        ts, request.method, request.url.path, status, elapsed_ms, ip,
    )
