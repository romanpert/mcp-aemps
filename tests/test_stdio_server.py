"""Tests for the stdio MCP server (`mcp-aemps stdio`) and HTTP↔stdio parity."""

from __future__ import annotations

import asyncio


EXPECTED_TOOLS = {
    # medicamentos
    "obtener_medicamento",
    "buscar_medicamentos",
    "buscar_en_ficha_tecnica",
    "listar_presentaciones",
    "obtener_presentacion",
    "buscar_vmpp",
    "consultar_maestras",
    # vigilancia
    "registro_cambios",
    "problemas_suministro",
    "problemas_suministro_dcp",
    "problemas_suministro_dcpf",
    "listar_notas",
    "obtener_notas",
    "listar_materiales",
    "obtener_materiales",
    # documentos
    "doc_secciones",
    "doc_contenido",
    "html_ficha_tecnica",
    "html_ficha_tecnica_multiple",
    "html_prospecto",
    "html_prospecto_multiple",
}


def test_build_server_registers_all_official_tools() -> None:
    """The stdio server must expose every official CIMA tool."""
    from app.stdio_server import build_server

    server = build_server()
    assert server.name == "mcp-aemps"

    tool_names = {t.name for t in asyncio.run(server.list_tools())}
    missing = EXPECTED_TOOLS - tool_names
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


def test_http_and_stdio_expose_the_same_tools() -> None:
    """Cross-transport parity: every CIMA tool MUST be reachable from both
    transports. ``get_system_info_prompt`` is intentionally HTTP-only (it
    serves the system prompt over a REST endpoint; the same content is
    delivered to stdio clients via FastMCP ``instructions``)."""
    from app.factory import create_app
    from app.stdio_server import build_server

    stdio_tools = {t.name for t in asyncio.run(build_server().list_tools())}

    spec = create_app().openapi()
    http_ops = {
        op["operationId"]
        for path, methods in spec["paths"].items()
        for method, op in methods.items()
        if method in ("get", "post") and op.get("operationId")
    }
    http_ops -= {"get_system_info_prompt"}

    assert stdio_tools == http_ops, (
        f"transport drift — only in stdio: {stdio_tools - http_ops}; "
        f"only in http: {http_ops - stdio_tools}"
    )
    assert stdio_tools == EXPECTED_TOOLS
