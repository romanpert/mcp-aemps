"""English locale variant of LLM-facing descriptions.

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
# Per-tool descriptions
# ---------------------------------------------------------------------------

medicamento_description = """\
Returns the complete record of ONE medicine authorised by AEMPS,
identified by National Code (`cn`) or registration number (`nregistro`).

When to use: you already know the CN or nregistro and need the
structured record (active substances, dose, dosage form, route,
authorisation and marketing status, regulatory flags, presentations,
associated documents).

Parameters (at least one required):
- `cn` (str, digits only): National Code of the presentation.
- `nregistro` (str, digits only): AEMPS registration number.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamento`.
Limitation: only medicines authorised in Spain.
"""

medicamentos_description = """\
Paginated list of medicines authorised in Spain matching the given
filters.

When to use: you do NOT know the CN/nregistro and need to find medicines
by name, active substance, manufacturer, ATC code, or by regulatory
attributes (orphan, biosimilar, black-triangle, substitutability...).

Parameters (all optional; combine freely):
- `nombre` (str): brand name (partial or exact).
- `laboratorio` (str): marketing-authorisation holder.
- `practiv1`, `practiv2` (str): name of an active substance.
- `idpractiv1`, `idpractiv2` (str): numeric ID of the active substance.
- `cn` (str, digits), `nregistro` (str, digits).
- `atc` (str): ATC code, complete or partial (also accepts description).
- `npactiv` (int): number of associated active substances.
- `triangulo`, `huerfano`, `biosimilar`, `comerc`, `autorizados`,
  `receta`, `estupefaciente`, `psicotropo`, `estuopsico` (int 0|1):
  binary flags.
- `sust` (int 1..5): special-medicine type (1=biologicals, 2=narrow
  therapeutic margin, 3=special medical control, 4=inhaled
  respiratory, 5=narrow therapeutic margin).
- `vmp` (str): VMP ID for clinical equivalents.
- `pagina` (int >=1, default 1).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamentos`.
Limitation: only medicines authorised in Spain; paginated results.
"""

buscar_ficha_tecnica_description = """\
Full-text search across sections of the SmPC (Summary of Product
Characteristics) of authorised medicines. Returns the list of medicines
whose SmPC matches ALL the given rules.

