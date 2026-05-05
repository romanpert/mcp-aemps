# mcp_aemps/app/mcp_aemps_server.py
# ================================================================
# FastAPI-MCP server — slim orchestrator.
# All route handlers live in app/routes/*.py.
# Logging config in app/logging_setup.py.
# Rate-limit tiers in app/rate_limits.py.
# ================================================================
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

# --- OpenTelemetry: init as early as possible ---
from app.otel_setup import init_otel, instrument_fastapi

init_otel(strict=False)

from app.config import settings
from app.logging_setup import configure_logging
from app.startup import lifespan

# Route modules
from app.routes.medicamentos import router as medicamentos_router
from app.routes.documentos import router as documentos_router
from app.routes.vigilancia import router as vigilancia_router
from app.routes.datos_locales import router as datos_locales_router
from app.routes.presentaciones import router as presentaciones_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = configure_logging()

# ---------------------------------------------------------------------------
# Metrics auth
# ---------------------------------------------------------------------------
METRICS_ENDPOINT = "/internal/metrics"
METRICS_KEY = os.getenv("METRICS_KEY")

# ---------------------------------------------------------------------------
# Create the FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MCP AEMPS CIMA",
    version=settings.mcp_aemps_version,
    description="Herramientas MCP sobre la API CIMA de la AEMPS",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class MetricsGuard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == METRICS_ENDPOINT:
            token = request.headers.get("x-metrics-key")
            if not token:
                auth = request.headers.get("authorization", "")
                if auth.lower().startswith("bearer "):
                    token = auth[7:].strip()
            if not METRICS_KEY or token != METRICS_KEY:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(MetricsGuard)

# CORS
cors_kwargs = dict(
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

if settings.allowed_origins == ["*"]:
    app.add_middleware(CORSMiddleware, allow_origin_regex=".*", allow_credentials=False, **cors_kwargs)
else:
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, **cors_kwargs)


# Security headers
@app.middleware("http")
async def add_security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.update({
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    })
    return resp


# ---------------------------------------------------------------------------
# Health & Observability
# ---------------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
async def health():
    return JSONResponse({"status": "ok"})


Instrumentator().instrument(app).expose(app, endpoint=METRICS_ENDPOINT, include_in_schema=False)
instrument_fastapi(app)

# ---------------------------------------------------------------------------
# Register route modules
# ---------------------------------------------------------------------------
app.include_router(medicamentos_router)
app.include_router(documentos_router)
app.include_router(vigilancia_router)
app.include_router(datos_locales_router)
app.include_router(presentaciones_router)

# ---------------------------------------------------------------------------
# Initialize MCP (Streamable HTTP transport at /mcp)
# ---------------------------------------------------------------------------
mcp = FastApiMCP(
    app,
    name="MCP AEMPS CIMA",
    description="Acceso estructurado en tiempo real a datos regulatorios",
)
mcp.mount_http()
