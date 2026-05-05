# app/factory.py
"""Application factory — the public extension API.

Community Edition uses `create_app()` with no arguments.
Enterprise builds on top by passing extra routers, middleware, and lifecycle
hooks — without forking the core:

    from app.factory import create_app
    from premium.routes import audit, batch_export, webhooks
    from premium.middleware import OTelMiddleware, RBACMiddleware
    from premium.lifecycle import init_otel, close_audit_log

    app = create_app(
        extra_routers=[audit.router, batch_export.router, webhooks.router],
        extra_middleware=[(OTelMiddleware, {}), (RBACMiddleware, {"required_scope": "aemps:read"})],
        startup_hooks=[init_otel],
        shutdown_hooks=[close_audit_log],
    )
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Sequence, Tuple, Type, Union

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core import OperationError
from app.lifespan import build_lifespan
from app.logging_setup import configure_logging

# Routes
from app.routes.datos_locales import router as datos_locales_router
from app.routes.documentos import router as documentos_router
from app.routes.medicamentos import router as medicamentos_router
from app.routes.vigilancia import router as vigilancia_router

LifecycleHook = Callable[[FastAPI], Awaitable[None]]
MiddlewareSpec = Union[Type[BaseHTTPMiddleware], Tuple[Type[BaseHTTPMiddleware], dict[str, Any]]]


def create_app(
    *,
    extra_routers: Sequence[APIRouter] = (),
    extra_middleware: Sequence[MiddlewareSpec] = (),
    startup_hooks: Sequence[LifecycleHook] = (),
    shutdown_hooks: Sequence[LifecycleHook] = (),
    mount_mcp: bool = True,
    title: str = "MCP AEMPS CIMA",
    description: str = "Herramientas MCP sobre la API CIMA de la AEMPS",
) -> FastAPI:
    """Build the FastAPI app. Pure function — no global side effects."""
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

    # Lightweight in-process metrics middleware (Community Edition).
    # For Prometheus/OTel, use the Enterprise edition.
    from app.metrics import METRICS, metrics_middleware

    app.middleware("http")(metrics_middleware)

    @app.exception_handler(OperationError)
    async def _operation_error_handler(request: Request, exc: OperationError):  # noqa: D401, ARG001
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.get("/health", include_in_schema=False)
    async def health():  # noqa: D401
        return JSONResponse(
            {
                "status": "ok",
                "version": settings.mcp_aemps_version,
                "cache": "redis" if getattr(app.state, "redis", None) else "in-memory",
            }
        )

    @app.get("/internal/metrics", include_in_schema=False)
    async def metrics():  # noqa: D401
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
