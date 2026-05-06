# mcp_aemps/app/routes/medicamentos.py
# Thin FastAPI adapters over app.core.medicamentos.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from app.core import (
    core_buscar_en_ficha_tecnica,
    core_buscar_medicamentos,
    core_buscar_vmpp,
    core_consultar_maestras,
    core_listar_presentaciones,
    core_obtener_medicamento,
    core_obtener_presentacion,
)
from app.mcp_constants import (
    buscar_ficha_tecnica_description,
    maestras_description,
    medicamento_description,
    medicamentos_description,
    presentacion_description,
    presentaciones_description,
    vmpp_description,
)
from app.rate_limits import limit_heavy, limit_standard

router = APIRouter(tags=["Medicamentos"])


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
    return await core_obtener_medicamento(cn=cn, nregistro=nregistro)


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
    return await core_buscar_medicamentos(
        nombre=nombre,
        laboratorio=laboratorio,
        practiv1=practiv1,
        practiv2=practiv2,
        idpractiv1=idpractiv1,
        idpractiv2=idpractiv2,
        cn=cn,
        atc=atc,
        nregistro=nregistro,
        npactiv=npactiv,
        triangulo=triangulo,
        huerfano=huerfano,
        biosimilar=biosimilar,
        sust=sust,
        vmp=vmp,
        comerc=comerc,
        autorizados=autorizados,
        receta=receta,
        estupefaciente=estupefaciente,
        psicotropo=psicotropo,
        estuopsico=estuopsico,
        pagina=pagina,
    )


@router.post(
    "/buscarEnFichaTecnica",
    operation_id="buscar_en_ficha_tecnica",
    summary="Busqueda textual sobre secciones de la ficha tecnica",
    description=buscar_ficha_tecnica_description,
    response_model=Dict[str, Any],
    dependencies=[limit_heavy],
)
async def buscar_en_ficha_tecnica(
    reglas: List[Dict[str, Any]] = Body(
        ...,
        description="Lista de reglas {seccion, texto, contiene}.",
        examples=[[{"seccion": "4.1", "texto": "cancer", "contiene": 1}]],
    ),
) -> Dict[str, Any]:
    return await core_buscar_en_ficha_tecnica(reglas)


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
    return await core_listar_presentaciones(
        cn=cn,
        nregistro=nregistro,
        vmp=vmp,
        vmpp=vmpp,
        idpractiv1=idpractiv1,
        comerc=comerc,
        estupefaciente=estupefaciente,
        psicotropo=psicotropo,
        estuopsico=estuopsico,
    )


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
    return await core_obtener_presentacion(cn=cn)


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
    return await core_buscar_vmpp(
        practiv1=practiv1,
        idpractiv1=idpractiv1,
        dosis=dosis,
        forma=forma,
        atc=atc,
        nombre=nombre,
        modoArbol=modoArbol,
        pagina=pagina,
    )


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
    return await core_consultar_maestras(
        maestra=maestra,
        nombre=nombre,
        id=id,
        codigo=codigo,
        estupefaciente=estupefaciente,
        psicotropo=psicotropo,
        estuopsico=estuopsico,
        enuso=enuso,
        pagina=pagina,
    )
