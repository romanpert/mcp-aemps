"""LLM-facing descriptions for every MCP tool exposed by mcp-aemps.

This module is a **locale dispatcher**. The actual content lives in
``app/_mcp_constants_es.py`` (Spanish, the original source of truth) and
``app/_mcp_constants_en.py`` (English). The active locale is selected by
the ``MCP_AEMPS_LOCALE`` env var (``es`` default, ``en`` available).

Public names re-exported for both transports (FastMCP stdio + FastAPI HTTP):

* ``READ_ONLY_AEMPS_ANNOTATIONS`` — tool annotations (locale-independent).
* ``MCP_AEMPS_SYSTEM_PROMPT`` — agent-level system prompt.
* ``TOOL_TITLES`` — display names per tool (spec tools §205 ``title``).
* 21 ``<name>_description`` constants — one per official CIMA tool.
* ``system_info_prompt_description`` — describes the meta-prompt route.

Adding a new locale: drop ``app/_mcp_constants_<lc>.py`` exporting the
exact same names, then extend the dispatcher branch below.
"""

from __future__ import annotations

# READ_ONLY_AEMPS_ANNOTATIONS is identical across locales — keep it here so
# importers don't have to round-trip through a locale module just for tool
# annotations.
from app._mcp_constants_es import READ_ONLY_AEMPS_ANNOTATIONS  # noqa: F401
from app.config import settings

if settings.mcp_aemps_locale == "en":
    from app._mcp_constants_en import (  # noqa: F401
        MCP_AEMPS_SYSTEM_PROMPT,
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
        system_info_prompt_description,
        vmpp_description,
    )
else:
    from app._mcp_constants_es import (  # noqa: F401
        MCP_AEMPS_SYSTEM_PROMPT,
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
        system_info_prompt_description,
        vmpp_description,
    )
