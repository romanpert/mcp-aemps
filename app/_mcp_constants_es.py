"""LLM-facing descriptions and display titles for every MCP tool.

Single source of truth (Spanish). Imported by both transports:
- ``app.stdio_server`` (FastMCP ``@server.tool(title=..., description=...)``)
- ``app.routes.*``      (FastAPI ``@router.get(..., summary=..., description=...)``)

Style guide (per CLAUDE.md "MCP Tool Design Principles"):
1. ≤ 2 sentences of body. Parameter detail belongs in the JSON inputSchema
   (auto-derived from the function signature) — do not duplicate it here.
2. One ``Fuente:`` line citing the upstream endpoint.
3. One ``Limitacion:`` line stating the scope.
4. Long examples (JSON snippets, exhaustive enum tables) live in prompts
   or in the README, never in the tool description (item 10 of the
   2026-Q2 audit — descriptions are loaded upfront by every host).
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

# ---------------------------------------------------------------------------
# Tool annotations — uniform across all 21 official CIMA tools
# ---------------------------------------------------------------------------
# CIMA is a public, read-only registry. Every mcp-aemps tool is therefore:
#   * read-only (no writes upstream — we are a thin proxy);
#   * non-destructive (no environment mutations of any kind);
#   * idempotent (same args at the same instant return the same payload —
#     CIMA versions its records, so call-twice == call-once for state);
#   * open-world (we hit an external HTTP API outside our process).
READ_ONLY_AEMPS_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


# ---------------------------------------------------------------------------
# Display titles — human-friendly labels shown in client pickers
# ---------------------------------------------------------------------------
# Spec ref: tools §205. ``title`` is the localised display name; ``name``
# stays stable for code. Claude Desktop, Inspector and Continue render the
# title in their tool pickers when present.
TOOL_TITLES: dict[str, str] = {
    "obtener_medicamento": "Obtener medicamento",
    "buscar_medicamentos": "Buscar medicamentos",
    "buscar_en_ficha_tecnica": "Buscar en ficha tecnica",
    "listar_presentaciones": "Listar presentaciones",
    "obtener_presentacion": "Obtener presentacion",
    "buscar_vmpp": "Buscar VMP / VMPP",
    "consultar_maestras": "Consultar maestras",
    "registro_cambios": "Registro de cambios",
    "problemas_suministro": "Problemas de suministro",
    "problemas_suministro_dcp": "Problemas de suministro (DCP)",
    "problemas_suministro_dcpf": "Problemas de suministro (DCPF)",
    "listar_notas": "Listar notas de seguridad",
    "obtener_notas": "Obtener notas (alias)",
    "listar_materiales": "Listar materiales informativos",
    "obtener_materiales": "Obtener materiales (alias)",
    "doc_secciones": "Secciones de documento",
    "doc_contenido": "Contenido de seccion",
    "html_ficha_tecnica": "HTML ficha tecnica",
    "html_ficha_tecnica_multiple": "HTML ficha tecnica (multiple)",
    "html_prospecto": "HTML prospecto",
    "html_prospecto_multiple": "HTML prospecto (multiple)",
    "get_system_info_prompt": "Prompt del sistema",
}


# ---------------------------------------------------------------------------
# System prompt — agent-level guidance
# ---------------------------------------------------------------------------
MCP_AEMPS_SYSTEM_PROMPT = """\
Eres un **agente regulatorio farmaceutico** con acceso a la API CIMA de la
Agencia Espanola de Medicamentos y Productos Sanitarios (AEMPS). Las
herramientas exponen exclusivamente **datos publicos** del registro de
medicamentos autorizados en Espana — nunca datos clinicos ni de pacientes.

Fuentes oficiales:
- CIMA REST API v1.23 (medicamentos, presentaciones, VMP/VMPP, maestras,
  registro de cambios, documentos segmentados, notas, materiales).
- CIMA Problemas de Suministro v1.01 (psuministro v2: por CN, DCP, DCPF y
  listado global).

# Catalogo de herramientas

## 1. Medicamento concreto
- `obtener_medicamento(cn|nregistro)` → ficha completa de UN medicamento
  identificado por Codigo Nacional (CN) o numero de registro AEMPS.
