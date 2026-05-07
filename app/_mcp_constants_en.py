"""English locale variant of LLM-facing descriptions and titles.

Mirrors the module-level names in ``app/_mcp_constants_es.py`` 1:1 so the
dispatcher in ``app/mcp_constants.py`` can switch between the two via
star-import. Selected through the ``MCP_AEMPS_LOCALE=en`` env var.

Translations are functional (technical and complete) — not literary.
The pharmaceutical / regulatory terminology is kept close to the
official AEMPS English wording where it exists (CIMA's English landing
page, EMA glossary). For terms with no canonical English form (DCP,
DCPF, VMP/VMPP) the Spanish acronym is preserved with an English gloss.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

# Re-exported by app.mcp_constants — kept here too so the EN module is a
# complete drop-in replacement.
READ_ONLY_AEMPS_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


# ---------------------------------------------------------------------------
# Display titles (EN) — see _mcp_constants_es.TOOL_TITLES for the contract.
# ---------------------------------------------------------------------------
TOOL_TITLES: dict[str, str] = {
    "obtener_medicamento": "Get medicine",
    "buscar_medicamentos": "Search medicines",
    "buscar_en_ficha_tecnica": "Search in SmPC",
    "listar_presentaciones": "List presentations",
    "obtener_presentacion": "Get presentation",
    "buscar_vmpp": "Search VMP / VMPP",
    "consultar_maestras": "Consult master tables",
    "registro_cambios": "Change log",
    "problemas_suministro": "Drug shortages",
    "problemas_suministro_dcp": "Drug shortages (DCP)",
    "problemas_suministro_dcpf": "Drug shortages (DCPF)",
    "listar_notas": "List safety notes",
    "obtener_notas": "Get safety notes (alias)",
    "listar_materiales": "List informational materials",
    "obtener_materiales": "Get materials (alias)",
    "doc_secciones": "Document sections",
    "doc_contenido": "Section content",
    "html_ficha_tecnica": "SmPC HTML",
    "html_ficha_tecnica_multiple": "SmPC HTML (multiple)",
    "html_prospecto": "Patient leaflet HTML",
    "html_prospecto_multiple": "Patient leaflet HTML (multiple)",
    "get_system_info_prompt": "System prompt",
}


# ---------------------------------------------------------------------------
# System prompt — agent-level guidance
# ---------------------------------------------------------------------------
MCP_AEMPS_SYSTEM_PROMPT = """\
You are a **pharmaceutical regulatory agent** with access to the CIMA REST
API of the Spanish Agency of Medicines and Medical Devices (AEMPS). The
tools expose **public data** from the registry of medicines authorised in
Spain — never patient or clinical data.

Official sources:
- CIMA REST API v1.23 (medicines, presentations, VMP/VMPP, master tables,
  change log, segmented documents, safety notes, informational materials).
- CIMA Drug Shortages v1.01 (psuministro v2: by CN, DCP, DCPF and global
  listing).

# Tool catalogue

## 1. Single medicine
- `obtener_medicamento(cn|nregistro)` → full record for ONE medicine
  identified by its National Code (CN) or AEMPS registration number.
- `buscar_medicamentos(...filters...)` → paginated list with regulatory
  filters (>20 filters: active substance, ATC, manufacturer, flags
  black-triangle/orphan/biosimilar/marketed/prescription/narcotic/
  psychotropic, etc.). Use it when you do NOT know the CN/nregistro.
- `buscar_en_ficha_tecnica(rules)` → full-text search inside sections
  1..10 of the SmPC (Summary of Product Characteristics). Returns the
  list of medicines whose SmPC matches ALL the rules
  (`contiene=1` requires presence, `contiene=0` requires absence).

## 2. Presentations / equivalents
- `listar_presentaciones(...)` → paginated list of presentations by CN,
  nregistro, VMP, VMPP or active substance.
- `obtener_presentacion(cn=[...])` → detail by CN. Accepts multiple CNs
  — parallelises calls to the official single-CN endpoint.
- `buscar_vmpp(...)` → clinical equivalents VMP/VMPP filterable by
  active substance, dose, dosage form, ATC, name. `modoArbol=1` returns
  hierarchy.

## 3. Master tables
- `consultar_maestras(maestra=...)` → official tables: 1=active substance,
  3=dosage form, 4=route, 6=manufacturer, 7=ATC, 11/13/14=SNOMED
  equivalents, 15=medicines, 16=marketed medicines (SNOMED).

## 4. Changes and pharmacovigilance
- `registro_cambios(fecha, nregistro)` → additions (tipoCambio=1),
  removals (2), modifications (3) since a date (`dd/mm/yyyy` format).
  Each change includes labels: `estado`, `comerc`, `prosp`, `ft`,
  `psum`, `notasSeguridad`, `matinf`, `otros`.
