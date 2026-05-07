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

import json
import logging
from typing import Any, Protocol

from cachetools import TTLCache
from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger(__name__)

# Note: the maestras warmup that lived here through v0.4.12 was
# **dead code**. Verified empirically with curl on 2026-05-08: every
# documented maestra ID (1, 3, 4, 6, 7, 11, 13, 14, 15, 16) returns
# `204 No Content` when called with only ``?maestra=N`` and no filter
# — CIMA blocks the bare enumeration of these catalogues (the
# principios-activos master alone is several thousand entries; CIMA
# requires a substring filter via ``nombre=``, ``codigo=``, or ``id=``
# to return data). Calling the warmup populated nothing because the
# 204 response had no body.
#
# The earlier v0.4.12 explanation that "IDs 2 and 5 don't exist" was
# wrong by deduction — IDs 1, 3, 4, 6, 7 ARE documented and they
# also return 204. The whole pattern is the issue, not the IDs.
#
# Do **not** re-introduce a warmup that calls bare ``?maestra=N``.
# If we ever need warm catalogues, the only working pattern is
# repeated calls with substring filters covering each letter, which
# is too much upstream load to justify for a startup-time benefit.
MAESTRAS_TTL_SECONDS = (
    86_400  # 24h — TTL kept for the on-demand cache populated by the consultar_maestras tool itself.
)

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


# `warm_maestras` and `periodic_maestras_refresh` removed in v0.4.13.
# See the long comment near the top of this module for the empirical
# reason: CIMA returns 204 for bare ``?maestra=N`` calls so the
# warmup populated nothing. The on-demand cache fed by the
# ``consultar_maestras`` tool itself (with whatever filter the caller
# passed) still works as before — every caller naturally hits the
# filter path.
