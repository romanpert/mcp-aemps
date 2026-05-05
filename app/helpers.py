# app/helpers.py
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.config import settings

API_CIMA_AEMPS_VERSION = "1.23"
API_PSUM_VERSION = "2.0"

MAX_LOG_BODY = 2_000
SENSITIVE_KEYS = {"token", "authorization", "auth", "api_key", "apikey", "key", "password", "pwd", "secret"}

CN_MIN = 600000
CN_MAX = 999999
CN_RE = re.compile(r"^\d{6}$")

HTML_BASE_URL = "https://cima.aemps.es/cima"

_DOC_HTML_INFO: dict[int, tuple[str, str]] = {
    1: ("ft", "FT"),
    2: ("p", "P"),
    3: ("ipe", "IPE"),
    4: ("ipt", "IPT"),
}

logger = logging.getLogger(__name__)
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Config (safe): %s", settings.safe_dump())


def build_dochtml_url(
    tipo_doc: int,
    nregistro: str,
    seccion: str | None = None,
    ext: str = "html",
) -> str:
    slug, prefix = _DOC_HTML_INFO.get(tipo_doc, (str(tipo_doc), str(tipo_doc).upper()))
    base = f"{HTML_BASE_URL}/dochtml/{slug}/{nregistro}/{prefix}_{nregistro}.{ext}"
    if seccion:
        return f"{base}#{seccion}"
    return base


def _redact_query_params(params: Any) -> Any:
    try:
        if hasattr(params, "items"):
            return {k: "***REDACTED***" if str(k).lower() in SENSITIVE_KEYS else v for k, v in params.items()}
    except Exception:
        pass
    return params


def _redact_url(url: Any) -> str:
    try:
        return re.sub(r"(://)([^:@/\s]+):([^@/\s]+)@", r"\1\2:***REDACTED***@", str(url))
    except Exception:
        return str(url)


def _truncate(s: Optional[str], limit: int = MAX_LOG_BODY) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def format_response(resultado: Any, metadatos: Dict[str, Any], fanout: bool = False) -> Any:
    if resultado is None:
        return {"data": None, **metadatos}

    if isinstance(resultado, list):
        if not fanout:
            return {"data": resultado, **metadatos}
        lista = []
        for item in resultado:
            if isinstance(item, dict):
                lista.append({**item, **metadatos})
            else:
                lista.append({"data": item, **metadatos})
        return lista

    if isinstance(resultado, dict):
        return {**resultado, **metadatos}

    return {"data": resultado, **metadatos}


