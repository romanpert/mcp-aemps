"""Core handlers for medicamentos / presentaciones / vmpp / maestras / ficha tecnica."""

from __future__ import annotations

import logging
from typing import Any

import app.cima_client as cima
from app.config import settings
from app.core.base import OperationError, safe_call
from app.helpers import (
    _build_metadata,
    bounded_gather,
    format_response,
    parse_cima_fechas,
    parse_cima_fechas_list,
)

logger = logging.getLogger("mcp.aemps")

MAX_RESULTS = settings.max_results


async def core_obtener_medicamento(
    *,
    cn: str | None = None,
    nregistro: str | None = None,
) -> dict[str, Any]:
    if not (cn or nregistro):
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Debe indicar al menos 'cn' o 'nregistro'.",
            details={"required_params": ["cn", "nregistro"]},
        )

    cn_clean = cn.strip() if cn else None
    nr_clean = nregistro.strip() if nregistro else None

    logger.info("medicamento: has_cn=%s has_nregistro=%s", bool(cn_clean), bool(nr_clean))

    resultado = await safe_call(cima.medicamento, cn=cn_clean, nregistro=nr_clean)
    parse_cima_fechas(resultado)

    params = {k: v for k, v in {"cn": cn_clean, "nregistro": nr_clean}.items() if v}
    return format_response(resultado, _build_metadata(params))


async def core_buscar_medicamentos(**filtros: Any) -> dict[str, Any]:
    pagina = filtros.get("pagina") or 1
    params: dict[str, Any] = {k: v for k, v in filtros.items() if v is not None}
    params["pagina"] = pagina

    logger.info(
        "medicamentos: pagina=%s n_filtros=%s",
        pagina,
        sum(1 for k, v in params.items() if v is not None and k != "pagina"),
    )

    resultados = await safe_call(cima.medicamentos, **params)

    if isinstance(resultados, dict) and "resultados" in resultados:
        parse_cima_fechas_list(resultados["resultados"])
        resultados["resultados"] = resultados["resultados"][:MAX_RESULTS]

    return format_response(resultados, _build_metadata(params))


async def core_buscar_en_ficha_tecnica(reglas: list[dict[str, Any]]) -> dict[str, Any]:
    if not reglas:
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Debe enviar al menos una regla {seccion, texto, contiene}.",
        )
    resultado = await safe_call(cima.buscar_en_ficha_tecnica, reglas)
    return format_response(resultado, _build_metadata({"reglas": reglas}))


async def core_listar_presentaciones(**filtros: Any) -> dict[str, Any]:
    params = {k: v for k, v in filtros.items() if v is not None}
    resultados = await safe_call(cima.presentaciones, **params)
    if resultados is None:
        resultados = {"totalFilas": 0, "resultados": []}
    parse_cima_fechas_list(resultados.get("resultados", []))
    return format_response(resultados, _build_metadata(params))


async def core_obtener_presentacion(*, cn: list[str]) -> dict[str, Any]:
    if not cn:
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Debe indicar al menos un 'cn'.",
        )

    if len(cn) == 1:
        detalle = await safe_call(cima.presentacion, cn[0])
        parse_cima_fechas(detalle)
        return format_response(detalle, _build_metadata({"cn": cn[0]}))

    tasks = [safe_call(cima.presentacion, code) for code in cn]
    respuestas = await bounded_gather(tasks)

    result_dict: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    for code, resp in zip(cn, respuestas):
        if isinstance(resp, Exception):
            errors[code] = {"detail": str(resp)}
            continue
        parse_cima_fechas(resp)
        result_dict[code] = format_response(resp, _build_metadata({"cn": code}))

    if not result_dict:
        raise OperationError(
            404,
            error="Ninguna presentacion encontrada",
            details={"not_found_cn": list(errors.keys()), "errors": errors},
        )

    response: dict[str, Any] = {**result_dict}
    if errors:
        response["errors"] = errors
    return response


async def core_buscar_vmpp(**filtros: Any) -> dict[str, Any]:
    params = {k: v for k, v in filtros.items() if v is not None}
    if not any(k for k in params if k != "pagina"):
        raise OperationError(
            400,
            error="Parametros insuficientes",
            message="Se requiere al menos un parametro de busqueda.",
        )
    resultados = await safe_call(cima.vmpp, **params)
    return format_response(resultados, _build_metadata(params))


async def core_consultar_maestras(**filtros: Any) -> dict[str, Any]:
    params = {k: v for k, v in filtros.items() if v is not None}
    resultados = await safe_call(cima.maestras, **params)
    return format_response(resultados, _build_metadata(params))
