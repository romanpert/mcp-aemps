# mcp_aemps/app/routes/datos_locales.py
# Local-data endpoints (DataFrame queries, no external CIMA calls):
#   /identificar-medicamento, /nomenclator, /descargar-imagenes,
#   /system-info-prompt
from __future__ import annotations

import logging
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

import app.cima_client as cima
import app.mcp_constants as constant
from app.helpers import (
    _build_metadata,
    _filter_bool,
    _filter_contains,
    _filter_date,
    _filter_exact,
    _filter_numeric,
    _normalize,
    _paginate,
    format_response,
)
from app.rate_limits import limit_heavy, limit_local

logger = logging.getLogger("mcp.aemps")

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. Identificar medicamento (local XLS)
# ---------------------------------------------------------------------------
@router.get(
    "/identificar-medicamento",
    operation_id="identificar_medicamento",
    summary="Identifica hasta 10 presentaciones en base a CN, nregistro o nombre",
    tags=["Presentaciones"],
    response_model=Dict[str, Any],
    dependencies=[limit_local],
)
async def identificar_medicamento(
    request: Request,
    nregistro: Optional[str] = Query(None, description="N de registro"),
    cn: Optional[str] = Query(None, description="Codigo Nacional"),
    nombre: Optional[str] = Query(None, description="Nombre del producto farmaceutico (parcial, case-insensitive)"),
    laboratorio: Optional[str] = Query(None, description="Nombre del laboratorio"),
    atc: Optional[str] = Query(None, description="Codigo ATC o descripcion parcial."),
    estado: Optional[str] = Query(None, description="Estado (p.ej. 'ALTA', 'BAJA')"),
    comercializado: Optional[bool] = Query(None, description="Comercializado (SI / NO)"),
    pagina: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    df: pd.DataFrame = request.app.state.df_presentaciones
    filt = df

    if nregistro:
        filt = _filter_exact(filt, "Nº Registro", nregistro)
    if cn:
        filt = _filter_exact(filt, "Cod. Nacional", cn)
    if laboratorio:
        filt = _filter_contains(filt, "Laboratorio", laboratorio)
    if atc:
        filt = _filter_contains(filt, "Cód. ATC", atc)
    if estado:
        filt = _filter_contains(filt, "Estado", estado)
    if comercializado is not None:
        filt = _filter_bool(filt, "¿Comercializado?", comercializado)

    if nombre:
        norm_query = _normalize(nombre)
        series_norm = filt["Presentación"].fillna("").apply(_normalize)

        # Substring matches
        substr = filt[series_norm.str.contains(norm_query)]
        # Fuzzy matches
        similares = get_close_matches(norm_query, series_norm.tolist(), n=page_size, cutoff=0.7)
        fuzzy = filt[series_norm.isin(similares)]
        filt = pd.concat([substr, fuzzy]).drop_duplicates()

    total = len(filt)
    page_df = _paginate(filt, pagina, page_size)
    docs = page_df.to_dict(orient="records")

    metadatos = _build_metadata({
        "nregistro": nregistro, "cn": cn, "nombre": nombre,
        "laboratorio": laboratorio, "atc": atc, "estado": estado,
        "comercializado": comercializado, "pagina": pagina,
        "page_size": page_size, "total": total,
    })

    return format_response(docs, metadatos)


# ---------------------------------------------------------------------------
# 2. Nomenclator de facturacion
# ---------------------------------------------------------------------------
@router.get(
    "/nomenclator",
    operation_id="buscar_nomenclator",
    summary="Busca productos farmaceuticos en el Nomenclator de facturacion",
    tags=["Nomenclator"],
    response_model=Dict[str, Any],
    dependencies=[limit_local],
)
async def buscar_nomenclator(
    request: Request,
    codigo_nacional: Optional[str] = Query(None, description="Codigo Nacional"),
    nombre_producto: Optional[str] = Query(None, description="Nombre del producto (parcial, case-insensitive)"),
    tipo_farmaco: Optional[str] = Query(None, description="Tipo de farmaco"),
    principio_activo: Optional[str] = Query(None, description="Principio activo o asociacion"),
    codigo_laboratorio: Optional[str] = Query(None, description="Codigo de laboratorio ofertante"),
    nombre_laboratorio: Optional[str] = Query(None, description="Nombre del laboratorio (parcial)"),
    estado: Optional[str] = Query(None, description="Estado (p.ej. 'ALTA', 'BAJA')"),
    fecha_alta_desde: Optional[str] = Query(None, description="Fecha alta >= dd/mm/yyyy"),
    fecha_alta_hasta: Optional[str] = Query(None, description="Fecha alta <= dd/mm/yyyy"),
    fecha_baja_desde: Optional[str] = Query(None, description="Fecha baja >= dd/mm/yyyy"),
    fecha_baja_hasta: Optional[str] = Query(None, description="Fecha baja <= dd/mm/yyyy"),
    aportacion_beneficiario: Optional[str] = Query(None, description="Aportacion del beneficiario"),
    precio_min_iva: Optional[float] = Query(None, description="Precio venta publico minimo con IVA"),
    precio_max_iva: Optional[float] = Query(None, description="Precio venta publico maximo con IVA"),
    agrupacion_codigo: Optional[str] = Query(None, description="Codigo de agrupacion homogenea"),
    agrupacion_nombre: Optional[str] = Query(None, description="Nombre de agrupacion homogenea (parcial)"),
    diagnostico_hospitalario: Optional[bool] = Query(None, description="Diagnostico hospitalario"),
    larga_duracion: Optional[bool] = Query(None, description="Tratamiento de larga duracion"),
    especial_control: Optional[bool] = Query(None, description="Especial control medico"),
    medicamento_huerfano: Optional[bool] = Query(None, description="Medicamento huerfano"),
    page_size: int = Query(10, ge=1, le=100, description="Maximo de resultados"),
) -> Dict[str, Any]:
    df: pd.DataFrame = request.app.state.df_nomenclator
    filt = df

    if codigo_nacional:
        filt = _filter_exact(filt, "Código Nacional", codigo_nacional)
    if nombre_producto:
        filt = _filter_contains(filt, "Nombre del producto farmacéutico", nombre_producto)
    if tipo_farmaco:
        filt = _filter_contains(filt, "Tipo de fármaco", tipo_farmaco)
    if principio_activo:
        filt = _filter_contains(filt, "Principio activo o asociación de principios activos", principio_activo)
    if codigo_laboratorio:
        filt = _filter_exact(filt, "Código del laboratorio ofertante", codigo_laboratorio)
    if nombre_laboratorio:
        filt = _filter_contains(filt, "Nombre del laboratorio ofertante", nombre_laboratorio)
    if estado:
        filt = _filter_contains(filt, "Estado", estado)
    if aportacion_beneficiario:
        filt = _filter_contains(filt, "Aportación del beneficiario", aportacion_beneficiario)
    if agrupacion_codigo:
        filt = _filter_exact(filt, "Código de la agrupación homogénea del producto sanitario", agrupacion_codigo)
    if agrupacion_nombre:
        filt = _filter_contains(filt, "Nombre de la agrupación homogénea del producto sanitario", agrupacion_nombre)

    filt = _filter_numeric(filt, "Precio venta al público con IVA", precio_min_iva, precio_max_iva)

    for flag, col in [
        (diagnostico_hospitalario, "Diagnóstico hospitalario"),
        (larga_duracion, "Tratamiento de larga duración"),
        (especial_control, "Especial control médico"),
        (medicamento_huerfano, "Medicamento huérfano"),
    ]:
        if flag is not None:
            filt = _filter_bool(filt, col, flag)

    if fecha_alta_desde:
        filt = _filter_date(filt, "Fecha de alta en el nomenclátor", fecha_alta_desde, "ge")
    if fecha_alta_hasta:
        filt = _filter_date(filt, "Fecha de alta en el nomenclátor", fecha_alta_hasta, "le")
    if fecha_baja_desde:
        filt = _filter_date(filt, "Fecha de baja en el nomenclátor", fecha_baja_desde, "ge")
    if fecha_baja_hasta:
        filt = _filter_date(filt, "Fecha de baja en el nomenclátor", fecha_baja_hasta, "le")

    total_available = len(filt)
    limit = min(page_size, total_available)
    records = filt.head(limit).to_dict(orient="records")

    metadatos = _build_metadata({
        "codigo_nacional": codigo_nacional, "nombre_producto": nombre_producto,
        "tipo_farmaco": tipo_farmaco, "principio_activo": principio_activo,
        "codigo_laboratorio": codigo_laboratorio, "nombre_laboratorio": nombre_laboratorio,
        "estado": estado, "fecha_alta_desde": fecha_alta_desde, "fecha_alta_hasta": fecha_alta_hasta,
        "fecha_baja_desde": fecha_baja_desde, "fecha_baja_hasta": fecha_baja_hasta,
        "aportacion_beneficiario": aportacion_beneficiario,
        "precio_min_iva": precio_min_iva, "precio_max_iva": precio_max_iva,
        "agrupacion_codigo": agrupacion_codigo, "agrupacion_nombre": agrupacion_nombre,
        "diagnostico_hospitalario": diagnostico_hospitalario, "larga_duracion": larga_duracion,
        "especial_control": especial_control, "medicamento_huerfano": medicamento_huerfano,
        "total": total_available, "page_size": limit,
    })

    return format_response(records, metadatos)


# ---------------------------------------------------------------------------
# 3. Descargar imagenes
# ---------------------------------------------------------------------------
@router.get(
    "/descargar-imagenes",
    operation_id="descargar_imagenes",
    summary="Descargar imagenes para uno o varios CN (forma farmaceutica y/o caja)",
    tags=["Medicamentos"],
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def descargar_imagenes(
    cn: Optional[List[str]] = Query(None, description="Uno o varios CN"),
    nregistro: Optional[List[str]] = Query(None, description="Uno o varios NRegistro"),
    tipos: List[str] = Query(["formafarmac", "materialas"], description="Tipos: formafarmac, materialas"),
    timeout: int = Query(15, ge=5, le=60, description="Timeout en segundos"),
) -> Dict[str, Any]:
    if not (cn or nregistro):
        raise HTTPException(400, "Debe proporcionar al menos un CN o un NRegistro")

    data_por_code = await cima.descargar_imagen(
        cn=cn,
        nregistro=nregistro,
        tipos=tipos,
        base_dir=None,
        timeout=timeout,
        only_url=True,
        with_base64=False,
    )

    params_used: Dict[str, Any] = {}
    if cn:
        params_used["cn"] = cn
    if nregistro:
        params_used["nregistro"] = nregistro
    if tipos:
        params_used["tipos"] = tipos

    return format_response({"imagenes": data_por_code}, _build_metadata(params_used))


# ---------------------------------------------------------------------------
# 4. System info prompt
# ---------------------------------------------------------------------------
@router.get(
    "/system-info-prompt",
    tags=["Prompts"],
    operation_id="get_system_info_prompt",
    summary="Obtener el Prompt del sistema para el agente MCP",
    dependencies=[limit_local],
)
async def get_system_prompt() -> str:
    return constant.MCP_AEMPS_SYSTEM_PROMPT