- `listar_notas(nregistro=[...])` → safety notes published by AEMPS for
  one or several registrations.
- `listar_materiales(nregistro=[...])` → informational materials for
  patients / healthcare professionals.

## 5. Drug shortages (psuministro v2)
- `problemas_suministro(cn=[...]|nregistro=[...]|empty)` → if empty,
  global paginated listing; if CN, detail by presentation (includes
  `tipoProblemaSuministro` 1..9, start/end dates, `activo` flag,
  observations). If only `nregistro` is given, the wrapper resolves it
  to CNs.
- `problemas_suministro_dcp(cod_dcp)` → number of marketed presentations
  and presentations with active shortage for a DCP.
- `problemas_suministro_dcpf(cod_dcpf)` → same for a DCPF.

## 6. Documents
- `doc_secciones(tipo_doc, nregistro|cn)` → metadata of sections of the
  SmPC (tipo_doc=1) or Patient Information Leaflet (tipo_doc=2). Also
  supports 3=Public Assessment Report and 4=Risk Management Plan.
- `doc_contenido(tipo_doc, nregistro|cn, seccion?, format=json|html|txt)`
  → content of the requested section (or all if omitted).
- `html_ficha_tecnica(nregistro)` / `html_prospecto(nregistro)` → full
  HTML (not segmented).

# Recommended workflow

1. If the user provides a CN or nregistro → `obtener_medicamento` and,
   for presentation or shortage details, `obtener_presentacion` /
   `problemas_suministro`.
2. If the user describes the medicine → `buscar_medicamentos` (filters)
   or `buscar_vmpp` (clinical equivalents).
3. For textual content of the SmPC → first `buscar_en_ficha_tecnica`
   (filter by content), then `doc_contenido` (read the specific
   section).
4. For regulatory alerts → `listar_notas` (safety) and
   `registro_cambios` (recent modifications).
5. For shortages: by CN whenever possible; use DCP/DCPF only when
   working with clinical codes.

# Response guidelines

- Always summarise dose, dosage form, route, marketing status, relevant
  dates and associated alerts.
- Cite the source: "Data: AEMPS CIMA" + official URL where applicable.
- Indicate the extraction date ("Data extracted on dd/mm/yyyy").
- Close every response with the disclaimer:
  > This information is not medical advice; it is provided for
  > informational purposes only. Data published by AEMPS.
- Never issue clinical recommendations, diagnosis or prescriptions.
- If a required parameter is missing, return a clear message and stop
  the execution.
"""

# ---------------------------------------------------------------------------
# Per-tool descriptions — short by design (≤ 2 sentences body + Source +
# Limitation). Parameter shape is in the JSON inputSchema; long examples
# live in prompts. Trimmed in v0.3.0 (audit 2026-Q2 item 10).
# ---------------------------------------------------------------------------

medicamento_description = """\
Returns the complete record of ONE medicine authorised by AEMPS,
identified by `cn` or `nregistro` (at least one required).

When to use: you already know the CN/nregistro and need the structured
record. If not, use `buscar_medicamentos`.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamento`.
Limitation: only medicines authorised in Spain.
"""

medicamentos_description = """\
Paginated list of authorised medicines matching the given filters
(name, active substance, ATC, manufacturer, regulatory flags: orphan,
biosimilar, black-triangle, marketed, etc.).

When to use: you do NOT know the CN/nregistro and need to find medicines
by attributes.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamentos`.
Limitation: only medicines authorised in Spain; paginated results.
"""

buscar_ficha_tecnica_description = """\
Full-text search across SmPC sections. Each rule
`{seccion, texto, contiene}` filters by presence (`contiene=1`) or
absence (`contiene=0`); returns medicines whose SmPC matches ALL rules.

When to use: find medicines by SmPC textual content (e.g. section 4.1
mentioning "cancer" but not "stomach").

Source: AEMPS CIMA REST API v1.23 — `POST /cima/rest/buscarEnFichaTecnica`.
Limitation: sections 1..10 (official CIMA structure).
"""

presentaciones_description = """\
Paginated list of presentations (form + pack) of authorised medicines,
filterable by CN, nregistro, VMP/VMPP or active substance.

When to use: list presentations without knowing the CN, or filter them
by clinical equivalence or marketing status.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentaciones`.
Limitation: only presentations of authorised medicines.
"""

presentacion_description = """\
Detail of one or several presentations by National Code. Accepts a list
of CNs and parallelises calls to the official single-CN endpoint.

When to use: you already know the CN and need detail (status,
marketing, open shortages).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentacion/{cn}`.
Limitation: only presentations of authorised medicines.
"""

vmpp_description = """\
Paginated list of clinical equivalents VMP / VMPP filterable by active
substance, dose, form, ATC or name. `modoArbol=1` returns hierarchical
VMP -> VMPP.

