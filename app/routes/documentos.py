# mcp_aemps/app/routes/documentos.py
# Document-access endpoints:
#   /doc-secciones, /doc-contenido, /doc-html/ft*, /doc-html/p*
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi import Path as FPath
from fastapi.responses import HTMLResponse
from httpx import HTTPStatusError

import app.cima_client as cima
from app.config import settings
from app.helpers import (
    _build_metadata,
    bounded_gather,
    build_dochtml_url,
    format_response,
    normalize_nregistro_and_cn,
    safe_cima_call,
)
from app.mcp_constants import (
    doc_contenido_description,
    doc_secciones_description,
    html_ft_description,
    html_ft_multiple_description,
    html_p_description,
    html_p_multiple_description,
)
from app.rate_limits import limit_document, limit_heavy, limit_standard

logger = logging.getLogger("mcp.aemps")
LOG_STACKTRACES = bool(settings.log_stacktraces)

router = APIRouter(tags=["Medicamentos"])


class Format(str, Enum):
    json = "json"
    html = "html"
    txt = "txt"


# ---------------------------------------------------------------------------
# 1. Doc secciones
# ---------------------------------------------------------------------------
@router.get(
    "/doc-secciones/{tipo_doc}",
    operation_id="doc_secciones",
    summary="Metadatos de secciones de Ficha Tecnica/prospecto",
    description=doc_secciones_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def doc_secciones(
    tipo_doc: int = FPath(..., ge=1, le=4, description="1=FT, 2=Prospecto, 3=IPE, 4=Plan Gestion Riesgos"),
    nregistro: Optional[List[str]] = Query(None, description="Uno o varios numeros de registro"),
    cn: Optional[List[str]] = Query(None, description="Uno o varios codigos nacionales"),
) -> Dict[str, Any]:
    if not (nregistro or cn):
        raise HTTPException(400, detail="Se requiere al menos un 'nregistro' o 'cn'.")

    resultados_agregados: List[Dict[str, Any]] = []
    normalized_nregistros: list[str] = []
    normalized_cns: list[str] = []

    try:
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
                    bloques = await safe_cima_call(cima.doc_secciones, tipo_doc, nregistro=nr_norm)
                    if bloques:
                        for b in bloques:
                            if isinstance(b, dict):
                                b["_codigo_origen"] = cn_norm or code
                                b["_nregistro"] = nr_norm
                        resultados_agregados.extend(bloques)
                        normalized_nregistros.append(nr_norm)
                except Exception as e:
                    logger.warning("Error procesando codigo %s: %s", code, type(e).__name__)
    except Exception:
        logger.error("Error general en doc_secciones", exc_info=LOG_STACKTRACES)
        raise HTTPException(500, detail="Error interno procesando solicitud")

    normalized_nregistros = sorted(set(normalized_nregistros))
    normalized_cns = sorted(set(normalized_cns))

    parametros = {
        "tipo_doc": tipo_doc,
        "nregistro": normalized_nregistros or nregistro,
        "cn": normalized_cns or cn,
    }

    if resultados_agregados:
        logger.info("Retornando %s secciones", len(resultados_agregados))
    return format_response(resultados_agregados, _build_metadata(parametros))


# ---------------------------------------------------------------------------
# 2. Doc contenido
# ---------------------------------------------------------------------------
@router.get(
    "/doc-contenido/{tipo_doc}",
    operation_id="doc_contenido",
    summary="Contenido de secciones de Ficha Tecnica/prospecto",
    description=doc_contenido_description,
    response_model=None,
    responses={200: {"content": {"application/json": {}, "text/html": {}, "text/plain": {}}}},
    dependencies=[limit_standard],
)
async def doc_contenido(
    tipo_doc: int = FPath(..., ge=1, le=2),
    nregistro: Optional[str] = Query(None, description="N Registro medicamento"),
    cn: Optional[str] = Query(None, description="Codigo Nacional del Medicamento"),
    seccion: Optional[str] = Query(None, description="Seccion estilo <2.1>, <4.2>, ..."),
    format: Format = Query(Format.json, description="Formato: json, html o txt"),
) -> Any:
    if not (nregistro or cn):
        raise HTTPException(400, "Se requiere 'nregistro' o 'cn'.")

    nr_norm, cn_norm = await normalize_nregistro_and_cn(nregistro=nregistro, cn=cn)

    if not nr_norm:
        raise HTTPException(
            404, detail="No se pudo resolver el numero de registro del medicamento solicitado"
        )

    ext_map = {Format.json: "html", Format.html: "html", Format.txt: "txt"}
    cima_url = build_dochtml_url(
        tipo_doc=tipo_doc, nregistro=nr_norm, seccion=seccion, ext=ext_map.get(format, "html")
    )

    try:
        resultado = await safe_cima_call(
            cima.doc_contenido,
            tipo_doc=tipo_doc,
            nregistro=nr_norm,
            seccion=seccion,
            format=format.value,
        )
    except Exception:
        logger.error("doc_contenido failed", exc_info=LOG_STACKTRACES)
        raise HTTPException(502, "Error al obtener contenido")

    if format == Format.json:
        return format_response(
            resultado,
            _build_metadata(
                {"tipo_doc": tipo_doc, "nregistro": nr_norm, "cn": cn_norm, "seccion": seccion},
                extra={"enlaces": {"cima_dochtml": cima_url}},
            ),
        )

    media_type = {Format.html: "text/html", Format.txt: "text/plain"}[format]
    return Response(content=resultado, media_type=media_type)


# ---------------------------------------------------------------------------
# 3. HTML ficha tecnica (batch + single)
# ---------------------------------------------------------------------------
async def _fetch_html_batch(
    tipo: str,
    nregistro: List[str],
    filename: str,
    not_found_label: str,
) -> Dict[str, Any]:
    if not nregistro or not filename:
        raise HTTPException(400, "Se requiere al menos un 'nregistro' y un 'filename'.")

    tasks = [cima.get_html_bytes(tipo=tipo, nregistro=nr, filename=filename) for nr in nregistro]
    responses = await bounded_gather(tasks)

    data_map: Dict[str, str] = {}
    errors: Dict[str, str] = {}

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
        raise HTTPException(404, {"error": "No se pudo generar ningun HTML", "errors": errors})

    metadatos = _build_metadata({"nregistro": nregistro, "filename": filename})
    payload: Dict[str, Any] = {"data": data_map}
    if errors:
        payload["errors"] = errors
    return format_response(payload, metadatos)


@router.get(
    "/doc-html/ft",
    operation_id="html_ficha_tecnica_multiple",
    summary="Fichas tecnicas HTML para varios registros",
    description=html_ft_multiple_description,
    response_model=None,
    dependencies=[limit_document],
)
async def html_ficha_tecnica_multiple(
    nregistro: List[str] = Query(..., description="N de registro (repetir)"),
    filename: str = Query(..., description="Nombre de archivo HTML ('FichaTecnica.html')"),
):
    return await _fetch_html_batch("ft", nregistro, filename, "Ficha tecnica no encontrada")


@router.get(
    "/doc-html/p",
    operation_id="html_prospecto_multiple",
    summary="Prospectos HTML para varios registros",
    description=html_p_multiple_description,
    response_model=None,
    dependencies=[limit_document],
)
async def html_prospecto_multiple(
    nregistro: List[str] = Query(..., description="N de registro (repetir)"),
    filename: str = Query(..., description="Nombre de archivo HTML ('Prospecto.html')"),
):
    return await _fetch_html_batch("p", nregistro, filename, "Prospecto no encontrado")


async def _fetch_html_single(tipo: str, nregistro: str, filename: str, label: str):
    try:
        data = await cima.get_html_bytes(tipo=tipo, nregistro=nregistro, filename=filename)
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, detail=f"{label} {nregistro} seccion '{filename}' no encontrada")
        raise HTTPException(502, detail=f"Error al obtener HTML: {e}")
    return HTMLResponse(content=data)


@router.get(
    "/doc-html/ft/{nregistro}/{filename:path}",
    operation_id="html_ficha_tecnica",
    summary="HTML completo de ficha tecnica (unico registro)",
    description=html_ft_description,
    response_model=None,
    dependencies=[limit_document],
)
async def html_ficha_tecnica(
    nregistro: str = FPath(..., description="Numero de registro"),
    filename: str = FPath(..., description="Ruta y nombre de archivo HTML"),
):
    return await _fetch_html_single("ft", nregistro, filename, "Ficha tecnica")


@router.get(
    "/doc-html/p/{nregistro}/{filename:path}",
    operation_id="html_prospecto",
    summary="HTML completo de prospecto (unico registro)",
    description=html_p_description,
    response_model=None,
    dependencies=[limit_document],
)
async def html_prospecto(
    nregistro: str = FPath(..., description="Numero de registro"),
    filename: str = FPath(..., description="Ruta y nombre de archivo HTML"),
):
    return await _fetch_html_single("p", nregistro, filename, "Prospecto")
