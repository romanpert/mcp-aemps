# mcp_aemps/app/routes/medicamentos.py
# Core CIMA drug-data endpoints:
#   /medicamento, /medicamentos, /presentaciones, /presentacion,
#   /vmpp, /maestras
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

import app.cima_client as cima
from app.config import settings
from app.helpers import (
    _build_metadata,
    bounded_gather,
    format_response,
    parse_cima_fechas,
    parse_cima_fechas_list,
    safe_cima_call,
)
from app.mcp_constants import (
    maestras_description,
    medicamento_description,
    medicamentos_description,
    presentacion_description,
    presentaciones_description,
    vmpp_description,
)
from app.rate_limits import limit_heavy, limit_standard

logger = logging.getLogger("mcp.aemps")

router = APIRouter(tags=["Medicamentos"])

MAX_RESULTS = settings.max_results


# ---------------------------------------------------------------------------
# 1. Medicamento (ficha unica)
# ---------------------------------------------------------------------------
@router.get(
    "/medicamento",
    operation_id="obtener_medicamento",
    summary="Obtener descripcion general de un medicamento (por CN o nregistro)",
    description=medicamento_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def obtener_medicamento(
    cn: Optional[str] = Query(None, pattern=r"^\d+$", description="Codigo Nacional (CN)."),
    nregistro: Optional[str] = Query(None, pattern=r"^\d+$", description="Numero de registro AEMPS."),
) -> Dict[str, Any]:
    if not (cn or nregistro):
        raise HTTPException(
            400,
            detail={
                "error": "Parametros insuficientes",
                "message": "Debe indicar al menos 'cn' o 'nregistro'.",
                "required_params": ["cn", "nregistro"],
            },
        )

    cn_clean = cn.strip() if cn else None
    nr_clean = nregistro.strip() if nregistro else None

    logger.info("Consultando medicamento: has_cn=%s has_nregistro=%s", bool(cn_clean), bool(nr_clean))

    try:
        resultado = await safe_cima_call(cima.medicamento, cn=cn_clean, nregistro=nr_clean)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise
        raise HTTPException(
            exc.status_code,
            detail={
                "error": "Error al obtener medicamento",
                "message": str(exc.detail),
            },
        )

    parse_cima_fechas(resultado)

    params = {k: v for k, v in {"cn": cn_clean, "nregistro": nr_clean}.items() if v}
    return format_response(resultado, _build_metadata(params))


# ---------------------------------------------------------------------------
# 2. Medicamentos (listado con filtros)
# ---------------------------------------------------------------------------
@router.get(
    "/medicamentos",
    operation_id="buscar_medicamentos",
    summary="Listado de medicamentos con filtros regulatorios avanzados",
    description=medicamentos_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def buscar_medicamentos(
    nombre: Optional[str] = Query(
        None, description="Nombre del medicamento (coincidencia parcial o exacta)."
    ),
    laboratorio: Optional[str] = Query(None, description="Nombre del laboratorio fabricante."),
    practiv1: Optional[str] = Query(None, description="Nombre del principio activo principal."),
    practiv2: Optional[str] = Query(None, description="Nombre de un segundo principio activo."),
    idpractiv1: Optional[str] = Query(None, description="ID numerico del principio activo principal."),
    idpractiv2: Optional[str] = Query(None, description="ID numerico de un segundo principio activo."),
    cn: Optional[str] = Query(None, description="Codigo Nacional del medicamento."),
    atc: Optional[str] = Query(None, description="Codigo ATC o descripcion parcial del mismo."),
    nregistro: Optional[str] = Query(None, description="Numero de registro AEMPS."),
    npactiv: Optional[int] = Query(None, description="Numero de principios activos."),
    triangulo: Optional[int] = Query(None, ge=0, le=1, description="1 = Tienen triangulo, 0 = No."),
    huerfano: Optional[int] = Query(None, ge=0, le=1, description="1 = Huerfano, 0 = No."),
    biosimilar: Optional[int] = Query(None, ge=0, le=1, description="1 = Biosimilar, 0 = No."),
    sust: Optional[int] = Query(None, ge=1, le=5, description="Tipo de medicamento especial (1-5)."),
    vmp: Optional[str] = Query(None, description="ID del codigo VMP para buscar equivalentes clinicos."),
    comerc: Optional[int] = Query(None, ge=0, le=1, description="1 = Comercializados, 0 = No."),
    autorizados: Optional[int] = Query(None, ge=0, le=1, description="1 = Solo autorizados, 0 = No."),
    receta: Optional[int] = Query(None, ge=0, le=1, description="1 = Con receta, 0 = Sin receta."),
    estupefaciente: Optional[int] = Query(
        None, ge=0, le=1, description="1 = Incluye estupefacientes, 0 = Excluye."
    ),
    psicotropo: Optional[int] = Query(None, ge=0, le=1, description="1 = Incluye psicotropos, 0 = Excluye."),
    estuopsico: Optional[int] = Query(
        None, ge=0, le=1, description="1 = Incluye estupefacientes o psicotropos, 0 = Excluye."
    ),
    pagina: Optional[int] = Query(1, ge=1, description="Numero de pagina de resultados (minimo 1)."),
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "nombre": nombre,
        "laboratorio": laboratorio,
        "practiv1": practiv1,
        "practiv2": practiv2,
        "idpractiv1": idpractiv1,
        "idpractiv2": idpractiv2,
        "cn": cn,
        "atc": atc,
        "nregistro": nregistro,
        "npactiv": npactiv,
        "triangulo": triangulo,
        "huerfano": huerfano,
        "biosimilar": biosimilar,
        "sust": sust,
        "vmp": vmp,
        "comerc": comerc,
        "autorizados": autorizados,
        "receta": receta,
        "estupefaciente": estupefaciente,
        "psicotropo": psicotropo,
        "estuopsico": estuopsico,
        "pagina": pagina,
    }
    params = {k: v for k, v in params.items() if v is not None or k == "pagina"}

    logger.info(
        "Buscando medicamentos: pagina=%s, n_filters=%s",
        pagina,
        sum(1 for v in params.values() if v is not None),
    )

    try:
        resultados = await safe_cima_call(cima.medicamentos, **params)
    except HTTPException as exc:
        if exc.status_code in (500, 502):
            raise HTTPException(
                exc.status_code,
                detail={
                    "error": "Error de respuesta de la API CIMA",
                    "message": "La API CIMA devolvio un error al buscar medicamentos",
                },
            )
        raise

    if isinstance(resultados, dict) and "resultados" in resultados:
        parse_cima_fechas_list(resultados["resultados"])
        resultados["resultados"] = resultados["resultados"][:MAX_RESULTS]

    return format_response(resultados, _build_metadata(params))


# ---------------------------------------------------------------------------
# 3. Presentaciones (listado)
# ---------------------------------------------------------------------------
@router.get(
    "/presentaciones",
    operation_id="listar_presentaciones",
    summary="Listar presentaciones de un medicamento con filtros (cn, nregistro, etc.)",
    description=presentaciones_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def listar_presentaciones(
    cn: Optional[str] = Query(None, description="Codigo Nacional del medicamento."),
    nregistro: Optional[str] = Query(None, description="Numero de registro AEMPS."),
    vmp: Optional[str] = Query(None, description="ID del codigo VMP para equivalentes clinicos."),
    vmpp: Optional[str] = Query(None, description="ID del codigo VMPP."),
    idpractiv1: Optional[str] = Query(None, description="ID del principio activo."),
    comerc: Optional[int] = Query(None, ge=0, le=1, description="1 = Comercializados, 0 = No."),
    estupefaciente: Optional[int] = Query(
        None, ge=0, le=1, description="1 = Incluye estupefacientes, 0 = Excluye."
    ),
    psicotropo: Optional[int] = Query(None, ge=0, le=1, description="1 = Incluye psicotropos, 0 = Excluye."),
    estuopsico: Optional[int] = Query(
        None, ge=0, le=1, description="1 = Incluye estupefacientes o psicotropos, 0 = Excluye."
    ),
) -> Dict[str, Any]:
    # BUG FIX: was using **locals() which passes all local vars to CIMA client.
    # Now uses explicit kwargs.
    cima_params = {
        k: v
        for k, v in {
            "cn": cn,
            "nregistro": nregistro,
            "vmp": vmp,
            "vmpp": vmpp,
            "idpractiv1": idpractiv1,
            "comerc": comerc,
            "estupefaciente": estupefaciente,
            "psicotropo": psicotropo,
            "estuopsico": estuopsico,
        }.items()
        if v is not None
    }

    resultados = await safe_cima_call(cima.presentaciones, **cima_params)
    if resultados is None:
        resultados = {"totalFilas": 0, "resultados": []}

    parse_cima_fechas_list(resultados.get("resultados", []))

    return format_response(resultados, _build_metadata(cima_params))


# ---------------------------------------------------------------------------
# 4. Presentacion (detalle por CN, uno o varios)
# ---------------------------------------------------------------------------
@router.get(
    "/presentacion",
    operation_id="obtener_presentacion",
    summary="Detalle de una o varias presentaciones (por uno o varios CN)",
    description=presentacion_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def obtener_presentacion(
    cn: List[str] = Query(..., description="Uno o varios Codigos Nacionales. Repetir: ?cn=123&cn=456"),
) -> Dict[str, Any]:
    if not cn:
        raise HTTPException(400, detail="Debe indicar al menos un 'cn'.")

    # Single CN — simple path
    if len(cn) == 1:
        detalle = await safe_cima_call(cima.presentacion, cn[0])
        parse_cima_fechas(detalle)
        return format_response(detalle, _build_metadata({"cn": cn[0]}))

    # Multiple CNs — concurrent
    tasks = [safe_cima_call(cima.presentacion, code) for code in cn]
    respuestas = await bounded_gather(tasks)

    result_dict: Dict[str, Any] = {}
    errors: Dict[str, Any] = {}

    for code, resp in zip(cn, respuestas):
        if isinstance(resp, Exception):
            errors[code] = {"detail": str(resp)}
            continue
        parse_cima_fechas(resp)
        result_dict[code] = format_response(resp, _build_metadata({"cn": code}))

    if not result_dict:
        raise HTTPException(
            404,
            detail={
                "error": "Ninguna presentacion encontrada",
                "not_found_cn": list(errors.keys()),
                "errors": errors,
            },
        )

    response: Dict[str, Any] = {**result_dict}
    if errors:
        response["errors"] = errors
    return response


# ---------------------------------------------------------------------------
# 5. VMP/VMPP
# ---------------------------------------------------------------------------
@router.get(
    "/vmpp",
    operation_id="buscar_vmpp",
    summary="Equivalentes clinicos VMP/VMPP filtrables por principio activo, dosis, forma, etc.",
    description=vmpp_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def buscar_vmpp(
    practiv1: Optional[str] = Query(None, description="Nombre del principio activo principal."),
    idpractiv1: Optional[str] = Query(None, description="ID del principio activo principal."),
    dosis: Optional[str] = Query(None, description="Dosis del medicamento."),
    forma: Optional[str] = Query(None, description="Nombre de la forma farmaceutica."),
    atc: Optional[str] = Query(None, description="Codigo ATC o descripcion parcial."),
    nombre: Optional[str] = Query(None, description="Nombre del medicamento."),
    modoArbol: Optional[int] = Query(None, ge=0, le=1, description="0=plano, 1=jerarquico"),
    pagina: Optional[int] = Query(None, ge=1, description="Numero de pagina (si aplica)"),
) -> Dict[str, Any]:
    if not any([practiv1, idpractiv1, dosis, forma, atc, nombre, modoArbol]):
        raise HTTPException(400, detail="Se requiere al menos un parametro de busqueda.")

    # BUG FIX: was using **locals()
    cima_params = {
        k: v
        for k, v in {
            "practiv1": practiv1,
            "idpractiv1": idpractiv1,
            "dosis": dosis,
            "forma": forma,
            "atc": atc,
            "nombre": nombre,
            "modoArbol": modoArbol,
            "pagina": pagina,
        }.items()
        if v is not None
    }

    resultados = await safe_cima_call(cima.vmpp, **cima_params)
    return format_response(resultados, _build_metadata(cima_params))


# ---------------------------------------------------------------------------
# 6. Maestras (catalogos de referencia)
# ---------------------------------------------------------------------------
@router.get(
    "/maestras",
    operation_id="consultar_maestras",
    summary="Consultar catalogos maestros: ATC, Principios Activos, Formas, Laboratorios...",
    description=maestras_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def consultar_maestras(
    maestra: Optional[int] = Query(None, description="ID de la maestra a consultar."),
    nombre: Optional[str] = Query(None, description="Nombre del elemento a recuperar."),
    id: Optional[str] = Query(None, description="ID del elemento a recuperar."),
    codigo: Optional[str] = Query(None, description="Codigo del elemento a recuperar."),
    estupefaciente: Optional[int] = Query(None, ge=0, le=1, description="1 = Solo PA estupefacientes."),
    psicotropo: Optional[int] = Query(None, ge=0, le=1, description="1 = Solo PA psicotropos."),
    estuopsico: Optional[int] = Query(None, ge=0, le=1, description="PA estupefacientes o psicotropos."),
    enuso: Optional[int] = Query(None, ge=0, le=1, description="0 = PA asociados o no a medicamentos."),
    pagina: Optional[int] = Query(1, ge=1, description="Numero de pagina (si la API lo soporta)."),
) -> Dict[str, Any]:
    # BUG FIX: was using **locals()
    cima_params = {
        k: v
        for k, v in {
            "maestra": maestra,
            "nombre": nombre,
            "id": id,
            "codigo": codigo,
            "estupefaciente": estupefaciente,
            "psicotropo": psicotropo,
            "estuopsico": estuopsico,
            "enuso": enuso,
            "pagina": pagina,
        }.items()
        if v is not None
    }

    resultados = await safe_cima_call(cima.maestras, **cima_params)
    return format_response(resultados, _build_metadata(cima_params))
