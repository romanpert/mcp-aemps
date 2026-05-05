"""Tests for the stdio MCP server (`mcp-aemps stdio`)."""

from __future__ import annotations

import asyncio


def test_build_server_registers_all_official_tools() -> None:
    """The stdio server must expose every official CIMA tool we ship in HTTP mode."""
    from app.stdio_server import build_server

    server = build_server()
    assert server.name == "mcp-aemps"

    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}

    expected = {
        "obtener_medicamento",
        "buscar_medicamentos",
        "buscar_en_ficha_tecnica",
        "listar_presentaciones",
        "obtener_presentacion",
        "buscar_vmpp",
        "consultar_maestras",
        "registro_cambios",
        "problemas_suministro",
        "problemas_suministro_dcp",
        "problemas_suministro_dcpf",
        "listar_notas",
        "listar_materiales",
        "doc_secciones",
        "doc_contenido",
        "html_ficha_tecnica",
        "html_prospecto",
    }

    missing = expected - tool_names
    assert not missing, f"stdio server missing official CIMA tools: {missing}"


def test_every_tool_has_a_description() -> None:
    """Tool surface quality — LLMs need descriptions to pick the right tool."""
    from app.stdio_server import build_server

    tools = asyncio.run(build_server().list_tools())
    tools_without_desc = [t.name for t in tools if not (t.description or "").strip()]
    assert not tools_without_desc, f"missing description: {tools_without_desc}"


def test_every_tool_input_schema_is_json_schema() -> None:
    """Each tool exposes a valid JSON schema for its inputs."""
    from app.stdio_server import build_server

    tools = asyncio.run(build_server().list_tools())
    for t in tools:
        schema = t.inputSchema
        assert isinstance(schema, dict), f"{t.name}: schema is not a dict"
        assert schema.get("type") == "object", f"{t.name}: schema.type != object"
        assert "properties" in schema, f"{t.name}: schema has no properties"