def _build_metadata(
    parametros_busqueda: Dict[str, Any],
    version_api: str = API_CIMA_AEMPS_VERSION,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fecha_hoy = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    metadata: Dict[str, Any] = {
        "fuente": "CIMA (AEMPS)",
        "fecha_consulta": fecha_hoy,
        "parametros_busqueda": parametros_busqueda,
        "version_api": version_api,
        "descargo_responsabilidad": {
            "texto": "Esta informacion no constituye consejo medico; se proporciona solo a efectos informativos.",
            "uso_responsable": "Consulte siempre con un profesional sanitario antes de tomar decisiones medicas.",
        },
    }
    if extra:
        metadata.update(extra)
    return {"metadata": metadata}


def parse_cima_fechas(item: Dict[str, Any]) -> None:
    """Parsea timestamps CIMA in-place para un resultado dict."""
    import app.cima_client as cima

    if not isinstance(item, dict):
        return

    estado = item.get("estado")
    if isinstance(estado, dict):
        for key in list(estado):
            estado[key] = cima._parse_fecha(estado[key])

    for doc in item.get("docs", []):
        if "fecha" in doc:
            doc["fecha"] = cima._parse_fecha(doc["fecha"])

    for foto in item.get("fotos", []):
        if "fecha" in foto:
            foto["fecha"] = cima._parse_fecha(foto["fecha"])

    for pres in item.get("presentaciones", []):
        pres_estado = pres.get("estado")
        if isinstance(pres_estado, dict):
            for key in list(pres_estado):
                pres_estado[key] = cima._parse_fecha(pres_estado[key])

    dps = item.get("detalleProblemaSuministro")
    if isinstance(dps, dict):
        for key in ("ini", "fini"):
            if key in dps:
                dps[key] = cima._parse_fecha(dps[key])


def parse_cima_fechas_list(items: list) -> None:
    for item in items:
        parse_cima_fechas(item)


async def bounded_gather(coros: list, *, limit: int | None = None, return_exceptions: bool = True) -> list:
    """Like asyncio.gather but caps concurrency at `limit`.

    Use in batch route handlers (e.g. /notas with multiple nregistros) to
    prevent a single batch request from spawning N parallel CIMA calls. The
    global CIMA_FANOUT_SEMAPHORE in cima_client provides a server-wide cap;
    this provides a per-request cap so one user's batch can't monopolise
    the upstream pool.
    """
    if limit is None:
        from app.rate_limits import BATCH_FANOUT_LIMIT

        limit = BATCH_FANOUT_LIMIT

    sem = asyncio.Semaphore(limit)

    async def _wrap(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(_wrap(c) for c in coros), return_exceptions=return_exceptions)


async def safe_cima_call(func, *args, **kwargs) -> Any:
    """Wrapper seguro para llamadas a CIMA con manejo robusto de errores."""
    try:
        return await func(*args, **kwargs)

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            body = _truncate(json.dumps(exc.response.json(), ensure_ascii=False))
        except Exception:
            body = _truncate(exc.response.text)
        url = _redact_url(getattr(exc.request, "url", "N/A"))
        params = _redact_query_params(getattr(exc.request, "params", {}))

        logger.error(
            "HTTPStatusError en API externa",
            extra={"status": status, "url": str(url), "params": params, "body": body},
        )

        if status == 404:
            raise HTTPException(status_code=404, detail="Recurso no encontrado en API externa")
        if status == 400:
            raise HTTPException(status_code=400, detail="Parametros invalidos para API externa (400)")
        raise HTTPException(status_code=502, detail=f"Error en API externa ({status})")

    except (httpx.RequestError, asyncio.TimeoutError) as exc:
        logger.error("Error de red/timeout con API externa: %s: %s", exc.__class__.__name__, exc)
        raise HTTPException(
            status_code=503, detail="Servicio no disponible: No se pudo conectar con la API externa"
        )

    except ValueError as exc:
        logger.error("Error de validacion en parametros: %s", exc)
        raise HTTPException(status_code=400, detail="Error en parametros")

    except Exception:
        logger.exception("Error inesperado en safe_cima_call")
        raise HTTPException(status_code=500, detail="Error interno inesperado procesando solicitud")


def _looks_like_cn(code: str) -> bool:
    if not code or not CN_RE.fullmatch(code):
        return False
    return CN_MIN <= int(code) <= CN_MAX


def _normalize(s: Optional[str]) -> str:
    if s is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


async def normalize_nregistro_and_cn(
    *,
    nregistro: Optional[str],
    cn: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resuelve CN -> nregistro via CIMA API (GET /presentacion/{cn}).
    Reemplaza la resolucion previa via DataFrame/Excel local.

    Devuelve (nregistro_normalizado, cn_normalizado).
    """
    import app.cima_client as cima

    # Si nregistro ya es un nregistro real (no parece CN), usarlo directamente
    if nregistro and not _looks_like_cn(nregistro):
        return nregistro, cn

    # Determinar el CN candidato
    candidate_cn: Optional[str] = None
    if cn:
        candidate_cn = cn
    elif nregistro and _looks_like_cn(nregistro):
        candidate_cn = nregistro

    if candidate_cn is None:
        return nregistro, cn

    # Resolver CN -> nregistro via API oficial CIMA: GET /presentacion/{cn}
    try:
        pres = await cima.presentacion(candidate_cn)
        if isinstance(pres, dict):
            nr = pres.get("nregistro") or pres.get("data", {}).get("nregistro")
            if nr:
                resolved = str(nr).strip()
                if resolved:
                    logger.info("Resuelto CN=%s -> nregistro=%s via CIMA API", candidate_cn, resolved)
                    return resolved, candidate_cn
    except Exception as e:
        logger.warning("No se pudo resolver CN=%s via CIMA API (%s)", candidate_cn, type(e).__name__)

    return None, candidate_cn
