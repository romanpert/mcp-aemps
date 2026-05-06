"""LLM-facing descriptions for every MCP tool exposed by mcp-aemps.

Single source of truth. Imported by both transports:
- ``app.stdio_server`` (FastMCP ``@server.tool(description=...)``)
- ``app.routes.*``      (FastAPI ``@router.get(..., description=...)``)

Style guide (per CLAUDE.md "MCP Tool Design Principles"):
1. Cite the data source ("Fuente: AEMPS CIMA REST API v1.23" or
   "Problemas de Suministro v1.01").
2. State the limitation ("solo medicamentos autorizados en Espana").
3. Give a "Cuando usar" cue so the LLM can disambiguate sibling tools.
4. Document parameter ranges as documented by AEMPS, not as the wrapper
   happens to behave.
5. Frame everything as regulatory data access — never clinical advice.

Date format note: all timestamps returned by the upstream API are Unix
epoch in milliseconds (CIMA core, GMT+2:00) or seconds (Problemas
Suministro). The wrapper parses them to ISO-8601 in ``parse_cima_fechas``
helpers, so tool results expose human-readable dates.
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
#
# Setting these hints lets MCP clients (Claude Desktop, ChatGPT Dev Mode,
# Cursor, Continue, Zed, JetBrains Junie, Codex …) auto-approve calls in
# their UI instead of treating every tool as potentially destructive. See
# https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
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
# Per-tool descriptions
# ---------------------------------------------------------------------------

medicamento_description = """\
Devuelve la ficha completa de UN medicamento autorizado por la AEMPS,
identificado por Codigo Nacional (`cn`) o numero de registro
(`nregistro`).

Cuando usar: ya conoces el CN o nregistro y necesitas la ficha
estructurada (principios activos, dosis, forma, via, estado de
autorizacion y comercializacion, flags regulatorios, presentaciones,
documentos asociados).

Parametros (al menos uno obligatorio):
- `cn` (str, solo digitos): Codigo Nacional de la presentacion.
- `nregistro` (str, solo digitos): numero de registro AEMPS.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamento`.
Limitacion: solo medicamentos autorizados en Espana.
"""

medicamentos_description = """\
Listado paginado de medicamentos autorizados en Espana que cumplen los
filtros indicados.

Cuando usar: NO conoces el CN/nregistro y necesitas localizar
medicamentos por nombre, principio activo, laboratorio, ATC, o por
caracteristicas regulatorias (huerfano, biosimilar, triangulo negro,
sustituibilidad...).

Parametros (todos opcionales; combinar libremente):
- `nombre` (str): nombre comercial (parcial o exacto).
- `laboratorio` (str): laboratorio titular.
- `practiv1`, `practiv2` (str): nombre de un principio activo.
- `idpractiv1`, `idpractiv2` (str): ID numerico del principio activo.
- `cn` (str, digitos), `nregistro` (str, digitos).
- `atc` (str): codigo ATC completo o parcial (acepta descripcion).
- `npactiv` (int): numero de principios activos asociados.
- `triangulo`, `huerfano`, `biosimilar`, `comerc`, `autorizados`,
  `receta`, `estupefaciente`, `psicotropo`, `estuopsico` (int 0|1):
  flags binarios.
- `sust` (int 1..5): tipo de medicamento especial (1=biologicos,
  2=estrecho margen terapeutico, 3=especial control medico,
  4=respiratorio inhalatoria, 5=estrecho margen terapeutico).
- `vmp` (str): ID VMP para equivalentes clinicos.
- `pagina` (int >=1, defecto 1).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/medicamentos`.
Limitacion: solo medicamentos autorizados en Espana; resultados
paginados.
"""

buscar_ficha_tecnica_description = """\
Busqueda textual sobre secciones de la ficha tecnica de los medicamentos
autorizados. Devuelve la lista de medicamentos cuya ficha cumple TODAS
las reglas indicadas.

