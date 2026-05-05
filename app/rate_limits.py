# app/rate_limits.py
"""Per-endpoint rate limiting + global CIMA fan-out cap.

Tiers (per minute, per client IP) — basis: CIMA publishes no formal rate
limits, but multi-tenant fairness + courtesy to AEMPS dictate caps tighter
than what one IP can sustain alone.

| Tier      | Limit     | Use case                                          |
|-----------|-----------|---------------------------------------------------|
| local     | 120/min   | local-only queries (no upstream cost)             |
| standard  | 30/min    | single CIMA call                                  |
| document  | 10/min    | HTML / PDF document fetches (large payloads)      |
| heavy     | 6/min     | batch / multi-call endpoints (fans out N calls)   |

Storage: in-memory by default (no infra). If REDIS_URL is configured the
same `limits` strategy uses Redis automatically — no code changes needed.

Plus: CIMA_FANOUT_SEMAPHORE — module-level asyncio.Semaphore that caps the
TOTAL concurrent CIMA requests this server makes upstream, regardless of
how many clients are hitting which tier. This is the single most impactful
defence against accidentally hammering AEMPS.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from limits import RateLimitItemPerMinute
from limits.aio.storage import MemoryStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter

from app.config import settings

logger = logging.getLogger(__name__)

# Per-client tiers
LIMIT_LOCAL = RateLimitItemPerMinute(120)
LIMIT_STANDARD = RateLimitItemPerMinute(30)
LIMIT_DOCUMENT = RateLimitItemPerMinute(10)
LIMIT_HEAVY = RateLimitItemPerMinute(6)

# Global fan-out cap: max concurrent CIMA requests this server makes upstream.
# 8 is conservative for a multi-tenant deployment with ~50-100 active users.
CIMA_FANOUT_LIMIT = 8
CIMA_FANOUT_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(CIMA_FANOUT_LIMIT)

# Per-batch-request fan-out cap: how many parallel CIMA calls a single
# /batch-style endpoint can spawn. Lower than the global so one batch
# request can't monopolise the upstream channel.
BATCH_FANOUT_LIMIT = 4

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
            detail=f"Rate limit exceeded ({item.amount}/min)",
            headers={"Retry-After": "60"},
        )


async def _local(request: Request) -> None:
    await _enforce(request, LIMIT_LOCAL)


async def _standard(request: Request) -> None:
    await _enforce(request, LIMIT_STANDARD)


async def _document(request: Request) -> None:
    await _enforce(request, LIMIT_DOCUMENT)


async def _heavy(request: Request) -> None:
    await _enforce(request, LIMIT_HEAVY)


limit_local = Depends(_local)
limit_standard = Depends(_standard)
limit_document = Depends(_document)
limit_heavy = Depends(_heavy)
