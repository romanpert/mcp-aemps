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

        for hook in startup_hooks:
            try:
                await hook(app)
            except Exception:
                logger.exception("Startup hook %s failed", getattr(hook, "__name__", hook))
                raise

        app.state.warmup_task = asyncio.create_task(warm_maestras(app))
        app.state.refresh_task = asyncio.create_task(periodic_maestras_refresh(app))

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

                for task_attr in ("warmup_task", "refresh_task"):
                    task = getattr(app.state, task_attr, None)
                    if task and not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await task

                await close_cache_backend(app)
                logger.info("Application lifespan finished")

    return lifespan
