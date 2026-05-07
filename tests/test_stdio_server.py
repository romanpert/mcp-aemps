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


def test_most_tools_expose_a_typed_output_schema() -> None:
    """Spec server/tools §"Output Schema" — code-mode hosts generate typed
    client APIs from outputSchema. Most CIMA tools expose a typed
    Pydantic envelope; the documented exceptions are:

    * ``doc_contenido`` — return shape is ``dict | str`` depending on
      ``format`` (json vs html/txt), an intentional Union we can't
      usefully constrain.
    * ``buscar_medicamentos``, ``listar_presentaciones``,
      ``listar_notas``, ``listar_materiales``, ``problemas_suministro``
      — emit ``ResourceLink`` ContentBlocks (item 7b), so they return a
      ``list[ContentBlock]`` instead of a typed envelope.
    * ``html_ficha_tecnica`` / ``html_prospecto`` — return raw HTML
      strings; FastMCP auto-wraps with ``{result: str}``.
    """
    from app.stdio_server import build_server

    tools = asyncio.run(build_server().list_tools())
    no_schema = [t.name for t in tools if not t.outputSchema]
    assert no_schema == ["doc_contenido"], (
        f"unexpected tools without outputSchema: {no_schema}"
    )

    typed_envelope_titles = {
        "CimaResponse",
        "CimaPaginatedResponse",
        "CimaCollectionResponse",
    }
    typed = [
        t for t in tools
        if t.outputSchema and t.outputSchema.get("title") in typed_envelope_titles
    ]
    titles_seen = {(t.outputSchema or {}).get("title") for t in tools}
    assert len(typed) >= 13, (
        f"expected ≥13 tools with a typed envelope; got "
        f"{len(typed)} (titles seen: {titles_seen})"
    )


def test_buscar_medicamentos_runtime_emits_resource_links() -> None:
    """End-to-end smoke for item 7b: with the upstream call mocked, the
    runtime ``tools/call`` content array MUST contain the original
    TextContent followed by one ResourceLink per hit. Code-mode hosts
    drop into ``resources/read`` against those URIs to lazy-load only
    the items the model wants."""
    from unittest.mock import AsyncMock, patch

    from mcp.types import ResourceLink, TextContent

    from app.stdio_server import build_server

    mock_payload = {
        "resultados": [
            {"nregistro": "12345", "nombre": "Aspirina 500mg", "cn": "654321"},
            {"nregistro": "67890", "nombre": "Ibuprofeno 600mg", "cn": "111222"},
        ],
        "totalFilas": 2,
        "metadata": {"fuente": "test"},
    }

    async def go():
        with patch(
            "app.stdio_server.core_buscar_medicamentos",
            AsyncMock(return_value=mock_payload),
        ):
            server = build_server()
            tool = server._tool_manager._tools["buscar_medicamentos"]
            return await tool.run({"nombre": "asp"}, context=None, convert_result=True)

    result = asyncio.run(go())
    assert isinstance(result, tuple), "expected (unstructured, structured) tuple"
    unstructured, _structured = result

    text_blocks = [c for c in unstructured if isinstance(c, TextContent)]
    link_blocks = [c for c in unstructured if isinstance(c, ResourceLink)]
    assert len(text_blocks) == 1, "expected exactly one TextContent envelope"
    assert "Aspirina" in text_blocks[0].text, "TextContent should contain the JSON payload"
    assert {str(l.uri) for l in link_blocks} == {
        "cima://medicamento/12345",
        "cima://medicamento/67890",
    }, "expected one ResourceLink per result keyed by nregistro"


def test_search_tools_emit_resource_link_content_blocks() -> None:
    """Item 7b: the 5 search/collection tools return ``list[ContentBlock]``
    so code-mode hosts can lazy-resolve hits via ``cima://`` URIs instead
    of inlining every full payload. The auto-generated outputSchema for
    these is a wrapper-shape (``{result: array}``), distinct from the
    typed Pydantic envelopes used by single-item tools."""
    from app.stdio_server import build_server

    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    expected_link_emitters = {
        "buscar_medicamentos",
        "listar_presentaciones",
        "listar_notas",
        "listar_materiales",
        "problemas_suministro",
    }
    for name in expected_link_emitters:
        t = tools[name]
        title = (t.outputSchema or {}).get("title", "")
        assert title.endswith("Output"), (
            f"{name}: expected list-of-ContentBlock auto-wrapper schema "
            f"(title ends with 'Output'); got title={title!r}"
        )


def test_every_tool_has_a_localised_title() -> None:
    """Spec tools §205: ``title`` is the human-friendly display name shown
    in client pickers (Claude Desktop, Inspector, Continue). Every CIMA
    tool MUST expose one in the active locale (default ES)."""
    from app.stdio_server import build_server

    tools = asyncio.run(build_server().list_tools())
    missing = [t.name for t in tools if not (t.title or "").strip()]
    assert not missing, f"tools missing localised title: {missing}"


def test_logging_set_level_capability_is_advertised() -> None:
    """MCP logging utility (server/utilities/logging) — clients can adjust
    verbosity at runtime. Capability is advertised automatically once the
    handler is registered on the lowlevel server."""
    from mcp.server.lowlevel import NotificationOptions
    from mcp.types import SetLevelRequest

    from app.stdio_server import build_server

    server = build_server()
    assert SetLevelRequest in server._mcp_server.request_handlers, (
        "logging/setLevel handler must be registered on the lowlevel server"
    )
    caps = server._mcp_server.get_capabilities(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )
    assert caps.logging is not None, "logging capability must be advertised"


def test_logging_set_level_applies_to_stdlib_loggers() -> None:
    """``apply_mcp_log_level`` mutates the stdlib logger tree so handlers
    actually emit at the requested level."""
    import logging

    from app.logging_setup import apply_mcp_log_level

    original_root = logging.getLogger().level
    original_app = logging.getLogger("mcp.aemps").level
    try:
        applied = apply_mcp_log_level("warning")
        assert applied == logging.WARNING
        assert logging.getLogger().level == logging.WARNING
        assert logging.getLogger("mcp.aemps").level == logging.WARNING
        # Unknown levels fall back to INFO rather than raising.
        applied_unknown = apply_mcp_log_level("not-a-level")
        assert applied_unknown == logging.INFO
    finally:
        logging.getLogger().setLevel(original_root)
        logging.getLogger("mcp.aemps").setLevel(original_app)


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


def test_http_transport_uses_the_same_fastmcp_server() -> None:
    """Since v0.2.7 the HTTP transport no longer goes via fastapi-mcp's
    OpenAPI→tools indirection — it mounts the same FastMCP instance that
    powers stdio. So tool annotations, prompts and resources are
    automatically identical across transports: there is only one server.

    This test pins the architecture: ``app.state.mcp_server`` must be a
    FastMCP instance equivalent to ``build_server()`` output."""
    from app.factory import create_app
    from app.stdio_server import build_server

    app = create_app()
    assert hasattr(app.state, "mcp_server"), (
        "create_app(mount_mcp=True) must store the FastMCP server on app.state.mcp_server"
    )
    server = app.state.mcp_server
    fresh = build_server()
    fresh_tools = {t.name for t in asyncio.run(fresh.list_tools())}
    http_tools = {t.name for t in asyncio.run(server.list_tools())}
    assert http_tools == fresh_tools, "HTTP-mounted MCP tools must match build_server() output"
    # Annotations are now native — no post-construction mutation needed.
    for tool in asyncio.run(server.list_tools()):
        assert tool.annotations is not None, f"{tool.name}: HTTP tool missing annotations"
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.openWorldHint is True, tool.name


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
