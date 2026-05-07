# app/resources.py
"""Curated MCP Resources — read-only URIs that clients can subscribe to,
cache, and stream without re-paying the token cost of a tool call.

Why resources rather than just more tools:

* **Token cost**: tools require the LLM to write a tool call and wait for
  the JSON response to land in context. Resources are URIs the host
  application can read once and cache without round-tripping the LLM.
  Repeated lookups against ``consultar_maestras`` for ATC codes are the
  dominant token waste in interactive sessions — exposing each maestra
  as a static URI lets the client cache it indefinitely.
* **Streaming**: full ficha técnica HTML can exceed 100 KB. Resources let
  the client stream the response directly to the user without going
  through a tool call boundary.
* **Discoverability**: static resources surface in
  ``resources/list`` with their MIME type. Clients (Claude Desktop,
  Continue, …) render attachable URIs in their UI without the LLM having
  to know they exist.

Two flavours:

* **Static resources** (one URI, no parameters): a maestra full list.
  Listed via ``resources/list``.
* **Resource templates** (URI with ``{vars}``): single-item lookups.
  Listed via ``resources/templates/list``.

URI scheme: ``cima://`` (custom; mcp-aemps owns the namespace). All
resources are read-only — there is no upstream write. MIME types match
the body: ``application/json`` for maestras, ``text/html`` for
documents.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core import (
    OperationError,
    core_consultar_maestras,
    core_html_ficha_tecnica,
    core_html_ficha_tecnica_multiple,
    core_html_prospecto,
    core_html_prospecto_multiple,
    core_obtener_medicamento,
    core_obtener_presentacion,
)

# Maestra IDs as documented in CIMA REST API v1.23 §"GET maestras".
# Keep the slug → id map small and obvious — adding a new maestra is one
# entry here plus one @server.resource() registration below.
MAESTRA_SLUG_TO_ID: dict[str, int] = {
    "principios-activos": 1,
    "formas-farmaceuticas": 3,
    "vias-administracion": 4,
    "laboratorios": 6,
    "atc": 7,
}

# Inverse lookup so error messages can list the valid slugs alphabetically.
_VALID_MAESTRA_SLUGS = sorted(MAESTRA_SLUG_TO_ID)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _maestra_url_for_codigo(slug: str, codigo: str) -> int:
    """Resolve the slug to its CIMA maestra id; raise OperationError on bad slug."""
    try:
        return MAESTRA_SLUG_TO_ID[slug]
    except KeyError:
        raise OperationError(
            404,
            error="Maestra desconocida",
            message=(
                f"Slug '{slug}' no es una maestra reconocida. "
                f"Slugs válidos: {', '.join(_VALID_MAESTRA_SLUGS)}."
            ),
        ) from None


async def _html_or_404(content: str, *, label: str, nregistro: str) -> str:
    """Wrap a possibly-empty doc body in a friendly 404 if upstream returned nothing."""
    if not content or not content.strip():
        raise OperationError(
            404,
            error=f"{label} no disponible",
            message=(
                f"AEMPS no publica {label.lower()} para el nregistro '{nregistro}'. "
                "Verifique el número de registro o consulte la presentación "
                "directamente en https://cima.aemps.es/."
            ),
        )
    return content


# ---------------------------------------------------------------------------
# Static resources — full maestras (one URI per maestra)
# ---------------------------------------------------------------------------


async def _maestra_full(slug: str) -> str:
    """Fetch the full content of one maestra and serialise to JSON."""
    maestra_id = MAESTRA_SLUG_TO_ID[slug]
    payload: dict[str, Any] = await core_consultar_maestras(maestra=maestra_id, pagina=1)
    # Page beyond first if upstream paginates (CIMA paginates at 100 by default).
    items: list[Any] = list(payload.get("data", []))
    page = 2
    total = payload.get("metadata", {}).get("total_filas") or 0
    while len(items) < total and page <= 50:  # 50 * 100 = 5000 cap
        next_payload = await core_consultar_maestras(maestra=maestra_id, pagina=page)
        next_items = next_payload.get("data", [])
        if not next_items:
            break
        items.extend(next_items)
        page += 1
    return json.dumps(
        {
            "maestra": slug,
            "maestra_id": maestra_id,
            "total": len(items),
            "items": items,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Templates — single-item maestra lookup
# ---------------------------------------------------------------------------


async def _maestra_lookup(slug: str, key: str) -> str:
    """Look up a single maestra item by codigo (ATC) or id (others).

    ATC uses the textual ``codigo`` column; principios-activos and the
    others use a numeric ``id``. CIMA accepts both as filters
    interchangeably for lookups.
    """
    maestra_id = _maestra_url_for_codigo(slug, key)
    # ATC keys are alphanumeric (e.g. "C09AA02"); numeric maestras use id.
    filtro = {"codigo": key} if slug == "atc" else {"id": key}
    payload = await core_consultar_maestras(maestra=maestra_id, **filtro, pagina=1)
    items = payload.get("data", [])
    if not items:
        raise OperationError(
            404,
            error=f"{slug} no encontrado",
            message=f"Sin resultados en maestra '{slug}' para clave '{key}'.",
        )
    return json.dumps(
        {"maestra": slug, "key": key, "items": items},
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Templates — full document HTML (FT / Prospecto, optionally por sección)
# ---------------------------------------------------------------------------


async def _ficha_tecnica_full(nregistro: str) -> str:
    body = await core_html_ficha_tecnica(nregistro=nregistro)
    return await _html_or_404(body, label="Ficha técnica", nregistro=nregistro)


async def _ficha_tecnica_seccion(nregistro: str, seccion: str) -> str:
    payload = await core_html_ficha_tecnica_multiple(nregistro=[nregistro])
    item = (payload.get("data") or [{}])[0]
    body = item.get("html", "") if isinstance(item, dict) else ""
    return await _html_or_404(body, label=f"Ficha técnica sección {seccion}", nregistro=nregistro)


async def _prospecto_full(nregistro: str) -> str:
    body = await core_html_prospecto(nregistro=nregistro)
    return await _html_or_404(body, label="Prospecto", nregistro=nregistro)


async def _prospecto_seccion(nregistro: str, seccion: str) -> str:
    payload = await core_html_prospecto_multiple(nregistro=[nregistro])
    item = (payload.get("data") or [{}])[0]
    body = item.get("html", "") if isinstance(item, dict) else ""
    return await _html_or_404(body, label=f"Prospecto sección {seccion}", nregistro=nregistro)


# ---------------------------------------------------------------------------
# Templates — single medicamento / presentacion lookup (v0.3.0 batch 3 item 7)
#
# Same payload as the matching tool (``obtener_medicamento`` /
# ``obtener_presentacion``) but exposed under the ``cima://`` URI scheme
# so clients can: (a) cache per-CN/per-nregistro without re-paying the
# tool-call token cost, (b) lazy-resolve hits returned by search tools
# (``buscar_medicamentos`` etc.) without inlining each full record into
# the conversation context.
# ---------------------------------------------------------------------------


async def _medicamento_lookup(nregistro: str) -> str:
    payload = await core_obtener_medicamento(nregistro=nregistro)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


async def _presentacion_lookup(cn: str) -> str:
    payload = await core_obtener_presentacion(cn=[cn])
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# Public API — register every resource onto a FastMCP server
# ---------------------------------------------------------------------------


def register_resources(server: FastMCP) -> None:
    """Wire all curated resources onto a FastMCP server instance.

    Called once from ``app.stdio_server.build_server()``. Both transports
    (stdio + Streamable HTTP at ``/mcp``) pick up the resources
    automatically because they share the same FastMCP instance.
    """

    # ---- Static maestras (auto-discoverable in resources/list) ----
    @server.resource(
        "cima://maestras/atc",
        name="Maestra ATC completa",
        description=(
            "Árbol completo de códigos ATC (Anatómico-Terapéutico-Químico) "
            "registrados en CIMA. Cacheable de forma agresiva — los códigos "
            "ATC cambian raramente."
        ),
        mime_type="application/json",
    )
    async def maestra_atc() -> str:
        return await _maestra_full("atc")

    @server.resource(
        "cima://maestras/principios-activos",
        name="Maestra de principios activos",
        description=(
            "Listado completo de principios activos (con sus códigos AEMPS) "
            "presentes en medicamentos autorizados en España."
        ),
        mime_type="application/json",
    )
    async def maestra_principios_activos() -> str:
        return await _maestra_full("principios-activos")

    @server.resource(
        "cima://maestras/laboratorios",
        name="Maestra de laboratorios titulares",
        description="Listado completo de laboratorios titulares de autorización en AEMPS.",
        mime_type="application/json",
    )
    async def maestra_laboratorios() -> str:
        return await _maestra_full("laboratorios")

    @server.resource(
        "cima://maestras/formas-farmaceuticas",
        name="Maestra de formas farmacéuticas",
        description="Listado completo de formas farmacéuticas (comprimido, jarabe, inyectable, …).",
        mime_type="application/json",
    )
    async def maestra_formas_farmaceuticas() -> str:
        return await _maestra_full("formas-farmaceuticas")

    @server.resource(
        "cima://maestras/vias-administracion",
        name="Maestra de vías de administración",
        description="Listado completo de vías de administración (oral, intravenosa, tópica, …).",
        mime_type="application/json",
    )
    async def maestra_vias_administracion() -> str:
        return await _maestra_full("vias-administracion")

    # ---- Templates — single-item maestra lookup ----
    @server.resource(
        "cima://maestras/atc/{codigo}",
        name="ATC por código",
        description=(
            "Busca un código ATC concreto (p.ej. C09AA02 para Enalapril) y "
            "devuelve la entrada con su nombre y nivel jerárquico."
        ),
        mime_type="application/json",
    )
    async def atc_por_codigo(codigo: str) -> str:
        return await _maestra_lookup("atc", codigo)

    @server.resource(
        "cima://maestras/principios-activos/{id}",
        name="Principio activo por id",
        description="Busca un principio activo por su id numérico AEMPS.",
        mime_type="application/json",
    )
    async def principio_activo_por_id(id: str) -> str:
        return await _maestra_lookup("principios-activos", id)

    # ---- Templates — documentos (FT y Prospecto) ----
    @server.resource(
        "cima://docs/ficha-tecnica/{nregistro}",
        name="Ficha técnica completa (HTML)",
        description=(
            "HTML completo de la ficha técnica de un medicamento. Más eficiente "
            "que llamar a la herramienta `html_ficha_tecnica` cuando solo "
            "necesitas mostrar el documento al usuario — los clientes que "
            "soportan recursos lo cachean automáticamente."
        ),
        mime_type="text/html",
    )
    async def ficha_tecnica(nregistro: str) -> str:
        return await _ficha_tecnica_full(nregistro)

    @server.resource(
        "cima://docs/ficha-tecnica/{nregistro}/{seccion}",
        name="Ficha técnica por sección",
        description=(
            "Sección concreta de la ficha técnica (4.1=Indicaciones, "
            "4.2=Posología, 4.3=Contraindicaciones, 4.4=Advertencias, "
            "4.5=Interacciones, 4.6=Embarazo y lactancia, 4.7=Conducción, "
            "4.8=Reacciones adversas, 5.1=Farmacodinámica, …). Útil para "
            "streaming de fragmentos pequeños sin descargar el HTML completo."
        ),
        mime_type="text/html",
    )
    async def ficha_tecnica_seccion(nregistro: str, seccion: str) -> str:
        return await _ficha_tecnica_seccion(nregistro, seccion)

    @server.resource(
        "cima://docs/prospecto/{nregistro}",
        name="Prospecto completo (HTML)",
        description=("HTML completo del prospecto de un medicamento (versión paciente)."),
        mime_type="text/html",
    )
    async def prospecto(nregistro: str) -> str:
        return await _prospecto_full(nregistro)

    @server.resource(
        "cima://docs/prospecto/{nregistro}/{seccion}",
        name="Prospecto por sección",
        description=(
            "Sección concreta del prospecto (1=Qué es, 2=Para qué se usa, "
            "3=Antes de tomarlo, 4=Cómo tomarlo, 5=Efectos adversos, "
            "6=Conservación). Lenguaje llano para pacientes."
        ),
        mime_type="text/html",
    )
    async def prospecto_seccion(nregistro: str, seccion: str) -> str:
        return await _prospecto_seccion(nregistro, seccion)

    # ---- Templates — medicamento / presentación por identificador ----
    @server.resource(
        "cima://medicamento/{nregistro}",
        name="Medicamento por nregistro",
        description=(
            "Ficha completa de un medicamento por número de registro AEMPS. "
            "Mismo payload que `obtener_medicamento(nregistro=...)`, expuesto "
            "como recurso para que los clientes lo cacheen y lo resuelvan "
            "perezosamente desde resultados de búsqueda."
        ),
        mime_type="application/json",
    )
    async def medicamento_por_nregistro(nregistro: str) -> str:
        return await _medicamento_lookup(nregistro)

    @server.resource(
        "cima://presentacion/{cn}",
        name="Presentación por CN",
        description=(
            "Detalle de una presentación por Código Nacional. Mismo payload "
            "que `obtener_presentacion(cn=[<CN>])`, expuesto como recurso "
            "para resolución perezosa y cacheo per-CN."
        ),
        mime_type="application/json",
    )
    async def presentacion_por_cn(cn: str) -> str:
        return await _presentacion_lookup(cn)


# ---------------------------------------------------------------------------
# Catalogue introspection (used by tests + README docs generator)
# ---------------------------------------------------------------------------

STATIC_RESOURCE_URIS = (
    "cima://maestras/atc",
    "cima://maestras/principios-activos",
    "cima://maestras/laboratorios",
    "cima://maestras/formas-farmaceuticas",
    "cima://maestras/vias-administracion",
)

RESOURCE_TEMPLATES = (
    "cima://maestras/atc/{codigo}",
    "cima://maestras/principios-activos/{id}",
    "cima://docs/ficha-tecnica/{nregistro}",
    "cima://docs/ficha-tecnica/{nregistro}/{seccion}",
    "cima://docs/prospecto/{nregistro}",
    "cima://docs/prospecto/{nregistro}/{seccion}",
    "cima://medicamento/{nregistro}",
    "cima://presentacion/{cn}",
)
