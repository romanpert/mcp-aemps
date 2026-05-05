"""Core handlers for registro de cambios, problemas de suministro, notas y materiales."""

from __future__ import annotations

import logging
from typing import Any

from dateutil import parser as date_parser

import app.cima_client as cima
from app.core.base import OperationError, safe_call
from app.helpers import (
    API_PSUM_VERSION,
    _build_metadata,
    bounded_gather,
    format_response,
)

logger = logging.getLogger("mcp.aemps")

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


async def core_registro_cambios(
    *,
    fecha: str | None = None,
    nregistro: list[str] | None = None,
    metodo: str = "GET",
) -> dict[str, Any]:
    resultados = await safe_call(
        cima.registro_cambios, fecha=fecha, nregistro=nregistro, metodo=metodo
    )
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


async def core_problemas_suministro(
    *,
    cn: list[str] | None = None,
    nregistro: list[str] | None = None,
    pagina: int = 1,
    tamanioPagina: int = 25,
) -> dict[str, Any]:
    parametros = {"cn": cn, "nregistro": nregistro, "pagina": pagina, "tamanioPagina": tamanioPagina}
    metadatos = _build_metadata(parametros, API_PSUM_VERSION)
    metadatos["metadata"]["tipo_problema_suministros"] = cima.TIPOS_PROBLEMA

    if not cn and not nregistro:
        listado = await safe_call(
            cima.psuministro_global, pagina=pagina, tamanioPagina=tamanioPagina
        )
        data = listado.get("resultados", []) if isinstance(listado, dict) else listado
        return format_response(data, metadatos)

    resolved_cn: list[str] = []
    errors_nregistro: dict[str, Any] = {}
    if nregistro:
        tasks = [safe_call(cima.medicamento, nregistro=nr) for nr in nregistro]
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

    cn_list = list(dict.fromkeys((cn or []) + list(dict.fromkeys(resolved_cn))))
    if not cn_list:
        raise OperationError(
            404,
            error="Sin CN para procesar",
            details={"errors_nregistro": errors_nregistro},
        )

    tasks = [safe_call(cima.psuministro_cn, codigo) for codigo in cn_list]
    responses = await bounded_gather(tasks)

    data: dict[str, Any] = {}
    errors_cn: dict[str, Any] = {}
    for codigo, resp in zip(cn_list, responses):
        if isinstance(resp, Exception):
            errors_cn[codigo] = {"detail": str(resp)}
        else:
            data[codigo] = resp

    if not data:
        raise OperationError(
            404,
            error="Sin problemas de suministro",
            details={"not_found_cn": list(errors_cn.keys()), "errors_cn": errors_cn},
        )

    payload: dict[str, Any] = {"data": data}
    if errors_nregistro:
        payload["errors_nregistro"] = errors_nregistro
    if errors_cn:
        payload["errors_cn"] = errors_cn
    return format_response(payload, metadatos)


async def core_problemas_suministro_dcp(*, cod_dcp: str) -> dict[str, Any]:
    resultado = await safe_call(cima.psuministro_dcp, cod_dcp)
    if not resultado:
        raise OperationError(
            404,
            error="DCP no encontrado",
            message=f"No hay datos para el DCP {cod_dcp}.",
        )
    return format_response(resultado, _build_metadata({"cod_dcp": cod_dcp}, API_PSUM_VERSION))


async def core_problemas_suministro_dcpf(*, cod_dcpf: str) -> dict[str, Any]:
    resultado = await safe_call(cima.psuministro_dcpf, cod_dcpf)
    if not resultado:
        raise OperationError(
            404,
            error="DCPF no encontrado",
            message=f"No hay datos para el DCPF {cod_dcpf}.",
        )
    return format_response(resultado, _build_metadata({"cod_dcpf": cod_dcpf}, API_PSUM_VERSION))


async def _fetch_notas_batch(registros: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    tasks = [safe_call(cima.notas, nregistro=nr) for nr in registros]
    responses = await bounded_gather(tasks)
    resultados: dict[str, Any] = {}
    errores: dict[str, str] = {}
    for nr, resp in zip(registros, responses):
        if isinstance(resp, Exception):
            errores[nr] = str(resp)
        elif not resp or (isinstance(resp, (list, dict)) and not resp):
            errores[nr] = "sin notas"
        else:
            resultados[nr] = resp
    return resultados, errores


async def core_listar_notas(*, nregistro: list[str]) -> dict[str, Any]:
    if not nregistro:
        raise OperationError(400, error="Sin parametros", message="Se requiere al menos un 'nregistro'.")
    resultados, errores = await _fetch_notas_batch(nregistro)
    if not resultados:
        raise OperationError(
            404,
            error="Sin notas",
            details={"errores": errores},
        )
    return format_response(
        {"notas": resultados, "errores": errores}, _build_metadata({"nregistro": nregistro})
    )


async def core_obtener_notas(*, nregistros: list[str]) -> dict[str, Any]:
    """Path-based variant. Same semantics as ``core_listar_notas`` but reports
    not-found registros explicitly."""
    if not nregistros:
        raise OperationError(400, error="Sin parametros", message="Se requiere al menos un nregistro.")
    resultados, errores = await _fetch_notas_batch(nregistros)
    if not resultados:
        raise OperationError(
            404,
            error="Ninguna nota encontrada",
            details={"not_found_nregistro": nregistros, "errores": errores},
        )
    return format_response(
        {"notas": resultados, "errores": errores}, _build_metadata({"nregistro": nregistros})
    )


async def core_listar_materiales(*, nregistro: list[str]) -> dict[str, Any]:
    if not nregistro:
        raise OperationError(400, error="Sin parametros", message="Se requiere al menos un 'nregistro'.")
    tareas = [safe_call(cima.materiales, nregistro=nr) for nr in nregistro]
    respuestas = await bounded_gather(tareas)
    data = [res for res in respuestas if not isinstance(res, Exception) and res]
    if not data:
        raise OperationError(
            404,
            error="Ningun material asociado",
            details={"not_found_nregistro": nregistro},
        )
    return format_response(data, _build_metadata({"nregistro": nregistro}))


async def core_obtener_materiales(*, nregistro: str) -> dict[str, Any]:
    resultado = await safe_call(cima.materiales, nregistro=nregistro)
    if not resultado:
        raise OperationError(
            404,
            error="Ningun material asociado",
            details={"not_found_nregistro": [nregistro]},
        )
    return format_response(resultado, _build_metadata({"nregistro": nregistro}))
