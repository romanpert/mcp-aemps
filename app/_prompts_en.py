# app/_prompts_en.py
"""English locale variant of the curated MCP Prompts catalogue.

Sister to ``app/_prompts_es.py``. Both modules export the exact same
public surface (``ALL_PROMPTS``, ``PATIENT_FACING_DISCLAIMER`` and the
9 prompt functions); the dispatcher in ``app/prompts.py`` chooses one
or the other based on ``MCP_AEMPS_LOCALE``.

Translations are functional and complete — same workflow steps, same
field names, same disclaimers; only the human-facing language changes.
The prompt body is what the LLM reads to orchestrate tool calls, so
keeping every step number and field reference identical is what
guarantees behaviour parity across locales.
"""

from __future__ import annotations

from typing import Awaitable, Callable

PromptFn = Callable[..., Awaitable[str]]


# ---------------------------------------------------------------------------
# Disclaimer block — every patient-facing prompt closes with this
# ---------------------------------------------------------------------------
PATIENT_FACING_DISCLAIMER = """\

---
**Legal notice**: this information comes from the public registry of
medicines authorised by AEMPS and is provided for informational
purposes. **It does not replace advice from a healthcare professional.**
For any question about treatment, dose, interactions or adverse
reactions, consult your doctor or pharmacist. The official patient
leaflet is available on the CIMA website: https://cima.aemps.es/
"""


# ---------------------------------------------------------------------------
# 1 · Community pharmacy — quick identification from a National Code
# ---------------------------------------------------------------------------
async def identificar_cn(cn: str) -> str:
    """Identify a medicine from its National Code (CN).

    Use case: community pharmacy. The patient brings a box or
    prescription with a CN; the pharmacist needs the summary record on
    a single screen — authorisation, marketing, prescription, active
    alerts, supply, photos.
    """
    return f"""\
Identify the medicine with national code {cn}. Follow **exactly** this
order of mcp-aemps tool calls:

1. `obtener_presentacion(cn=["{cn}"])` to resolve the `nregistro`,
   brand name and manufacturer.
2. `obtener_medicamento(nregistro=…)` with the obtained nregistro.
3. `problemas_suministro(cn=["{cn}"])` to know the **current** supply
   status.
4. If the `notas` field of the medicine is `true`:
   `listar_notas(nregistro=[…])` and then
   `obtener_notas(nregistros=[…])` only for the recent-dated notes.

Return a **summary card** in this order:

- **Brand name** + marketing-authorisation holder.
- **Presentation**: dosage form + dose.
- **Regulatory status**: authorised / suspended / revoked, date.
- **Marketed**: yes / no.
- **Prescription**: yes / no (and if it is a narcotic, psychotropic or
  needs visa, indicate it).
- **Black triangle / orphan / biosimilar**: only if any apply.
- **Supply**: ✅ no problems / ⚠️ active since {{fini}} ({{observ}}).
- **Active safety alerts**: list with date + subject + AEMPS URL, or
  "No active alerts".
- **Official images** (`fotos` field of the response): include the URLs
  distinguishing `materialas` (box / outer packaging) and `formafarmac`
  (the tablet / dosage form). Do not download, just link.
- **AEMPS documentation**: from the `docs` field, list each document by
  `tipo` (1=SmPC, 2=Patient Leaflet, 3=Public Assessment Report, 4=Risk
  Management Plan) with its URL.

Do not consult the full SmPC unless the user asks for it explicitly —
the card must fit on one screen.
"""


