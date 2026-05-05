"""cima_client.py
====================
Cliente asincrono para la API REST oficial de CIMA (AEMPS).
Endpoints documentados en CIMA REST API v1.23.
Transport: httpx (sin aiohttp).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Union

import httpx
from dateutil import parser
from httpx import HTTPStatusError

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://cima.aemps.es/cima/rest"
HTML_BASE_URL = "https://cima.aemps.es/cima"
TIMEOUT = httpx.Timeout(15)

# Connection pool against cima.aemps.es. Caps total upstream pressure regardless
# of how many concurrent requests are spawned by route handlers.
_CIMA_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

TIPOS_PROBLEMA = {
    1: "Consultar Nota Informativa",
    2: "Suministro solo a hospitales",
    3: "El medico prescriptor debera determinar la posibilidad de utilizar otros tratamientos comercializados",
    4: "Desabastecimiento temporal",
    5: "Existe/n otro/s medicamento/s con el mismo principio activo y para la misma via de administracion",
    6: "Existe/n otro/s medicamento/s con los mismos principios activos y para la misma via de administracion",
    7: "Se puede solicitar como medicamento extranjero",
    8: "Se recomienda restringir su prescripcion reservandolo para casos en que no exista una alternativa apropiada",
    9: "El titular de autorizacion de comercializacion esta realizando una distribucion controlada al existir unidades limitadas",
}

_DEFAULT_HEADERS = {"Accept": "application/json", "User-Agent": "mcp-aemps/1.0"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(params: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _parse_fecha(valor: Any) -> Any:
    """Convierte timestamps UNIX (ms) o strings de fecha a ISO8601."""
    if isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.isdigit()):
        ms = int(valor)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        try:
            dt = epoch + timedelta(milliseconds=ms)
            return dt.isoformat()
        except OverflowError:
            return valor

    if isinstance(valor, str):
        try:
            dt = parser.parse(valor)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, parser.ParserError):
            return valor

    return valor


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[Any]:
    # Lazy import to avoid circulars: rate_limits imports config which is fine,
    # but cima_client is a dep of cache which is a dep of factory; keep the
    # global semaphore reference here.
    from app.rate_limits import CIMA_FANOUT_SEMAPHORE

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=TIMEOUT, limits=_CIMA_LIMITS)

    try:
        clean_params = _clean(params)
        full_url = f"{BASE_URL}/{path}"

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "HTTP %s %s | params_keys=%s", method, path, sorted(list((clean_params or {}).keys()))
            )

        async with CIMA_FANOUT_SEMAPHORE:
            resp = await client.request(
                method, full_url, params=clean_params, json=json_body, headers=_DEFAULT_HEADERS
            )

        if logger.isEnabledFor(logging.DEBUG):
            clen = resp.headers.get("Content-Length") or (
                len(resp.content) if resp.content is not None else 0
            )
            logger.debug("HTTP %s %s | status=%s | bytes=%s", method, path, resp.status_code, clen)

        resp.raise_for_status()

        if not resp.content:
            return None

        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return resp.text

    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTPStatusError status=%s path=%s",
            e.response.status_code,
            path,
            exc_info=settings.log_stacktraces,
        )
        raise
    except httpx.RequestError as e:
        logger.error("RequestError (%s) path=%s", type(e).__name__, path, exc_info=settings.log_stacktraces)
        raise
    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# 1. Medicamentos
# ---------------------------------------------------------------------------
async def medicamentos(
    *,
    nombre: str | None = None,
    laboratorio: str | None = None,
    practiv1: str | None = None,
    practiv2: str | None = None,
    idpractiv1: str | None = None,
    idpractiv2: str | None = None,
    cn: str | None = None,
    atc: str | None = None,
    nregistro: str | None = None,
    npactiv: int | None = None,
    triangulo: int | None = None,
    huerfano: int | None = None,
    biosimilar: int | None = None,
    sust: int | None = None,
    vmp: str | None = None,
    comerc: int | None = None,
    autorizados: int | None = None,
    receta: int | None = None,
    estupefaciente: int | None = None,
    psicotropo: int | None = None,
    estuopsico: int | None = None,
    pagina: int | None = None,
) -> Any | None:
    """GET /medicamentos"""
    return await _request("GET", "medicamentos", params=locals())


async def medicamento(*, cn: str | None = None, nregistro: str | None = None) -> Any | None:
    """GET /medicamento"""
    if not (cn or nregistro):
        raise ValueError("Se requiere 'cn' o 'nregistro'.")
    return await _request("GET", "medicamento", params=locals())


# ---------------------------------------------------------------------------
# 2. Buscar en ficha tecnica (oficial POST)
# ---------------------------------------------------------------------------
async def buscar_en_ficha_tecnica(reglas: list[dict[str, Any]]) -> Any | None:
    """POST /buscarEnFichaTecnica"""
    if not reglas:
        raise ValueError("Debe proporcionar al menos una regla de busqueda.")
    return await _request("POST", "buscarEnFichaTecnica", json_body=reglas)


# ---------------------------------------------------------------------------
# 3. Presentaciones
# ---------------------------------------------------------------------------
async def presentaciones(
    *,
    cn: str | None = None,
    nregistro: str | None = None,
    vmp: str | None = None,
    vmpp: str | None = None,
    idpractiv1: str | None = None,
    comerc: int | None = None,
    estupefaciente: int | None = None,
    psicotropo: int | None = None,
    estuopsico: int | None = None,
    pagina: int | None = None,
) -> Any | None:
    """GET /presentaciones"""
    return await _request("GET", "presentaciones", params=locals())


async def presentacion(cn: str) -> Any | None:
    """GET /presentacion/{cn} — Detalle de una presentacion por codigo nacional."""
    return await _request("GET", f"presentacion/{cn}")


# ---------------------------------------------------------------------------
# 4. Descripcion clinica (VMP/VMPP)
# ---------------------------------------------------------------------------
async def vmpp(
    *,
    practiv1: str | None = None,
    idpractiv1: str | None = None,
    dosis: str | None = None,
    forma: str | None = None,
    atc: str | None = None,
    nombre: str | None = None,
    modoArbol: int | None = None,
    pagina: int | None = None,
) -> Any | None:
    """GET /vmpp"""
    return await _request("GET", "vmpp", params=locals())


# ---------------------------------------------------------------------------
# 5. Maestras
# ---------------------------------------------------------------------------
async def maestras(
    *,
    maestra: int | None = None,
    nombre: str | None = None,
    id: str | None = None,
    codigo: str | None = None,
    estupefaciente: int | None = None,
    psicotropo: int | None = None,
    estuopsico: int | None = None,
    enuso: int | None = None,
    pagina: int | None = None,
) -> Any | None:
    """GET /maestras — Catalogos: laboratorios, ATC, formas, etc."""
    return await _request("GET", "maestras", params=locals())


# ---------------------------------------------------------------------------
# 6. Registro de cambios
# ---------------------------------------------------------------------------
async def registro_cambios(
    *,
    fecha: str | None = None,
    nregistro: list[str] | None = None,
    metodo: str = "GET",
) -> Any:
    """GET|POST /registroCambios"""
    payload_or_params: dict = {}
    if fecha is not None:
        payload_or_params["fecha"] = fecha
    if nregistro is not None:
        payload_or_params["nregistro"] = nregistro

    if metodo.upper() == "POST":
        return await _request("POST", "registroCambios", json_body=payload_or_params)
    return await _request("GET", "registroCambios", params=payload_or_params)


# ---------------------------------------------------------------------------
# 7. Problemas de suministro
#
# Fuentes oficiales:
#   - CIMA REST API v1.23:
#       GET /psuministro              → listado global paginado
#       GET /psuministro/:codNacional → problemas por CN (respuesta basica)
#   - CIMA REST API Problemas de Suministro v1.01 (AEMPS/Ministerio de Sanidad):
#       GET /psuministro/v2/cn/{cn}       → por CN, respuesta enriquecida (estado, comerc)
#       GET /psuministro/v2/dcp/{cod_dcp} → por DCP (descripcion clinica del producto)
#       GET /psuministro/v2/dcpf/{cod_dcpf} → por DCPF (descripcion clinica con formato)
# ---------------------------------------------------------------------------


def _enrich_psuministro(item: dict) -> None:
    """Normaliza fechas y añade descripcion textual del tipo de problema."""
    observ = item.get("observ", "").lower()
    tipo_code = item.get("tipoProblemaSuministro")
    if "sin problemas" in observ or tipo_code is None:
        item["tipoProblemaSuministro_descripcion"] = "No existen problemas detectados"
        item.setdefault("fecha_inicio", None)
        item.setdefault("fecha_fin", None)
    else:
        item["tipoProblemaSuministro_descripcion"] = TIPOS_PROBLEMA.get(tipo_code, "Desconocido")
        if "fini" in item:
            item["fecha_inicio"] = _parse_fecha(item.pop("fini"))
        if "ffin" in item:
            item["fecha_fin"] = _parse_fecha(item.pop("ffin"))
    # Normalizar estado.* si existe
    estado = item.get("estado")
    if isinstance(estado, dict):
        for k in list(estado):
            estado[k] = _parse_fecha(estado[k])


async def psuministro_global(pagina: int = 1, tamanioPagina: int = 25) -> dict:
    """GET /psuministro — listado global paginado (v1)."""
    raw = await _request(
        "GET",
        "psuministro",
        params={"pagina": pagina, "tamanioPagina": tamanioPagina},
    )
    if raw is None:
        return {"totalFilas": 0, "pagina": pagina, "tamanioPagina": tamanioPagina, "resultados": []}
    for item in raw.get("resultados", []):
        _enrich_psuministro(item)
    return raw


async def psuministro_cn_v1(cn: str) -> Any:
    """GET /psuministro/:codNacional — por CN, respuesta basica (v1)."""
    raw = await _request("GET", f"psuministro/{cn}")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        _enrich_psuministro(item)
    return items


async def psuministro_cn(cn: str) -> dict:
    """
    GET /psuministro/v2/cn/{cn} — por CN, respuesta enriquecida (v2).
    Incluye estado de la presentacion (aut/susp/rev) y comerc.
    Si v2 falla con 404 hace fallback al endpoint v1.
    """
    try:
        raw = await _request("GET", f"psuministro/v2/cn/{cn}")
        if raw is None:
            return {}
        _enrich_psuministro(raw)
        raw["_fuente"] = "v2"
        return raw
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            # fallback a v1
            items = await psuministro_cn_v1(cn)
            return {"cn": cn, "resultados_v1": items, "_fuente": "v1_fallback"}
        raise


async def psuministro_dcp(cod_dcp: str) -> dict:
    """
    GET /psuministro/v2/dcp/{cod_dcp}
    Devuelve presentaciones comercializadas y cuantas tienen problemas de suministro
    para ese DCP (descripcion clinica del producto).
    """
    raw = await _request("GET", f"psuministro/v2/dcp/{cod_dcp}")
    return raw or {}


async def psuministro_dcpf(cod_dcpf: str) -> dict:
    """
    GET /psuministro/v2/dcpf/{cod_dcpf}
    Devuelve presentaciones comercializadas y cuantas tienen problemas de suministro
    para ese DCPF (descripcion clinica del producto con formato).
    """
    raw = await _request("GET", f"psuministro/v2/dcpf/{cod_dcpf}")
    return raw or {}


async def psuministro(
    cn: str | None = None,
    pagina: int = 1,
    tamanioPagina: int = 25,
) -> dict | list:
    """
    Funcion unificada de compatibilidad:
    - Sin cn: llama a psuministro_global (v1)
    - Con cn: llama a psuministro_cn (v2 con fallback v1)
    """
    if cn:
        return await psuministro_cn(cn)
    return await psuministro_global(pagina=pagina, tamanioPagina=tamanioPagina)


# ---------------------------------------------------------------------------
# 8. Documentos segmentados — Secciones
# ---------------------------------------------------------------------------
async def doc_secciones(
    tipo_doc: int,
    *,
    nregistro: str,
) -> Optional[List[Dict[str, Any]]]:
    """GET /docSegmentado/secciones/{tipo_doc}"""
    if not nregistro:
        raise ValueError("Se requiere 'nregistro'.")

    try:
        result = await _request(
            "GET",
            f"docSegmentado/secciones/{tipo_doc}",
            params={"nregistro": nregistro},
        )

        if result is None:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]

        logger.warning("Resultado inesperado de CIMA (secciones): %s", type(result))
        return []

    except Exception as e:
        logger.error("doc_secciones fallo (%s)", type(e).__name__, exc_info=settings.log_stacktraces)
        raise


# ---------------------------------------------------------------------------
# 9. Documentos segmentados — Contenido
# ---------------------------------------------------------------------------
async def doc_contenido(
    tipo_doc: int,
    *,
    nregistro: str,
    seccion: str | None = None,
    format: str = "json",
) -> Any | None:
    """GET /docSegmentado/contenido/{tipo_doc}"""
    if not nregistro:
        raise ValueError("Se requiere 'nregistro'.")

    if tipo_doc not in [1, 2]:
        raise ValueError(f"tipo_doc debe ser 1 o 2, recibido: {tipo_doc}")

    params = _clean({"nregistro": nregistro, "seccion": seccion})

    try:
        result = await _request("GET", f"docSegmentado/contenido/{tipo_doc}", params=params)

        if format == "html":
            if isinstance(result, list) and result:
                return "".join(sec.get("contenido", "") for sec in result if isinstance(sec, dict))
            elif isinstance(result, dict) and "contenido" in result:
                return result["contenido"]
            return str(result)

        if format == "txt":
            import re as _re

            if isinstance(result, list) and result:
                parts = []
                for sec in result:
                    if isinstance(sec, dict):
                        if "titulo" in sec:
                            parts.append(sec["titulo"])
                        if "contenido" in sec:
                            parts.append(_re.sub("<[^<]+?>", "", sec["contenido"]))
                return "\n\n".join(parts).strip()
            elif isinstance(result, dict) and "contenido" in result:
                return _re.sub("<[^<]+?>", "", result["contenido"])
            return str(result)

        return result

    except Exception as e:
        logger.error("doc_contenido error (%s)", type(e).__name__, exc_info=settings.log_stacktraces)
        raise


# ---------------------------------------------------------------------------
# 10. Notas de seguridad
# ---------------------------------------------------------------------------
async def notas(nregistro: str) -> Any | None:
    """GET /notas?nregistro={nregistro} o GET /notas/{nregistro}"""
    data = await _request("GET", "notas", params={"nregistro": nregistro})
    if data is None or (isinstance(data, dict) and not data):
        return await _request("GET", f"notas/{nregistro}")
    return data


# ---------------------------------------------------------------------------
# 11. Materiales informativos
# ---------------------------------------------------------------------------
async def materiales(nregistro: Union[str, List[str]]) -> Any | None:
    """GET /materiales?nregistro={nregistro} o GET /materiales/{nregistro}"""

    async def _fetch_one(nr: str) -> list | None:
        try:
            data = await _request("GET", "materiales", params={"nregistro": nr})
            if not data:
                data = await _request("GET", f"materiales/{nr}")
            if isinstance(data, dict):
                if "materiales" in data and isinstance(data["materiales"], list):
                    return data["materiales"]
                return [data]
            return data or None
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    if isinstance(nregistro, list):
        tareas = [_fetch_one(nr) for nr in nregistro]
        respuestas = await asyncio.gather(*tareas, return_exceptions=True)
        resultados = []
        for nr, res in zip(nregistro, respuestas):
            if isinstance(res, Exception):
                continue
            if res:
                resultados.append({"nregistro": nr, "materiales": res})
        return resultados or None

    mat = await _fetch_one(nregistro)
    return {"nregistro": nregistro, "materiales": mat} if mat else None


# ---------------------------------------------------------------------------
# 12. HTML completo (FT / Prospecto)
# ---------------------------------------------------------------------------
async def get_html(
    tipo: Literal["ft", "p"],
    nregistro: str,
    filename: str,
) -> AsyncIterator[bytes]:
    """Streaming desde https://cima.aemps.es/cima/dochtml/{tipo}/{nregistro}/{filename}"""
    url = f"{HTML_BASE_URL}/dochtml/{tipo}/{nregistro}/{filename}"
    client = httpx.AsyncClient(timeout=TIMEOUT, headers=_DEFAULT_HEADERS)
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes():
            yield chunk
    finally:
        await client.aclose()


async def get_html_bytes(
    tipo: Literal["ft", "p"],
    nregistro: str,
    filename: str,
) -> bytes:
    """Descarga completa en bytes desde cima.aemps.es/cima/dochtml/..."""
    url = f"{HTML_BASE_URL}/dochtml/{tipo}/{nregistro}/{filename}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_DEFAULT_HEADERS) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
