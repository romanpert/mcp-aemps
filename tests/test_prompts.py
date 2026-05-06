"""Tests for the curated MCP Prompt catalogue (app/prompts.py).

Pins:
* The exact set of 10 prompts is exposed (drift = explicit decision).
* Required vs optional args match the function signature.
* Each prompt body returns a non-empty user message that mentions at
  least one mcp-aemps tool by name (otherwise the prompt is just chat,
  not an orchestration template).
* Patient-facing prompts include the "no es consejo médico" disclaimer.
* Edge-case validation: empty list / >max list → returns an explicit
  error string instead of crashing FastMCP.
"""

from __future__ import annotations

import asyncio

import pytest

from app.prompts import (
    ALL_PROMPTS,
    PATIENT_FACING_DISCLAIMER,
    auditar_cartera_laboratorio,
    comparar_fichas_tecnicas,
    comprobar_interaccion_principios_activos,
    equivalencias_genericas,
    identificar_cn,
    info_medicamento_para_no_sanitarios,
    informe_posicionamiento_terapeutico,
    material_visual_paciente,
    monitorizar_cambios_cartera,
    vigilancia_paciente,
)
from app.stdio_server import build_server

EXPECTED_PROMPTS = {
    "identificar_cn",
    "equivalencias_genericas",
    "vigilancia_paciente",
    "comparar_fichas_tecnicas",
    "auditar_cartera_laboratorio",
    "monitorizar_cambios_cartera",
    "informe_posicionamiento_terapeutico",
    "material_visual_paciente",
    "info_medicamento_para_no_sanitarios",
    "comprobar_interaccion_principios_activos",
}

# Prompts that hand information to a non-clinician user must close with the
# explicit disclaimer. Adding a new patient-facing prompt without it = test fails.
PATIENT_FACING = {
    "info_medicamento_para_no_sanitarios",
    "material_visual_paciente",
    "comprobar_interaccion_principios_activos",
}


# ---------------------------------------------------------------------------
# Catalogue invariants
# ---------------------------------------------------------------------------


def test_all_prompts_registered_on_stdio_server() -> None:
    """The exact set of 10 prompts ships on the stdio MCP transport."""
    server = build_server()
    prompts = asyncio.run(server.list_prompts())
    names = {p.name for p in prompts}
    missing = EXPECTED_PROMPTS - names
    extra = names - EXPECTED_PROMPTS
    assert not missing, f"prompts missing from stdio surface: {missing}"
    assert not extra, f"unexpected prompts on stdio surface (drift): {extra}"


def test_all_prompts_module_exports_match_registered() -> None:
    """ALL_PROMPTS tuple in app/prompts.py is the single source of truth."""
    declared = {name for name, _description, _fn in ALL_PROMPTS}
    assert declared == EXPECTED_PROMPTS


def test_every_prompt_has_a_substantive_description() -> None:
    """LLMs pick prompts off descriptions — short = ambiguous = wrong choice."""
    for name, description, _fn in ALL_PROMPTS:
        assert len(description) >= 80, f"{name}: description too short ({len(description)} chars)"
        # Must mention the use case ("Caso de uso" idiom) so the LLM can route.
        assert "Caso de uso" in description, f"{name}: missing 'Caso de uso' framing"


# ---------------------------------------------------------------------------
# Per-prompt arg schema and body
# ---------------------------------------------------------------------------


def _required_args(name: str) -> set[str]:
    server = build_server()
    prompts = asyncio.run(server.list_prompts())
    p = next(p for p in prompts if p.name == name)
    return {a.name for a in (p.arguments or []) if a.required}


def test_required_args_per_prompt() -> None:
    """The required-arg surface is the public contract — clients build forms
    from this. Pinning prevents accidental backwards-incompat changes."""
    expected = {
        "identificar_cn": {"cn"},
        "equivalencias_genericas": {"nregistro"},
        "vigilancia_paciente": {"nregistros"},
        "comparar_fichas_tecnicas": {"nregistros"},
        "auditar_cartera_laboratorio": {"laboratorio"},
        "monitorizar_cambios_cartera": {"nregistros"},
        "informe_posicionamiento_terapeutico": {"nregistro"},
        "material_visual_paciente": {"nregistro"},
        "info_medicamento_para_no_sanitarios": {"nombre_o_cn"},
        "comprobar_interaccion_principios_activos": {"principios_activos"},
    }
    for name, required in expected.items():
        assert _required_args(name) == required, f"{name}: required args drift"