# ---------------------------------------------------------------------------
# 2 · Community pharmacy — search for generic equivalents
# ---------------------------------------------------------------------------
async def equivalencias_genericas(
    nregistro: str,
    comercializados_solo: bool = True,
) -> str:
    """Find equivalent medicines (same active substance / dose / dosage
    form), ideally marketed.

    Use case: substitution during a shortage, or quick lookup of
    cheaper alternatives for the patient.
    """
    filtro = "1 (marketed only)" if comercializados_solo else "0 (authorised, marketed or not)"
    return f"""\
Search for equivalent alternatives to medicine `nregistro={nregistro}`.
Steps:

1. `obtener_medicamento(nregistro="{nregistro}")` and extract:
   - The identifier of the first active substance (field
     `principiosActivos[0].id` → use it as `idpractiv1`).
   - The dose (`dosis`) and the dosage form (`formaFarmaceutica.nombre`).
2. `buscar_medicamentos(idpractiv1=…, comerc={filtro})` with `pagina=1`.
   If the result has `totalFilas > 25`, also call with `pagina=2` to
   have a sufficient sample.
3. **Filter the candidates** keeping only those with the same dose and
   the same dosage form as the original medicine. The brand name must
   be different from the starting one.
4. For each surviving candidate: check the `psum` field (true = open
   supply problems) and, if active, run
   `problemas_suministro(nregistro=[…])` for the detail.

Return a **table** with columns:

| CN | Brand name | Manufacturer | Prescription | Supply | Box photo |

Where "Box photo" is the URL from the `fotos[]` field with
`tipo=materialas` of the candidate (the first one if multiple) — useful
to visually confirm the equivalence with the patient.

If you do not find marketed alternatives, indicate it explicitly and
suggest re-running the query with `comercializados_solo=false` to see
the full authorised portfolio.
"""


# ---------------------------------------------------------------------------
# 3 · Hospital — pharmacovigilance review for a patient's medication list
# ---------------------------------------------------------------------------
async def vigilancia_paciente(nregistros: list[str]) -> str:
    """Review of active safety notes for all of a patient's medicines.

    Use case: hospital pharmacist or physician reviewing a patient's
    medication list — aligned with EMA GVP Module VI (signal
    management).
    """
    if not nregistros:
        return "Error: the `nregistros` list is empty."
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Carry out a pharmacovigilance review for the following AEMPS
registration numbers: {listado}.

Steps:

1. `listar_notas(nregistro=[{listado}])` to obtain the index of notes
   associated with each medicine.
2. For each medicine that has at least one note:
   `obtener_notas(nregistros=[…])` with the filtered list.
3. **Do not** consult the SmPC — the goal of this flow is only
   pharmacovigilance.

Return a **table** with columns:

| Nregistro | Name | # active notes | Latest note (date + subject) | AEMPS URL |

After the table, group by category the most relevant notes:

- 🔴 **Use restrictions / suspensions**: notes affecting authorised
  indications.
- 🟡 **New adverse reactions / interactions**: notes adding safety
  information without restricting use.
- 🔵 **Informative / labelling changes**: administrative updates.

For each highlighted note, include its full CIMA URL (`url` field of
the `Nota` object) so the clinician can download the official PDF.

