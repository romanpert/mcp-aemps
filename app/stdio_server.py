# app/stdio_server.py
"""Native stdio MCP server.

The Anthropic-canonical MCP usage pattern is `uvx mcp-aemps stdio`: the
client (Claude Desktop, Codex, …) launches us as a subprocess and talks
JSON-RPC over stdin/stdout. This module implements exactly that, exposing
every official CIMA tool as an MCP tool — no HTTP server, no bridge, no
external proxy.

The HTTP server (`mcp-aemps up`) and this stdio server share the same
underlying CIMA client (`app.cima_client`) and metadata helpers, so a tool
call returns the same JSON shape regardless of transport.

Run with:  python -m app.stdio_server
Or via:    mcp-aemps stdio
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

import app.cima_client as cima
from app.config import settings
from app.helpers import (
    API_PSUM_VERSION,
    _build_metadata,
    bounded_gather,
    format_response,
    normalize_nregistro_and_cn,
    parse_cima_fechas,
    parse_cima_fechas_list,
    safe_cima_call,
)
from app.logging_setup import configure_logging
from app.mcp_constants import MCP_AEMPS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def build_server() -> FastMCP:
    """Construct the FastMCP server with all official CIMA tools."""
    server = FastMCP(
        name="mcp-aemps",
        instructions=MCP_AEMPS_SYSTEM_PROMPT,
    )

    # ------------------------------------------------------------------
    # Medicamentos
    # ------------------------------------------------------------------
    @server.tool()
    async def obtener_medicamento(
        cn: str | None = None,
        nregistro: str | None = None,
    ) -> dict[str, Any]:
        """Obtener ficha completa de un medicamento por CN o nregistro AEMPS."""
        if not (cn or nregistro):
            return {"error": "Se requiere 'cn' o 'nregistro'."}
        result = await safe_cima_call(cima.medicamento, cn=cn, nregistro=nregistro)
        parse_cima_fechas(result)
        params = {k: v for k, v in {"cn": cn, "nregistro": nregistro}.items() if v}
        return format_response(result, _build_metadata(params))

    @server.tool()
    async def buscar_medicamentos(
        nombre: str | None = None,
        laboratorio: str | None = None,
        practiv1: str | None = None,
        practiv2: str | None = None,
        idpractiv1: str | None = None,
        atc: str | None = None,
        cn: str | None = None,
        nregistro: str | None = None,
        triangulo: int | None = None,
        huerfano: int | None = None,
        biosimilar: int | None = None,
        comerc: int | None = None,
        receta: int | None = None,
        estupefaciente: int | None = None,
        psicotropo: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        """Listado paginado de medicamentos con filtros regulatorios avanzados."""
        params = {k: v for k, v in locals().items() if v is not None}
        result = await safe_cima_call(cima.medicamentos, **params)
        if isinstance(result, dict) and "resultados" in result:
            parse_cima_fechas_list(result["resultados"])
            result["resultados"] = result["resultados"][: settings.max_results]
        return format_response(result, _build_metadata(params))

    @server.tool()
    async def buscar_en_ficha_tecnica(reglas: list[dict[str, Any]]) -> dict[str, Any]:
        """Búsqueda textual dentro de secciones de la ficha técnica.

        `reglas` es una lista de objetos `{seccion, texto, contiene}` donde:
          - seccion: str (e.g. "4.1")
          - texto: str a buscar
          - contiene: 1 si debe contenerlo, 0 si no debe contenerlo
        """
        result = await safe_cima_call(cima.buscar_en_ficha_tecnica, reglas)
        return format_response(result, _build_metadata({"reglas": reglas}))

    # ------------------------------------------------------------------
    # Presentaciones / VMP / Maestras
    # ------------------------------------------------------------------
    @server.tool()
    async def listar_presentaciones(
        cn: str | None = None,
        nregistro: str | None = None,
        vmp: str | None = None,
        vmpp: str | None = None,
        idpractiv1: str | None = None,
        comerc: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        """Listado paginado de presentaciones con filtros."""
        params = {k: v for k, v in locals().items() if v is not None}
        result = await safe_cima_call(cima.presentaciones, **params)
        return format_response(result, _build_metadata(params))

    @server.tool()
    async def obtener_presentacion(cn: list[str]) -> dict[str, Any]:
        """Detalle de una o varias presentaciones por Código Nacional (paraleliza)."""
        if not cn:
            return {"error": "Se requiere al menos un 'cn'."}
        coros = [safe_cima_call(cima.presentacion, c) for c in cn]
        responses = await bounded_gather(coros)
        data: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for c, resp in zip(cn, responses):
            if isinstance(resp, Exception):
                errors[c] = str(resp)
            else:
                data[c] = resp
        payload: dict[str, Any] = {"data": data}
        if errors:
            payload["errors"] = errors
        return format_response(payload, _build_metadata({"cn": cn}))

    @server.tool()
    async def buscar_vmpp(
        practiv1: str | None = None,
        idpractiv1: str | None = None,
        dosis: str | None = None,
        forma: str | None = None,
        atc: str | None = None,
        nombre: str | None = None,
        modoArbol: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        """Equivalentes clínicos VMP/VMPP filtrables (principio activo, dosis, forma, ATC, …)."""
        params = {k: v for k, v in locals().items() if v is not None}
        result = await safe_cima_call(cima.vmpp, **params)
        return format_response(result, _build_metadata(params))

    @server.tool()
    async def consultar_maestras(
        maestra: int,
        nombre: str | None = None,
        id: str | None = None,
        codigo: str | None = None,
        estupefaciente: int | None = None,
        psicotropo: int | None = None,
        enuso: int | None = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        """Catálogos maestros AEMPS (1=ppio activo, 3=forma, 4=vía, 6=labs, 7=ATC, …)."""
        params = {k: v for k, v in locals().items() if v is not None}
        result = await safe_cima_call(cima.maestras, **params)
        return format_response(result, _build_metadata(params))

    # ------------------------------------------------------------------
    # Vigilancia
    # ------------------------------------------------------------------
    @server.tool()
    async def registro_cambios(
        fecha: str | None = None,
        nregistro: list[str] | None = None,
        metodo: str = "GET",
    ) -> dict[str, Any]:
        """Historial de altas/bajas/modificaciones de medicamentos. `fecha` formato dd/mm/yyyy."""
        result = await safe_cima_call(cima.registro_cambios, fecha=fecha, nregistro=nregistro, metodo=metodo)
        return format_response(result, _build_metadata({"fecha": fecha, "nregistro": nregistro}))

    @server.tool()
    async def problemas_suministro(
        cn: list[str] | None = None,
        nregistro: list[str] | None = None,
        pagina: int = 1,
        tamanioPagina: int = 25,
    ) -> dict[str, Any]:
        """Problemas de suministro: global paginado o detalle por CN (v2 con fallback v1)."""
        meta = _build_metadata(
            {"cn": cn, "nregistro": nregistro, "pagina": pagina, "tamanioPagina": tamanioPagina},
            API_PSUM_VERSION,
        )
        meta["metadata"]["tipo_problema_suministros"] = cima.TIPOS_PROBLEMA

        if not cn and not nregistro:
            listado = await safe_cima_call(
                cima.psuministro_global, pagina=pagina, tamanioPagina=tamanioPagina
            )
            data = listado.get("resultados", []) if isinstance(listado, dict) else listado
            return format_response(data, meta)

        # Resolver nregistro -> CNs
        resolved_cn: list[str] = []
        if nregistro:
            coros = [safe_cima_call(cima.medicamento, nregistro=nr) for nr in nregistro]
            responses = await bounded_gather(coros)
            for resp in responses:
                if not isinstance(resp, Exception):
                    pres = resp.get("data", {}).get("presentaciones") or resp.get("presentaciones") or []
                    for p in pres:
                        if p.get("cn"):
                            resolved_cn.append(p["cn"])

        cn_list = list(dict.fromkeys((cn or []) + resolved_cn))
        if not cn_list:
            return format_response({"error": "No se encontraron CN para procesar"}, meta)

        coros = [safe_cima_call(cima.psuministro_cn, c) for c in cn_list]
        responses = await bounded_gather(coros)
        data: dict[str, Any] = {}
        for c, resp in zip(cn_list, responses):
            if not isinstance(resp, Exception):
                data[c] = resp
        return format_response({"data": data}, meta)

    @server.tool()
    async def problemas_suministro_dcp(cod_dcp: str) -> dict[str, Any]:
        """Presentaciones comercializadas + con problemas para un DCP (descripción clínica)."""
        result = await safe_cima_call(cima.psuministro_dcp, cod_dcp)
        return format_response(result, _build_metadata({"cod_dcp": cod_dcp}, API_PSUM_VERSION))

    @server.tool()
    async def problemas_suministro_dcpf(cod_dcpf: str) -> dict[str, Any]:
        """Presentaciones comercializadas + con problemas para un DCPF (con forma farmacéutica)."""
        result = await safe_cima_call(cima.psuministro_dcpf, cod_dcpf)
        return format_response(result, _build_metadata({"cod_dcpf": cod_dcpf}, API_PSUM_VERSION))

    @server.tool()
    async def listar_notas(nregistro: list[str]) -> dict[str, Any]:
        """Notas de seguridad para uno o varios registros."""
        if not nregistro:
            return {"error": "Se requiere al menos un 'nregistro'."}
        coros = [safe_cima_call(cima.notas, nregistro=nr) for nr in nregistro]
        responses = await bounded_gather(coros)
        data: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for nr, resp in zip(nregistro, responses):
            if isinstance(resp, Exception):
                errors[nr] = str(resp)
            elif resp:
                data[nr] = resp
        return format_response({"notas": data, "errores": errors}, _build_metadata({"nregistro": nregistro}))

    @server.tool()
    async def listar_materiales(nregistro: list[str]) -> dict[str, Any]:
        """Materiales informativos para uno o varios registros."""
        if not nregistro:
            return {"error": "Se requiere al menos un 'nregistro'."}
        coros = [safe_cima_call(cima.materiales, nregistro=nr) for nr in nregistro]
        responses = await bounded_gather(coros)
        data = [r for r in responses if not isinstance(r, Exception) and r]
        return format_response(data, _build_metadata({"nregistro": nregistro}))

    # ------------------------------------------------------------------
    # Documentos segmentados (FT, prospecto)
    # ------------------------------------------------------------------
    @server.tool()
    async def doc_secciones(
        tipo_doc: int,
        nregistro: list[str] | None = None,
        cn: list[str] | None = None,
    ) -> dict[str, Any]:
        """Metadatos de secciones de FT (tipo_doc=1), prospecto (2), u otros (3-4)."""
        if not (nregistro or cn):
            return {"error": "Se requiere al menos un 'nregistro' o 'cn'."}
        results: list[dict[str, Any]] = []
        for code_list, is_cn in [(nregistro or [], False), (cn or [], True)]:
            for code in code_list:
                nr_norm, cn_norm = await normalize_nregistro_and_cn(
                    nregistro=None if is_cn else code,
                    cn=code if is_cn else None,
                )
                if not nr_norm:
                    continue
                bloques = await safe_cima_call(cima.doc_secciones, tipo_doc, nregistro=nr_norm)
                if bloques:
                    for b in bloques:
                        if isinstance(b, dict):
                            b["_codigo_origen"] = cn_norm or code
                            b["_nregistro"] = nr_norm
                    results.extend(bloques)
        return format_response(
            results, _build_metadata({"tipo_doc": tipo_doc, "cn": cn, "nregistro": nregistro})
        )

    @server.tool()
    async def doc_contenido(
        tipo_doc: int,
        nregistro: str | None = None,
        cn: str | None = None,
        seccion: str | None = None,
        format: str = "json",
    ) -> Any:
        """Contenido de secciones (FT/prospecto). format=json|html|txt."""
        if not (nregistro or cn):
            return {"error": "Se requiere 'nregistro' o 'cn'."}
        nr_norm, cn_norm = await normalize_nregistro_and_cn(nregistro=nregistro, cn=cn)
        if not nr_norm:
            return {"error": "No se pudo resolver nregistro"}
        result = await safe_cima_call(
            cima.doc_contenido,
            tipo_doc=tipo_doc,
            nregistro=nr_norm,
            seccion=seccion,
            format=format,
        )
        if format == "json":
            return format_response(
                result,
                _build_metadata(
                    {"tipo_doc": tipo_doc, "nregistro": nr_norm, "cn": cn_norm, "seccion": seccion}
                ),
            )
        return result

    @server.tool()
    async def html_ficha_tecnica(nregistro: str, filename: str = "FichaTecnica.html") -> str:
        """HTML completo de la ficha técnica de un medicamento."""
        data = await cima.get_html_bytes(tipo="ft", nregistro=nregistro, filename=filename)
        return data.decode("utf-8")

    @server.tool()
    async def html_prospecto(nregistro: str, filename: str = "Prospecto.html") -> str:
        """HTML completo del prospecto de un medicamento."""
        data = await cima.get_html_bytes(tipo="p", nregistro=nregistro, filename=filename)
        return data.decode("utf-8")

    return server


def main() -> None:
    """Entry point for `mcp-aemps stdio` and `python -m app.stdio_server`."""
    configure_logging()
    server = build_server()
    # FastMCP.run() defaults to stdio transport — exactly what we want.
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
