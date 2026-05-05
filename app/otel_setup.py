# v2/mcp_aemps/app/otel_setup.py
from __future__ import annotations

import os
import logging
from typing import Optional

# --- OpenTelemetry SDK & Exporters ---
from opentelemetry import trace, propagate
from opentelemetry.trace import get_tracer_provider, Tracer
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as OTLPSpanExporterGRPC,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as OTLPSpanExporterHTTP,
)

# --- Auto-instrumentations ---
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

log = logging.getLogger("aemps.otel")

# -------------------------------
# Utilidades de entorno
# -------------------------------
def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

def _split_kv(s: str) -> dict:
    """
    Convierte 'a=b,c=d' o 'key=value' o 'deployment.environment=prod'
    en dict. Para OTEL_RESOURCE_ATTRIBUTES.
    """
    out = {}
    if not s:
        return out
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out

# -------------------------------
# Sampler según variables .env
# -------------------------------
def _build_sampler() -> ParentBased:
    sampler_name = os.getenv("OTEL_TRACES_SAMPLER", "parentbased_traceidratio").strip().lower()
    arg = _env_float("OTEL_TRACES_SAMPLER_ARG", 0.2)

    if sampler_name in {"parentbased_traceidratio", "traceidratio", "ratio"}:
        root = TraceIdRatioBased(max(0.0, min(1.0, arg)))
    elif sampler_name in {"always_on"}:
        # Equivalente a "samplear todo"
        root = TraceIdRatioBased(1.0)
    elif sampler_name in {"always_off"}:
        # Equivalente a "no samplear nada"
        root = TraceIdRatioBased(0.0)
    else:
        # Compatibilidad con variantes 'parentbased_*'
        if sampler_name.startswith("parentbased"):
            root = TraceIdRatioBased(max(0.0, min(1.0, arg)))
        else:
            root = TraceIdRatioBased(0.2)
            log.warning("OTEL_TRACES_SAMPLER=%s no reconocido; uso TraceIdRatioBased(0.2)", sampler_name)

    # ParentBased respeta decisión del padre; usa 'root' para spans raíz
    return ParentBased(root)

# -------------------------------
# Exportador según protocolo / endpoint
# -------------------------------
def _build_exporter():
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").strip().lower()
    # Permite endpoints por señal; si no, usa el base
    traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    endpoint = traces_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317").strip()

    headers_env = os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "") or os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    headers = {}
    if headers_env:
        for kv in headers_env.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                headers[k.strip()] = v.strip()

    if protocol in {"http", "http/protobuf", "http/json"}:
        # Para OTLP/HTTP, si te pasan el base endpoint, el exporter construye /v1/traces.
        # Si te pasan el traces endpoint específico, debería terminar en /v1/traces.
        if not traces_endpoint and endpoint.endswith(":4317"):
            endpoint = endpoint.replace(":4317", ":4318")
        return OTLPSpanExporterHTTP(endpoint=endpoint, headers=headers)
    else:
        insecure = _env_bool("OTEL_EXPORTER_OTLP_INSECURE", False)
        return OTLPSpanExporterGRPC(endpoint=endpoint, insecure=insecure, headers=headers)

