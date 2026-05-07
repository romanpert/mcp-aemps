# app/cache.py
"""Cache backend abstraction.

Two backends behind one interface:
- in-memory TTL cache (``cachetools``) — zero infra required, default.
- Redis (or any Redis-compatible store like Valkey) when ``REDIS_URL`` is set
  and reachable.

The selection is automatic. If ``REDIS_URL`` is configured but the server
cannot reach it at startup, we log a warning and fall back to in-memory so
the process keeps serving traffic.
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

# CIMA REST API v1.23 §maestras documents the IDs 1, 3, 4, 6, 7,
# 11, 13, 14, 15, 16. IDs 2 and 5 do NOT exist — they return
# `204 No Content`. The pre-v0.4.12 list `(1, 2, 3, 4, 5)` was a
# carry-over from an early misreading of the spec; warming hit two
# invalid IDs on every startup, polluting logs with two harmless-
# but-confusing 204s. We now warm the five core catalogues actually
# referenced by the tools (principios activos, formas farmacéuticas,
# vías de administración, laboratorios, ATC). The SNOMED maestras
# (11/13/14/15/16) are large and rarely queried interactively, so
# we keep them off the warmup path.
MAESTRAS_TYPES: tuple[int, ...] = (1, 3, 4, 6, 7)
MAESTRAS_TTL_SECONDS = 86_400  # 24h

_DEFAULT_MAXSIZE = 4096


class CacheBackend(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def close(self) -> None: ...


class InMemoryCache:
    """Async wrapper over cachetools.TTLCache. Pure Python, no infra.

    No lock needed: ``TTLCache`` operations are O(1) and safe in a single
    asyncio loop because the wrapper methods do not await between read and
    write. A lock would only add contention.
    """

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE, ttl: int = MAESTRAS_TTL_SECONDS):
        self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    async def get(self, key: str) -> Any:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
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
