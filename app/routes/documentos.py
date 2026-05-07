# mcp_aemps/app/routes/documentos.py
# Thin FastAPI adapters over app.core.documentos.
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi import Path as FPath
from fastapi.responses import StreamingResponse
from httpx import HTTPStatusError

from app.cima_client import stream_html_bytes
from app.core import (
    core_doc_contenido,
    core_doc_secciones,
    core_html_ficha_tecnica_multiple,
    core_html_prospecto_multiple,
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

router = APIRouter(tags=["Medicamentos"])


class Format(str, Enum):
    json = "json"
    html = "html"
    txt = "txt"


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
    return await core_doc_secciones(tipo_doc=tipo_doc, nregistro=nregistro, cn=cn)


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
    resultado = await core_doc_contenido(
        tipo_doc=tipo_doc,
        nregistro=nregistro,
        cn=cn,
        seccion=seccion,
        format=format.value,
    )
    if format == Format.json:
        return resultado
    return Response(content=resultado["content"], media_type=resultado["media_type"])


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
    return await core_html_ficha_tecnica_multiple(nregistro=nregistro, filename=filename)


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
    return await core_html_prospecto_multiple(nregistro=nregistro, filename=filename)


async def _stream_dochtml(tipo: str, nregistro: str, filename: str, label: str) -> StreamingResponse:
    """Wrap ``cima_client.stream_html_bytes`` so HTTP errors raised
    before the first chunk arrive as proper 4xx/5xx (404 if upstream
    is missing the document). Once the iterator yields any byte the
    response status is committed; partial reads are surfaced as
    truncated bodies, not retroactive error codes."""
    iterator = stream_html_bytes(tipo, nregistro, filename)
    try:
        first_chunk = await iterator.__anext__()
    except StopAsyncIteration:
        raise HTTPException(status_code=404, detail=f"{label} no encontrado") from None
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"{label} no encontrado") from exc
        raise HTTPException(
            status_code=502,
            detail=f"Error al obtener {label.lower()} (HTTP {exc.response.status_code})",
        ) from exc

    async def body():
        yield first_chunk
        async for chunk in iterator:
            yield chunk

    return StreamingResponse(body(), media_type="text/html; charset=utf-8")


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
    # Streamed straight from CIMA — avoids buffering multi-MB SmPC
    # bodies in process memory. The MCP tool path
    # (``core_html_ficha_tecnica``) still uses the buffered variant
    # because TextContent needs the whole string at once.
    return await _stream_dochtml("ft", nregistro, filename, "Ficha tecnica")


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
    return await _stream_dochtml("p", nregistro, filename, "Prospecto")