# -------------------------------
# Recursos (service.*, deployment.*, etc.)
# -------------------------------
def _build_resource() -> Resource:
    base = {
        "service.name": os.getenv("OTEL_SERVICE_NAME", "mcp-aemps-cima"),
    }
    extra = _split_kv(os.getenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=prod"))
    svc_version = os.getenv("MCP_AEMPS_VERSION")
    if svc_version:
        base["service.version"] = svc_version
    return Resource.create({**base, **extra})

# -------------------------------
# Estado interno
# -------------------------------
_INITIALIZED = False
_LOGGING_INSTRUMENTED = False

# -------------------------------
# API pública
# -------------------------------
def init_otel(strict: bool = False) -> None:
    """
    Inicializa OpenTelemetry **lo antes posible** en el ciclo de arranque
    (antes de crear tu logger/formatter y antes de importar módulos que hagan
    trace.get_tracer(...)).

    - Respeta OTEL_TRACES_EXPORTER=none para desactivar trazas por env.
    - Configura sampler/recursos/exportador desde .env.
    - Activa correlación de logs si OTEL_PYTHON_LOG_CORRELATION=true.
    - Instrumenta clientes (httpx/aiohttp/redis).

    Si strict=True lanza si no puede construir exporter.
    """
    global _INITIALIZED, _LOGGING_INSTRUMENTED
    if _INITIALIZED:
        return

    traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "otlp").strip().lower()
    if traces_exporter in {"none", ""}:
        log.info("OTEL: trazas desactivadas por OTEL_TRACES_EXPORTER=%s", traces_exporter)
        _maybe_instrument_logging()
        _instrument_clients()
        _INITIALIZED = True
        return

    # TracerProvider + Sampler + Resource
    resource = _build_resource()
    sampler = _build_sampler()
    provider = TracerProvider(resource=resource, sampler=sampler)

    # Exporter + Processor
    try:
        exporter = _build_exporter()
        processor = BatchSpanProcessor(exporter)
    except Exception as exc:
        if strict:
            raise
        log.exception("OTEL: no se pudo crear exportador OTLP, uso SimpleSpanProcessor + consola: %s", exc)
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        processor = SimpleSpanProcessor(ConsoleSpanExporter())

    provider.add_span_processor(processor)

    # Set provider global
    trace.set_tracer_provider(provider)

    # Propagadores: W3C por defecto; soporta B3 single/multi si se pide
    propagator = os.getenv("OTEL_PROPAGATORS", "tracecontext,baggage").strip().lower()
    if "b3multi" in propagator:
        from opentelemetry.propagators.b3 import B3MultiFormat
        propagate.set_global_textmap(B3MultiFormat())  # multi‑header
    elif "b3" in propagator:
        from opentelemetry.propagators.b3 import B3Format
        propagate.set_global_textmap(B3Format())       # single‑header

    _maybe_instrument_logging()
    _instrument_clients()

    _INITIALIZED = True
    log.info(
        "OTEL: inicializado (protocol=%s, endpoint=%s, sampler=%s)",
        os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
        os.getenv("OTEL_TRACES_SAMPLER", "parentbased_traceidratio"),
    )

def _maybe_instrument_logging() -> None:
    global _LOGGING_INSTRUMENTED
    if _LOGGING_INSTRUMENTED:
        return
    if _env_bool("OTEL_PYTHON_LOG_CORRELATION", False):
        # No tocamos tu formatter porque ya soporta %(otelTraceID)s/%(otelSpanID)s
        LoggingInstrumentor().instrument(set_logging_format=False)
        _LOGGING_INSTRUMENTED = True
        log.info("OTEL: correlación de logs activada")

def _instrument_clients() -> None:
    # Clientes que usas en el proyecto
    try:
        HTTPXClientInstrumentor().instrument()
    except Exception:
        log.debug("OTEL: httpx ya instrumentado o no disponible", exc_info=False)
    try:
        AioHttpClientInstrumentor().instrument()
    except Exception:
        log.debug("OTEL: aiohttp ya instrumentado o no disponible", exc_info=False)
    try:
        RedisInstrumentor().instrument()
    except Exception:
        log.debug("OTEL: redis ya instrumentado o no disponible", exc_info=False)

def instrument_fastapi(app, excluded_urls: Optional[str] = None) -> None:
    """
    Llama a esto una vez creada la app FastAPI, para instrumentar el servidor.
    """
    if not _INITIALIZED:
        init_otel(strict=False)

    def _server_request_hook(span, scope):
        if not span:
            return
        try:
            path = scope.get("path", "")
            span.set_attribute("http.target", path)
        except Exception:
            pass

    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=_server_request_hook,
        excluded_urls=excluded_urls or "/health|/internal/metrics",
    )

def tracer(name: str = "aemps") -> Tracer:
    """
    Obtiene un tracer **después** de init_otel(). Úsalo en vez de crear
    tracers de módulo en import‑time.
    """
    return trace.get_tracer(name)

def shutdown_otel() -> None:
    """
    Descarga spans pendientes. Debe llamarse una sola vez por proceso.
    """
    provider = get_tracer_provider()
    if isinstance(provider, TracerProvider):
        try:
            provider.shutdown()  # SDK: shutdown debe llamarse exactamente una vez
        except Exception:
            log.debug("OTEL: error en shutdown()", exc_info=True)

# -------------------------------
# Hooks para UVicorn/Gunicorn
# -------------------------------
def on_fork_worker() -> None:
    """
    Si usas múltiples workers (uvicorn --workers N) llama a esto en cada worker
    tras el fork/arranque del proceso hijo.
    """
    init_otel(strict=False)
