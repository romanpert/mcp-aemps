"""Transport-agnostic operation handlers.

Each ``core_<op>`` function is the single source of truth for an MCP tool.
HTTP routes (FastAPI) and stdio tools (FastMCP) are thin adapters that
parse parameters, call the matching ``core_<op>``, and translate
``OperationError`` into the transport's native error shape.

Adding a new tool means: implement one async function here, expose it on
both transports. No more drift, no more duplicated business logic.
"""

from app.core.base import OperationError, safe_call
from app.core.schemas import (
    CimaCollectionResponse,
    CimaMetadataBlock,
    CimaPaginatedResponse,
    CimaResponse,
    DocContenidoResponse,
)
from app.core.documentos import (
    core_doc_contenido,
    core_doc_secciones,
    core_html_ficha_tecnica,
    core_html_ficha_tecnica_multiple,
    core_html_prospecto,
    core_html_prospecto_multiple,
)
from app.core.medicamentos import (
    core_buscar_en_ficha_tecnica,
    core_buscar_medicamentos,
    core_buscar_vmpp,
    core_consultar_maestras,
    core_listar_presentaciones,
    core_obtener_medicamento,
    core_obtener_presentacion,
)
from app.core.vigilancia import (
    core_listar_materiales,
    core_listar_notas,
    core_obtener_materiales,
    core_obtener_notas,
    core_problemas_suministro,
    core_problemas_suministro_dcp,
    core_problemas_suministro_dcpf,
    core_registro_cambios,
)

__all__ = [
    "OperationError",
    "safe_call",
    # response schemas (v0.3.0 batch 3)
    "CimaResponse",
    "CimaPaginatedResponse",
    "CimaCollectionResponse",
    "CimaMetadataBlock",
    "DocContenidoResponse",
    # medicamentos
    "core_obtener_medicamento",
    "core_buscar_medicamentos",
    "core_buscar_en_ficha_tecnica",
    "core_listar_presentaciones",
    "core_obtener_presentacion",
    "core_buscar_vmpp",
    "core_consultar_maestras",
    # documentos
    "core_doc_secciones",
    "core_doc_contenido",
    "core_html_ficha_tecnica",
    "core_html_ficha_tecnica_multiple",
    "core_html_prospecto",
    "core_html_prospecto_multiple",
    # vigilancia
    "core_registro_cambios",
    "core_problemas_suministro",
    "core_problemas_suministro_dcp",
    "core_problemas_suministro_dcpf",
    "core_listar_notas",
    "core_obtener_notas",
    "core_listar_materiales",
    "core_obtener_materiales",
]