- `buscar_medicamentos(...filtros...)` → listado paginado con filtros
  regulatorios (>20 filtros: principio activo, ATC, laboratorio, flags
  triangulo/huerfano/biosimilar/comerc/receta/estupefaciente/psicotropo,
  etc.). Usalo cuando NO conoces el CN/nregistro.
- `buscar_en_ficha_tecnica(reglas)` → busqueda textual dentro de
  secciones 1..10 de la ficha tecnica. Devuelve la lista de medicamentos
  que cumplen TODAS las reglas (`contiene=1` exige presencia,
  `contiene=0` exige ausencia).

## 2. Presentaciones / equivalentes
- `listar_presentaciones(...)` → listado paginado de presentaciones por
  CN, nregistro, VMP, VMPP o principio activo.
- `obtener_presentacion(cn=[...])` → detalle por CN. Acepta varios
  CN — paraleliza llamadas al endpoint oficial single-CN.
- `buscar_vmpp(...)` → equivalentes clinicos VMP/VMPP filtrables por
  principio activo, dosis, forma, ATC, nombre. `modoArbol=1` devuelve
  jerarquia.

## 3. Catalogos
- `consultar_maestras(maestra=...)` → tablas oficiales: 1=ppio activo,
  3=forma, 4=via, 6=laboratorio, 7=ATC, 11/13/14=SNOMED equivalentes,
  15=medicamentos, 16=medicamentos comercializados (SNOMED).

## 4. Cambios y vigilancia
- `registro_cambios(fecha, nregistro)` → altas (tipoCambio=1), bajas (2),
  modificaciones (3) desde una fecha (formato `dd/mm/yyyy`). Cada cambio
  incluye etiquetas: `estado`, `comerc`, `prosp`, `ft`, `psum`,
  `notasSeguridad`, `matinf`, `otros`.
- `listar_notas(nregistro=[...])` → notas de seguridad publicadas por la
  AEMPS para uno o varios registros.
- `listar_materiales(nregistro=[...])` → materiales informativos para
  pacientes / profesionales sanitarios.

## 5. Problemas de suministro (psuministro v2)
- `problemas_suministro(cn=[...]|nregistro=[...]|vacio)` → si vacio,
  listado paginado global; si CN, detalle por presentacion (incluye
  `tipoProblemaSuministro` 1..9, fechas inicio/fin, `activo`,
  observaciones). Si solo das `nregistro`, el wrapper lo resuelve a CNs.
- `problemas_suministro_dcp(cod_dcp)` → numero de presentaciones
  comercializadas y con problema activo para un DCP.
- `problemas_suministro_dcpf(cod_dcpf)` → idem para DCPF.

## 6. Documentos
- `doc_secciones(tipo_doc, nregistro|cn)` → metadatos de secciones de
  ficha tecnica (tipo_doc=1) o prospecto (tipo_doc=2). Tambien admite
  3=Informe Publico de Evaluacion y 4=Plan de Gestion de Riesgos.
- `doc_contenido(tipo_doc, nregistro|cn, seccion?, format=json|html|txt)`
  → contenido de la seccion solicitada (o todas si se omite).
- `html_ficha_tecnica(nregistro)` / `html_prospecto(nregistro)` →
  HTML completo (sin trocear en secciones).

# Flujo recomendado

1. Si el usuario da un CN o nregistro → `obtener_medicamento` y, si pide
   detalle de presentacion o suministro, `obtener_presentacion` /
   `problemas_suministro`.
2. Si el usuario describe el medicamento → `buscar_medicamentos`
   (filtros) o `buscar_vmpp` (equivalentes clinicos).
3. Si pregunta por contenido textual de la ficha → primero
   `buscar_en_ficha_tecnica` (filtra por contenido), luego
   `doc_contenido` (lee la seccion concreta).
4. Para alertas regulatorias → `listar_notas` (seguridad) y
   `registro_cambios` (modificaciones recientes).
5. Para suministro: por CN siempre que sea posible; usa DCP/DCPF solo
   si trabajas con codigos clinicos.

# Pautas para las respuestas

- Resume siempre dosis, forma farmaceutica, via, estado comercial,
  fechas relevantes y alertas asociadas.
- Cita la fuente: "Datos: AEMPS CIMA" + URL oficial cuando proceda.
- Indica la fecha de extraccion ("Datos extraidos el dd/mm/yyyy").
- Cierra cada respuesta con el descargo de responsabilidad:
  > Esta informacion no constituye consejo medico; se proporciona unicamente a efectos informativos. Datos publicados por la AEMPS.
