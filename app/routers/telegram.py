"""
app/routers/telegram.py

POST /telegram/notify — отправить сообщение в Telegram через существующий бот.

Использует TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID из .env.
Поддерживает Markdown-разметку.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_token
from app.config import settings

log = logging.getLogger("telegram")
router = APIRouter(prefix="/telegram", tags=["telegram"])

_TG_API = "https://api.telegram.org/bot{token}/sendMessage"


class NotifyRequest(BaseModel):
    message:    str  = Field(..., min_length=1, max_length=4096,
                             description="Текст сообщения (поддерживается Markdown)")
    chat_id:    str  = Field("", description="Переопределить chat_id (по умолчанию из .env)")
    parse_mode: str  = Field("Markdown", description="HTML или Markdown")


class NotifyResponse(BaseModel):
    ok:         bool
    message_id: int | None = None
    detail:     str = ""


@router.post("/notify", response_model=NotifyResponse)
async def telegram_notify(
    body: NotifyRequest,
    _:    str = Depends(verify_token),
):
    """
    Отправляет сообщение в Telegram.

    Пример:
        POST /telegram/notify
        {"message": "🔔 Новая вакансия: *Senior C++* в EPAM"}
    """
    token = settings.telegram_bot_token
    if not token:
        raise HTTPException(status_code=503,
                            detail="TELEGRAM_BOT_TOKEN не задан")

    chat_id = body.chat_id or settings.telegram_chat_id
    if not chat_id:
        raise HTTPException(status_code=503,
                            detail="TELEGRAM_CHAT_ID не задан")

    url = _TG_API.format(token=token)
    payload = {
        "chat_id":    chat_id,
        "text":       body.message,
        "parse_mode": body.parse_mode,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except Exception as e:
        log.error("Telegram request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Telegram недоступен: {e}")

    if not data.get("ok"):
        err = data.get("description", "unknown error")
        log.warning("Telegram API error: %s", err)
        raise HTTPException(status_code=400, detail=f"Telegram: {err}")

    msg_id = data.get("result", {}).get("message_id")
    log.info("Telegram message sent: id=%s chat=%s", msg_id, chat_id)
    return NotifyResponse(ok=True, message_id=msg_id)
