"""Core handlers for documentos segmentados (FT/prospecto) and HTML downloads."""

from __future__ import annotations

import logging
from typing import Any

from httpx import HTTPStatusError

import app.cima_client as cima
from app.core.base import OperationError, safe_call
from app.helpers import (
    _build_metadata,
    build_dochtml_url,
    format_response,
    normalize_nregistro_and_cn,
    progress_gather,
)

logger = logging.getLogger("mcp.aemps")

ALLOWED_FORMATS = {"json", "html", "txt"}


async def core_doc_secciones(
    *,
    tipo_doc: int,
    nregistro: list[str] | None = None,
    cn: list[str] | None = None,
) -> dict[str, Any]:
    if not (nregistro or cn):
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Se requiere al menos un 'nregistro' o 'cn'.",
        )

    resultados_agregados: list[dict[str, Any]] = []
    normalized_nregistros: list[str] = []
    normalized_cns: list[str] = []

    for code_list, is_cn in [(nregistro or [], False), (cn or [], True)]:
        for code in code_list:
            nr_norm, cn_norm = await normalize_nregistro_and_cn(
                nregistro=None if is_cn else code,
                cn=code if is_cn else None,
            )
            if cn_norm:
                normalized_cns.append(cn_norm)
            if not nr_norm:
                logger.warning("doc_secciones: no se pudo resolver nregistro desde '%s'", code)
                continue
            try:
                bloques = await safe_call(cima.doc_secciones, tipo_doc, nregistro=nr_norm)
            except OperationError as exc:
                logger.warning("Error procesando %s: %s", code, exc.error)
                continue
            if bloques:
                for b in bloques:
                    if isinstance(b, dict):
                        b["_codigo_origen"] = cn_norm or code
                        b["_nregistro"] = nr_norm
                resultados_agregados.extend(bloques)
                normalized_nregistros.append(nr_norm)

    parametros = {
        "tipo_doc": tipo_doc,
        "nregistro": sorted(set(normalized_nregistros)) or nregistro,
        "cn": sorted(set(normalized_cns)) or cn,
    }
    return format_response(resultados_agregados, _build_metadata(parametros))


async def core_doc_contenido(
    *,
    tipo_doc: int,
    nregistro: str | None = None,
    cn: str | None = None,
    seccion: str | None = None,
    format: str = "json",
) -> dict[str, Any]:
    """Return shape:
    - json:  {"data": <json>, "metadata": {...}}            (already format_response)
    - html:  {"content": "<html>",  "media_type": "text/html"}
    - txt:   {"content": "...",     "media_type": "text/plain"}

    HTTP route turns html/txt into ``Response(content, media_type)``;
    stdio tool returns ``content`` directly so the LLM gets the body.
    """
    if format not in ALLOWED_FORMATS:
        raise OperationError(
            400,
            error="Formato invalido",
            message=f"format debe ser uno de {sorted(ALLOWED_FORMATS)}.",
        )
    if not (nregistro or cn):
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Se requiere 'nregistro' o 'cn'.",
        )

    nr_norm, cn_norm = await normalize_nregistro_and_cn(nregistro=nregistro, cn=cn)
    if not nr_norm:
        raise OperationError(
            404,
            error="Medicamento no encontrado",
            message="No se pudo resolver el numero de registro.",
        )

    ext_map = {"json": "html", "html": "html", "txt": "txt"}
    cima_url = build_dochtml_url(tipo_doc=tipo_doc, nregistro=nr_norm, seccion=seccion, ext=ext_map[format])

    resultado = await safe_call(
        cima.doc_contenido,
        tipo_doc=tipo_doc,
        nregistro=nr_norm,
        seccion=seccion,
        format=format,
    )

    if format == "json":
        return format_response(
            resultado,
            _build_metadata(
                {"tipo_doc": tipo_doc, "nregistro": nr_norm, "cn": cn_norm, "seccion": seccion},
                extra={"enlaces": {"cima_dochtml": cima_url}},
            ),
        )

    media_type = "text/html" if format == "html" else "text/plain"
    return {"content": resultado, "media_type": media_type}


async def _fetch_html_batch(
    tipo: str,
    nregistro: list[str],
    filename: str,
    not_found_label: str,
    *,
    ctx: Any = None,
) -> dict[str, Any]:
    if not nregistro or not filename:
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Se requiere al menos un 'nregistro' y un 'filename'.",
        )

    tasks = [cima.get_html_bytes(tipo=tipo, nregistro=nr, filename=filename) for nr in nregistro]
    label = f"{tipo}-html"
    responses = await progress_gather(tasks, ctx=ctx, label=label)

    data_map: dict[str, str] = {}
    errors: dict[str, str] = {}

    for nr, resp in zip(nregistro, responses):
        if isinstance(resp, HTTPStatusError):
            errors[nr] = (
                not_found_label
                if resp.response.status_code == 404
                else f"Error HTTP {resp.response.status_code}"
            )
        elif isinstance(resp, Exception):
            errors[nr] = f"Error inesperado: {type(resp).__name__}"
        else:
            data_map[nr] = resp.decode("utf-8")

    if not data_map:
        raise OperationError(
            404,
            error="No se pudo generar ningun HTML",
            details={"errors": errors},
        )

    metadatos = _build_metadata({"nregistro": nregistro, "filename": filename})
    payload: dict[str, Any] = {"data": data_map}
    if errors:
        payload["errors"] = errors
    return format_response(payload, metadatos)


async def core_html_ficha_tecnica_multiple(
    *, nregistro: list[str], filename: str = "FichaTecnica.html", ctx: Any = None
) -> dict[str, Any]:
    return await _fetch_html_batch("ft", nregistro, filename, "Ficha tecnica no encontrada", ctx=ctx)


async def core_html_prospecto_multiple(
    *, nregistro: list[str], filename: str = "Prospecto.html", ctx: Any = None
) -> dict[str, Any]:
    return await _fetch_html_batch("p", nregistro, filename, "Prospecto no encontrado", ctx=ctx)


async def _fetch_html_single(tipo: str, nregistro: str, filename: str, label: str) -> str:
    try:
        data = await cima.get_html_bytes(tipo=tipo, nregistro=nregistro, filename=filename)
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise OperationError(
                404,
                error=f"{label} no encontrada",
                details={"nregistro": nregistro, "filename": filename},
            ) from exc
        raise OperationError(
            502,
            error="Error al obtener HTML",
            message=f"HTTP {exc.response.status_code}",
        ) from exc
    return data.decode("utf-8")


async def core_html_ficha_tecnica(*, nregistro: str, filename: str = "FichaTecnica.html") -> str:
    return await _fetch_html_single("ft", nregistro, filename, "Ficha tecnica")


async def core_html_prospecto(*, nregistro: str, filename: str = "Prospecto.html") -> str:
    return await _fetch_html_single("p", nregistro, filename, "Prospecto")