- Nunca emitas recomendaciones clinicas, diagnostico o prescripcion.
- Si falta un parametro obligatorio, devuelve un mensaje claro y para
  la ejecucion.
"""

# ---------------------------------------------------------------------------
# Per-tool descriptions — short by design (≤ 2 sentences body + Fuente +
# Limitacion). Parameter shape is in the JSON inputSchema; long examples
# live in prompts. Trimmed in v0.3.0 (audit 2026-Q2 item 10).
# ---------------------------------------------------------------------------

medicamento_description = """\
Devuelve la ficha completa de UN medicamento autorizado por la AEMPS,
identificado por CN o `nregistro` (al menos uno obligatorio).

Cuando usar: ya conoces el CN/nregistro y necesitas la ficha estructurada.
Si no lo conoces, usa `buscar_medicamentos`.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamento`.
Limitacion: solo medicamentos autorizados en Espana.
"""

medicamentos_description = """\
Listado paginado de medicamentos autorizados que cumplen los filtros
indicados (nombre, principio activo, ATC, laboratorio, flags
regulatorios: triangulo, huerfano, biosimilar, comerc, etc.).

Cuando usar: NO conoces el CN/nregistro y necesitas localizar
medicamentos por atributos.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamentos`.
Limitacion: solo medicamentos autorizados en Espana; resultados paginados.
"""

buscar_ficha_tecnica_description = """\
Busqueda textual sobre secciones de la ficha tecnica. Cada regla
`{seccion, texto, contiene}` filtra por presencia (`contiene=1`) o
ausencia (`contiene=0`); devuelve medicamentos que cumplen TODAS.

Cuando usar: localizar medicamentos por contenido de su ficha tecnica
(p.ej. seccion 4.1 con "cancer" y sin "estomago").

Fuente: AEMPS CIMA REST API v1.23 — `POST /cima/rest/buscarEnFichaTecnica`.
Limitacion: secciones 1..10 (estructura oficial CIMA).
"""

presentaciones_description = """\
Listado paginado de presentaciones (formato + envase) de medicamentos
autorizados, filtrable por CN, nregistro, VMP/VMPP o principio activo.

Cuando usar: necesitas listar presentaciones sin saber CN, o filtrarlas
por equivalencias clinicas o estado de comercializacion.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentaciones`.
Limitacion: solo presentaciones de medicamentos autorizados.
"""

presentacion_description = """\
Detalle de una o varias presentaciones por Codigo Nacional. Acepta lista
de CN y paraleliza llamadas al endpoint oficial single-CN.

Cuando usar: ya conoces el CN y necesitas el detalle (estado,
comercializacion, problemas de suministro abiertos).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentacion/{cn}`.
Limitacion: solo presentaciones de medicamentos autorizados.
"""

vmpp_description = """\
Listado paginado de equivalentes clinicos VMP / VMPP filtrable por
principio activo, dosis, forma, ATC o nombre. `modoArbol=1` devuelve
jerarquia VMP -> VMPP.

Cuando usar: equivalencias clinicas para sustitucion o busqueda de
alternativas autorizadas.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/vmpp`.
Limitacion: solo equivalencias publicadas por AEMPS.
"""

maestras_description = """\
Catalogos maestros oficiales (`maestra` obligatorio). IDs principales:
1=ppio activo, 3=forma, 4=via, 6=laboratorio, 7=ATC, 11/13/14=SNOMED,
15/16=medicamentos.

Cuando usar: resolver / listar elementos de una tabla oficial (p.ej.
todos los codigos ATC, o el ID de un principio activo para usarlo como
`idpractiv1` en otras herramientas).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/maestras`.
"""

registro_cambios_description = """\
Historial de altas (`tipoCambio=1`), bajas (2) y modificaciones (3) de
medicamentos desde una `fecha` (`dd/mm/yyyy`) y/o para `nregistro` dado.
Cada cambio trae etiquetas: `estado`, `comerc`, `prosp`, `ft`, `psum`,
`notasSeguridad`, `matinf`, `otros`.

Cuando usar: detectar cambios regulatorios recientes.

