# app/cache.py
"""Cache backend abstraction.

Community Edition: in-memory TTL cache (cachetools), zero infra required.
Enterprise Edition: same interface, Redis-backed when REDIS_URL is configured.

The selection is automatic — if REDIS_URL is set and reachable, Redis is used;
otherwise the server falls back to in-memory and continues working with no
external dependencies.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from cachetools import TTLCache
from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger(__name__)

MAESTRAS_TYPES: tuple[int, ...] = (1, 2, 3, 4, 5)
MAESTRAS_TTL_SECONDS = 86_400  # 24h

_DEFAULT_MAXSIZE = 4096


class CacheBackend(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def close(self) -> None: ...


class InMemoryCache:
    """Async wrapper over cachetools.TTLCache. Pure Python, no infra."""

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE, ttl: int = MAESTRAS_TTL_SECONDS):
        self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        async with self._lock:
            return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._store[key] = value

    async def close(self) -> None:
        return None


class RedisCache:
    """Redis-backed cache. Used when REDIS_URL is set and reachable."""

    def __init__(self, redis: Any):
        self._redis = redis

    async def get(self, key: str) -> Any:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._redis.setex(key, ttl, json.dumps(value))

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:
            pass


async def init_cache_backend(app: FastAPI) -> None:
    """Pick a backend based on settings.redis_url; populate app.state."""
    if settings.redis_url:
        try:
            from redis.asyncio import Redis

            redis = Redis.from_url(str(settings.redis_url))
            await redis.ping()
            app.state.cache = RedisCache(redis)
            app.state.redis = redis
            logger.info("Cache backend: Redis (%s)", settings.redis_url.host)
            return
        except Exception as exc:
            logger.warning(
                "Redis unreachable (%s); falling back to in-memory cache",
                type(exc).__name__,
            )

    app.state.cache = InMemoryCache()
    app.state.redis = None
    logger.info("Cache backend: in-memory")


async def close_cache_backend(app: FastAPI) -> None:
    cache = getattr(app.state, "cache", None)
    if cache is not None:
        await cache.close()


async def warm_maestras(app: FastAPI) -> None:
    """Populate maestras catalogues at startup so the first request is fast."""
    import app.cima_client as cima

    cache: CacheBackend = app.state.cache
    for maestra_id in MAESTRAS_TYPES:
        key = f"mcp:maestras:{maestra_id}"
        try:
            if await cache.get(key) is not None:
                logger.debug("maestras tipo=%s already cached", maestra_id)
                continue
            data = await cima.maestras(maestra=maestra_id)
            if data:
                await cache.set(key, data, MAESTRAS_TTL_SECONDS)
                logger.info("Warmed maestras tipo=%s", maestra_id)
        except Exception as exc:
            logger.warning(
                "Warmup maestras tipo=%s failed (%s); will fetch on demand",
                maestra_id,
                type(exc).__name__,
            )


async def periodic_maestras_refresh(app: FastAPI) -> None:
    """Background task: refresh maestras every 24h without restarting the app."""
    while True:
        try:
            await asyncio.sleep(MAESTRAS_TTL_SECONDS)
            logger.info("Refreshing maestras cache")
            await warm_maestras(app)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("maestras refresh error (%s)", type(exc).__name__)