When to use: you need to find medicines by textual content of their
SmPC (e.g. "those mentioning 'cancer' in section 4.1 but NOT mentioning
'stomach'").

Parameter:
- `reglas` (list, required): list of objects `{seccion, texto, contiene}`:
  - `seccion` (str): section number in `N` or `N.N` format
    (1..10 per AEMPS spec; e.g. `"4.1"`).
  - `texto` (str): string to search for.
  - `contiene` (int 0|1): 1 = the section MUST contain the text;
    0 = it MUST NOT contain it.

Example:
```json
[
  {"seccion": "4.1", "texto": "cancer",  "contiene": 1},
  {"seccion": "4.1", "texto": "stomach", "contiene": 0}
]
```

Source: AEMPS CIMA REST API v1.23 — `POST /cima/rest/buscarEnFichaTecnica`.
Limitation: only SmPCs of authorised medicines; sections 1..10
(official CIMA structure).
"""

presentaciones_description = """\
Paginated list of presentations of authorised medicines.

When to use: you need to list presentations (form + pack) without
knowing the CN, or to filter them by VMP/VMPP/active substance/
marketing status.

Parameters (all optional):
- `cn` (str, digits), `nregistro` (str, digits).
- `vmp`, `vmpp` (str): VMP/VMPP ID for clinical equivalence.
- `idpractiv1` (str): active substance ID.
- `comerc` (int 0|1): 1 marketed, 0 not marketed.
- `estupefaciente`, `psicotropo`, `estuopsico` (int 0|1): flags.
- `pagina` (int >=1, default 1).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentaciones`.
Limitation: only presentations of authorised medicines.
"""

presentacion_description = """\
Detail of one or several presentations by National Code.

When to use: you already know the CN and need the detail (status,
marketing, open shortage problems). Accepts a list of CNs and
parallelises calls to the official single-CN endpoint.

Parameter:
- `cn` (list[str], required): one or several National Codes (digits only).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentacion/{cn}`.
Wrapper: parallelises one call per CN and aggregates results in
`{cn: detail, ...}` with `errors` for unresolved CNs.
Limitation: only presentations of authorised medicines.
"""

vmpp_description = """\
Paginated list of clinical equivalents VMP / VMPP (Virtual Medicinal
Product / Virtual Medicinal Product Pack).

When to use: you need clinical equivalence between medicines by active
substance + dose + form + route, e.g. for substitution or finding
authorised alternatives.

Parameters (all optional):
- `practiv1` (str): name of the principal active substance.
- `idpractiv1` (str): active substance ID.
- `dosis` (str): dose (CIMA format).
- `forma` (str): dosage form.
- `atc` (str): full or partial ATC code.
- `nombre` (str): medicine name.
- `modoArbol` (int 0|1): 1 = hierarchical response VMP -> VMPP.
- `pagina` (int >=1, default 1).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/vmpp`.
Limitation: only equivalences published by AEMPS.
"""

maestras_description = """\
Official AEMPS master tables (active substances, dosage forms, routes,
manufacturers, ATC, SNOMED equivalents, medicines).

When to use: you need to resolve / list elements of an official table
(e.g. all level-4 ATC codes, or the ID of an active substance to use
as `idpractiv1` in other tools).

Parameters:
- `maestra` (int, REQUIRED): table ID:
  - 1 Active substances
  - 3 Dosage forms
  - 4 Routes of administration
  - 6 Manufacturers
  - 7 ATC codes
  - 11 Active substances (SNOMED)
  - 13 Simplified dosage forms (SNOMED)
  - 14 Simplified routes (SNOMED)
  - 15 Medicines
  - 16 Marketed medicines (SNOMED)
- `nombre`, `id`, `codigo` (str, optional): element filters.
- `estupefaciente`, `psicotropo`, `estuopsico`, `enuso` (int 0|1).
- `pagina` (int >=1, default 1).

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/maestras`.
"""

registro_cambios_description = """\
History of additions, removals and modifications of medicines from a
given date and/or for a specific nregistro.

When to use: you need to detect recent regulatory changes (new
authorisations, withdrawals, leaflet / SmPC / shortage / safety-note /
informational-material updates).

Parameters:
- `fecha` (str, optional): minimum date in `dd/mm/yyyy` format.
- `nregistro` (list[str] | str, optional): one or several registrations
  to narrow the query.
- `metodo` (str, optional, default `GET`): internal HTTP method; use
  `POST` if the registration list is very long.

Each returned element carries:
- `tipoCambio` (int): 1 new, 2 removal, 3 modified.
- `cambios` (list[str]): labels such as `estado`, `comerc`, `prosp`,
  `ft`, `psum`, `notasSeguridad`, `matinf`, `otros`.

Source: AEMPS CIMA REST API v1.23 — `GET/POST /cima/rest/registroCambios`.
"""

problemas_suministro_description = """\
Supply status of pharmaceutical presentations. Returns the global
paginated list or detail by one or several CNs / nregistros.

When to use:
- No parameters: global snapshot of active drug shortages.
- With `cn=[...]`: detail by presentation (preferred — the official
  endpoint works by national code).
- With `nregistro=[...]`: the wrapper resolves each nregistro to its
  associated CNs and queries each one.

Parameters (all optional):
- `cn` (list[str]): one or several National Codes.
- `nregistro` (list[str]): one or several AEMPS registration numbers.
- `pagina` (int >=1, default 1) — only applies to the global listing.
- `tamanioPagina` (int 1..100, default 25) — only applies to the
  global listing.

Each presentation with active shortage exposes:
- `tipoProblemaSuministro` (int 1..9): type per AEMPS table (1 informative
  note, 2 hospital-only, 3 consider alternative treatment,
  4 temporary shortage, 5 alternative with same active substance,
  6 alternatives with same active substances, 7 foreign medicine,
  8 restricted prescription, 9 controlled distribution).
- `fini` / `ffin` (epoch ms): start and expected end of the problem.
- `activo` (bool), `observ` (str).

Source: AEMPS CIMA Shortages v1.01 — `GET /cima/rest/psuministro` and
`GET /cima/rest/psuministro/v2/cn/{cn}` (with v1 fallback if v2 fails).
"""

problemas_suministro_dcp_description = """\
Summary of marketed and shortage-affected presentations for a DCP
(Clinical Description of Product: active substance + dose + form
without format detail).

When to use: you work with clinical DCP codes instead of National Codes
and want to know, aggregating all presentations of that DCP, how many
are marketed and how many have an active problem.

Parameter:
- `cod_dcp` (str, required, digits only): AEMPS DCP code.

Response:
- `comercializados` (int): number of marketed presentations.
- `con_psuministro` (int): number of presentations with active
  shortage.

Source: AEMPS CIMA Shortages v1.01 —
`GET /cima/rest/psuministro/v2/dcp/{cod_dcp}`.
"""

problemas_suministro_dcpf_description = """\
Summary of marketed and shortage-affected presentations for a DCPF
(Clinical Description of Product with Format: active substance + dose
+ specific dosage form).

When to use: you work with clinical DCPF codes (more specific than DCP)
and want the aggregate by marketed / active-shortage presentation.

Parameter:
- `cod_dcpf` (str, required, digits only): AEMPS DCPF code.

Response:
- `comercializados` (int)
- `con_psuministro` (int)

Source: AEMPS CIMA Shortages v1.01 —
`GET /cima/rest/psuministro/v2/dcpf/{cod_dcpf}`.
"""

doc_secciones_description = """\
Metadata of sections available for one document type of one or several
medicines. Does NOT include content — use `doc_contenido` to fetch it.

When to use: you want to know which sections exist (number, title,
order) in the SmPC or leaflet before requesting the content, or you
need to compare section availability between medicines.

Parameters:
- `tipo_doc` (int, required):
  - 1 SmPC (Summary of Product Characteristics)
  - 2 Patient Information Leaflet
  - 3 Public Assessment Report (IPE)
  - 4 Risk Management Plan (PGR)
- `nregistro` (list[str], optional): one or several registration numbers.
- `cn` (list[str], optional): one or several National Codes (the
  wrapper resolves CN -> nregistro automatically).

At least one of `nregistro` or `cn` is required.

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/secciones/{tipoDoc}`.
"""

doc_contenido_description = """\
Content of one section (or all) of a segmented document: SmPC or
patient leaflet.

When to use: you already know which section you need (e.g. `4.2`
posology) and want its textual content. If `seccion` is omitted,
returns ALL sections.

Parameters:
- `tipo_doc` (int, required): 1 SmPC, 2 Leaflet.
- `nregistro` (str, optional, digits) or `cn` (str, optional, digits).
  One of them is required; if `cn` is given, it is resolved to
  `nregistro`.
- `seccion` (str, optional): section ID (`N` or `N.N`, e.g. `"4.2"`).
  If empty, returns all sections.
- `format` (str, optional, default `json`): `json` (structured),
  `html` (HTML content only) or `txt` (plain text).

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/contenido/{tipoDoc}`.
"""

listar_notas_description = """\
Safety notes published by AEMPS for one or several medicines.

When to use: you need to check whether AEMPS has issued safety alerts
or communications about one or several specific medicines.

Parameter:
- `nregistro` (list[str], required): one or several registration
  numbers. Each call is parallelised.

Response: `{nregistro: [notes...], ...}` plus an `errores` object with
the registrations that failed. Each note includes `num`, `ref`,
`asunto`, `fecha` (epoch ms) and the official AEMPS `url`.

Source: AEMPS CIMA REST API v1.23 — `GET /cima/rest/notas/{nregistro}`.
"""

obtener_notas_description = listar_notas_description  # alias backward-compat

listar_materiales_description = """\
Safety informational materials associated with one or several medicines
(documents for patients and healthcare professionals, training videos,
etc.).

When to use: you need to check risk-minimisation materials or
educational documentation that AEMPS associates with a medicine.

Parameter:
- `nregistro` (list[str], required): one or several registration
  numbers. Each call is parallelised.

Response: flat list with the materials found. Each element carries
`titulo`, `listaDocsPaciente`, `listaDocsProfesional` and, if
applicable, `video`.

Source: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/materiales/{nregistro}`.
"""

obtener_materiales_description = listar_materiales_description  # alias

html_ft_description = """\
Full HTML of the SmPC (Summary of Product Characteristics) of a medicine.

When to use: you need the entire document (not segmented by sections)
to display to the user or for downstream processing. If you only want
a specific section, prefer `doc_contenido`.

Parameters:
- `nregistro` (str, required): AEMPS registration number.
- `filename` (str, optional, default `FichaTecnica.html`).

Source: AEMPS — `GET https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html`.
"""

html_ft_multiple_description = html_ft_description  # alias backward-compat

html_p_description = """\
Full HTML of the patient information leaflet of a medicine.

When to use: you need the complete leaflet. If you only want a specific
section, prefer `doc_contenido(tipo_doc=2, ...)`.

Parameters:
- `nregistro` (str, required): AEMPS registration number.
- `filename` (str, optional, default `Prospecto.html`).

Source: AEMPS — `GET https://cima.aemps.es/cima/dochtml/p/{nregistro}/Prospecto.html`.
"""

html_p_multiple_description = html_p_description  # alias backward-compat

system_info_prompt_description = """\
Returns `MCP_AEMPS_SYSTEM_PROMPT`: tool catalogue, recommended workflows
and response guidelines for a pharmaceutical regulatory agent operating
on AEMPS / CIMA.

When to use: the MCP client wants to re-inject the server's base prompt
(e.g. after compaction) or expose it as static context.
"""
