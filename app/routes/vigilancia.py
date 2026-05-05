# mcp_aemps/app/routes/vigilancia.py
# Regulatory monitoring endpoints:
#   /registro-cambios
#   /problemas-suministro          — global o por CN (v2 con fallback v1)
#   /problemas-suministro/dcp/{cod_dcp}   — por DCP (v2 oficial)
#   /problemas-suministro/dcpf/{cod_dcpf} — por DCPF (v2 oficial)
#   /notas*, /materiales*
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as FPath

import app.cima_client as cima
from app.config import settings
from app.helpers import (
    API_PSUM_VERSION,
    _build_metadata,
    bounded_gather,
    format_response,
    safe_cima_call,
)
from app.rate_limits import limit_heavy, limit_standard

logger = logging.getLogger("mcp.aemps")
LOG_STACKTRACES = bool(settings.log_stacktraces)

router = APIRouter(tags=["Medicamentos"])

TIPO_CAMBIO_MAP = {1: "Nuevo", 2: "Baja", 3: "Modificado"}
CAMBIOS_MAP = {
    "estado": "Estado de autorizacion",
    "comerc": "Estado de comercializacion",
    "prosp": "Prospecto",
    "ft": "Ficha tecnica",
    "psum": "Problemas de suministro",
    "notasSeguridad": "Notas de seguridad",
    "matinf": "Materiales informativos",
    "otros": "Otros",
}