@pytest.mark.parametrize(
    "fn, kwargs, must_mention_tool",
    [
        (identificar_cn, {"cn": "12345"}, "obtener_presentacion"),
        (equivalencias_genericas, {"nregistro": "12345"}, "buscar_medicamentos"),
        (vigilancia_paciente, {"nregistros": ["12345", "67890"]}, "listar_notas"),
        (
            comparar_fichas_tecnicas,
            {"nregistros": ["111", "222"]},
            "doc_contenido",
        ),
        (auditar_cartera_laboratorio, {"laboratorio": "Bayer"}, "buscar_medicamentos"),
        (
            monitorizar_cambios_cartera,
            {"nregistros": ["111", "222"]},
            "registro_cambios",
        ),
        (informe_posicionamiento_terapeutico, {"nregistro": "12345"}, "obtener_medicamento"),
        (material_visual_paciente, {"nregistro": "12345"}, "obtener_medicamento"),
        (info_medicamento_para_no_sanitarios, {"nombre_o_cn": "ibuprofeno"}, "buscar_medicamentos"),
        (
            comprobar_interaccion_principios_activos,
            {"principios_activos": ["warfarina", "amiodarona"]},
            "buscar_en_ficha_tecnica",
        ),
    ],
)
def test_each_prompt_orchestrates_at_least_one_tool(fn, kwargs, must_mention_tool) -> None:
    """Every prompt body must reference the relevant mcp-aemps tool by name —
    otherwise the LLM has nothing to act on."""
    body = asyncio.run(fn(**kwargs))
    assert body, "prompt body is empty"
    assert must_mention_tool in body, f"{fn.__name__}: body must reference tool {must_mention_tool!r}"
    # Every prompt must end with a real instruction, not a placeholder.
    assert len(body) > 300, f"{fn.__name__}: body suspiciously short ({len(body)} chars)"


# ---------------------------------------------------------------------------
# Patient-facing safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn, kwargs",
    [
        (material_visual_paciente, {"nregistro": "12345"}),
        (info_medicamento_para_no_sanitarios, {"nombre_o_cn": "aspirina"}),
        (
            comprobar_interaccion_principios_activos,
            {"principios_activos": ["warfarina", "amiodarona"]},
        ),
    ],
)
def test_patient_facing_prompts_carry_the_disclaimer(fn, kwargs) -> None:
    """Patient-facing prompts MUST close with the no-clinical-advice disclaimer.
    Removing it is a regulatory regression (MDR 2017/745 framing — this server
    is not a medical device)."""
    body = asyncio.run(fn(**kwargs))
    assert PATIENT_FACING_DISCLAIMER.strip() in body, (
        f"{fn.__name__}: missing patient-facing disclaimer block"
    )
    # The exact phrase that must be present (compliance team will grep for it).
    assert "consulte a su médico o farmacéutico" in body, (
        f"{fn.__name__}: must include explicit referral language"
    )


def test_patient_facing_set_is_pinned() -> None:
    """If you mark a prompt as patient-facing, the disclaimer test catches you.
    If you forget to mark a new patient-facing prompt — this list will rot.
    Update PATIENT_FACING in this file when adding any new patient prompt."""
    # Sanity: the marked patient-facing prompts must actually be in the catalogue.
    for name in PATIENT_FACING:
        assert name in EXPECTED_PROMPTS, f"PATIENT_FACING entry {name} not in catalogue"


# ---------------------------------------------------------------------------
# Edge-case input validation (defensive — the LLM passes whatever)
# ---------------------------------------------------------------------------


def test_vigilancia_paciente_rejects_empty_list() -> None:
    body = asyncio.run(vigilancia_paciente(nregistros=[]))
    assert body.startswith("Error:"), "empty list must return explicit error"


def test_comparar_fichas_tecnicas_rejects_too_few() -> None:
    body = asyncio.run(comparar_fichas_tecnicas(nregistros=["12345"]))
    assert body.startswith("Error:"), "<2 nregistros must return explicit error"


def test_comparar_fichas_tecnicas_rejects_too_many() -> None:
    body = asyncio.run(comparar_fichas_tecnicas(nregistros=["1", "2", "3", "4", "5", "6"]))
    assert body.startswith("Error:"), ">5 nregistros must return explicit error"


def test_monitorizar_cambios_cartera_rejects_too_many() -> None:
    body = asyncio.run(monitorizar_cambios_cartera(nregistros=[str(i) for i in range(51)]))
    assert body.startswith("Error:"), ">50 nregistros must return explicit error"


def test_comprobar_interaccion_rejects_too_few() -> None:
    body = asyncio.run(comprobar_interaccion_principios_activos(principios_activos=["warfarina"]))
    assert body.startswith("Error:"), "<2 active substances must return explicit error"


def test_comprobar_interaccion_rejects_too_many() -> None:
    body = asyncio.run(
        comprobar_interaccion_principios_activos(principios_activos=["a", "b", "c", "d", "e", "f"])
    )
    assert body.startswith("Error:"), ">5 active substances must return explicit error"


def test_comprobar_interaccion_warns_about_clinical_tools() -> None:
    """The interactions prompt is safety-critical: it MUST surface that it
    is NOT a substitute for a formal clinical interaction-checker."""
    body = asyncio.run(
        comprobar_interaccion_principios_activos(principios_activos=["warfarina", "amiodarona"])
    )
    # Expect the limitations block to mention at least one canonical clinical tool.
    canonical_tools = ("BOT PLUS", "Lexicomp", "Stockley", "Micromedex")
    assert any(t in body for t in canonical_tools), (
        "interactions prompt must reference a formal clinical interaction-checking tool"
    )


def test_monitorizar_cambios_cartera_rejects_empty() -> None:
    body = asyncio.run(monitorizar_cambios_cartera(nregistros=[]))
    assert body.startswith("Error:"), "empty list must return explicit error"
