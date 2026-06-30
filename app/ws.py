"""
app/ws.py — WebSocket manager и роутер /ws/updates.

Клиент подключается и получает push-уведомления когда:
- morning_brief находит новые вакансии
- поступает любое другое событие через broadcast()

Пример JS-клиента:
    const ws = new WebSocket("wss://your-app.railway.app/ws/updates");
    ws.onmessage = (e) => console.log(JSON.parse(e.data));
"""
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("ws")
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Хранит активные WS-соединения и рассылает сообщения."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        log.info("WS connected, total=%d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        log.info("WS disconnected, total=%d", len(self._connections))

    async def broadcast(self, event: str, data: Any) -> None:
        """Разослать событие всем подключённым клиентам."""
        if not self._connections:
            return
        payload = json.dumps({
            "event":     event,
            "data":      data,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass

    @property
    def count(self) -> int:
        return len(self._connections)


# Синглтон — импортируется из других модулей
manager = ConnectionManager()


async def broadcast_new_vacancies(vacancies: list[dict]) -> None:
    """Вспомогательная функция — вызывается из brief/scheduler."""
    if not vacancies:
        return
    await manager.broadcast("new_vacancies", {
        "count": len(vacancies),
        "items": vacancies[:10],   # первые 10 чтобы не перегружать
    })


# ── Роутер ────────────────────────────────────────────────────────────────

@router.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket):
    """
    WebSocket endpoint для real-time уведомлений.
    Авторизация: передать токен в query-параметре ?token=...
        ws = new WebSocket("wss://host/ws/updates?token=<API_TOKEN>")
    """
    from app.config import settings

    token = websocket.query_params.get("token", "")
    if token != settings.api_token:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket)
    # Приветственное сообщение
    await websocket.send_text(json.dumps({
        "event": "connected",
        "data":  {"clients": manager.count},
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }))
    try:
        while True:
            # Держим соединение живым, принимаем ping от клиента
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
