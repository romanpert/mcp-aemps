# app/stdio_server.py
"""Native stdio MCP server.

Anthropic-canonical pattern: ``uvx mcp-aemps stdio`` runs us as a
subprocess speaking JSON-RPC over stdin/stdout. Every tool here is a
thin wrapper over the matching ``app.core.core_<op>`` — same code path
as the HTTP server in ``app.factory``. Adding a tool means implementing
one ``core_<op>``; both transports pick it up automatically as long as
they call it.

Errors raised by core handlers (``OperationError``) are serialised to a
dict so the LLM gets a structured payload instead of an opaque
exception traceback.

Run with:  python -m app.stdio_server
Or via:    mcp-aemps stdio
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from mcp.server.fastmcp import FastMCP

from app.core import (
    core_buscar_en_ficha_tecnica,
    core_buscar_medicamentos,
    core_buscar_vmpp,
    core_consultar_maestras,
    core_doc_contenido,
    core_doc_secciones,
    core_html_ficha_tecnica,
    core_html_ficha_tecnica_multiple,
    core_html_prospecto,
    core_html_prospecto_multiple,
    core_listar_materiales,
    core_listar_notas,
    core_listar_presentaciones,
    core_obtener_materiales,
    core_obtener_medicamento,
    core_obtener_notas,
    core_obtener_presentacion,
    core_problemas_suministro,
    core_problemas_suministro_dcp,
    core_problemas_suministro_dcpf,
    core_registro_cambios,
)
from app.logging_setup import configure_logging
from app.mcp_constants import (
    MCP_AEMPS_SYSTEM_PROMPT,
    buscar_ficha_tecnica_description,
    doc_contenido_description,
    doc_secciones_description,
    html_ft_description,
    html_ft_multiple_description,
    html_p_description,
    html_p_multiple_description,
    listar_materiales_description,
    listar_notas_description,
    maestras_description,
    medicamento_description,
    medicamentos_description,
    obtener_materiales_description,
    obtener_notas_description,
    presentacion_description,
    presentaciones_description,
    problemas_suministro_dcp_description,
    problemas_suministro_dcpf_description,
    problemas_suministro_description,
    registro_cambios_description,
    vmpp_description,
)
from app.tool_hooks import HookSet, PostHookFn, PreHookFn, wrap_stdio_tool

logger = logging.getLogger(__name__)


def build_server(
    *,
    pre_tool_hooks: Sequence[PreHookFn] = (),
    post_tool_hooks: Sequence[PostHookFn] = (),
) -> FastMCP:
    """Construct the FastMCP server with every official CIMA tool.

    Pre/post hooks fire around every tool invocation. See ``app.tool_hooks``
    for the contract. The same hooks should be passed to ``create_app`` so
    HTTP and stdio transports observe identical audit trails.
    """
    server = FastMCP(name="mcp-aemps", instructions=MCP_AEMPS_SYSTEM_PROMPT)
    hooks = HookSet.from_sequences(pre=pre_tool_hooks, post=post_tool_hooks)

    def _wrap(func):
        return wrap_stdio_tool(hooks, func)

    # ------------------------------------------------------------------
    # Medicamentos
    # ------------------------------------------------------------------
    @server.tool(description=medicamento_description)
    @_wrap
    async def obtener_medicamento(
        cn: str | None = None,
        nregistro: str | None = None,
    ) -> dict[str, Any]:
        return await core_obtener_medicamento(cn=cn, nregistro=nregistro)

    @server.tool(description=medicamentos_description)
    @_wrap
    async def buscar_medicamentos(
        nombre: str | None = None,
        laboratorio: str | None = None,
        practiv1: str | None = None,
        practiv2: str | None = None,
        idpractiv1: str | None = None,
        idpractiv2: str | None = None,
        atc: str | None = None,
        cn: str | None = None,
        nregistro: str | None = None,
        npactiv: int | None = None,
        triangulo: int | None = None,
        huerfano: int | None = None,
        biosimilar: int | None = None,
        sust: int | None = None,
        vmp: str | None = None,
        comerc: int | None = None,
        autorizados: int | None = None,
        receta: int | None = None,
        estupefaciente: int | None = None,
        psicotropo: int | None = None,
        estuopsico: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        return await core_buscar_medicamentos(
            nombre=nombre, laboratorio=laboratorio, practiv1=practiv1, practiv2=practiv2,
            idpractiv1=idpractiv1, idpractiv2=idpractiv2, atc=atc, cn=cn, nregistro=nregistro,
            npactiv=npactiv, triangulo=triangulo, huerfano=huerfano, biosimilar=biosimilar,
            sust=sust, vmp=vmp, comerc=comerc, autorizados=autorizados, receta=receta,
            estupefaciente=estupefaciente, psicotropo=psicotropo, estuopsico=estuopsico,
            pagina=pagina,
        )

    @server.tool(description=buscar_ficha_tecnica_description)
    @_wrap
    async def buscar_en_ficha_tecnica(reglas: list[dict[str, Any]]) -> dict[str, Any]:
        return await core_buscar_en_ficha_tecnica(reglas)

    # ------------------------------------------------------------------
    # Presentaciones / VMP / Maestras
    # ------------------------------------------------------------------
    @server.tool(description=presentaciones_description)
    @_wrap
    async def listar_presentaciones(
        cn: str | None = None,
        nregistro: str | None = None,
        vmp: str | None = None,
        vmpp: str | None = None,
        idpractiv1: str | None = None,
        comerc: int | None = None,
        estupefaciente: int | None = None,
        psicotropo: int | None = None,
        estuopsico: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        return await core_listar_presentaciones(
            cn=cn, nregistro=nregistro, vmp=vmp, vmpp=vmpp, idpractiv1=idpractiv1,
            comerc=comerc, estupefaciente=estupefaciente, psicotropo=psicotropo,
            estuopsico=estuopsico, pagina=pagina,
        )

    @server.tool(description=presentacion_description)
    @_wrap
    async def obtener_presentacion(cn: list[str]) -> dict[str, Any]:
        return await core_obtener_presentacion(cn=cn)

    @server.tool(description=vmpp_description)
    @_wrap
    async def buscar_vmpp(
        practiv1: str | None = None,
        idpractiv1: str | None = None,
        dosis: str | None = None,
        forma: str | None = None,
        atc: str | None = None,
        nombre: str | None = None,
        modoArbol: int | None = None,
        pagina: int | None = None,
    ) -> dict[str, Any]:
        return await core_buscar_vmpp(
            practiv1=practiv1, idpractiv1=idpractiv1, dosis=dosis, forma=forma,
            atc=atc, nombre=nombre, modoArbol=modoArbol, pagina=pagina,
        )

    @server.tool(description=maestras_description)
    @_wrap
    async def consultar_maestras(
        maestra: int | None = None,
        nombre: str | None = None,
        id: str | None = None,
        codigo: str | None = None,
        estupefaciente: int | None = None,
        psicotropo: int | None = None,
        estuopsico: int | None = None,
        enuso: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        return await core_consultar_maestras(
            maestra=maestra, nombre=nombre, id=id, codigo=codigo,
            estupefaciente=estupefaciente, psicotropo=psicotropo, estuopsico=estuopsico,
            enuso=enuso, pagina=pagina,
        )

    # ------------------------------------------------------------------
    # Vigilancia
    # ------------------------------------------------------------------
    @server.tool(description=registro_cambios_description)
    @_wrap
    async def registro_cambios(
        fecha: str | None = None,
        nregistro: list[str] | None = None,
        metodo: str = "GET",
    ) -> dict[str, Any]:
        return await core_registro_cambios(fecha=fecha, nregistro=nregistro, metodo=metodo)

    @server.tool(description=problemas_suministro_description)
    @_wrap
    async def problemas_suministro(
        cn: list[str] | None = None,
        nregistro: list[str] | None = None,
        pagina: int = 1,
        tamanioPagina: int = 25,
    ) -> dict[str, Any]:
        return await core_problemas_suministro(
            cn=cn, nregistro=nregistro, pagina=pagina, tamanioPagina=tamanioPagina,
        )

    @server.tool(description=problemas_suministro_dcp_description)
    @_wrap
    async def problemas_suministro_dcp(cod_dcp: str) -> dict[str, Any]:
        return await core_problemas_suministro_dcp(cod_dcp=cod_dcp)

    @server.tool(description=problemas_suministro_dcpf_description)
    @_wrap
    async def problemas_suministro_dcpf(cod_dcpf: str) -> dict[str, Any]:
        return await core_problemas_suministro_dcpf(cod_dcpf=cod_dcpf)

    @server.tool(description=listar_notas_description)
    @_wrap
    async def listar_notas(nregistro: list[str]) -> dict[str, Any]:
        return await core_listar_notas(nregistro=nregistro)

    @server.tool(description=obtener_notas_description)
    @_wrap
    async def obtener_notas(nregistros: list[str]) -> dict[str, Any]:
        return await core_obtener_notas(nregistros=nregistros)

    @server.tool(description=listar_materiales_description)
    @_wrap
    async def listar_materiales(nregistro: list[str]) -> dict[str, Any]:
        return await core_listar_materiales(nregistro=nregistro)

    @server.tool(description=obtener_materiales_description)
    @_wrap
    async def obtener_materiales(nregistro: str) -> dict[str, Any]:
        return await core_obtener_materiales(nregistro=nregistro)

    # ------------------------------------------------------------------
    # Documentos segmentados (FT, prospecto)
    # ------------------------------------------------------------------
    @server.tool(description=doc_secciones_description)
    @_wrap
    async def doc_secciones(
        tipo_doc: int,
        nregistro: list[str] | None = None,
        cn: list[str] | None = None,
    ) -> dict[str, Any]:
        return await core_doc_secciones(tipo_doc=tipo_doc, nregistro=nregistro, cn=cn)

    @server.tool(description=doc_contenido_description)
    @_wrap
    async def doc_contenido(
        tipo_doc: int,
        nregistro: str | None = None,
        cn: str | None = None,
        seccion: str | None = None,
        format: str = "json",
    ) -> Any:
        result = await core_doc_contenido(
            tipo_doc=tipo_doc, nregistro=nregistro, cn=cn, seccion=seccion, format=format,
        )
        # html / txt → return raw content; json → return the dict.
        if format != "json" and isinstance(result, dict) and "content" in result:
            return result["content"]
        return result

    @server.tool(description=html_ft_description)
    @_wrap
    async def html_ficha_tecnica(nregistro: str, filename: str = "FichaTecnica.html") -> str:
        return await core_html_ficha_tecnica(nregistro=nregistro, filename=filename)

    @server.tool(description=html_ft_multiple_description)
    @_wrap
    async def html_ficha_tecnica_multiple(
        nregistro: list[str], filename: str = "FichaTecnica.html"
    ) -> dict[str, Any]:
        return await core_html_ficha_tecnica_multiple(nregistro=nregistro, filename=filename)

    @server.tool(description=html_p_description)
    @_wrap
    async def html_prospecto(nregistro: str, filename: str = "Prospecto.html") -> str:
        return await core_html_prospecto(nregistro=nregistro, filename=filename)

    @server.tool(description=html_p_multiple_description)
    @_wrap
    async def html_prospecto_multiple(
        nregistro: list[str], filename: str = "Prospecto.html"
    ) -> dict[str, Any]:
        return await core_html_prospecto_multiple(nregistro=nregistro, filename=filename)

    return server


def main() -> None:
    """Entry point for ``mcp-aemps stdio`` and ``python -m app.stdio_server``."""
    configure_logging()
    server = build_server()
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
