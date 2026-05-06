# app/factory.py
"""Application factory — the public extension API.

Default usage: ``create_app()`` with no arguments.

Downstream consumers can compose on top by passing extra routers,
middleware, and lifecycle hooks — without forking the core::

    from app.factory import create_app
    from my_org.routes import audit, batch_export, webhooks
    from my_org.middleware import OTelMiddleware, RBACMiddleware
    from my_org.lifecycle import init_otel, close_audit_log

    app = create_app(
        extra_routers=[audit.router, batch_export.router, webhooks.router],
        extra_middleware=[(OTelMiddleware, {}), (RBACMiddleware, {"required_scope": "aemps:read"})],
        startup_hooks=[init_otel],
        shutdown_hooks=[close_audit_log],
    )
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Sequence, Tuple, Type, Union

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP
from pydantic import SecretStr
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from app.config import settings
from app.core import OperationError
from app.lifespan import build_lifespan
from app.logging_setup import configure_logging
from app.tool_hooks import EMPTY_HOOKS, HookSet, PostHookFn, PreHookFn

logger = logging.getLogger("mcp.aemps")

# Routes
from app.routes.datos_locales import router as datos_locales_router
from app.routes.documentos import router as documentos_router
from app.routes.medicamentos import router as medicamentos_router
from app.routes.vigilancia import router as vigilancia_router

LifecycleHook = Callable[[FastAPI], Awaitable[None]]
MiddlewareSpec = Union[Type[BaseHTTPMiddleware], Tuple[Type[BaseHTTPMiddleware], dict[str, Any]]]
HealthExtraFn = Callable[[FastAPI], Awaitable[dict[str, Any]]]


def create_app(
    *,
    extra_routers: Sequence[APIRouter] = (),
    extra_middleware: Sequence[MiddlewareSpec] = (),
    startup_hooks: Sequence[LifecycleHook] = (),
    shutdown_hooks: Sequence[LifecycleHook] = (),
    pre_tool_hooks: Sequence[PreHookFn] = (),
    post_tool_hooks: Sequence[PostHookFn] = (),
    health_extra: HealthExtraFn | None = None,
    metrics_replace: bool = False,
    mount_mcp: bool = True,
    title: str = "MCP AEMPS CIMA",
    description: str = "Herramientas MCP sobre la API CIMA de la AEMPS",
) -> FastAPI:
    """Build the FastAPI app. Pure function — no global side effects.

    Extension kwargs (downstream consumers, e.g. MOXI):

    * ``pre_tool_hooks`` / ``post_tool_hooks`` — fire around every MCP tool
      invocation (HTTP routes with an ``operation_id`` and stdio tools share
      the same hook contract). See ``app.tool_hooks``. Pass the same lists
      to ``stdio_server.build_server`` for cross-transport parity.
    * ``health_extra`` — async callable returning a dict that is merged into
      ``/health/ready``. Any key whose value is a dict containing
      ``"ready": False``, or any top-level key suffixed ``_ready`` that is
      ``False``, flips the response to 503. Use it to gate readiness on
      additional resources (e.g. dataframe load, downstream API).
    * ``metrics_replace`` — opt out of the in-process metrics middleware so
      a downstream consumer can install Prometheus / OTel exposition without
      double-counting requests.
    """
    configure_logging()

    lifespan = build_lifespan(
        startup_hooks=startup_hooks,
        shutdown_hooks=shutdown_hooks,
    )

    app = FastAPI(
        title=title,
        version=settings.mcp_aemps_version,
        description=description,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )

    _install_default_middleware(app)
    _install_extra_middleware(app, extra_middleware)

    # Lightweight in-process metrics middleware. Replace via the
    # extra_middleware/startup_hooks args when you need Prometheus or OTel,
    # and pass metrics_replace=True to skip this one to avoid double-counting.
    from app.metrics import METRICS, metrics_middleware

    if not metrics_replace:
        app.middleware("http")(metrics_middleware)

    # Tool-call hooks — install only if any hook is provided. Stored on
    # app.state so the middleware closure can be a module-level function.
    tool_hooks = HookSet.from_sequences(pre=pre_tool_hooks, post=post_tool_hooks)
    app.state.tool_hooks = tool_hooks
    if not tool_hooks.is_empty():
        app.middleware("http")(_tool_hook_middleware)

    @app.exception_handler(OperationError)
    async def _operation_error_handler(request: Request, exc: OperationError):  # noqa: D401, ARG001
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.get("/health/live", include_in_schema=False)
    async def health_live():  # noqa: D401
        """Liveness — process is alive and the event loop responds."""
        return JSONResponse({"status": "ok", "version": settings.mcp_aemps_version})

    @app.get("/health/ready", include_in_schema=False)
    async def health_ready():  # noqa: D401
        """Readiness — cache backend reachable AND maestras warmup completed.

        Kubernetes uses this to decide whether to send traffic. Returns 503
        until the warmup task finishes (typically <5s on a cold start).

        If a ``health_extra`` callable is registered, its dict is merged into
        the response body. Any returned key suffixed ``_ready`` whose value
        is falsy flips the response to 503.
        """
        cache_mode = "redis" if getattr(app.state, "redis", None) else "in-memory"
        warmup_task = getattr(app.state, "warmup_task", None)
        warmup_done = warmup_task is None or warmup_task.done()

        if not warmup_done:
            body: dict[str, Any] = {
                "status": "starting",
                "cache": cache_mode,
                "warmup": "in_progress",
            }
            if health_extra is not None:
                body.update(await _safe_health_extra(app, health_extra))
            return JSONResponse(body, status_code=503)

        body = {
            "status": "ok",
            "version": settings.mcp_aemps_version,
            "cache": cache_mode,
            "warmup": "completed",
        }
        if health_extra is not None:
            extra = await _safe_health_extra(app, health_extra)
            body.update(extra)
            if _has_unready_flag(extra):
                body["status"] = "degraded"
                return JSONResponse(body, status_code=503)
        return JSONResponse(body)

    @app.get("/health", include_in_schema=False)
    async def health():  # noqa: D401
        """Backwards-compatible combined liveness+cache snapshot."""
        return JSONResponse(
            {
                "status": "ok",
                "version": settings.mcp_aemps_version,
                "cache": "redis" if getattr(app.state, "redis", None) else "in-memory",
            }
        )

    @app.get("/internal/metrics", include_in_schema=False)
    async def metrics(x_metrics_key: str | None = Header(default=None)):  # noqa: D401
        configured = settings.metrics_key
        if configured is not None:
            expected = (
                configured.get_secret_value()
                if isinstance(configured, SecretStr)
                else str(configured)
            )
            if not x_metrics_key or x_metrics_key != expected:
                raise HTTPException(status_code=401, detail="Invalid or missing X-Metrics-Key.")
        return JSONResponse(METRICS.snapshot())

    app.include_router(medicamentos_router)
    app.include_router(documentos_router)
    app.include_router(vigilancia_router)
    app.include_router(datos_locales_router)
    for router in extra_routers:
        app.include_router(router)

    if mount_mcp:
        mcp = FastApiMCP(app, name=title, description=description)
        mcp.mount_http()

    if settings.metrics_key is None:
        logger.warning(
            "METRICS_KEY is not set — /internal/metrics is publicly readable. "
            "Set METRICS_KEY in production deployments."
        )

    return app


def _install_default_middleware(app: FastAPI) -> None:
    cors_kwargs: dict[str, Any] = dict(
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )
    if settings.allowed_origins == ["*"]:
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=".*",
            allow_credentials=False,
            **cors_kwargs,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            **cors_kwargs,
        )

    @app.middleware("http")
    async def _security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers.update(
            {
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
            }
        )
        return resp


def _install_extra_middleware(app: FastAPI, specs: Sequence[MiddlewareSpec]) -> None:
    for spec in specs:
        if isinstance(spec, tuple):
            cls, kwargs = spec
            app.add_middleware(cls, **kwargs)
        else:
            app.add_middleware(spec)


async def _safe_health_extra(app: FastAPI, fn: HealthExtraFn) -> dict[str, Any]:
    """Run a health_extra callable defensively — never let it crash the probe."""
    try:
        result = await fn(app)
    except Exception:
        logger.exception("health_extra callable raised — marking degraded")
        return {"health_extra_error": True}
    if not isinstance(result, dict):
        logger.warning("health_extra returned %r (expected dict)", type(result).__name__)
        return {"health_extra_error": True}
    return result


def _has_unready_flag(extra: dict[str, Any]) -> bool:
    """Return True if any *_ready key is falsy. Plain ``ready=False`` also counts."""
    for key, value in extra.items():
        if key == "ready" and value is False:
            return True
        if key.endswith("_ready") and value is False:
            return True
    return False


async def _tool_hook_middleware(request: Request, call_next):
    """Fire pre/post tool hooks around HTTP routes that carry an ``operation_id``.

    Any non-MCP route (no ``operation_id``) is passed through untouched so
    /health/* and /internal/* are never instrumented.
    """
    hooks: HookSet = getattr(request.app.state, "tool_hooks", EMPTY_HOOKS)
    if hooks.is_empty():
        return await call_next(request)

    operation_id: str | None = None
    for route in request.app.routes:
        if not hasattr(route, "matches"):
            continue
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            operation_id = getattr(route, "operation_id", None) or None
            break

    if operation_id is None:
        return await call_next(request)

    args: dict[str, Any] = dict(request.query_params)
    try:
        await hooks.run_pre(operation_id, args)
    except OperationError as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    started = time.perf_counter()
    err: BaseException | None = None
    try:
        return await call_next(request)
    except BaseException as exc:
        err = exc
        raise
    finally:
        elapsed = time.perf_counter() - started
        await hooks.run_post(operation_id, args, err, elapsed)
