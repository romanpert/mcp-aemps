"""Pydantic response models for the 21 CIMA tools.

Spec ref: server/tools §"Output Schema" + Anthropic client-best-practices
("the real fix is for server authors to provide outputSchema"). Adding
typed envelopes lets code-mode hosts (Claude Code, Codex CLI) navigate
``response.metadata`` / ``response.resultados`` / ``response.errors``
without re-extracting fields from a generic ``dict[str, Any]``.

Design notes:

* ``extra='allow'`` on every model — upstream CIMA payloads carry many
  fields we don't want to enumerate exhaustively (each medicamento has
  ~40+ keys). Declared fields are the navigation skeleton; everything
  else rides through.
* Optional defaults instead of empty containers — so absent fields don't
  appear as ``[]`` / ``{}`` in ``structuredContent``. FastMCP runs
  ``model.model_dump(mode='json')`` after validating, so every declared
  field shows up; ``None`` values are kept but at least they signal
  "absent" rather than "empty".
* No required fields — tool output is *envelope-shape*, never the schema
  contract. The runtime dict from ``helpers.format_response`` always
  satisfies these models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CimaMetadataBlock(BaseModel):
    """The ``metadata`` block injected by ``helpers._build_metadata`` into
    every CIMA tool response. Declares the stable keys; CIMA endpoints
    that add their own metadata flow through ``extra='allow'``."""

    model_config = ConfigDict(extra="allow")

    fuente: str | None = None
    fecha_consulta: str | None = None
    parametros_busqueda: dict[str, Any] | None = None
    version_api: str | None = None
    descargo_responsabilidad: dict[str, Any] | None = None


class CimaResponse(BaseModel):
    """Generic envelope returned by single-item CIMA tools. The upstream
    payload is preserved verbatim (extra keys); only the outer
    ``metadata`` block is typed."""

    model_config = ConfigDict(extra="allow")

    metadata: CimaMetadataBlock | None = None


class CimaPaginatedResponse(CimaResponse):
    """Envelope for tools that mirror CIMA's paginated GET endpoints:
    ``/medicamentos``, ``/presentaciones``, ``/vmpp``, ``/maestras``,
    ``/registroCambios``."""

    totalFilas: int | None = None
    pagina: int | None = None
    tamanioPagina: int | None = None
    resultados: list[dict[str, Any]] | None = None


class CimaCollectionResponse(CimaResponse):
    """Envelope for batch / fan-out tools that return a per-key payload
    plus optional error map: ``listar_notas`` / ``listar_materiales`` /
    ``obtener_presentacion`` / ``problemas_suministro`` (CN mode) /
    ``html_ficha_tecnica_multiple`` / ``html_prospecto_multiple``."""

    data: dict[str, Any] | list[Any] | None = None
    errors: dict[str, Any] | None = None
    errors_cn: dict[str, Any] | None = None
    errors_nregistro: dict[str, Any] | None = None


class DocContenidoResponse(BaseModel):
    """``doc_contenido`` is the union outlier: ``format=json`` returns a
    full CIMA envelope; ``format=html`` / ``format=txt`` returns the raw
    document body. The stdio wrapper normalises both into this shape so
    downstream hosts get a stable ``structuredContent``."""

    model_config = ConfigDict(extra="allow")

    content: str | None = None
    media_type: str | None = None
    metadata: CimaMetadataBlock | None = None


__all__ = [
    "CimaCollectionResponse",
    "CimaMetadataBlock",
    "CimaPaginatedResponse",
    "CimaResponse",
    "DocContenidoResponse",
]
