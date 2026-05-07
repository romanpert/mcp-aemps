"""MCP ``completion/complete`` handler — autocomplete for prompt args
and resource-template path parameters.

Spec ref: spec/server/utilities/completion + prompts §108. FastMCP
routes incoming ``completion/complete`` requests through the single
handler registered via ``@server.completion()``; we branch on the
reference type (``PromptReference`` vs ``ResourceTemplateReference``)
and on the argument name to pick a CIMA-backed source of suggestions.

Design notes:

* **Source of truth is CIMA, not a static list.** Suggestions come from
  ``core_buscar_medicamentos`` / ``core_consultar_maestras`` so the
  catalogue stays current. Slow vs. a static dict (~200-500 ms per
  call) but clients debounce, and ``MAX_VALUES`` caps the response.
* **Empty prefix returns nothing.** CIMA's filtered search is
  unbounded; without a prefix we'd return tens of thousands of items.
  Letting the user type at least 2 chars keeps both wire payloads and
  upstream load reasonable.
* **Soft fail.** Any exception inside the handler logs and returns
  ``None`` — autocomplete is non-essential UX, never block a tool
  call because completion failed.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
)

from app.core import core_buscar_medicamentos, core_consultar_maestras

logger = logging.getLogger("mcp.aemps.completions")

# Cap suggestions per call. Spec allows up to 100 values; we keep it
# tighter to bound upstream load.
MAX_VALUES = 50

# Maestras IDs — keep in sync with helpers / system prompt.
PRINCIPIOS_ACTIVOS_ID = 1
LABORATORIOS_ID = 6
ATC_ID = 7

# Minimum prefix length before we hit upstream. CIMA's free-text filters
# are reasonably indexed but a 0-char prefix would hammer the API.
MIN_PREFIX_LEN = 2


# ---------------------------------------------------------------------------
# Source helpers — each returns a flat list[str] of suggestions
# ---------------------------------------------------------------------------


async def _by_nregistro(prefix: str) -> list[str]:
    if len(prefix) < MIN_PREFIX_LEN:
        return []
    payload = await core_buscar_medicamentos(nregistro=prefix, pagina=1)
    out: list[str] = []
    seen: set[str] = set()
    for item in payload.get("resultados") or []:
        nr = item.get("nregistro")
        if nr is None:
            continue
        nr_s = str(nr)
        if nr_s in seen:
            continue
        seen.add(nr_s)
        out.append(nr_s)
        if len(out) >= MAX_VALUES:
            break
    return out


async def _by_cn(prefix: str) -> list[str]:
    if len(prefix) < MIN_PREFIX_LEN:
        return []
    payload = await core_buscar_medicamentos(cn=prefix, pagina=1)
    out: list[str] = []
    seen: set[str] = set()
    for item in payload.get("resultados") or []:
        for pres in item.get("presentaciones") or []:
            cn = pres.get("cn")
            if cn is None:
                continue
            cn_s = str(cn)
            if not cn_s.startswith(prefix) or cn_s in seen:
                continue
            seen.add(cn_s)
            out.append(cn_s)
            if len(out) >= MAX_VALUES:
                return out
    return out


async def _by_laboratorio(prefix: str) -> list[str]:
    if len(prefix) < MIN_PREFIX_LEN:
        return []
    payload = await core_consultar_maestras(maestra=LABORATORIOS_ID, nombre=prefix, pagina=1)
    items = payload.get("resultados") or []
    return [str(it.get("nombre")) for it in items if it.get("nombre")][:MAX_VALUES]


async def _by_principio_activo(prefix: str) -> list[str]:
    if len(prefix) < MIN_PREFIX_LEN:
        return []
    payload = await core_consultar_maestras(maestra=PRINCIPIOS_ACTIVOS_ID, nombre=prefix, pagina=1)
    items = payload.get("resultados") or []
    return [str(it.get("nombre")) for it in items if it.get("nombre")][:MAX_VALUES]


async def _by_atc(prefix: str) -> list[str]:
    if len(prefix) < MIN_PREFIX_LEN:
        return []
    # ATC has both `codigo` (alphanumeric like C09AA02) and `nombre`. Try
    # codigo first; fall back to nombre filter for descriptive prefixes.
    payload = await core_consultar_maestras(maestra=ATC_ID, codigo=prefix, pagina=1)
    items = payload.get("resultados") or []
    out = [str(it.get("codigo")) for it in items if it.get("codigo")]
    if out:
        return out[:MAX_VALUES]
    payload = await core_consultar_maestras(maestra=ATC_ID, nombre=prefix, pagina=1)
    items = payload.get("resultados") or []
    return [str(it.get("codigo")) for it in items if it.get("codigo")][:MAX_VALUES]


# ---------------------------------------------------------------------------
# Routing tables — argument name → source helper
# ---------------------------------------------------------------------------

# Prompt args (singular and list-of variants alike — completions are
# always single-value suggestions; the host inserts one at a time).
_PROMPT_ARG_SOURCES: dict[str, Callable[[str], Awaitable[list[str]]]] = {
    "cn": _by_cn,
    "nregistro": _by_nregistro,
    "nregistros": _by_nregistro,
    "nombre_o_cn": _by_cn,  # tools accept either; CN is the safer default
    "laboratorio": _by_laboratorio,
    "principio_activo": _by_principio_activo,
    "principios_activos": _by_principio_activo,
    "atc": _by_atc,
}

# Resource-template path params keyed by template URI. Adding a new
# template here is the only place to wire its autocomplete.
_RESOURCE_TEMPLATE_SOURCES: dict[str, dict[str, Callable[[str], Awaitable[list[str]]]]] = {
    "cima://medicamento/{nregistro}": {"nregistro": _by_nregistro},
    "cima://presentacion/{cn}": {"cn": _by_cn},
    "cima://docs/ficha-tecnica/{nregistro}": {"nregistro": _by_nregistro},
    "cima://docs/ficha-tecnica/{nregistro}/{seccion}": {"nregistro": _by_nregistro},
    "cima://docs/prospecto/{nregistro}": {"nregistro": _by_nregistro},
    "cima://docs/prospecto/{nregistro}/{seccion}": {"nregistro": _by_nregistro},
    "cima://maestras/atc/{codigo}": {"codigo": _by_atc},
}


# ---------------------------------------------------------------------------
# FastMCP integration
# ---------------------------------------------------------------------------


async def _suggest(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
) -> list[str]:
    """Resolve the matching source for the (ref, argument) pair and run it.

    Returns an empty list (= no completions) if no source is wired or
    the prefix is too short. Any upstream error propagates so the
    caller can swallow it uniformly.
    """
    prefix = (argument.value or "").strip()
    if isinstance(ref, ResourceTemplateReference):
        sources = _RESOURCE_TEMPLATE_SOURCES.get(ref.uri, {})
        source = sources.get(argument.name)
    elif isinstance(ref, PromptReference):
        source = _PROMPT_ARG_SOURCES.get(argument.name)
    else:
        return []
    if source is None:
        return []
    return await source(prefix)


def register_completions(server: FastMCP) -> None:
    """Wire the completion handler onto a FastMCP server instance.

    Called once from ``app.stdio_server.build_server()``. Both transports
    (stdio + Streamable HTTP) inherit the handler because they share the
    same FastMCP instance.
    """

    @server.completion()
    async def handle_completion(
        ref: PromptReference | ResourceTemplateReference,
        argument: CompletionArgument,
        context: CompletionContext | None,
    ) -> Completion | None:  # noqa: D401
        try:
            values = await _suggest(ref, argument)
        except Exception:  # noqa: BLE001
            logger.exception(
                "completion failed for %s arg=%r value=%r",
                getattr(ref, "uri", getattr(ref, "name", "?")),
                argument.name,
                argument.value,
            )
            return None
        if not values:
            return None
        return Completion(
            values=values,
            total=len(values),
            hasMore=len(values) >= MAX_VALUES,
        )
