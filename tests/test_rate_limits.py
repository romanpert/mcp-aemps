"""Tests for the rate-limit module's tiers and fan-out caps."""

from __future__ import annotations

import asyncio

import pytest


def test_tier_limits_match_documented_values() -> None:
    from app.rate_limits import (
        BATCH_FANOUT_LIMIT,
        CIMA_FANOUT_LIMIT,
        LIMIT_DOCUMENT,
        LIMIT_HEAVY,
        LIMIT_LOCAL,
        LIMIT_STANDARD,
    )

    # v0.4.9 — limits bumped again to fit multi-agent pharma intranet
    # deployments (5-10 simultaneous sessions on the same IP). Upstream
    # courtesy still enforced via CIMA_FANOUT_SEMAPHORE (32 ceiling).
    assert LIMIT_LOCAL.amount == 500
    assert LIMIT_STANDARD.amount == 300
    assert LIMIT_DOCUMENT.amount == 200
    assert LIMIT_HEAVY.amount == 100
    assert CIMA_FANOUT_LIMIT == 32
    assert BATCH_FANOUT_LIMIT == 20


def test_global_semaphore_caps_concurrent_acquisitions() -> None:
    """The global CIMA fan-out semaphore must cap concurrent acquisitions."""
    from app.rate_limits import CIMA_FANOUT_LIMIT, CIMA_FANOUT_SEMAPHORE

    async def runner():
        active = 0
        peak = 0

        async def task():
            nonlocal active, peak
            async with CIMA_FANOUT_SEMAPHORE:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        # Launch 2x the limit so we definitely saturate the semaphore
        # — with N tasks <= limit, observed peak == N tells us nothing.
        await asyncio.gather(*(task() for _ in range(CIMA_FANOUT_LIMIT * 2)))
        return peak

    peak = asyncio.run(runner())
    assert peak <= CIMA_FANOUT_LIMIT


@pytest.mark.asyncio
async def test_bounded_gather_respects_limit() -> None:
    """bounded_gather must cap concurrent coroutines per call."""
    from app.helpers import bounded_gather

    active = 0
    peak = 0

    async def task(i: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return i

    coros = [task(i) for i in range(20)]
    results = await bounded_gather(coros, limit=3)

    assert len(results) == 20
    assert sorted(results) == list(range(20))
    assert peak <= 3


@pytest.mark.asyncio
async def test_bounded_gather_returns_exceptions_by_default() -> None:
    from app.helpers import bounded_gather

    async def ok():
        return "ok"

    async def fail():
        raise RuntimeError("boom")

    results = await bounded_gather([ok(), fail(), ok()], limit=2)
    assert results[0] == "ok"
    assert isinstance(results[1], RuntimeError)
    assert results[2] == "ok"


def test_version_resolved_from_package_metadata() -> None:
    """settings.mcp_aemps_version must read from importlib.metadata, not be hardcoded."""
    from importlib.metadata import version

    from app.config import settings

    expected = version("mcp-aemps")
    assert settings.mcp_aemps_version == expected
