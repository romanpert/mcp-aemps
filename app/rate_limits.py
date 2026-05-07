# app/rate_limits.py
"""Per-endpoint rate limiting + global CIMA fan-out cap.

Tiers (per minute, per client IP). Tuned 2026-05-07 to fit how
LLM agents actually work: a single conversation routinely fans out
10-30 tool calls in a few seconds when the model is reasoning across
medicamentos / presentaciones / fichas técnicas. The previous caps
(30/min standard, 6/min heavy) blocked legitimate single-agent work;
the new caps still protect upstream + multi-tenant fairness without
acting as a candado on solo users.

| Tier      | Limit     | Burst budget    | Use case                              |
|-----------|-----------|-----------------|---------------------------------------|
| local     | 300/min   | ~5/s sustained  | in-process operations (no upstream)   |
| standard  | 120/min   | ~2/s sustained  | single CIMA call                      |
| document  | 30/min    | ~1 every 2s     | HTML / PDF document fetches           |
| heavy     | 20/min    | ~1 every 3s     | batch / multi-call fan-out endpoints  |

The actual upstream-courtesy guarantee is the global
``CIMA_FANOUT_SEMAPHORE`` (16 concurrent — bumped from 8 in v0.4.8).
Per-tier limits are about per-client fairness; the semaphore is what
keeps total concurrent CIMA requests bounded across all clients.

Storage: in-memory by default (no infra). If REDIS_URL is configured the
same `limits` strategy uses Redis automatically — no code changes needed.
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

# Per-client tiers (per minute). See module docstring for the rationale
# behind each value — 2.5x-3.3x the v0.4.7 baseline so legitimate agent
# bursts (10-30 calls in a few seconds when reasoning across CIMA) don't
# trip the limiter on the first turn of a conversation.
LIMIT_LOCAL = RateLimitItemPerMinute(300)
LIMIT_STANDARD = RateLimitItemPerMinute(120)
LIMIT_DOCUMENT = RateLimitItemPerMinute(30)
LIMIT_HEAVY = RateLimitItemPerMinute(20)

# Global fan-out cap: max concurrent CIMA requests this server makes
# upstream. Bumped 8 → 16 alongside the per-tier increase — single agents
# now legitimately do 4-8 parallel calls during fan-out (listar_notas
# across 6 nregistros, problemas_suministro multi-CN), and 8 was the
# observed bottleneck. 16 still keeps a hard ceiling on what we send to
# AEMPS regardless of client count.
CIMA_FANOUT_LIMIT = 16
CIMA_FANOUT_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(CIMA_FANOUT_LIMIT)

# Per-batch-request fan-out cap: how many parallel CIMA calls a single
# /batch-style endpoint can spawn. Lower than the global so one batch
# request can't monopolise the upstream channel. Bumped 4 → 8 to match.
BATCH_FANOUT_LIMIT = 8

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


# Stable public API. Downstream consumers (e.g. MOXI premium routes) can rely
# on these names across 0.2.x — adding new tiers is non-breaking; renaming or
# removing one requires a MINOR bump.
__all__ = [
    "limit_local",
    "limit_standard",
    "limit_document",
    "limit_heavy",
    "LIMIT_LOCAL",
    "LIMIT_STANDARD",
    "LIMIT_DOCUMENT",
    "LIMIT_HEAVY",
    "CIMA_FANOUT_SEMAPHORE",
    "CIMA_FANOUT_LIMIT",
    "BATCH_FANOUT_LIMIT",
]
