# mcp_aemps/app/routes/vigilancia.py
# Thin FastAPI adapters over app.core.vigilancia.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi import Path as FPath

from app.core import (
    core_listar_materiales,
    core_listar_notas,
    core_obtener_materiales,
    core_obtener_notas,
    core_problemas_suministro,
    core_problemas_suministro_dcp,
    core_problemas_suministro_dcpf,
    core_registro_cambios,
)
from app.mcp_constants import (
    listar_materiales_description,
    listar_notas_description,
    obtener_materiales_description,
    obtener_notas_description,
    problemas_suministro_dcp_description,
    problemas_suministro_dcpf_description,
    problemas_suministro_description,
    registro_cambios_description,
)
from app.rate_limits import limit_heavy, limit_standard

router = APIRouter(tags=["Medicamentos"])


@router.get(
    "/registro-cambios",
    operation_id="registro_cambios",
    summary="Historial de altas, bajas y modificaciones de medicamentos",
    description=registro_cambios_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def registro_cambios(
    fecha: Optional[str] = Query(None, description="Fecha (dd/mm/yyyy)."),
    nregistro: Optional[List[str]] = Query(None, description="Numero de registro AEMPS (repetir)."),
    metodo: str = Query("GET", pattern="^(GET|POST)$", description="Metodo HTTP interno."),
) -> Dict[str, Any]:
    return await core_registro_cambios(fecha=fecha, nregistro=nregistro, metodo=metodo)


@router.get(
    "/problemas-suministro",
    operation_id="problemas_suministro",
    summary="Problemas de suministro: global paginado o detalle por CN (v2 con fallback v1)",
    description=problemas_suministro_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def problemas_suministro(
    cn: Optional[List[str]] = Query(None, description="Uno o mas Codigos Nacionales."),
    nregistro: Optional[List[str]] = Query(None, description="Uno o mas numeros de registro."),
    pagina: int = Query(1, ge=1, description="Pagina (solo en listado global)"),
    tamanioPagina: int = Query(25, ge=1, le=100, description="Tamano de pagina (solo en listado global)"),
) -> Dict[str, Any]:
    return await core_problemas_suministro(
        cn=cn,
        nregistro=nregistro,
        pagina=pagina,
        tamanioPagina=tamanioPagina,
    )


@router.get(
    "/problemas-suministro/dcp/{cod_dcp}",
    operation_id="problemas_suministro_dcp",
    summary="Presentaciones comercializadas y con problemas de suministro para un DCP",
    description=problemas_suministro_dcp_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def problemas_suministro_dcp(
    cod_dcp: str = FPath(..., description="Codigo DCP (descripcion clinica del producto)"),
) -> Dict[str, Any]:
    return await core_problemas_suministro_dcp(cod_dcp=cod_dcp)


@router.get(
    "/problemas-suministro/dcpf/{cod_dcpf}",
    operation_id="problemas_suministro_dcpf",
    summary="Presentaciones comercializadas y con problemas de suministro para un DCPF",
    description=problemas_suministro_dcpf_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def problemas_suministro_dcpf(
    cod_dcpf: str = FPath(..., description="Codigo DCPF (descripcion clinica del producto con formato)"),
) -> Dict[str, Any]:
    return await core_problemas_suministro_dcpf(cod_dcpf=cod_dcpf)


@router.get(
    "/notas",
    operation_id="listar_notas",
    summary="Notas de seguridad para uno o varios registros",
    description=listar_notas_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def listar_notas(
    nregistro: List[str] = Query(..., description="Repite: ?nregistro=AAA&nregistro=BBB"),
) -> Dict[str, Any]:
    return await core_listar_notas(nregistro=nregistro)


@router.get(
    "/notas/{nregistros}",
    operation_id="obtener_notas",
    summary="Detalle de notas de seguridad de uno o varios registros",
    description=obtener_notas_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def obtener_notas(
    nregistros: str = FPath(..., description="Registro(s) separados por comas: AAA,BBB,CCC"),
) -> Dict[str, Any]:
    registros = [nr.strip() for nr in nregistros.split(",") if nr.strip()]
    return await core_obtener_notas(nregistros=registros)


@router.get(
    "/materiales",
    operation_id="listar_materiales",
    summary="Materiales informativos para uno o varios registros",
    description=listar_materiales_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def listar_materiales(
    nregistro: List[str] = Query(..., description="Repite: ?nregistro=AAA&nregistro=BBB"),
) -> Dict[str, Any]:
    return await core_listar_materiales(nregistro=nregistro)


@router.get(
    "/materiales/{nregistro}",
    operation_id="obtener_materiales",
    summary="Materiales informativos de un registro",
    description=obtener_materiales_description,
    response_model=Dict[str, Any],
    dependencies=[limit_standard],
)
async def obtener_materiales(
    nregistro: str = FPath(..., description="Numero de registro"),
) -> Dict[str, Any]:
    return await core_obtener_materiales(nregistro=nregistro)