Cuando usar: necesitas localizar medicamentos por contenido textual
de su ficha tecnica (p.ej. "que mencionen 'cancer' en la seccion 4.1
pero NO mencionen 'estomago'").

Parametro:
- `reglas` (list, obligatorio): lista de objetos
  `{seccion, texto, contiene}`:
  - `seccion` (str): numero de seccion en formato `N` o `N.N`
    (1..10 segun spec AEMPS; p.ej. `"4.1"`).
  - `texto` (str): cadena a buscar.
  - `contiene` (int 0|1): 1 = la seccion DEBE contener el texto;
    0 = NO debe contenerlo.

Ejemplo:
```json
[
  {"seccion": "4.1", "texto": "cancer",  "contiene": 1},
  {"seccion": "4.1", "texto": "estomago","contiene": 0}
]
```

Fuente: AEMPS CIMA REST API v1.23 — `POST /cima/rest/buscarEnFichaTecnica`.
Limitacion: solo fichas tecnicas de medicamentos autorizados; secciones
1..10 (estructura oficial CIMA).
"""

presentaciones_description = """\
Listado paginado de presentaciones de medicamentos autorizados.

Cuando usar: necesitas listar presentaciones (formato + envase) sin
saber CN, o filtrarlas por VMP/VMPP/principio activo/comercializacion.

Parametros (todos opcionales):
- `cn` (str, digitos), `nregistro` (str, digitos).
- `vmp`, `vmpp` (str): ID de VMP/VMPP para equivalencias clinicas.
- `idpractiv1` (str): ID del principio activo.
- `comerc` (int 0|1): 1 comercializadas, 0 no comercializadas.
- `estupefaciente`, `psicotropo`, `estuopsico` (int 0|1): flags.
- `pagina` (int >=1, defecto 1).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentaciones`.
Limitacion: solo presentaciones de medicamentos autorizados.
"""

presentacion_description = """\
Detalle de una o varias presentaciones por Codigo Nacional.

Cuando usar: ya conoces el CN y necesitas el detalle (estado,
comercializacion, problemas de suministro abiertos). Acepta una lista
de CNs y paraleliza llamadas al endpoint oficial single-CN.

Parametro:
- `cn` (list[str], obligatorio): uno o varios Codigos Nacionales (solo
  digitos).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/presentacion/{cn}`.
Wrapper: paraleliza una llamada por cada CN y agrega resultados en
`{cn: detalle, ...}` con `errors` para los CNs no resueltos.
Limitacion: solo presentaciones de medicamentos autorizados.
"""

vmpp_description = """\
Listado paginado de equivalentes clinicos VMP / VMPP (Virtual Medicinal
Product / Virtual Medicinal Product Pack).

Cuando usar: necesitas equivalencias clinicas entre medicamentos por
principio activo + dosis + forma + via, p.ej. para sustitucion o
busqueda de alternativas autorizadas.

Parametros (todos opcionales):
- `practiv1` (str): nombre del principio activo principal.
- `idpractiv1` (str): ID del principio activo.
- `dosis` (str): dosis (formato CIMA).
- `forma` (str): forma farmaceutica.
- `atc` (str): codigo ATC completo o parcial.
- `nombre` (str): nombre del medicamento.
- `modoArbol` (int 0|1): 1 = respuesta jerarquica VMP -> VMPP.
- `pagina` (int >=1, defecto 1).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/vmpp`.
Limitacion: solo equivalencias publicadas por AEMPS.
"""

maestras_description = """\
Catalogos maestros oficiales de la AEMPS (principios activos, formas,
vias, laboratorios, ATC, equivalencias SNOMED, medicamentos).

Cuando usar: necesitas resolver / listar elementos de una tabla oficial
(p.ej. todos los codigos ATC del nivel 4, o el ID de un principio activo
para usarlo como `idpractiv1` en otras herramientas).

Parametros:
- `maestra` (int, OBLIGATORIO): ID de la maestra:
  - 1 Principios activos
  - 3 Formas farmaceuticas
  - 4 Vias de administracion
  - 6 Laboratorios
  - 7 Codigos ATC
  - 11 Principios activos (SNOMED)
  - 13 Formas farmaceuticas simplificadas (SNOMED)
  - 14 Vias de administracion simplificadas (SNOMED)
  - 15 Medicamentos
  - 16 Medicamentos comercializados (SNOMED)
- `nombre`, `id`, `codigo` (str, opcionales): filtros del elemento.
- `estupefaciente`, `psicotropo`, `estuopsico`, `enuso` (int 0|1).
- `pagina` (int >=1, defecto 1).

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/maestras`.
"""

registro_cambios_description = """\
Historial de altas, bajas y modificaciones de medicamentos a partir de
una fecha y/o para un nregistro concreto.

Cuando usar: necesitas detectar cambios regulatorios recientes (nuevas
autorizaciones, retiradas, cambios de prospecto / ficha tecnica /
problemas de suministro / notas de seguridad / materiales informativos).

Parametros:
- `fecha` (str, opcional): fecha minima en formato `dd/mm/yyyy`.
- `nregistro` (list[str] | str, opcional): uno o varios registros para
  acotar la consulta.
- `metodo` (str, opcional, defecto `GET`): metodo HTTP interno; usar
  `POST` si la lista de nregistros es muy larga.

Cada elemento devuelto trae:
- `tipoCambio` (int): 1 nuevo, 2 baja, 3 modificado.
- `cambios` (list[str]): etiquetas como `estado`, `comerc`, `prosp`,
  `ft`, `psum`, `notasSeguridad`, `matinf`, `otros`.

Fuente: AEMPS CIMA REST API v1.23 — `GET/POST /cima/rest/registroCambios`.
"""

problemas_suministro_description = """\
Estado de suministro de presentaciones farmaceuticas. Devuelve la lista
global paginada o el detalle por uno o varios CNs / nregistros.

Cuando usar:
- Sin parametros: snapshot global de problemas de suministro activos.
- Con `cn=[...]`: detalle por presentacion (preferido — el endpoint
  oficial trabaja por codigo nacional).
- Con `nregistro=[...]`: el wrapper resuelve cada nregistro a sus CNs
  asociados y consulta cada uno.

Parametros (todos opcionales):
- `cn` (list[str]): uno o varios Codigos Nacionales.
- `nregistro` (list[str]): uno o varios numeros de registro AEMPS.
- `pagina` (int >=1, defecto 1) — solo aplica al listado global.
- `tamanioPagina` (int 1..100, defecto 25) — solo aplica al listado
  global.

Cada presentacion con problema activo expone:
- `tipoProblemaSuministro` (int 1..9): tipo segun tabla AEMPS (1 nota
  informativa, 2 solo hospitales, 3 valorar tratamiento alternativo,
  4 desabastecimiento temporal, 5 existe alternativa con mismo p.activo,
  6 existen alternativas con mismos p.activos, 7 medicamento extranjero,
  8 prescripcion restringida, 9 distribucion controlada).
- `fini` / `ffin` (epoch ms): inicio y fin previsto del problema.
- `activo` (bool), `observ` (str).

Fuente: AEMPS CIMA Problemas Suministro v1.01 — `GET /cima/rest/psuministro`
y `GET /cima/rest/psuministro/v2/cn/{cn}` (con fallback v1 si v2 falla).
"""

problemas_suministro_dcp_description = """\
Resumen de presentaciones comercializadas y con problemas de suministro
activos para un DCP (Descripcion Clinica del Producto: principio activo
+ dosis + forma sin formato).

Cuando usar: trabajas con codigos clinicos DCP en lugar de Codigo
Nacional y quieres saber, agregando todas las presentaciones de ese
DCP, cuantas estan comercializadas y cuantas tienen problema activo.

Parametro:
- `cod_dcp` (str, obligatorio, solo digitos): codigo DCP AEMPS.

Respuesta:
- `comercializados` (int): n.o de presentaciones comercializadas.
- `con_psuministro` (int): n.o de presentaciones con problema de
  suministro activo.

Fuente: AEMPS CIMA Problemas Suministro v1.01 —
`GET /cima/rest/psuministro/v2/dcp/{cod_dcp}`.
"""

problemas_suministro_dcpf_description = """\
Resumen de presentaciones comercializadas y con problemas de suministro
activos para un DCPF (Descripcion Clinica del Producto con Formato:
principio activo + dosis + forma farmaceutica especifica).

Cuando usar: trabajas con codigos clinicos DCPF (mas especificos que el
DCP) y quieres el agregado por presentacion comercializada / con
problema activo.

Parametro:
- `cod_dcpf` (str, obligatorio, solo digitos): codigo DCPF AEMPS.

Respuesta:
- `comercializados` (int)
- `con_psuministro` (int)

Fuente: AEMPS CIMA Problemas Suministro v1.01 —
`GET /cima/rest/psuministro/v2/dcpf/{cod_dcpf}`.
"""

doc_secciones_description = """\
Metadatos de las secciones disponibles para un tipo de documento de
uno o varios medicamentos. NO incluye el contenido — usa
`doc_contenido` para descargarlo.

Cuando usar: quieres saber que secciones existen (numero, titulo,
orden) en la ficha tecnica o prospecto antes de pedir el contenido,
o necesitas comparar disponibilidad de secciones entre medicamentos.

Parametros:
- `tipo_doc` (int, obligatorio):
  - 1 Ficha Tecnica
  - 2 Prospecto
  - 3 Informe Publico de Evaluacion (IPE)
  - 4 Plan de Gestion de Riesgos (PGR)
- `nregistro` (list[str], opcional): uno o varios numeros de registro.
- `cn` (list[str], opcional): uno o varios Codigos Nacionales (el
  wrapper resuelve CN -> nregistro automaticamente).

Se requiere al menos uno entre `nregistro` o `cn`.

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/secciones/{tipoDoc}`.
"""

doc_contenido_description = """\
Contenido de una seccion (o todas) de un documento segmentado: ficha
tecnica o prospecto.

Cuando usar: ya sabes que seccion necesitas (p.ej. `4.2` posologia) y
quieres su contenido textual. Si `seccion` se omite, devuelve TODAS
las secciones.

Parametros:
- `tipo_doc` (int, obligatorio): 1 Ficha Tecnica, 2 Prospecto.
- `nregistro` (str, opcional, digitos) o `cn` (str, opcional, digitos).
  Se requiere uno de los dos; si se da `cn`, se resuelve a `nregistro`.
- `seccion` (str, opcional): ID de la seccion (`N` o `N.N`, p.ej.
  `"4.2"`). Si vacio, devuelve todas las secciones.
- `format` (str, opcional, defecto `json`): `json` (estructurado),
  `html` (solo HTML del contenido) o `txt` (texto plano).

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/docSegmentado/contenido/{tipoDoc}`.
"""

listar_notas_description = """\
Notas de seguridad publicadas por la AEMPS para uno o varios
medicamentos.

Cuando usar: necesitas comprobar si la AEMPS ha emitido alertas /
comunicados de seguridad sobre uno o varios medicamentos concretos.

Parametro:
- `nregistro` (list[str], obligatorio): uno o varios numeros de
  registro. Cada llamada se paraleliza.

Respuesta: `{nregistro: [notas...], ...}` mas un objeto `errores` con
los registros que fallaron. Cada nota incluye `num`, `ref`, `asunto`,
`fecha` (epoch ms) y `url` oficial AEMPS.

Fuente: AEMPS CIMA REST API v1.23 — `GET /cima/rest/notas/{nregistro}`.
"""

obtener_notas_description = listar_notas_description  # alias backward-compat

listar_materiales_description = """\
Materiales informativos de seguridad asociados a uno o varios
medicamentos (documentos para pacientes y profesionales sanitarios,
videos formativos, etc.).

Cuando usar: necesitas comprobar materiales de minimizacion de riesgos
o documentacion educativa que la AEMPS asocia a un medicamento.

Parametro:
- `nregistro` (list[str], obligatorio): uno o varios numeros de
  registro. Cada llamada se paraleliza.

Respuesta: lista plana con los materiales encontrados. Cada elemento
trae `titulo`, `listaDocsPaciente`, `listaDocsProfesional` y, si
aplica, `video`.

Fuente: AEMPS CIMA REST API v1.23 —
`GET /cima/rest/materiales/{nregistro}`.
"""

obtener_materiales_description = listar_materiales_description  # alias

html_ft_description = """\
HTML completo de la ficha tecnica de un medicamento.

Cuando usar: necesitas el documento integro (no segmentado por
secciones) para mostrarlo al usuario o para procesamiento downstream.
Si solo quieres una seccion concreta, prefiere `doc_contenido`.

Parametros:
- `nregistro` (str, obligatorio): numero de registro AEMPS.
- `filename` (str, opcional, defecto `FichaTecnica.html`).

Fuente: AEMPS — `GET https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html`.
"""

html_ft_multiple_description = html_ft_description  # alias backward-compat

html_p_description = """\
HTML completo del prospecto de un medicamento.

Cuando usar: necesitas el prospecto integro. Si solo quieres una
seccion, prefiere `doc_contenido(tipo_doc=2, ...)`.

Parametros:
- `nregistro` (str, obligatorio): numero de registro AEMPS.
- `filename` (str, opcional, defecto `Prospecto.html`).

Fuente: AEMPS — `GET https://cima.aemps.es/cima/dochtml/p/{nregistro}/Prospecto.html`.
"""

html_p_multiple_description = html_p_description  # alias backward-compat

system_info_prompt_description = """\
Devuelve `MCP_AEMPS_SYSTEM_PROMPT`: catalogo de herramientas, flujos
recomendados y pautas de respuesta para un agente regulatorio
farmaceutico operando sobre AEMPS / CIMA.

Cuando usar: el cliente MCP quiere reinyectar el prompt base del
servidor (p.ej. tras una compactacion) o exponerlo como contexto
estatico.
"""