# ---------------------------------------------------------------------------
# 1. Registro de cambios
# ---------------------------------------------------------------------------
@router.get(
    "/registro-cambios",
    operation_id="registro_cambios",
    summary="Historial de altas, bajas y modificaciones de medicamentos",
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def registro_cambios(
    fecha: Optional[str] = Query(None, description="Fecha (dd/mm/yyyy)."),
    nregistro: Optional[List[str]] = Query(None, description="Numero de registro AEMPS (repetir)."),
    metodo: str = Query("GET", pattern="^(GET|POST)$", description="Metodo HTTP interno."),
) -> Dict[str, Any]:
    resultados = await safe_cima_call(cima.registro_cambios, fecha=fecha, nregistro=nregistro, metodo=metodo)

    if resultados is None:
        resultados = {"totalFilas": 0, "pagina": 1, "tamanioPagina": 0, "resultados": []}

    for item in resultados.get("resultados", []):
        tipo = item.get("tipoCambio")
        if tipo in TIPO_CAMBIO_MAP:
            item["tipoCambioDesc"] = TIPO_CAMBIO_MAP[tipo]

        if isinstance(item.get("cambio"), list):
            item["cambioDesc"] = [CAMBIOS_MAP.get(code, code) for code in item["cambio"]]

        raw = item.get("fecha")
        iso = cima._parse_fecha(raw)
        if isinstance(iso, str):
            try:
                dt = date_parser.isoparse(iso)
                item["fechaStr"] = dt.strftime("%d/%m/%Y %H:%M:%S")
            except (ValueError, date_parser.ParserError):
                item["fechaStr"] = None
        else:
            item["fechaStr"] = None

    parametros = {
        k: v for k, v in {"fecha": fecha, "nregistro": nregistro, "metodo": metodo}.items() if v is not None
    }
    return format_response(resultados, _build_metadata(parametros))


# ---------------------------------------------------------------------------
# 2a. Problemas de suministro — global o por CN
#     Sin params: GET /psuministro (v1, listado global paginado)
#     Con cn/nregistro: GET /psuministro/v2/cn/{cn} (v2, con fallback v1)
# ---------------------------------------------------------------------------
@router.get(
    "/problemas-suministro",
    operation_id="problemas_suministro",
    summary="Problemas de suministro: global paginado o detalle por CN (v2 con fallback v1)",
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def problemas_suministro(
    cn: Optional[List[str]] = Query(None, description="Uno o mas Codigos Nacionales."),
    nregistro: Optional[List[str]] = Query(None, description="Uno o mas numeros de registro."),
    pagina: int = Query(1, ge=1, description="Pagina (solo en listado global)"),
    tamanioPagina: int = Query(25, ge=1, le=100, description="Tamano de pagina (solo en listado global)"),
) -> Dict[str, Any]:
    parametros = {"cn": cn, "nregistro": nregistro, "pagina": pagina, "tamanioPagina": tamanioPagina}
    metadatos = _build_metadata(parametros, API_PSUM_VERSION)
    metadatos["metadata"]["tipo_problema_suministros"] = cima.TIPOS_PROBLEMA

    # Global listing
    if not cn and not nregistro:
        listado = await safe_cima_call(cima.psuministro_global, pagina=pagina, tamanioPagina=tamanioPagina)
        return format_response(
            listado.get("resultados", []) if isinstance(listado, dict) else listado, metadatos
        )

    # Resolver nregistro → CNs via CIMA medicamento
    resolved_cn: List[str] = []
    errors_nregistro: Dict[str, Any] = {}
    if nregistro:
        tasks = [safe_cima_call(cima.medicamento, nregistro=nr) for nr in nregistro]
        responses = await bounded_gather(tasks)

        for nr, resp in zip(nregistro, responses):
            if isinstance(resp, Exception):
                errors_nregistro[nr] = {"detail": str(resp)}
                continue
            pres = resp.get("data", {}).get("presentaciones") or resp.get("presentaciones") or []
            if not pres:
                errors_nregistro[nr] = {"detail": "No hay presentaciones para este nregistro"}
                continue
            for p in pres:
                cn_val = p.get("cn")
                if cn_val:
                    resolved_cn.append(cn_val)

    resolved_cn = list(dict.fromkeys(resolved_cn))
    cn_list = list(dict.fromkeys((cn or []) + resolved_cn))

    if not cn_list:
        raise HTTPException(
            404, detail={"error": "No se encontraron CN para procesar", "errors_nregistro": errors_nregistro}
        )

    # Consultar v2/cn para cada CN (con fallback v1 integrado en psuministro_cn)
    tasks = [safe_cima_call(cima.psuministro_cn, codigo) for codigo in cn_list]
    responses = await bounded_gather(tasks)

    data: Dict[str, Any] = {}
    errors_cn: Dict[str, Any] = {}
    for codigo, resp in zip(cn_list, responses):
        if isinstance(resp, Exception):
            errors_cn[codigo] = {"detail": str(resp)}
        else:
            data[codigo] = resp

    if not data:
        raise HTTPException(
            404,
            detail={
                "error": "No se encontraron problemas de suministro",
                "not_found_cn": list(errors_cn.keys()),
                "errors_cn": errors_cn,
            },
        )

    payload: Dict[str, Any] = {"data": data}
    if errors_nregistro:
        payload["errors_nregistro"] = errors_nregistro
    if errors_cn:
        payload["errors_cn"] = errors_cn
    return format_response(payload, metadatos)


# ---------------------------------------------------------------------------
# 2b. Problemas de suministro por DCP
#     GET /psuministro/v2/dcp/{cod_dcp}
#     Devuelve: comercializados + con_psuministro para ese DCP
# ---------------------------------------------------------------------------
@router.get(
    "/problemas-suministro/dcp/{cod_dcp}",
    operation_id="problemas_suministro_dcp",
    summary="Presentaciones comercializadas y con problemas de suministro para un DCP",
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def problemas_suministro_dcp(
    cod_dcp: str = FPath(..., description="Codigo DCP (descripcion clinica del producto)"),
) -> Dict[str, Any]:
    resultado = await safe_cima_call(cima.psuministro_dcp, cod_dcp)
    if not resultado:
        raise HTTPException(404, detail=f"No hay datos para el DCP {cod_dcp}")
    return format_response(resultado, _build_metadata({"cod_dcp": cod_dcp}, API_PSUM_VERSION))


# ---------------------------------------------------------------------------
# 2c. Problemas de suministro por DCPF
#     GET /psuministro/v2/dcpf/{cod_dcpf}
#     Devuelve: comercializados + con_psuministro para ese DCPF
# ---------------------------------------------------------------------------
@router.get(
    "/problemas-suministro/dcpf/{cod_dcpf}",
    operation_id="problemas_suministro_dcpf",
    summary="Presentaciones comercializadas y con problemas de suministro para un DCPF",
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def problemas_suministro_dcpf(
    cod_dcpf: str = FPath(..., description="Codigo DCPF (descripcion clinica del producto con formato)"),
) -> Dict[str, Any]:
    resultado = await safe_cima_call(cima.psuministro_dcpf, cod_dcpf)
    if not resultado:
        raise HTTPException(404, detail=f"No hay datos para el DCPF {cod_dcpf}")
    return format_response(resultado, _build_metadata({"cod_dcpf": cod_dcpf}, API_PSUM_VERSION))


# ---------------------------------------------------------------------------
# 3. Notas de seguridad
# ---------------------------------------------------------------------------
async def _fetch_notas_batch(registros: List[str]) -> tuple[Dict[str, Any], Dict[str, str]]:
    tasks = [safe_cima_call(cima.notas, nregistro=nr) for nr in registros]
    responses = await bounded_gather(tasks)

    resultados: Dict[str, Any] = {}
    errores: Dict[str, str] = {}

    for nr, resp in zip(registros, responses):
        if isinstance(resp, Exception):
            errores[nr] = str(resp)
        elif not resp or (isinstance(resp, (list, dict)) and not resp):
            errores[nr] = "sin notas"
        else:
            resultados[nr] = resp

    return resultados, errores


@router.get(
    "/notas",
    operation_id="listar_notas",
    summary="Notas de seguridad para uno o varios registros",
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def listar_notas(
    nregistro: List[str] = Query(..., description="Repite: ?nregistro=AAA&nregistro=BBB"),
) -> Dict[str, Any]:
    if not nregistro:
        raise HTTPException(400, "Se requiere al menos un 'nregistro'.")

    resultados, errores = await _fetch_notas_batch(nregistro)

    if not resultados:
        raise HTTPException(404, {"error": "ninguna nota", "detalles": errores})

    return format_response(
        {"notas": resultados, "errores": errores}, _build_metadata({"nregistro": nregistro})
    )


@router.get(
    "/notas/{nregistros}",
    operation_id="obtener_notas",
    summary="Detalle de notas de seguridad de uno o varios registros",
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def obtener_notas(
    nregistros: str = FPath(..., description="Registro(s) separados por comas: AAA,BBB,CCC"),
) -> Dict[str, Any]:
    registros = [nr.strip() for nr in nregistros.split(",") if nr.strip()]

    resultados, errores = await _fetch_notas_batch(registros)

    if not resultados:
        raise HTTPException(
            404,
            detail={
                "error": "Ninguna nota encontrada",
                "not_found_nregistro": registros,
                "errores": errores,
            },
        )

    return format_response(
        {"notas": resultados, "errores": errores}, _build_metadata({"nregistro": registros})
    )


# ---------------------------------------------------------------------------
# 4. Materiales informativos
# ---------------------------------------------------------------------------
@router.get(
    "/materiales",
    operation_id="listar_materiales",
    summary="Materiales informativos para uno o varios registros",
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def listar_materiales(
    nregistro: List[str] = Query(..., description="Repite: ?nregistro=AAA&nregistro=BBB"),
) -> Dict[str, Any]:
    if not nregistro:
        raise HTTPException(400, detail="Se requiere al menos un 'nregistro'.")

    tareas = [safe_cima_call(cima.materiales, nregistro=nr) for nr in nregistro]
    respuestas = await bounded_gather(tareas)

    data = [res for res in respuestas if not isinstance(res, Exception) and res]

    if not data:
        raise HTTPException(
            404, detail={"error": "Ningun material asociado", "not_found_nregistro": nregistro}
        )

    return format_response(data, _build_metadata({"nregistro": nregistro}))


@router.get(
    "/materiales/{nregistro}",
    operation_id="obtener_materiales",
    summary="Materiales informativos de un registro",
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def obtener_materiales(
    nregistro: str = FPath(..., description="Numero de registro"),
) -> Dict[str, Any]:
    try:
        resultado = await safe_cima_call(cima.materiales, nregistro=nregistro)
    except Exception:
        logger.error("Error obteniendo material %s", nregistro, exc_info=LOG_STACKTRACES)
        raise HTTPException(502, detail="Error al consultar material en CIMA.")

    if not resultado:
        raise HTTPException(
            404, detail={"error": "Ningun material asociado", "not_found_nregistro": [nregistro]}
        )

    return format_response(resultado, _build_metadata({"nregistro": nregistro}))
