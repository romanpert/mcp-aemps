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

# Note: ``from __future__ import annotations`` is intentionally NOT imported
# here. FastMCP's ``func_metadata`` resolves return-type annotations using
# the function's ``__globals__`` to derive ``outputSchema``. After
# ``functools.wraps`` is applied by ``wrap_stdio_tool``, the wrapper's
# ``__globals__`` points at ``app.tool_hooks`` — which doesn't import the
# response models. Eager (non-stringified) annotations sidestep that lookup
# entirely. PEP 585 / PEP 604 syntax (``list[str]``, ``str | None``) is
# runtime-supported on the Python ≥ 3.11 we ship for.

import asyncio
import logging
from typing import Any, Sequence

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ContentBlock

from app.completions import register_completions
from app.config import settings as _settings
from app.content_links import (
    build_search_response,
    links_for_medicamentos,
    links_for_presentaciones,
    links_from_keys,
    medicamento_link,
    presentacion_link,
)
from app.core import (
    CimaCollectionResponse,
    CimaPaginatedResponse,
    CimaResponse,
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
from app.logging_setup import apply_mcp_log_level, configure_logging
from app.mcp_constants import (
    MCP_AEMPS_SYSTEM_PROMPT,
    READ_ONLY_AEMPS_ANNOTATIONS,
    TOOL_TITLES,
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
from app.prompts import register_prompts
from app.resources import register_resources
from app.tool_hooks import HookSet, PostHookFn, PreHookFn, wrap_stdio_tool

logger = logging.getLogger(__name__)


def build_server(
    *,
    pre_tool_hooks: Sequence[PreHookFn] = (),
    post_tool_hooks: Sequence[PostHookFn] = (),
    streamable_http_path: str = "/mcp",
    auth_settings: Any = None,
    token_verifier: Any = None,
) -> FastMCP:
    """Construct the FastMCP server with every official CIMA tool, prompt,
    and resource.

    Single source of truth for both the stdio transport (``mcp-aemps stdio``)
    and the HTTP Streamable transport mounted by ``app.factory.create_app``.

    * ``pre_tool_hooks`` / ``post_tool_hooks`` fire around every tool
      invocation regardless of transport (see ``app.tool_hooks``).
    * ``streamable_http_path`` controls where FastMCP serves the
      Streamable-HTTP endpoint relative to its own Starlette root. Default
      ``/mcp`` matches the CLI's standalone behaviour. ``create_app``
      passes ``"/"`` so it can mount the resulting app at ``/mcp`` in the
      outer FastAPI app — mounting at ``/mcp`` with the default would
      double the prefix to ``/mcp/mcp``.
    * ``auth_settings`` / ``token_verifier`` enable OAuth 2.1 Resource-
      Server mode on the HTTP transport. See ``app.auth`` for the
      construction helpers. stdio is not affected — process-local access
      is not gated by OAuth.
    """
    # MCP transport security: FastMCP ≥ 1.27 auto-enables DNS rebinding
    # protection when host is localhost-y, with an allowed_hosts list
    # that rejects both FastAPI TestClient's ``testserver`` and any
    # user-supplied reverse-proxy hostname. We always pass an explicit
    # TransportSecuritySettings so behaviour is deterministic and
    # controllable via the env vars MCP_AEMPS_DNS_REBINDING_PROTECTION /
    # MCP_AEMPS_ALLOWED_HOSTS / MCP_AEMPS_ALLOWED_ORIGINS (see
    # app.config.Settings).
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=_settings.mcp_aemps_dns_rebinding_protection,
        allowed_hosts=_settings.mcp_aemps_allowed_hosts
        or [
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "127.0.0.1",
            "localhost",
            "[::1]",
            # FastAPI TestClient default — keeps the test surface working
            # without leaking real attack surface (no DNS resolves to
            # ``testserver`` in the wild).
            "testserver",
        ],
        allowed_origins=_settings.mcp_aemps_allowed_origins
        or [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ],
    )

    fastmcp_kwargs: dict[str, Any] = {
        "name": "mcp-aemps",
        "instructions": MCP_AEMPS_SYSTEM_PROMPT,
        "streamable_http_path": streamable_http_path,
        "transport_security": transport_security,
    }
    if auth_settings is not None:
        fastmcp_kwargs["auth"] = auth_settings
    if token_verifier is not None:
        fastmcp_kwargs["token_verifier"] = token_verifier
    server = FastMCP(**fastmcp_kwargs)
    hooks = HookSet.from_sequences(pre=pre_tool_hooks, post=post_tool_hooks)

    def _wrap(func):
        return wrap_stdio_tool(hooks, func)

    # Curry FastMCP.tool so every CIMA tool inherits the uniform read-only
    # annotations + the localised display title. ``title`` is looked up by
    # the wrapped function's ``__name__`` (which is also what FastMCP uses
    # as the tool ``name``), so adding a tool only needs the matching entry
    # in ``TOOL_TITLES``. Per-tool overrides (e.g. a future write tool) can
    # still call ``server.tool(annotations=...)`` directly.
    def _tool(*, description: str):
        def decorator(func):
            return server.tool(
                title=TOOL_TITLES.get(func.__name__),
                description=description,
                annotations=READ_ONLY_AEMPS_ANNOTATIONS,
            )(func)

        return decorator

    # ------------------------------------------------------------------
    # Medicamentos
    # ------------------------------------------------------------------
    @_tool(description=medicamento_description)
    @_wrap
    async def obtener_medicamento(
        cn: str | None = None,
        nregistro: str | None = None,
    ) -> CimaResponse:
        return await core_obtener_medicamento(cn=cn, nregistro=nregistro)

    @_tool(description=medicamentos_description)
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
    ) -> list[ContentBlock]:
        # Item 7b: emit one ResourceLink per hit pointing at
        # cima://medicamento/{nregistro} so code-mode hosts can lazy-resolve
        # only the items the model actually wants. Loses structuredContent
        # vs. the typed envelope used by single-item tools — see
        # app.content_links for the trade-off.
        payload = await core_buscar_medicamentos(
            nombre=nombre,
            laboratorio=laboratorio,
            practiv1=practiv1,
            practiv2=practiv2,
            idpractiv1=idpractiv1,
            idpractiv2=idpractiv2,
            atc=atc,
            cn=cn,
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
        links = links_for_medicamentos(payload.get("resultados") or [])
        return build_search_response(payload, links)

    @_tool(description=buscar_ficha_tecnica_description)
    @_wrap
    async def buscar_en_ficha_tecnica(reglas: list[dict[str, Any]]) -> CimaResponse:
        return await core_buscar_en_ficha_tecnica(reglas)

    # ------------------------------------------------------------------
    # Presentaciones / VMP / Maestras
    # ------------------------------------------------------------------
    @_tool(description=presentaciones_description)
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
    ) -> list[ContentBlock]:
        # Item 7b: emit ResourceLinks pointing at cima://presentacion/{cn}.
        payload = await core_listar_presentaciones(
            cn=cn,
            nregistro=nregistro,
            vmp=vmp,
            vmpp=vmpp,
            idpractiv1=idpractiv1,
            comerc=comerc,
            estupefaciente=estupefaciente,
            psicotropo=psicotropo,
            estuopsico=estuopsico,
            pagina=pagina,
        )
        links = links_for_presentaciones(payload.get("resultados") or [])
        return build_search_response(payload, links)

    @_tool(description=presentacion_description)
    @_wrap
    async def obtener_presentacion(cn: list[str]) -> CimaCollectionResponse:
        return await core_obtener_presentacion(cn=cn)

    @_tool(description=vmpp_description)
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
    ) -> CimaPaginatedResponse:
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

    @_tool(description=maestras_description)
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
    ) -> CimaPaginatedResponse:
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

    # ------------------------------------------------------------------
    # Vigilancia
    # ------------------------------------------------------------------
    @_tool(description=registro_cambios_description)
    @_wrap
    async def registro_cambios(
        fecha: str | None = None,
        nregistro: list[str] | None = None,
        metodo: str = "GET",
    ) -> CimaPaginatedResponse:
        return await core_registro_cambios(fecha=fecha, nregistro=nregistro, metodo=metodo)

    @_tool(description=problemas_suministro_description)
    @_wrap
    async def problemas_suministro(
        cn: list[str] | None = None,
        nregistro: list[str] | None = None,
        pagina: int = 1,
        tamanioPagina: int = 25,
    ) -> list[ContentBlock]:
        # Item 7b: emit ResourceLinks per CN so code-mode hosts can pull
        # the full presentacion record on demand. The CN-keyed `data`
        # dict drives the link list; the global-listing case (no params)
        # falls back to deriving links from the resultados list.
        payload = await core_problemas_suministro(
            cn=cn,
            nregistro=nregistro,
            pagina=pagina,
            tamanioPagina=tamanioPagina,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            # CN/nregistro mode: keys are CN strings.
            links = links_from_keys(list(data.keys()), presentacion_link)
        elif isinstance(data, list):
            # Global mode: derive links from each row's `cn`.
            links = links_for_presentaciones(data)
        else:
            links = []
        return build_search_response(payload, links)

    @_tool(description=problemas_suministro_dcp_description)
    @_wrap
    async def problemas_suministro_dcp(cod_dcp: str) -> CimaResponse:
        return await core_problemas_suministro_dcp(cod_dcp=cod_dcp)

    @_tool(description=problemas_suministro_dcpf_description)
    @_wrap
    async def problemas_suministro_dcpf(cod_dcpf: str) -> CimaResponse:
        return await core_problemas_suministro_dcpf(cod_dcpf=cod_dcpf)

    @_tool(description=listar_notas_description)
    @_wrap
    async def listar_notas(
        nregistro: list[str],
        ctx: Context = None,  # type: ignore[assignment]
    ) -> list[ContentBlock]:
        # Item 7b: emit ResourceLinks for each nregistro that returned
        # at least one nota.
        # Item 4: ctx threads through to progress_gather inside the core
        # so clients with a progressToken see one /progress notification
        # per completed nregistro.
        payload = await core_listar_notas(nregistro=nregistro, ctx=ctx)
        notas = payload.get("notas") if isinstance(payload, dict) else None
        keys = list(notas.keys()) if isinstance(notas, dict) else []
        links = links_from_keys(keys, medicamento_link)
        return build_search_response(payload, links)

    @_tool(description=obtener_notas_description)
    @_wrap
    async def obtener_notas(nregistros: list[str]) -> CimaCollectionResponse:
        return await core_obtener_notas(nregistros=nregistros)

    @_tool(description=listar_materiales_description)
    @_wrap
    async def listar_materiales(
        nregistro: list[str],
        ctx: Context = None,  # type: ignore[assignment]
    ) -> list[ContentBlock]:
        # Item 7b: emit ResourceLinks for each input nregistro. The core
        # returns a flat list of materiales without per-medicamento keys,
        # so we use the requested nregistros as the link source.
        # Item 4: ctx threaded through for per-nregistro progress.
        payload = await core_listar_materiales(nregistro=nregistro, ctx=ctx)
        links = links_from_keys(nregistro, medicamento_link)
        return build_search_response(payload, links)

    @_tool(description=obtener_materiales_description)
    @_wrap
    async def obtener_materiales(nregistro: str) -> CimaResponse:
        return await core_obtener_materiales(nregistro=nregistro)

    # ------------------------------------------------------------------
    # Documentos segmentados (FT, prospecto)
    # ------------------------------------------------------------------
    @_tool(description=doc_secciones_description)
    @_wrap
    async def doc_secciones(
        tipo_doc: int,
        nregistro: list[str] | None = None,
        cn: list[str] | None = None,
    ) -> CimaResponse:
        return await core_doc_secciones(tipo_doc=tipo_doc, nregistro=nregistro, cn=cn)

    @_tool(description=doc_contenido_description)
    @_wrap
    async def doc_contenido(
        tipo_doc: int,
        nregistro: str | None = None,
        cn: str | None = None,
        seccion: str | None = None,
        format: str = "json",
    ) -> list[ContentBlock]:
        # Item 1c (v0.3.0 batch 4): normalise to list[ContentBlock] so
        # FastMCP emits an outputSchema (closes the 21/21 gap from
        # batch 3). The LLM-visible payload is preserved: format=json
        # surfaces the full envelope as JSON; format=html/txt surfaces
        # the raw body without the dict wrapper. HTTP transport keeps
        # returning ``Response(content, media_type=...)`` separately.
        import json as _json

        from mcp.types import TextContent

        result = await core_doc_contenido(
            tipo_doc=tipo_doc,
            nregistro=nregistro,
            cn=cn,
            seccion=seccion,
            format=format,
        )
        if format != "json" and isinstance(result, dict) and "content" in result:
            body = result["content"] or ""
            return [TextContent(type="text", text=str(body))]
        return [TextContent(type="text", text=_json.dumps(result, ensure_ascii=False, default=str))]

    @_tool(description=html_ft_description)
    @_wrap
    async def html_ficha_tecnica(nregistro: str, filename: str = "FichaTecnica.html") -> str:
        return await core_html_ficha_tecnica(nregistro=nregistro, filename=filename)

    @_tool(description=html_ft_multiple_description)
    @_wrap
    async def html_ficha_tecnica_multiple(
        nregistro: list[str],
        filename: str = "FichaTecnica.html",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> CimaCollectionResponse:
        # Item 4: per-nregistro progress so clients render "5/12" while
        # the HTML fanout downloads.
        return await core_html_ficha_tecnica_multiple(nregistro=nregistro, filename=filename, ctx=ctx)

    @_tool(description=html_p_description)
    @_wrap
    async def html_prospecto(nregistro: str, filename: str = "Prospecto.html") -> str:
        return await core_html_prospecto(nregistro=nregistro, filename=filename)

    @_tool(description=html_p_multiple_description)
    @_wrap
    async def html_prospecto_multiple(
        nregistro: list[str],
        filename: str = "Prospecto.html",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> CimaCollectionResponse:
        # Item 4: per-nregistro progress for the prospecto HTML fanout.
        return await core_html_prospecto_multiple(nregistro=nregistro, filename=filename, ctx=ctx)

    # ------------------------------------------------------------------
    # MCP logging utility — clients can adjust verbosity at runtime via
    # ``logging/setLevel``. Spec ref: server/utilities/logging. Wired here
    # so both transports inherit it (HTTP transport mounts the same FastMCP
    # instance from app.factory.create_app).
    # ------------------------------------------------------------------
    @server._mcp_server.set_logging_level()
    async def _set_log_level(level: str) -> None:  # pragma: no cover - thin shim
        applied = apply_mcp_log_level(level)
        logger.info(
            "MCP logging/setLevel applied: %s → stdlib level %s",
            level,
            logging.getLevelName(applied),
        )

    # ------------------------------------------------------------------
    # Curated MCP Prompts — workflows for farmacia / hospital / industria /
    # non-specialist users. See app/prompts.py for the full catalogue.
    # ------------------------------------------------------------------
    register_prompts(server)

    # ------------------------------------------------------------------
    # Curated MCP Resources — ``cima://`` URIs for streaming docs and
    # cacheable maestras. See app/resources.py for the full catalogue.
    # ------------------------------------------------------------------
    register_resources(server)

    # ------------------------------------------------------------------
    # MCP completion/complete — autocomplete for prompt args and
    # resource-template params (v0.3.0 batch 4 item 3). See
    # app/completions.py for the catalogue and source helpers.
    # ------------------------------------------------------------------
    register_completions(server)

    return server


def main() -> None:
    """Entry point for ``mcp-aemps stdio`` and ``python -m app.stdio_server``."""
    configure_logging()
    server = build_server()

    async def _run() -> None:
        # Fire-and-forget outdated-version check (matches HTTP lifespan
        # behaviour). The MCP host pipes our stderr to its log, so the
        # warning surfaces in Claude Desktop / Codex / VS Code logs.
        # Keep a local reference: asyncio may GC a task before its
        # body runs if no strong reference is held.
        from app.config import settings
        from app.version_check import schedule_check

        _version_task = schedule_check(settings.mcp_aemps_version)  # noqa: F841
        await server.run_stdio_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
