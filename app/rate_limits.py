# app/rate_limits.py
"""Per-endpoint rate limiting.

Tiers (per minute, per client IP):
- local:    60   — local-only queries
- standard: 30   — single CIMA API call
- heavy:    12   — batch/multi-call endpoints

Storage: in-memory by default (no infra). If REDIS_URL is configured,
the same `limits` strategy uses Redis automatically — no code changes needed.
This is the Community/Enterprise seam: deploy with Redis to get distributed
rate limiting across replicas; deploy without and it just works on a single node.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from limits import RateLimitItemPerMinute
from limits.aio.storage import MemoryStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter

from app.config import settings

logger = logging.getLogger(__name__)

LIMIT_LOCAL = RateLimitItemPerMinute(60)
LIMIT_STANDARD = RateLimitItemPerMinute(30)
LIMIT_HEAVY = RateLimitItemPerMinute(12)

_storage: Optional[Storage] = None
_limiter: Optional[MovingWindowRateLimiter] = None


def _get_limiter() -> MovingWindowRateLimiter:
    global _storage, _limiter
    if _limiter is not None:
        return _limiter

    if settings.redis_url:
        try:
            from limits.aio.storage import RedisStorage

            _storage = RedisStorage(f"async+{settings.redis_url}")
            logger.info("Rate-limit backend: Redis")
        except Exception as exc:
            logger.warning(
                "Could not initialise Redis rate-limit storage (%s); using in-memory",
                type(exc).__name__,
            )
            _storage = MemoryStorage()
    else:
        _storage = MemoryStorage()
        logger.info("Rate-limit backend: in-memory")

    _limiter = MovingWindowRateLimiter(_storage)
    return _limiter


def _client_id(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


async def _enforce(request: Request, item: RateLimitItemPerMinute) -> None:
    limiter = _get_limiter()
    identifier = _client_id(request)
    namespace = f"mcp:{request.url.path}"
    allowed = await limiter.hit(item, namespace, identifier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({item.amount}/{item.GRANULARITY.name})",
            headers={"Retry-After": str(item.multiples)},
        )


async def _local(request: Request) -> None:
    await _enforce(request, LIMIT_LOCAL)


async def _standard(request: Request) -> None:
    await _enforce(request, LIMIT_STANDARD)


async def _heavy(request: Request) -> None:
    await _enforce(request, LIMIT_HEAVY)


limit_local = Depends(_local)
limit_standard = Depends(_standard)
limit_heavy = Depends(_heavy)
