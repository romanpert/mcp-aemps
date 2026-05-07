# app/rate_limits.py
"""Per-endpoint rate limiting + global CIMA fan-out cap.

Tiers (per minute, per client IP). Tuned 2026-05-07 to fit how
LLM agents actually work: a single conversation routinely fans out
10-30 tool calls in a few seconds when the model is reasoning across
medicamentos / presentaciones / fichas técnicas. The previous caps
(30/min standard, 6/min heavy) blocked legitimate single-agent work;
the new caps still protect upstream + multi-tenant fairness without
acting as a candado on solo users.

| Tier      | Limit     | Burst budget     | Use case                             |
|-----------|-----------|------------------|--------------------------------------|
| local     | 500/min   | ~8/s sustained   | in-process operations (no upstream)  |
| standard  | 300/min   | ~5/s sustained   | single CIMA call                     |
| document  | 200/min   | ~3/s sustained   | HTML / PDF document fetches          |
| heavy     | 100/min   | ~1.6/s sustained | batch / multi-call fan-out endpoints |

The actual upstream-courtesy guarantee is the global
``CIMA_FANOUT_SEMAPHORE`` (32 concurrent — bumped from 16 in v0.4.9).
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

# Per-client tiers (per minute). See module docstring for the rationale.
# Bumped again in v0.4.9 (~1.7-6.7× the v0.4.8 baseline) for power users
# running several agents in parallel against the same instance — pharma
# regulatory teams often have 5-10 simultaneous Claude Code / Cursor
# sessions on the same intranet IP, and the v0.4.8 caps started biting.
LIMIT_LOCAL = RateLimitItemPerMinute(500)
LIMIT_STANDARD = RateLimitItemPerMinute(300)
LIMIT_DOCUMENT = RateLimitItemPerMinute(200)
LIMIT_HEAVY = RateLimitItemPerMinute(100)

# Global fan-out cap: max concurrent CIMA requests this server makes
# upstream. Bumped 16 → 32 — modern CIMA backends (post 2025-Q3 upgrade)
# handle this comfortably, and 16 was the observed bottleneck for
# multi-tenant pharma deployments. 32 still keeps a hard ceiling on
# upstream pressure regardless of client count.
CIMA_FANOUT_LIMIT = 32
CIMA_FANOUT_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(CIMA_FANOUT_LIMIT)

# Per-batch-request fan-out cap: how many parallel CIMA calls a single
# /batch-style endpoint can spawn. Bumped 8 → 20 — large batches like
# `listar_notas(nregistro=[<15-20 nregistros>])` (one per drug in a
# pharmacist's vade-mecum query) now run wide instead of serialising.
BATCH_FANOUT_LIMIT = 20

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
