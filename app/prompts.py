# app/prompts.py
"""Locale-dispatched curated MCP Prompts.

This module is a thin dispatcher. The actual prompt bodies and
descriptions live in two sister modules:

* ``app/_prompts_es.py`` — Spanish (default, the original source of
  truth).
* ``app/_prompts_en.py`` — English (added in v0.2.9 to close the
  i18n story started in v0.2.8).

Both modules export the exact same public surface — ``ALL_PROMPTS``,
``PATIENT_FACING_DISCLAIMER`` and the 9 prompt functions — so this
file can switch them by simple star-import based on the active locale.

Adding a new locale: drop ``app/_prompts_<lc>.py`` exporting the same
names, then extend the dispatcher branch below.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.config import settings

if settings.mcp_aemps_locale == "en":
    from app._prompts_en import (  # noqa: F401
        ALL_PROMPTS,
        PATIENT_FACING_DISCLAIMER,
        PromptFn,
        auditar_cartera_laboratorio,
        comparar_fichas_tecnicas,
        equivalencias_genericas,
        identificar_cn,
        info_medicamento_para_no_sanitarios,
        informe_posicionamiento_terapeutico,
        material_visual_paciente,
        monitorizar_cambios_cartera,
        vigilancia_paciente,
    )
else:
    from app._prompts_es import (  # noqa: F401
        ALL_PROMPTS,
        PATIENT_FACING_DISCLAIMER,
        PromptFn,
        auditar_cartera_laboratorio,
        comparar_fichas_tecnicas,
        equivalencias_genericas,
        identificar_cn,
        info_medicamento_para_no_sanitarios,
        informe_posicionamiento_terapeutico,
        material_visual_paciente,
        monitorizar_cambios_cartera,
        vigilancia_paciente,
    )


def register_prompts(server: FastMCP) -> None:
    """Register every curated prompt onto a FastMCP server.

    Called once from ``app.stdio_server.build_server()``. Idempotent
    only at the level of one ``server`` instance — calling it twice on
    the same server raises (FastMCP rejects duplicate prompt names).

    The active language (Spanish or English) is decided at import time
    based on ``MCP_AEMPS_LOCALE``. Both locales register the same 9
    prompt names with the same arg signatures — clients that hard-code
    prompt names keep working when the operator switches language.
    """
    for name, description, fn in ALL_PROMPTS:
        server.prompt(name=name, description=description)(fn)
