# v2/mcp_aemps/app/startup.py
import asyncio
import logging
import os
from contextlib import suppress
from glob import glob
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.dependencies import rate_limiter_dep
from app.docs_utils import download_presentaciones, download_nomenclator_csv
from app.otel_setup import shutdown_otel, tracer as get_tracer

tracer = get_tracer("aemps.startup")
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager, suppress


async def _init_dataframes_background(app: FastAPI) -> None:
    """
    Descarga (si hace falta) y carga los DataFrames en background.
    No debe levantar excepciones hacia lifespan: loggea y marca estado degradado si falla.
    """
    with tracer.start_as_current_span("descargas_iniciales"):
        data_dir = Path(settings.data_dir) / "documentacion"
        data_dir.mkdir(parents=True, exist_ok=True)

        xls_path = data_dir / "Presentaciones.xls"
        csv_dir = data_dir

        offline = os.getenv("AEMPS_OFFLINE", "").lower() in {"1", "true", "yes"}
        if offline:
            logger.warning(
                "AEMPS_OFFLINE activo: se omiten descargas en arranque; se intentará usar solo caché local."
            )

        downloaded_xls = None
        downloaded_csv = None

        if not offline:
            try:
                results = await asyncio.gather(
                    download_presentaciones(xls_path, timeout=60),
                    download_nomenclator_csv(csv_dir, timeout=60),
                    return_exceptions=True,
                )
                xls_res, csv_res = results
                downloaded_xls = xls_res if not isinstance(xls_res, Exception) else None
                downloaded_csv = csv_res if not isinstance(csv_res, Exception) else None

                if isinstance(xls_res, Exception):
                    logger.warning(
                        "Presentaciones.xls no pudo descargarse (%s). Se usará caché si existe.",
                        type(xls_res).__name__,
                    )
                if isinstance(csv_res, Exception):
                    logger.warning(
                        "Nomenclátor CSV no pudo descargarse (%s). Se usará caché si existe.",
                        type(csv_res).__name__,
                    )
            except Exception as exc:
                logger.error(
                    "Error en descargas iniciales (%s)",
                    type(exc).__name__,
                    exc_info=settings.log_stacktraces,
                )
                downloaded_xls = None
                downloaded_csv = None

        # Fallback a caché local
        if downloaded_xls is None and xls_path.exists():
            downloaded_xls = xls_path
            logger.info("Usando Presentaciones.xls en caché local.")
        elif downloaded_xls is None:
            logger.warning(
                "No hay Presentaciones.xls descargado ni en caché; se continuará con DF vacío."
            )

        if downloaded_csv is None:
            candidates = sorted(
                [Path(p) for p in glob(str(csv_dir / "*.csv"))],
                reverse=True,
            )
            if candidates:
                downloaded_csv = candidates[0]
                logger.info(
                    "Usando Nomenclátor CSV en caché local: %s",
                    downloaded_csv.name,
                )
            else:
                logger.warning(
                    "No hay CSV de Nomenclátor en caché; se continuará con DF vacío."
                )

    with tracer.start_as_current_span("carga_dataframes"):
        def _read_xls_safe(p: Path | None) -> pd.DataFrame:
            if not p or not p.exists():
                return pd.DataFrame()
            try:
                return pd.read_excel(p, engine="xlrd")
            except Exception:
                return pd.read_excel(p, engine="openpyxl")

        def _read_csv_safe(p: Path | None) -> pd.DataFrame:
            if not p or not p.exists():
                return pd.DataFrame()
            try:
                return pd.read_csv(p)
            except Exception:
                try:
                    return pd.read_csv(p, sep=";", encoding="latin-1")
                except Exception:
                    return pd.read_csv(p, sep=None, engine="python", encoding="latin-1")

        try:
            df_presentaciones, df_nomenclator = await asyncio.gather(
                run_in_threadpool(_read_xls_safe, downloaded_xls),
                run_in_threadpool(_read_csv_safe, downloaded_csv),
            )

            app.state.df_presentaciones = df_presentaciones
            app.state.df_nomenclator = df_nomenclator
            app.state.data_degraded = (
                df_presentaciones.empty or df_nomenclator.empty
            )

            logger.info(
                "DataFrames cargados (presentaciones=%s filas, nomenclator=%s filas; degradado=%s)",
                len(df_presentaciones),
                len(df_nomenclator),
                app.state.data_degraded,
            )
        except Exception as exc:
            logger.error(
                "Error al leer ficheros (%s)",
                type(exc).__name__,
                exc_info=settings.log_stacktraces,
            )
            app.state.df_presentaciones = pd.DataFrame()
            app.state.df_nomenclator = pd.DataFrame()
            app.state.data_degraded = True
        finally:
            # Señalizamos a quien quiera esperar
            event = getattr(app.state, "data_ready_event", None)
            if event is not None:
                event.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    with tracer.start_as_current_span("startup"):
        logger.info("Iniciando lifespan de la aplicación")

        # Estado inicial mínimo
        app.state.df_presentaciones = pd.DataFrame()
        app.state.df_nomenclator = pd.DataFrame()
        app.state.data_degraded = True

        # Evento opcional para que endpoints puedan esperar a que haya datos
        app.state.data_ready_event = asyncio.Event()

        # Lanzamos la tarea de descargas + carga en background
        app.state.data_task = asyncio.create_task(_init_dataframes_background(app))

        # --- Inicialización de Redis / caché / rate limit ---
        with tracer.start_as_current_span("init_cache_y_rate_limit"):
            if settings.redis_url:
                try:
                    redis = Redis.from_url(str(settings.redis_url))
                    pong = await redis.ping()
                    if not pong:
                        raise RuntimeError("Redis ping devolvió falso")
                    FastAPICache.init(
                        RedisBackend(redis),
                        prefix=settings.cache_prefix,
                    )
                    await FastAPILimiter.init(redis, prefix="mcp_rl:")
                    app.state.redis = redis
                    logger.info(
                        "Redis conectado: cache y rate limiter inicializados"
                    )
                except Exception as exc:
                    logger.warning(
                        "No se pudo inicializar Redis (%s). Usando caché en memoria y sin limitador.",
                        type(exc).__name__,
                    )
                    FastAPICache.init(
                        InMemoryBackend(),
                        prefix="inmemory",
                    )
                    app.dependency_overrides[rate_limiter_dep] = lambda: None
            else:
                logger.info(
                    "settings.redis_url vacío: usando caché en memoria sin limitador"
                )
                FastAPICache.init(InMemoryBackend(), prefix="inmemory")

        # --- Aquí ya dejamos arrancar el servidor ---
        try:
            yield
        finally:
            with tracer.start_as_current_span("shutdown"):
                # Cerrar Redis si existe
                redis = getattr(app.state, "redis", None)
                if redis:
                    try:
                        await redis.close()
                        if hasattr(redis, "wait_closed"):
                            await redis.wait_closed()
                    except Exception:
                        pass

                # Cancelar la tarea de datos si sigue viva
                data_task = getattr(app.state, "data_task", None)
                if data_task:
                    data_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await data_task

                logger.info("Finalizando lifespan de la aplicación")
                shutdown_otel()
