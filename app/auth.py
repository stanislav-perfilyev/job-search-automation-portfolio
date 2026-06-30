"""
app/auth.py — Bearer-токен авторизация.

Токен задаётся в .env как API_TOKEN.
Клиент передаёт: Authorization: Bearer <token>
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=True)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Зависимость FastAPI: проверяет Bearer-токен."""
    if credentials.credentials != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