Close with an executive summary of 2-3 sentences on the aggregate risk
of the portfolio (for example: "3 of the 7 medicines have active notes
in the last 12 months, one of them restrictive").
"""


# ---------------------------------------------------------------------------
# 4 · Hospital + industry — section-by-section SmPC comparison
# ---------------------------------------------------------------------------
async def comparar_fichas_tecnicas(
    nregistros: list[str],
    secciones: str = "4.1, 4.2, 4.3, 4.4, 4.5, 4.8",
) -> str:
    """Compare two or more medicines section by section of the SmPC.

    Use case: hospital pharmacy committee selecting between therapeutic
    alternatives; competitive analysis in industry.
    """
    if len(nregistros) < 2:
        return "Error: at least 2 nregistros are needed to compare."
    if len(nregistros) > 5:
        return "Error: maximum 5 simultaneous nregistros (LLM token limit)."
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Compare the SmPCs (tipo_doc=1) of the following medicines: {listado}.

Target sections: {secciones}. If the user has not indicated otherwise,
use these sections by default:
- 4.1: Therapeutic indications
- 4.2: Posology and method of administration
- 4.3: Contraindications
- 4.4: Special warnings and precautions for use
- 4.5: Interactions
- 4.8: Adverse reactions

Steps:

1. For each nregistro: `obtener_medicamento(nregistro=…)` to resolve
   the brand name + manufacturer (you need them as table headers).
2. For each nregistro **and** each requested section:
   `doc_contenido(tipo_doc=1, nregistro=…, seccion="…", format="txt")`.
3. If the section does not exist for some medicine (the API returns
   404), mark it as "—" in the table — it is not a fatal error.

Return a **wide-format table**: rows = sections, columns = one medicine
per column (header with the brand name). The content of each cell must
be a **structured bullet-point summary** of the official text — do not
copy the full plain text, that would be unreadable.

After the table, add a **section of clinically relevant divergences**
(3-5 bullets) highlighting where the medicines differ in indications,
critical contraindications or major interactions.

Close with the links to the full HTML SmPC of each medicine (`docs[]`
field with `tipo=1` of the Medicamento object, or build
`https://cima.aemps.es/cima/dochtml/ft/{{nregistro}}/FichaTecnica.html`).
"""


# ---------------------------------------------------------------------------
# 5 · Industry — regulatory portfolio audit of a manufacturer
# ---------------------------------------------------------------------------
async def auditar_cartera_laboratorio(
    laboratorio: str,
    incluir_no_comercializados: bool = False,
) -> str:
    """Snapshot of the regulatory portfolio of a marketing-authorisation
    holder.

    Use case: pharma business intelligence, due diligence, competitive
    benchmarking.
    """
    filtro_comerc = "1" if not incluir_no_comercializados else "0"
    return f"""\
Audit the portfolio of the marketing-authorisation holder
**"{laboratorio}"**. Steps:

1. `buscar_medicamentos(laboratorio="{laboratorio}", autorizados=1, comerc={filtro_comerc}, pagina=1)`.
   If `totalFilas > 25`, fetch pages 2 and 3 too (maximum 75 medicines
   to keep token cost bounded).
2. For a **representative sample of 20 medicines** (variety of
   therapeutic areas if possible), call
   `obtener_medicamento(nregistro=…)` to enrich.
3. For medicines with `notas=true`: `listar_notas(nregistro=[…])`.
4. For medicines with `psum=true`: already flagged, no extra call
   needed.

Return a **dashboard** with these blocks:

### 1. Global metrics
- Total authorised medicines.
- % marketed.
- % with open supply problems (`psum=true`).
- % with associated safety notes (`notas=true`).
- % with informational materials (`materialesInf=true`).
- % with Public Assessment Report (IPE/IPT) in `docs[]` with `tipo=3`
  — **high regulatory-impact signal**, AEMPS only publishes it for
  priority active substances.
- % with Risk Management Plan in `docs[]` with `tipo=4`.

### 2. Therapeutic areas
Aggregate by ATC level-1 code (`atcs[].codigo` truncated to the first
character): how many medicines per area.

### 3. Medicines with black triangle
List (with simple table: nregistro, name, authorisation date) — these
are medicines under additional monitoring, relevant data for
pharmacovigilance.

### 4. Top 5 with most active notes
Table: nregistro, name, # of notes, date of the most recent.

### 5. Open supply risks
List of marketed medicines with `psum=true`, with CN, name and
`fini`/`ffin` of the supply problem.

Close with a brief analysis (3-5 sentences) of the **aggregate
regulatory profile**: therapeutic specialisation, portfolio maturity
(many recent authorisations? many orphans?), exposure to supply
problems, presence in priority treatment lines for the system (IPT
presence).
"""


# ---------------------------------------------------------------------------
# 6 · Industry — monitor regulatory changes over a portfolio
# ---------------------------------------------------------------------------
async def monitorizar_cambios_cartera(
    nregistros: list[str],
    desde_fecha: str = "",
) -> str:
    """Detect regulatory changes (new, removal, modification) over a list
    of medicines in a given period.

    Use case: regulatory affairs reviewing their portfolio monthly.
    """
    if not nregistros:
        return "Error: the `nregistros` list is empty."
    if len(nregistros) > 50:
        return "Error: maximum 50 nregistros per query (operational limit)."
    fecha_arg = (
        f'fecha="{desde_fecha}"'
        if desde_fecha
        else 'fecha=""  # optional; without a date CIMA returns recent changes'
    )
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Monitor the regulatory changes of the following medicines in the
requested period: {listado}.

Steps:

1. `registro_cambios({fecha_arg}, nregistro=[{listado}], metodo="POST")`.
   The POST method is mandatory when sending a long list of nregistros
   (the GET URL would exceed maximum length).
2. For each detected change, identify the `tipoCambio`:
   - 1: New (addition).
   - 2: Removal (revocation or suspension).
   - 3: Modified.
3. For changes of type 3 (modification), review the `cambios` array
   to understand what changed: `estado`, `comerc`, `prosp` (leaflet),
   `ft` (SmPC), `psum` (supply), `notasSeguridad`, `matinf`
   (informational materials), `otros`.
4. For changes that include `notasSeguridad`:
   `obtener_notas(nregistros=[<the affected medicine>])` to bring the
   note's context.

Return the output in this format:

### Executive summary
- Total changes in the period.
- Breakdown by type (Addition / Removal / Modification).
- Affected medicines (how many of the {len(nregistros)} consulted).

### Timeline (most recent first)
One entry per change, with this structure:

```
📅 {{fecha}} · {{nregistro}} {{nombre}}
   Type: {{Addition|Removal|Modification}}
   Changes: {{list of fields that changed, in English: "SmPC",
            "Leaflet", "Marketing status", "Safety notes", …}}
   If there is an associated safety note → 1-line summary + AEMPS URL.
```

### Suggested actions
2-3 bullets on what would require immediate follow-up (changes in SmPC
or status, new safety notes).

If **there are no changes** in the period, indicate it clearly with
the date of the last verification and suggest retrying later.
"""


# ---------------------------------------------------------------------------
# 7 · Hospital + industry — Therapeutic Positioning Report (IPT/IPE)
# ---------------------------------------------------------------------------
async def informe_posicionamiento_terapeutico(nregistro: str) -> str:
    """Retrieve and summarise the Public Assessment Report (IPE/IPT) and
    the authorised indication of a medicine.

    Use case: hospital pharmacy committee evaluating inclusion in the
    formulary; market access in industry.
    """
    return f"""\
Retrieve the Therapeutic Positioning Report for the medicine
`nregistro={nregistro}` and complement it with the authorised
indication.

Steps:

1. `obtener_medicamento(nregistro="{nregistro}")` and extract:
   - Brand name, manufacturer, active substances, ATC.
   - The `docs[]` array. **Look specifically** for the document with
     `tipo=3` (Public Assessment Report, equivalent to IPT/IPE).
   - Also note whether `tipo=4` (Risk Management Plan), `tipo=1`
     (SmPC), `tipo=2` (Patient Leaflet) exist.
2. `doc_contenido(tipo_doc=1, nregistro="{nregistro}", seccion="4.1", format="txt")`
   to bring the **official therapeutic indication** (section 4.1 of
   the SmPC).
3. `doc_contenido(tipo_doc=1, nregistro="{nregistro}", seccion="5.1", format="txt")`
   for the **pharmacodynamic properties / mechanism of action**
   (section 5.1 — useful to contextualise the IPT).
4. If the medicine has `notas=true`:
   `listar_notas(nregistro=["{nregistro}"])` and, if there are active
   notes, `obtener_notas(nregistros=["{nregistro}"])` (a note posterior
   to the IPT may modify the positioning).

Return the output with this structure:

### Identification
Brand name · Manufacturer · Active substance · ATC code.

### Authorised indication (SmPC 4.1)
Structured summary of section 4.1, with bullets for each indication
if there are several.

### Mechanism of action (SmPC 5.1)
Brief summary (3-5 sentences) of the pharmacodynamics.

### Therapeutic Positioning Report
- If the medicine has IPT (`docs[]` with `tipo=3`): indicate document
  date and the full URL to download the PDF. **Do not try to download
  the PDF** — the IPT is not in the segmented-documents endpoint, it
  is only available as a PDF at the URL provided by the API.
- If it does **not** have a published IPT: indicate it explicitly. The
  absence of IPT does not imply lack of efficacy — AEMPS only
  publishes IPT for selected medicines (high-budget-impact
  innovations, biosimilars in their first inclusions, selected orphan
  active substances).

### Additional documentation available
List the other documents in the `docs[]` array (SmPC, Leaflet, Risk
Management Plan) with their URLs.

### Subsequent safety notes
If any, chronological list with date + subject + URL. Mark with ⚠️
those that may affect the positioning (use restrictions, new
contraindications).

Close with a usage note: "The IPT represents the official positioning
of the Ministry of Health/AEMPS at the time of its publication. Always
verify the date and the existence of subsequent notes that may have
updated the criterion."
"""


# ---------------------------------------------------------------------------
# 8 · Pharmacy + patient — visual and multimedia kit for counseling
# ---------------------------------------------------------------------------
async def material_visual_paciente(nregistro: str) -> str:
    """Gather the official visual and multimedia material of a medicine
    to explain it to a patient: photos of the box and dosage form,
    instruction videos (inhalers, pens, autoinjectors), informational
    material segregated by audience.

    Use case: community or hospital pharmacy — counseling the patient
    on how to correctly use a complex administration device.
    """
    return f"""\
Gather the official AEMPS visual and multimedia material of the
medicine `nregistro={nregistro}` for patient counseling.

Steps:

1. `obtener_medicamento(nregistro="{nregistro}")` and extract:
   - Brand name, presentation, dosage form.
   - The `fotos[]` array: each entry has `tipo` (`materialas` = photo
     of the box / outer packaging, `formafarmac` = photo of the
     dosage form) and `url`.
   - The `materialesInf` flag (boolean).
2. **Only if** `materialesInf == true`:
   - `listar_materiales(nregistro=["{nregistro}"])` to confirm
     availability.
   - `obtener_materiales(nregistro="{nregistro}")` to bring the full
     content: `listaDocsPaciente[]`, `listaDocsProfesional[]`, and
     very importantly the `video` field (URL — only present when the
     material is available in video format, typical of inhalers,
     insulin devices, EpiPen-type autoinjectors, prefilled pens,
     etc.).
3. **Do not download** the images or PDFs — limit the output to the
   official AEMPS URLs (MCP clients render them directly when they
   know how).

Return the output with this structure:

### Quick identification
Brand name · Dosage form · Dose.

### 📷 Official images
- **Box / outer packaging** (`tipo=materialas`): {{URL}}
- **Dosage form** (`tipo=formafarmac`): {{URL}}

(If only one of the two is available, indicate it. If there are no
images at all, indicate "No official images available".)

### 📄 Patient informational material
If `listaDocsPaciente` has content: list each document with its name
and official URL. These are materials written specifically for the
patient to understand how to use the medicine (they are not the
leaflet — they are visual guides / pictograms / patient cards that
AEMPS requires from manufacturers for certain complex-use or
risk-bearing products).

### 🎥 Instruction video
If the `video` field is present: include the URL as a featured link.
Briefly indicate what type of device it covers (inhaler, pen,
autoinjector, etc.) inferring it from the name and the dosage form.

### 📋 Material for the healthcare professional (reference)
If `listaDocsProfesional` has content: brief list. These materials do
not go to the patient, but the pharmacist can consult them.

### No multimedia material available
If `materialesInf == false` and there are no `fotos[]`, indicate that
for this medicine AEMPS does not require additional visual material
beyond the standard leaflet. Suggest reviewing section 6.6 of the
SmPC ("Special precautions for disposal and handling") for usage
instructions.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# 9 · Non-specialist — plain-language summary + alerts + mandatory disclaimer
# ---------------------------------------------------------------------------
async def info_medicamento_para_no_sanitarios(nombre_o_cn: str) -> str:
    """Plain-language summary of a medicine for a non-healthcare user
    (patient, journalist, developer building on the server). Includes
    photos, active alerts and mandatory disclaimer.

    Use case: general user who has heard about a medicine and wants to
    understand what it is. **Critical**: the prompt instructs the LLM
    to NEVER give medical advice — everything ends with "consult your
    doctor or pharmacist".
    """
    return f"""\
The user wants information about the medicine "{nombre_o_cn}". This
flow is intended for a **person without healthcare training** (patient,
family member, journalist). The register and language must be
accessible, without medical jargon.

Steps:

1. Determine if "{nombre_o_cn}" is a national code (all digits) or a
   brand name:
   - If numeric: `obtener_presentacion(cn=["{nombre_o_cn}"])` →
     extract the `nregistro`.
   - If text: `buscar_medicamentos(nombre="{nombre_o_cn}", pagina=1)`.
     Take the first **marketed** result (`comerc=true`); if none is
     marketed, take the first authorised one. Extract its `nregistro`.
2. `obtener_medicamento(nregistro=…)` to bring the full record.
3. `doc_contenido(tipo_doc=2, nregistro=…, seccion="2", format="txt")`
   for section 2 of the **patient leaflet** ("What it is and what it
   is used for"). This section is written for patients — it is the
   correct source for a plain explanation, not the SmPC (which is
   written for healthcare professionals).
4. If the medicine has `notas=true`:
   `listar_notas(nregistro=[…])` and, if there are recent active
   alerts, `obtener_notas(nregistros=[…])`.

Return the output in **5 short blocks**, without technicalities:

### 💊 What it is
One sentence identifying the medicine (brand name + what it is
generally prescribed for). Do not mention active substances unless
they are necessary to understand the indication.

### 🩺 What it is used for
Plain summary of section 2 of the leaflet, in 3-5 bullets. If section
2 mentions technical indications, "translate" them into everyday
language.

### 📷 What it looks like
If photos are available (`fotos[]` of the medicine): include URLs.
One of the **box** (`tipo=materialas`) and one of the **tablet**
(`tipo=formafarmac`), if both exist. This helps the user visually
confirm it is the correct product.

### ⚠️ Active official alerts
If there are active safety notes: list each one with date + a
**one-sentence** summary of the subject + the URL to the official
AEMPS PDF. If there are **no** active alerts, indicate it explicitly:
"There are no active safety alerts published by AEMPS for this
medicine as of the consultation date".

### 📚 Where to read more
- Link to the **full leaflet** (`docs[]` field with `tipo=2`, or build
  `https://cima.aemps.es/cima/dochtml/p/{{nregistro}}/Prospecto.html`).
- Link to the official medicine page on CIMA:
  `https://cima.aemps.es/cima/publico/detalle.html?nregistro={{nregistro}}`.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# 10 · Hospital + pharmacy + patient — interactions documented in SmPC 4.5
# ---------------------------------------------------------------------------
async def comprobar_interaccion_principios_activos(
    principios_activos: list[str],
) -> str:
    """Check whether section 4.5 (Interactions) of AEMPS SmPCs mentions
    cross-interactions between the given active substances.

    Use case: preliminary interaction review for a drug combination.
    **Does NOT replace a formal clinical interaction-checking tool**
    (BOT PLUS, Lexicomp, Stockley, Micromedex, etc.) — it only searches
    for textual mentions in the official AEMPS documentation, which is
    a lower bound, not an upper bound, of potential interactions.
    """
    if len(principios_activos) < 2:
        return "Error: at least 2 active substances are needed to search for interactions."
    if len(principios_activos) > 5:
        return "Error: maximum 5 active substances per query (token limit)."
    listado = ", ".join(f'"{p}"' for p in principios_activos)
    n_pares = len(principios_activos) * (len(principios_activos) - 1) // 2
    return f"""\
Check potential interactions **documented in AEMPS SmPCs** between the
following active substances: {listado}.

Steps:

1. For each active substance, locate a representative marketed
   medicine: `buscar_medicamentos(practiv1="<substance>", comerc=1, pagina=1)`.
   Take the first result and store its `nregistro` and `nombre`.

2. For each pair of active substances (A, B), search for cross-mentions
   in section 4.5 (Interactions) of the SmPC:
   `buscar_en_ficha_tecnica(reglas=[
       {{"seccion": "4.5", "texto": "<substance_B>", "contiene": 1}}
   ])`. Repeat with A and B swapped (the mention may be in only one
   direction).

3. For each medicine that comes back as a match: extract the relevant
   paragraph from section 4.5:
   `doc_contenido(tipo_doc=1, nregistro="<nregistro>", seccion="4.5", format="txt")`.
   Trim to the 3-6 sentences that mention the other active substance
   (do not copy the full section, it is usually very long).

Return the output with this structure:

### Summary
- Combinations reviewed: {n_pares}.
- Interactions documented in AEMPS SmPC: N.

### Detail per combination
For each pair A↔B, a sub-section:

#### A ↔ B
- ✅ "No cross-mentions in section 4.5 of the consulted SmPCs" — if
  there is nothing.
- ⚠️ If there are mentions: for each match, indicate:
  - Medicine: brand name · nregistro · manufacturer.
  - Relevant paragraph (3-6 sentences) from section 4.5.
  - URL to the full SmPC.

### ⚠️ Limitations (CRITICAL — always include)
- This search only covers textual mentions in section 4.5 of the
  official AEMPS SmPC of **one representative medicine** per active
  substance. It **does NOT replace** a formal clinical
  interaction-checking tool (BOT PLUS / Bot Plus Web, Lexicomp,
  Stockley's Drug Interactions, Micromedex, UpToDate Lexicomp).
- **Absence of mention does NOT imply absence of interaction** — it
  only means the specific medicine consulted does not document it in
  its SmPC. Other medicines with the same active substance may
  document it.
- Pharmacokinetic / pharmacodynamic interactions depend on dose,
  route, patient, renal/hepatic function, comorbidity, polypharmacy.
  **Always consult a clinical pharmacist or physician** before making
  prescription, substitution or deprescription decisions.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# Public API — registered onto the FastMCP server by app.prompts.register_prompts
# ---------------------------------------------------------------------------
ALL_PROMPTS: tuple[tuple[str, str, PromptFn], ...] = (
    (
        "identificar_cn",
        "Identify a medicine by its National Code (CN) and return a "
        "summary card ready to display on a pharmacy counter: name, "
        "presentation, authorisation, marketing, active alerts, supply, "
        "official photos and links to AEMPS documentation. Use case: "
        "community pharmacy.",
        identificar_cn,
    ),
    (
        "equivalencias_genericas",
        "Find equivalent medicines (same active substance, dose and "
        "dosage form) starting from an AEMPS nregistro, filtering by "
        "marketed with up-to-date supply problems. Use case: "
        "substitution during a shortage.",
        equivalencias_genericas,
    ),
    (
        "vigilancia_paciente",
        "Review of active AEMPS safety notes for a list of nregistros "
        "(a patient's medication list). Group by criticality and link "
        "the official PDF. Use case: hospital pharmacy, aligned with "
        "EMA GVP Module VI.",
        vigilancia_paciente,
    ),
    (
        "comparar_fichas_tecnicas",
        "Compare two or more medicines section by section of the SmPC "
        "(4.1 Indications, 4.2 Posology, 4.3 Contraindications, 4.4 "
        "Warnings, 4.5 Interactions, 4.8 Adverse reactions by default). "
        "Returns a wide-format table. Use case: hospital pharmacy "
        "committee, competitive analysis in industry.",
        comparar_fichas_tecnicas,
    ),
    (
        "auditar_cartera_laboratorio",
        "Complete regulatory snapshot of the portfolio of a "
        "marketing-authorisation holder: global metrics, therapeutic "
        "areas (ATC), black triangle, top 5 with active notes, open "
        "supply risks, presence of Therapeutic Positioning Report "
        "(IPT). Use case: pharma business intelligence, due diligence.",
        auditar_cartera_laboratorio,
    ),
    (
        "monitorizar_cambios_cartera",
        "Detect regulatory changes (addition, removal, modification of "
        "SmPC, leaflet, marketing, safety notes) over a list of "
        "nregistros from a given date. Use case: regulatory affairs "
        "reviewing monthly.",
        monitorizar_cambios_cartera,
    ),
    (
        "informe_posicionamiento_terapeutico",
        "Retrieve the Public Assessment Report (IPE/IPT) of a medicine "
        "(when AEMPS has published it), together with the authorised "
        "indication (SmPC 4.1) and the mechanism of action (SmPC 5.1). "
        "Clearly indicate when the IPT does not exist — its absence "
        "does not imply lack of efficacy. Use case: hospital pharmacy "
        "committee, market access in industry.",
        informe_posicionamiento_terapeutico,
    ),
    (
        "material_visual_paciente",
        "Gather the official AEMPS visual and multimedia material of a "
        "medicine: photos of the box and the dosage form, instruction "
        "videos (inhalers, insulin pens, autoinjectors), informational "
        "material segregated by audience (patient vs healthcare "
        "professional). Use case: patient counseling.",
        material_visual_paciente,
    ),
    (
        "info_medicamento_para_no_sanitarios",
        "Plain-language summary of a medicine for a user without "
        "healthcare training (patient, family member, journalist, "
        "developer building on the server). 5 blocks: what it is, what "
        "it is used for, what it looks like (photos), active alerts, "
        "where to read more. Closes with mandatory disclaimer: not "
        "medical advice. Use case: general public who wants to "
        "understand a medicine without asking the LLM to act as a "
        "clinical consultant.",
        info_medicamento_para_no_sanitarios,
    ),
    (
        "comprobar_interaccion_principios_activos",
        "Check whether section 4.5 (Interactions) of AEMPS SmPCs "
        "mentions cross-interactions between 2-5 active substances. "
        "It is a textual search over official documentation — does NOT "
        "replace a formal clinical interaction-checking tool (BOT PLUS, "
        "Lexicomp, Stockley, Micromedex). Use case: preliminary "
        "polypharmacy review in hospital pharmacy, validation of "
        "combinations for protocols.",
        comprobar_interaccion_principios_activos,
    ),
)
