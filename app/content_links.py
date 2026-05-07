"""ResourceLink builders for collection tools (v0.3.0 batch 3 item 7b).

Spec ref: tools §370 ``ResourceLink`` ContentBlock. When a search tool
returns N hits, returning the full payload for each hit inline burns
token budget on every host even when the user only cares about a few
items. Emitting one ``resource_link`` per hit lets code-mode hosts
(Claude Code, Codex CLI) lazy-resolve via ``resources/read`` only the
items the model actually wants.

Trade-off: tools that emit ResourceLinks return a ``list[ContentBlock]``
instead of a Pydantic envelope, so they lose ``structuredContent``.
This is the architectural conflict between item 1 (typed envelopes,
helps every host) and item 7b (resource_link, helps code-mode hosts on
search results). Applied selectively to the 5 search tools where token
savings are largest; single-item tools keep their typed envelopes.

The TextContent first element preserves the existing wire format so
non-code-mode hosts keep seeing the same JSON they did before — this
is strictly additive for them.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from mcp.types import ContentBlock, ResourceLink, TextContent

__all__ = [
    "medicamento_link",
    "presentacion_link",
    "build_search_response",
    "links_for_medicamentos",
    "links_for_presentaciones",
    "links_from_keys",
]


def medicamento_link(nregistro: str, *, name: str | None = None) -> ResourceLink:
    """Build a `cima://medicamento/{nregistro}` ResourceLink."""
    label = name or f"Medicamento {nregistro}"
    return ResourceLink(
        type="resource_link",
        uri=f"cima://medicamento/{nregistro}",
        name=label,
        title=label,
        description=f"Ficha completa del medicamento (nregistro {nregistro}).",
        mimeType="application/json",
    )


def presentacion_link(cn: str, *, name: str | None = None) -> ResourceLink:
    """Build a `cima://presentacion/{cn}` ResourceLink."""
    label = name or f"Presentacion CN {cn}"
    return ResourceLink(
        type="resource_link",
        uri=f"cima://presentacion/{cn}",
        name=label,
        title=label,
        description=f"Detalle de la presentacion (CN {cn}).",
        mimeType="application/json",
    )


def links_for_medicamentos(items: Sequence[dict[str, Any]]) -> list[ResourceLink]:
    """One ResourceLink per medicamento hit, keyed by ``nregistro``.

    Skips items without a usable nregistro. Uses ``nombre`` as the link
    label so pickers render something meaningful instead of the bare ID.
    Deduplicates on nregistro to keep the link list under control when
    upstream returns the same medicamento twice (e.g. paginated edges).
    """
    out: list[ResourceLink] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        nr = item.get("nregistro")
        if not nr:
            continue
        nr_str = str(nr).strip()
        if not nr_str or nr_str in seen:
            continue
        seen.add(nr_str)
        out.append(medicamento_link(nr_str, name=item.get("nombre")))
    return out


def links_for_presentaciones(items: Sequence[dict[str, Any]]) -> list[ResourceLink]:
    """One ResourceLink per presentation hit, keyed by ``cn``.

    Same dedup contract as ``links_for_medicamentos``.
    """
    out: list[ResourceLink] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cn = item.get("cn")
        if not cn:
            continue
        cn_str = str(cn).strip()
        if not cn_str or cn_str in seen:
            continue
        seen.add(cn_str)
        out.append(presentacion_link(cn_str, name=item.get("nombre")))
    return out


def links_from_keys(keys: Sequence[str], builder: Any) -> list[ResourceLink]:
    """Build ResourceLinks from a flat sequence of identifier keys (used
    when the payload is keyed by ``nregistro`` / ``cn`` rather than a list
    of dicts). ``builder`` is one of ``medicamento_link`` or
    ``presentacion_link``."""
    out: list[ResourceLink] = []
    seen: set[str] = set()
    for key in keys or []:
        if not key:
            continue
        s = str(key).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(builder(s))
    return out


def build_search_response(
    payload: Any,
    links: Sequence[ResourceLink],
) -> list[ContentBlock]:
    """Combine the original JSON payload (as ``TextContent``) with the
    derived ResourceLinks into the ``content`` array MCP returns to the
    client.

    The TextContent first element keeps the existing wire format so
    non-code-mode hosts see the same JSON they did before this change.
    Code-mode hosts pick up the ResourceLink suffix and lazy-resolve.
    """
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return [TextContent(type="text", text=body), *links]