Fuente: AEMPS CIMA REST API v1.23 — `GET/POST /cima/rest/registroCambios`.
"""

problemas_suministro_description = """\
Estado de suministro: sin parametros, snapshot global paginado; con
`cn=[...]`, detalle por presentacion (incluye `tipoProblemaSuministro`
1..9, fechas, `activo`, `observ`). Si das `nregistro`, el wrapper lo
resuelve a CNs.

Cuando usar: comprobar desabastecimientos / restricciones de suministro.

Fuente: AEMPS CIMA Problemas Suministro v1.01 — `GET /cima/rest/psuministro`
y `GET /cima/rest/psuministro/v2/cn/{cn}` (con fallback v1).
"""

problemas_suministro_dcp_description = """\
Resumen de presentaciones comercializadas y con problema activo para un
DCP (Descripcion Clinica del Producto: principio activo + dosis + forma
sin formato).

Cuando usar: trabajas con codigos clinicos DCP en lugar de Codigo
Nacional.

Fuente: AEMPS CIMA Problemas Suministro v1.01 —
`GET /cima/rest/psuministro/v2/dcp/{cod_dcp}`.
"""

problemas_suministro_dcpf_description = """\
Resumen de presentaciones comercializadas y con problema activo para un
DCPF (DCP + formato concreto). Mas especifico que DCP.

Cuando usar: trabajas con codigos clinicos DCPF.

Fuente: AEMPS CIMA Problemas Suministro v1.01 —
`GET /cima/rest/psuministro/v2/dcpf/{cod_dcpf}`.
"""

doc_secciones_description = """\
Metadatos de las secciones (numero, titulo, orden) de un documento
segmentado: 1=ficha tecnica, 2=prospecto, 3=IPE, 4=PGR. NO incluye el
contenido — usa `doc_contenido` para descargarlo.

Cuando usar: comprobar que secciones existen antes de pedir contenido,
o comparar disponibilidad entre medicamentos.

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/secciones/{tipoDoc}`.
"""

doc_contenido_description = """\
Contenido de una seccion (`N` o `N.N`, p.ej. `"4.2"`) de un documento
segmentado: 1=ficha tecnica, 2=prospecto. `format` admite `json`
(estructurado), `html` o `txt`. Si omites `seccion`, devuelve todas.

Cuando usar: ya sabes que seccion necesitas y quieres su contenido
textual.

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/contenido/{tipoDoc}`.
"""

listar_notas_description = """\
Notas de seguridad publicadas por la AEMPS para uno o varios
medicamentos. Cada nota incluye `num`, `ref`, `asunto`, `fecha` (epoch
ms) y `url` oficial.

Cuando usar: comprobar alertas / comunicados de seguridad emitidos por
AEMPS.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/notas/{nregistro}`.
"""

obtener_notas_description = listar_notas_description  # alias backward-compat

listar_materiales_description = """\
Materiales informativos asociados a uno o varios medicamentos
(documentos para pacientes y profesionales, videos formativos). Cada
elemento trae `titulo`, `listaDocsPaciente`, `listaDocsProfesional` y
opcionalmente `video`.

Cuando usar: comprobar materiales de minimizacion de riesgos o
documentacion educativa AEMPS.

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/materiales/{nregistro}`.
"""

obtener_materiales_description = listar_materiales_description  # alias

html_ft_description = """\
HTML completo de la ficha tecnica de un medicamento.

Cuando usar: necesitas el documento integro. Si solo quieres una
seccion, prefiere `doc_contenido`.

Fuente: AEMPS — `GET https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html`.
"""

html_ft_multiple_description = html_ft_description  # alias backward-compat

html_p_description = """\
HTML completo del prospecto de un medicamento.

Cuando usar: necesitas el prospecto integro. Si solo quieres una
seccion, prefiere `doc_contenido(tipo_doc=2, ...)`.

Fuente: AEMPS — `GET https://cima.aemps.es/cima/dochtml/p/{nregistro}/Prospecto.html`.
"""

html_p_multiple_description = html_p_description  # alias backward-compat

system_info_prompt_description = """\
Devuelve `MCP_AEMPS_SYSTEM_PROMPT`: catalogo de herramientas, flujos
recomendados y pautas de respuesta para un agente regulatorio
farmaceutico operando sobre AEMPS / CIMA.

Cuando usar: el cliente MCP quiere reinyectar el prompt base del
servidor (p.ej. tras una compactacion).
"""
