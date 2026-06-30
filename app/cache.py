"""
app/cache.py — Redis-кэш с graceful fallback.

Если REDIS_URL не задан или Redis недоступен — кэш прозрачно отключается,
запросы идут напрямую в БД (degraded mode, без краша).

Использование:
    from app.cache import cache
    data = await cache.get("stats:7")
    await cache.set("stats:7", data, ttl=300)
    await cache.delete("stats:7")
    await cache.delete_pattern("stats:*")
"""
import json
import logging
from typing import Any

log = logging.getLogger("cache")

_redis_client = None   # глобальный клиент, инициализируется в lifespan


async def init_cache(redis_url: str) -> None:
    """Вызывается при старте приложения (lifespan)."""
    global _redis_client
    if not redis_url:
        log.info("REDIS_URL не задан — кэш отключён")
        return
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
        )
        await client.ping()
        _redis_client = client
        log.info("Redis подключён: %s", redis_url.split("@")[-1])
    except Exception as e:
        log.warning("Redis недоступен (%s) — кэш отключён", e)
        _redis_client = None


async def close_cache() -> None:
    """Вызывается при остановке приложения (lifespan)."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        log.info("Redis соединение закрыто")


class Cache:
    """Тонкая обёртка над redis.asyncio с JSON-сериализацией."""

    @property
    def available(self) -> bool:
        return _redis_client is not None

    async def get(self, key: str) -> Any | None:
        if not self.available:
            return None
        try:
            raw = await _redis_client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            log.warning("cache.get(%s) error: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.available:
            return False
        try:
            await _redis_client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
            return True
        except Exception as e:
            log.warning("cache.set(%s) error: %s", key, e)
            return False

    async def delete(self, key: str) -> None:
        if not self.available:
            return
        try:
            await _redis_client.delete(key)
        except Exception as e:
            log.warning("cache.delete(%s) error: %s", key, e)

    async def delete_pattern(self, pattern: str) -> int:
        """Удалить все ключи по паттерну (SCAN + DEL)."""
        if not self.available:
            return 0
        try:
            keys = await _redis_client.keys(pattern)
            if keys:
                await _redis_client.delete(*keys)
            return len(keys)
        except Exception as e:
            log.warning("cache.delete_pattern(%s) error: %s", pattern, e)
            return 0


cache = Cache()
