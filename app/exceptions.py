"""
app/exceptions.py — кастомные HTTP-исключения FastAPI.

Иерархия::

    AppError                # базовый класс (несёт HTTP-статус и detail)
    ├── NotFoundError       # 404
    ├── ValidationError     # 422 (бизнес-логика, не pydantic)
    ├── UnauthorizedError   # 401
    ├── ForbiddenError      # 403
    └── ServiceUnavailable  # 503 (БД/Redis недоступны)

Глобальный обработчик регистрируется в app/main.py::

    from app.exceptions import AppError, app_error_handler
    app.add_exception_handler(AppError, app_error_handler)
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Базовый класс. Конвертируется в JSONResponse через app_error_handler."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str, *, error_code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if error_code is not None:
            self.error_code = error_code

    def to_dict(self) -> dict:
        return {"error": self.error_code, "detail": self.detail}


class NotFoundError(AppError):
    """Ресурс не найден (404)."""
    status_code = 404
    error_code = "NOT_FOUND"


class UnauthorizedError(AppError):
    """Не передан или неверный токен авторизации (401)."""
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    """Доступ запрещён (403)."""
    status_code = 403
    error_code = "FORBIDDEN"


class ValidationError(AppError):
    """Бизнес-логика: некорректные данные запроса (422)."""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ServiceUnavailable(AppError):
    """Внешняя зависимость (БД / Redis) недоступна (503)."""
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


# ── Глобальный обработчик ─────────────────────────────────────────────────────


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )
