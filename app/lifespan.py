# app/lifespan.py
"""Composable lifespan with explicit extension points.

Default wiring: cache backend init -> maestras warmup -> serving ->
maestras task cancellation -> cache backend close.

Downstream consumers can inject extra hooks (OTel init, audit log flush,
external connection pools, etc.) via the ``startup_hooks`` and
``shutdown_hooks`` parameters of ``build_lifespan`` — without forking this
module.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from typing import TYPE_CHECKING, Awaitable, Callable, Sequence

from fastapi import FastAPI

from app.cache import (
    close_cache_backend,
    init_cache_backend,
    periodic_maestras_refresh,
    warm_maestras,
)
from app.cima_client import aclose_shared_client
from app.config import settings as _settings
from app.etag_store import (
    InMemoryETagStore,
    RedisETagStore,
)
from app.etag_store import (
    set_active_store as _set_etag_store,
)
from app.version_check import schedule_check as _schedule_version_check

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

LifecycleHook = Callable[[FastAPI], Awaitable[None]]


def build_lifespan(
    *,
    startup_hooks: Sequence[LifecycleHook] = (),
    shutdown_hooks: Sequence[LifecycleHook] = (),
    fastmcp_server: "FastMCP | None" = None,
):
    """Return a FastAPI-compatible lifespan with the given extension hooks.

    If ``fastmcp_server`` is provided, its ``session_manager.run()`` context
    is opened around the serving period — required when mounting the
    FastMCP Streamable-HTTP app inside the outer FastAPI app, because
    Starlette sub-app lifespans don't auto-run when mounted.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting application lifespan")

        await init_cache_backend(app)

        # Wire the ETag store: Redis-backed when init_cache_backend
        # confirmed Redis is reachable (multi-replica deployments share
        # the revalidation map and the 304 win scales with replicas);
        # in-memory otherwise. Stdio (no FastAPI lifespan) keeps the
        # in-memory default that ``app.etag_store`` initialises at
        # import time.
        redis_client = getattr(app.state, "redis", None)
        if redis_client is not None:
            _set_etag_store(RedisETagStore(redis_client))
            logger.info("ETag store: Redis (shared across replicas)")
        else:
            _set_etag_store(InMemoryETagStore())
            logger.info("ETag store: in-memory (process-local)")

        for hook in startup_hooks:
            try:
                await hook(app)
            except Exception:
                logger.exception("Startup hook %s failed", getattr(hook, "__name__", hook))
                raise

        app.state.warmup_task = asyncio.create_task(warm_maestras(app))
        app.state.refresh_task = asyncio.create_task(periodic_maestras_refresh(app))

        # Fire-and-forget outdated-version check. Logs a single WARNING
        # if PyPI has a newer release; never blocks startup.
        app.state.version_check_task = _schedule_version_check(_settings.mcp_aemps_version)

        # Nest the FastMCP session manager around the serving period when
        # the HTTP transport is mounted. Without this, /mcp requests crash
        # with "Task group is not initialized" because the session manager's
        # background task group never starts.
        async with AsyncExitStack() as stack:
            if fastmcp_server is not None:
                await stack.enter_async_context(fastmcp_server.session_manager.run())

            try:
                yield
            finally:
                for hook in reversed(shutdown_hooks):
                    try:
                        await hook(app)
                    except Exception:
                        logger.exception("Shutdown hook %s failed", getattr(hook, "__name__", hook))

                for task_attr in ("warmup_task", "refresh_task", "version_check_task"):
                    task = getattr(app.state, task_attr, None)
                    if task and not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await task

                await close_cache_backend(app)
                # Drain the shared CIMA httpx client (v0.4.11 perf
                # fix). Best-effort: never raises.
                await aclose_shared_client()
                logger.info("Application lifespan finished")

    return lifespan
