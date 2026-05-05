# mcp_aemps/app/rate_limits.py
# Per-endpoint rate limiting tiers.
#
# Three tiers based on cost:
#   - local:    60 req/min — DataFrame-only queries, no external I/O
#   - standard: 30 req/min — single CIMA API call
#   - heavy:    12 req/min — batch/multi-call endpoints (N concurrent CIMA requests)
from __future__ import annotations

from fastapi import Depends
from fastapi_limiter.depends import RateLimiter


def _local() -> RateLimiter:
    return RateLimiter(times=60, seconds=60)


def _standard() -> RateLimiter:
    return RateLimiter(times=30, seconds=60)


def _heavy() -> RateLimiter:
    return RateLimiter(times=12, seconds=60)


limit_local = Depends(_local)
limit_standard = Depends(_standard)
limit_heavy = Depends(_heavy)
