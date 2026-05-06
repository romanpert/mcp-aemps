"""Tests for the curated MCP Resources catalogue (app/resources.py).

Scope: catalogue invariants + URI parsing + input validation. Actual
upstream-data correctness is covered indirectly by the existing
``app.core`` tests — resources are thin orchestrators on top of those.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core import OperationError
from app.resources import (
    MAESTRA_SLUG_TO_ID,
    RESOURCE_TEMPLATES,
    STATIC_RESOURCE_URIS,
    _maestra_url_for_codigo,
)
from app.stdio_server import build_server

# ---------------------------------------------------------------------------
# Catalogue invariants
# ---------------------------------------------------------------------------


def test_static_resources_are_all_registered() -> None:
    """The exact set of static resources matches what the module declares."""
    server = build_server()
    statics = asyncio.run(server.list_resources())
    declared = set(STATIC_RESOURCE_URIS)
    registered = {str(r.uri) for r in statics}
    missing = declared - registered
    extra = registered - declared
    assert not missing, f"declared static resources missing from server: {missing}"
    assert not extra, f"server exposes static resources not in declaration: {extra}"


def test_resource_templates_are_all_registered() -> None:
    """The exact set of templates matches the module declaration."""
    server = build_server()
    templates = asyncio.run(server.list_resource_templates())
    declared = set(RESOURCE_TEMPLATES)
    registered = {t.uriTemplate for t in templates}
    missing = declared - registered
    extra = registered - declared
    assert not missing, f"declared templates missing from server: {missing}"
    assert not extra, f"server exposes templates not in declaration: {extra}"


def test_static_resources_carry_mime_types() -> None:
    """Every static resource declares its MIME type — clients use this to
    decide how to render the body (JSON pretty-print vs HTML preview)."""
    server = build_server()
    for r in asyncio.run(server.list_resources()):
        assert r.mimeType, f"static resource {r.uri} missing MIME type"
        assert r.mimeType in {"application/json", "text/html"}, (
            f"unexpected MIME type {r.mimeType!r} on {r.uri}"
        )


def test_static_resource_uris_use_the_cima_scheme() -> None:
    """All curated resources live under the ``cima://`` URI scheme — the
    namespace mcp-aemps owns. Foreign schemes would clash with other servers."""
    for uri in STATIC_RESOURCE_URIS:
        assert uri.startswith("cima://"), f"resource {uri} not under cima:// scheme"
    for tpl in RESOURCE_TEMPLATES:
        assert tpl.startswith("cima://"), f"template {tpl} not under cima:// scheme"


# ---------------------------------------------------------------------------
# Maestra slug ↔ id mapping
# ---------------------------------------------------------------------------


def test_maestra_slug_to_id_matches_cima_spec() -> None:
    """CIMA REST API v1.23 §maestras pins the IDs — drift is a regression."""
    expected = {
        "principios-activos": 1,
        "formas-farmaceuticas": 3,
        "vias-administracion": 4,
        "laboratorios": 6,
        "atc": 7,
    }
    assert MAESTRA_SLUG_TO_ID == expected


def test_unknown_slug_raises_operation_error() -> None:
    """Bad URI parameter must surface as a clean OperationError, not a KeyError."""
    with pytest.raises(OperationError) as excinfo:
        _maestra_url_for_codigo("does-not-exist", "anything")
    assert excinfo.value.status_code == 404
    assert "does-not-exist" in (excinfo.value.message or "")


def test_known_slugs_resolve_without_error() -> None:
    """Every slug declared in the catalogue must resolve."""
    for slug in MAESTRA_SLUG_TO_ID:
        assert _maestra_url_for_codigo(slug, "irrelevant") == MAESTRA_SLUG_TO_ID[slug]


# ---------------------------------------------------------------------------
# Per-template path parameter contract
# ---------------------------------------------------------------------------


def test_templates_carry_the_expected_parameters() -> None:
    """The {var} placeholders are the public contract for client-side
    URI templating. Renaming or adding/removing a placeholder is a
    breaking change."""
    expected_params = {
        "cima://maestras/atc/{codigo}": {"codigo"},
        "cima://maestras/principios-activos/{id}": {"id"},
        "cima://docs/ficha-tecnica/{nregistro}": {"nregistro"},
        "cima://docs/ficha-tecnica/{nregistro}/{seccion}": {"nregistro", "seccion"},
        "cima://docs/prospecto/{nregistro}": {"nregistro"},
        "cima://docs/prospecto/{nregistro}/{seccion}": {"nregistro", "seccion"},
    }
    import re

    for tpl in RESOURCE_TEMPLATES:
        params = set(re.findall(r"\{([^}]+)\}", tpl))
        assert params == expected_params[tpl], f"{tpl}: param drift, got {params}"
