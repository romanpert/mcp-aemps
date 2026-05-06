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


def test_every_stdio_tool_has_read_only_annotations() -> None:
    """ChatGPT Dev Mode and Claude Desktop auto-approve UI keys off these
    hints. Every CIMA tool is a non-destructive read against an external
    open-world API — the invariant is uniform across all 21 tools."""
    from app.stdio_server import build_server

    tools = asyncio.run(build_server().list_tools())
    missing: list[str] = []
    wrong: list[str] = []
    for t in tools:
        ann = t.annotations
        if ann is None:
            missing.append(t.name)
            continue
        if not (
            ann.readOnlyHint is True
            and ann.destructiveHint is False
            and ann.idempotentHint is True
            and ann.openWorldHint is True
        ):
            wrong.append(t.name)
    assert not missing, f"tools without annotations: {missing}"
    assert not wrong, f"tools with wrong annotation values: {wrong}"


def test_every_http_tool_has_read_only_annotations() -> None:
    """Cross-transport parity for tool annotations — fastapi-mcp doesn't
    propagate them automatically, so the factory mutates them after
    FastApiMCP() construction. Verify the mutation took effect."""
    from fastapi_mcp import FastApiMCP

    from app.factory import create_app

    app = create_app(mount_mcp=False)
    # Build the MCP layer the same way create_app does, so we inspect the
    # exact Tool objects that ship.
    mcp = FastApiMCP(app, name=app.title, description=app.description)
    from app.mcp_constants import READ_ONLY_AEMPS_ANNOTATIONS

    for tool in mcp.tools:
        tool.annotations = READ_ONLY_AEMPS_ANNOTATIONS

    assert mcp.tools, "FastApiMCP produced zero tools — wiring is broken"
    for t in mcp.tools:
        ann = t.annotations
        assert ann is not None, f"http tool {t.name} missing annotations"
        assert ann.readOnlyHint is True, t.name
        assert ann.destructiveHint is False, t.name
        assert ann.idempotentHint is True, t.name
        assert ann.openWorldHint is True, t.name


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
        f"transport drift — only in stdio: {stdio_tools - http_ops}; only in http: {http_ops - stdio_tools}"
    )
    assert stdio_tools == EXPECTED_TOOLS