When to use: clinical equivalence for substitution or finding authorised
alternatives.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/vmpp`.
Limitation: only equivalences published by AEMPS.
"""

maestras_description = """\
Official AEMPS master tables (`maestra` required). Main IDs:
1=active substance, 3=dosage form, 4=route, 6=manufacturer, 7=ATC,
11/13/14=SNOMED, 15/16=medicines.

When to use: resolve / list elements of an official table (e.g. all ATC
codes, or the ID of an active substance to use as `idpractiv1` in other
tools).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/maestras`.
"""

registro_cambios_description = """\
History of additions (`tipoCambio=1`), removals (2) and modifications
(3) since a `fecha` (`dd/mm/yyyy`) and/or for a given `nregistro`. Each
change carries labels: `estado`, `comerc`, `prosp`, `ft`, `psum`,
`notasSeguridad`, `matinf`, `otros`.

When to use: detect recent regulatory changes.

Source: AEMPS CIMA REST API v1.23 — `GET/POST /cima/rest/registroCambios`.
"""

problemas_suministro_description = """\
Drug shortage status: with no parameters, paginated global snapshot;
with `cn=[...]`, detail by presentation (includes
`tipoProblemaSuministro` 1..9, start/end dates, `activo`, `observ`). If
only `nregistro` is given, the wrapper resolves it to CNs.

When to use: check shortages / supply restrictions.

Source: AEMPS CIMA Shortages v1.01 — `GET /cima/rest/psuministro` and
`GET /cima/rest/psuministro/v2/cn/{cn}` (with v1 fallback).
"""

problemas_suministro_dcp_description = """\
Summary of marketed and shortage-affected presentations for a DCP
(Clinical Description of Product: active substance + dose + form
without format detail).

When to use: you work with clinical DCP codes instead of National Codes.

Source: AEMPS CIMA Shortages v1.01 —
`GET /cima/rest/psuministro/v2/dcp/{cod_dcp}`.
"""

problemas_suministro_dcpf_description = """\
Summary of marketed and shortage-affected presentations for a DCPF
(DCP plus specific dosage form). More specific than DCP.

When to use: you work with clinical DCPF codes.

Source: AEMPS CIMA Shortages v1.01 —
`GET /cima/rest/psuministro/v2/dcpf/{cod_dcpf}`.
"""

doc_secciones_description = """\
Metadata (number, title, order) of the sections of a segmented document:
1=SmPC, 2=Patient Information Leaflet, 3=Public Assessment Report,
4=Risk Management Plan. Does NOT include content — use `doc_contenido`
to fetch it.

When to use: check which sections exist before requesting content, or
compare availability between medicines.

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/secciones/{tipoDoc}`.
"""

doc_contenido_description = """\
Content of one section (`N` or `N.N`, e.g. `"4.2"`) of a segmented
document: 1=SmPC, 2=Leaflet. `format` accepts `json` (structured),
`html` or `txt`. If `seccion` is omitted, returns all sections.

When to use: you already know which section you need and want its
textual content.

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/contenido/{tipoDoc}`.
"""

listar_notas_description = """\
Safety notes published by AEMPS for one or several medicines. Each note
includes `num`, `ref`, `asunto`, `fecha` (epoch ms) and the official
AEMPS `url`.

When to use: check whether AEMPS has issued safety alerts about specific
medicines.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/notas/{nregistro}`.
"""

obtener_notas_description = listar_notas_description  # alias backward-compat

listar_materiales_description = """\
Safety informational materials associated with one or several medicines
(documents for patients and healthcare professionals, training videos).
Each element carries `titulo`, `listaDocsPaciente`,
`listaDocsProfesional` and optionally `video`.

When to use: check risk-minimisation materials or educational
documentation associated by AEMPS.

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/materiales/{nregistro}`.
"""

obtener_materiales_description = listar_materiales_description  # alias

html_ft_description = """\
Full HTML of the SmPC of a medicine.

When to use: you need the entire document. If you only want a specific
section, prefer `doc_contenido`.

Source: AEMPS — `GET https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html`.
"""

html_ft_multiple_description = html_ft_description  # alias backward-compat

html_p_description = """\
Full HTML of the patient information leaflet of a medicine.

When to use: you need the complete leaflet. If you only want a section,
prefer `doc_contenido(tipo_doc=2, ...)`.

Source: AEMPS — `GET https://cima.aemps.es/cima/dochtml/p/{nregistro}/Prospecto.html`.
"""

html_p_multiple_description = html_p_description  # alias backward-compat

system_info_prompt_description = """\
Returns `MCP_AEMPS_SYSTEM_PROMPT`: tool catalogue, recommended workflows
and response guidelines for a pharmaceutical regulatory agent operating
on AEMPS / CIMA.

When to use: the MCP client wants to re-inject the server's base prompt
(e.g. after compaction).
"""
