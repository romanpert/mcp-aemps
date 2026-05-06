# app/_prompts_es.py
"""Spanish locale variant of the curated MCP Prompts catalogue.

Sister to ``app/_prompts_en.py``. Both modules export the exact same
public surface (``ALL_PROMPTS``, ``PATIENT_FACING_DISCLAIMER`` and the
9 prompt functions); the dispatcher in ``app/prompts.py`` chooses one
or the other based on ``MCP_AEMPS_LOCALE``.

Why nine prompts: they cover farmacia comunitaria, farmacia
hospitalaria, industria farmacéutica and non-specialist users without
overlapping; all leverage the rich payload of ``obtener_medicamento``
(``docs[]``, ``fotos[]``, ``materialesInf``) instead of treating CIMA
as a thin field lookup. Every patient-facing prompt closes with
``PATIENT_FACING_DISCLAIMER`` (MDR 2017/745 framing — this server is
not a medical device).
"""

from __future__ import annotations

from typing import Awaitable, Callable

PromptFn = Callable[..., Awaitable[str]]


# ---------------------------------------------------------------------------
# Disclaimer block — every patient-facing prompt closes with this
# ---------------------------------------------------------------------------
PATIENT_FACING_DISCLAIMER = """\

---
**Aviso legal**: esta información procede del registro público de
medicamentos autorizados por la AEMPS y se ofrece con fines
informativos. **No sustituye el consejo de un profesional sanitario.**
Para cualquier duda sobre tratamiento, dosis, interacciones o efectos
adversos, consulte a su médico o farmacéutico. El prospecto oficial
está disponible en la web de CIMA: https://cima.aemps.es/
"""


# ---------------------------------------------------------------------------
# 1 · Farmacia comunitaria — identificación rápida desde un código nacional
# ---------------------------------------------------------------------------
async def identificar_cn(cn: str) -> str:
    """Identifica un medicamento a partir de su Código Nacional (CN).

    Caso de uso: farmacia comunitaria. El paciente trae una caja o una
    receta con un CN; el farmacéutico necesita la ficha resumida en una
    sola pantalla — autorización, comercialización, receta, alertas
    activas, suministro, fotos.
    """
    return f"""\
Identifica el medicamento con código nacional {cn}. Sigue **exactamente**
este orden de llamadas a las herramientas mcp-aemps:

1. `obtener_presentacion(cn=["{cn}"])` para resolver el `nregistro`,
   nombre comercial y laboratorio.
2. `obtener_medicamento(nregistro=…)` con el nregistro obtenido.
3. `problemas_suministro(cn=["{cn}"])` para conocer el estado **actual**
   de suministro.
4. Si el campo `notas` del medicamento es `true`:
   `listar_notas(nregistro=[…])` y a continuación
   `obtener_notas(nregistros=[…])` solo para las notas con fecha
   reciente.

Devuelve una **tarjeta resumen** en este orden:

- **Nombre comercial** + laboratorio titular.
- **Presentación**: forma farmacéutica + dosis.
- **Estado regulatorio**: autorizado / suspendido / revocado, fecha.
- **Comercializado**: sí / no.
- **Receta**: sí / no (y si es estupefaciente, psicótropo o requiere
  visado, indícalo).
- **Triángulo negro / huérfano / biosimilar**: solo si aplica alguno.
- **Suministro**: ✅ sin problemas / ⚠️ activo desde {{fini}} ({{observ}}).
- **Alertas de seguridad activas**: lista con fecha + asunto + URL
  AEMPS, o "Sin alertas activas".
- **Imágenes oficiales** (campo `fotos` de la respuesta): incluye las
  URLs distinguiendo `materialas` (caja / envoltorio) y `formafarmac`
  (la pastilla / forma farmacéutica). No descargues, solo enlaza.
- **Documentación AEMPS**: del campo `docs`, lista cada documento por
  `tipo` (1=Ficha Técnica, 2=Prospecto, 3=Informe Público Evaluación,
  4=Plan de gestión de riesgos) con su URL.

No consultes la ficha técnica completa salvo que el usuario la pida
explícitamente — la tarjeta debe caber en una pantalla.
"""


# ---------------------------------------------------------------------------
# 2 · Farmacia comunitaria — búsqueda de equivalencias genéricas
# ---------------------------------------------------------------------------
async def equivalencias_genericas(
    nregistro: str,
    comercializados_solo: bool = True,
) -> str:
    """Encuentra medicamentos equivalentes (mismo principio activo / dosis /
    forma farmacéutica), idealmente comercializados.

    Caso de uso: sustitución durante un desabastecimiento, o consulta
    rápida de alternativas más económicas para el paciente.
    """
    filtro = "1 (solo comercializados)" if comercializados_solo else "0 (autorizados, comercializados o no)"
    return f"""\
Busca alternativas equivalentes al medicamento `nregistro={nregistro}`.
Pasos:

1. `obtener_medicamento(nregistro="{nregistro}")` y extrae:
   - El identificador del primer principio activo (campo
     `principiosActivos[0].id` → úsalo como `idpractiv1`).
   - La dosis (`dosis`) y la forma farmacéutica
     (`formaFarmaceutica.nombre`).
2. `buscar_medicamentos(idpractiv1=…, comerc={filtro})` con `pagina=1`.
   Si el resultado tiene `totalFilas > 25`, llama también con
   `pagina=2` para tener una muestra suficiente.
3. **Filtra los candidatos** quedándote sólo con los que tengan la
   misma dosis y la misma forma farmacéutica que el medicamento
   original. El nombre comercial debe ser distinto del de partida.
4. Para cada candidato superviviente: comprueba el campo `psum`
   (true = problemas de suministro abiertos) y, si está activo, lanza
   `problemas_suministro(nregistro=[…])` para el detalle.

Devuelve una **tabla** con columnas:

| CN | Nombre comercial | Laboratorio | Receta | Suministro | Foto caja |

Donde "Foto caja" es la URL del campo `fotos[]` con `tipo=materialas`
del candidato (la primera si hay varias) — útil para confirmar
visualmente la equivalencia con el paciente.

Si no encuentras alternativas comercializadas, indícalo explícitamente
y sugiere repetir la consulta con `comercializados_solo=false` para
ver toda la cartera autorizada.
"""


# ---------------------------------------------------------------------------
# 3 · Hospital — revisión de farmacovigilancia para una cartera de paciente
# ---------------------------------------------------------------------------
async def vigilancia_paciente(nregistros: list[str]) -> str:
    """Revisión de notas de seguridad activas para todos los medicamentos
    de un paciente.

    Caso de uso: farmacéutico hospitalario o médico revisando la
    cartera de medicación de un paciente — alineado con EMA GVP
    Module VI (signal management).
    """
    if not nregistros:
        return "Error: la lista `nregistros` está vacía."
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Realiza una revisión de farmacovigilancia para los siguientes
números de registro AEMPS: {listado}.

Pasos:

1. `listar_notas(nregistro=[{listado}])` para obtener el índice de
   notas asociadas a cada medicamento.
2. Para cada medicamento que tenga al menos una nota:
   `obtener_notas(nregistros=[…])` con la lista filtrada.
3. **No** consultes la ficha técnica — el objetivo de este flujo es
   solo vigilancia.

Devuelve una **tabla** con columnas:

| Nregistro | Nombre | Nº de notas activas | Última nota (fecha + asunto) | URL AEMPS |

Después de la tabla, agrupa por categoría las notas más relevantes:

- 🔴 **Restricciones de uso / suspensiones**: notas que afecten a
  indicaciones autorizadas.
- 🟡 **Nuevas reacciones adversas / interacciones**: notas que
  añadan información de seguridad sin restringir el uso.
- 🔵 **Informativas / cambios de etiquetado**: actualizaciones
  administrativas.

Para cada nota destacada, incluye su URL completa en CIMA (campo `url`
del objeto `Nota`) para que el clínico pueda descargar el PDF
oficial.

Cierra con un resumen ejecutivo de 2-3 frases sobre el riesgo agregado
de la cartera (por ejemplo: "3 de los 7 medicamentos tienen notas
activas en los últimos 12 meses, una de ellas restrictiva").
"""


# ---------------------------------------------------------------------------
# 4 · Hospital + industria — comparativa sección a sección de fichas técnicas
# ---------------------------------------------------------------------------
async def comparar_fichas_tecnicas(
    nregistros: list[str],
    secciones: str = "4.1, 4.2, 4.3, 4.4, 4.5, 4.8",
) -> str:
    """Compara dos o más medicamentos sección a sección de la ficha técnica.

    Caso de uso: comité de farmacia hospitalaria seleccionando entre
    alternativas terapéuticas; análisis competitivo en industria.
    """
    if len(nregistros) < 2:
        return "Error: se necesitan al menos 2 nregistros para comparar."
    if len(nregistros) > 5:
        return "Error: máximo 5 nregistros simultáneos (limite de tokens del LLM)."
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Compara las fichas técnicas (tipo_doc=1) de los siguientes medicamentos:
{listado}.

Secciones objetivo: {secciones}. Si el usuario no ha indicado lo
contrario, usa esas secciones por defecto:
- 4.1: Indicaciones terapéuticas
- 4.2: Posología y forma de administración
- 4.3: Contraindicaciones
- 4.4: Advertencias y precauciones especiales de empleo
- 4.5: Interacciones
- 4.8: Reacciones adversas

Pasos:

1. Para cada nregistro: `obtener_medicamento(nregistro=…)` para
   resolver el nombre comercial + laboratorio (los necesitas como
   cabeceras de la tabla).
2. Para cada nregistro **y** cada sección pedida:
   `doc_contenido(tipo_doc=1, nregistro=…, seccion="…", format="txt")`.
3. Si la sección no existe para algún medicamento (la API devuelve
   404), márcalo como "—" en la tabla — no es un error fatal.

Devuelve una **tabla wide-format**: filas = secciones, columnas = un
medicamento por columna (cabecera con el nombre comercial). El
contenido de cada celda debe ser un **resumen estructurado en
viñetas** del texto oficial — no copies el texto plano completo, eso
sería ilegible.

Tras la tabla, añade una **sección de divergencias clínicamente
relevantes** (3-5 viñetas) destacando dónde se diferencian los
medicamentos en indicaciones, contraindicaciones críticas o
interacciones mayores.

Cierra con los enlaces a la ficha técnica HTML completa de cada
medicamento (campo `docs[]` con `tipo=1` del objeto Medicamento,
o construye `https://cima.aemps.es/cima/dochtml/ft/{{nregistro}}/FichaTecnica.html`).
"""


# ---------------------------------------------------------------------------
# 5 · Industria — auditoría de la cartera regulatoria de un laboratorio
# ---------------------------------------------------------------------------
async def auditar_cartera_laboratorio(
    laboratorio: str,
    incluir_no_comercializados: bool = False,
) -> str:
    """Snapshot de la cartera regulatoria de un laboratorio titular.

    Caso de uso: business intelligence pharma, due diligence,
    benchmarking competitivo.
    """
    filtro_comerc = "1" if not incluir_no_comercializados else "0"
    return f"""\
Audita la cartera del laboratorio titular **"{laboratorio}"**. Pasos:

1. `buscar_medicamentos(laboratorio="{laboratorio}", autorizados=1, comerc={filtro_comerc}, pagina=1)`.
   Si `totalFilas > 25`, recoge las páginas 2 y 3 también (máximo 75
   medicamentos para mantener el coste de tokens acotado).
2. Para una **muestra de 20 medicamentos** representativa (variedad
   de áreas terapéuticas si es posible), llama a
   `obtener_medicamento(nregistro=…)` para enriquecer.
3. Para los medicamentos con `notas=true`: `listar_notas(nregistro=[…])`.
4. Para los medicamentos con `psum=true`: ya viene marcado, no hace
   falta llamada extra.

Devuelve un **dashboard** con estos bloques:

### 1. Métricas globales
- Total medicamentos autorizados.
- % comercializados.
- % con problemas de suministro abiertos (`psum=true`).
- % con notas de seguridad asociadas (`notas=true`).
- % con materiales informativos (`materialesInf=true`).
- % con Informe Público de Evaluación (IPE/IPT) en `docs[]` con
  `tipo=3` — **señal de impacto regulatorio alto**, AEMPS solo lo
  publica para principios activos prioritarios.
- % con Plan de Gestión de Riesgos en `docs[]` con `tipo=4`.

### 2. Áreas terapéuticas
Agregado por código ATC nivel 1 (campo `atcs[].codigo` truncado al
primer carácter): cuántos medicamentos por área.

### 3. Medicamentos con triángulo negro
Lista (con tabla simple: nregistro, nombre, fecha autorización) — son
medicamentos sujetos a seguimiento adicional, dato relevante para
farmacovigilancia.

### 4. Top 5 con más notas activas
Tabla: nregistro, nombre, nº de notas, fecha de la más reciente.

### 5. Riesgos abiertos de suministro
Lista de medicamentos comercializados con `psum=true`, con CN, nombre
y `fini`/`ffin` del problema de suministro.

Cierra con un breve análisis (3-5 frases) del **perfil regulatorio
agregado**: especialización terapéutica, madurez de la cartera
(¿muchas autorizaciones recientes?, ¿muchos huérfanos?), exposición a
problemas de suministro, presencia en líneas de tratamiento
prioritarias para el sistema (presencia de IPT).
"""


# ---------------------------------------------------------------------------
# 6 · Industria — monitorización de cambios regulatorios sobre una cartera
# ---------------------------------------------------------------------------
async def monitorizar_cambios_cartera(
    nregistros: list[str],
    desde_fecha: str = "",
) -> str:
    """Detecta cambios regulatorios (alta, baja, modificación) sobre una
    lista de medicamentos en un periodo dado.

    Caso de uso: regulatory affairs revisando mensualmente su cartera.
    """
    if not nregistros:
        return "Error: la lista `nregistros` está vacía."
    if len(nregistros) > 50:
        return "Error: máximo 50 nregistros por consulta (limite operativo)."
    fecha_arg = (
        f'fecha="{desde_fecha}"'
        if desde_fecha
        else 'fecha=""  # opcional; sin fecha CIMA devuelve los cambios recientes'
    )
    listado = ", ".join(f'"{n}"' for n in nregistros)
    return f"""\
Monitoriza los cambios regulatorios de los siguientes medicamentos en
el periodo solicitado: {listado}.

Pasos:

1. `registro_cambios({fecha_arg}, nregistro=[{listado}], metodo="POST")`.
   El método POST es obligatorio cuando se envía una lista larga de
   nregistros (la URL GET excedería la longitud máxima).
2. Por cada cambio detectado, identifica el `tipoCambio`:
   - 1: Nuevo (alta).
   - 2: Baja (revocación o suspensión).
   - 3: Modificado.
3. Para los cambios tipo 3 (modificación), revisa el array `cambios`
   para entender qué cambió: `estado`, `comerc`, `prosp` (prospecto),
   `ft` (ficha técnica), `psum` (suministro), `notasSeguridad`,
   `matinf` (materiales informativos), `otros`.
4. Para los cambios que incluyan `notasSeguridad`:
   `obtener_notas(nregistros=[<el medicamento afectado>])` para traer
   el contexto de la nota.

Devuelve la salida en este formato:

### Resumen ejecutivo
- Total cambios en el periodo.
- Desglose por tipo (Alta / Baja / Modificación).
- Medicamentos afectados (cuántos de los {len(nregistros)} consultados).

### Cronología (más reciente primero)
Una entrada por cambio, con esta estructura:

```
📅 {{fecha}} · {{nregistro}} {{nombre}}
   Tipo: {{Alta|Baja|Modificación}}
   Cambios: {{lista de campos que cambiaron, en español: "Ficha técnica",
            "Prospecto", "Estado de comercialización", "Notas de seguridad", …}}
   Si hay nota de seguridad asociada → resumen de 1 línea + URL AEMPS.
```

### Acciones sugeridas
2-3 viñetas con qué requeriría seguimiento inmediato (cambios en FT
o estado, notas de seguridad nuevas).

Si **no hay cambios** en el periodo, indícalo claramente con la fecha
de la última verificación y sugiere reintentar más adelante.
"""


# ---------------------------------------------------------------------------
# 7 · Hospital + industria — Informe de Posicionamiento Terapéutico (IPT/IPE)
# ---------------------------------------------------------------------------
async def informe_posicionamiento_terapeutico(nregistro: str) -> str:
    """Recupera y resume el Informe Público de Evaluación (IPE/IPT) y la
    indicación autorizada de un medicamento.

    Caso de uso: comité de farmacia hospitalaria evaluando inclusión
    en la guía farmacoterapéutica; market access en industria.
    """
    return f"""\
Recupera el Informe de Posicionamiento Terapéutico para el medicamento
`nregistro={nregistro}` y compleméntalo con la indicación autorizada.

Pasos:

1. `obtener_medicamento(nregistro="{nregistro}")` y extrae:
   - Nombre comercial, laboratorio, principios activos, ATC.
   - El array `docs[]`. **Busca específicamente** el documento con
     `tipo=3` (Informe Público Evaluación, equivalente al IPT/IPE).
   - Anota también si existen `tipo=4` (Plan de Gestión de Riesgos),
     `tipo=1` (Ficha Técnica), `tipo=2` (Prospecto).
2. `doc_contenido(tipo_doc=1, nregistro="{nregistro}", seccion="4.1", format="txt")`
   para traer la **indicación terapéutica oficial** (sección 4.1 de la FT).
3. `doc_contenido(tipo_doc=1, nregistro="{nregistro}", seccion="5.1", format="txt")`
   para las **propiedades farmacodinámicas / mecanismo de acción**
   (sección 5.1 — útil para contextualizar el IPT).
4. Si el medicamento tiene `notas=true`:
   `listar_notas(nregistro=["{nregistro}"])` y, si hay activas,
   `obtener_notas(nregistros=["{nregistro}"])` (una nota posterior
   al IPT puede modificar el posicionamiento).

Devuelve la salida con esta estructura:

### Identificación
Nombre comercial · Laboratorio · Principio activo · Código ATC.

### Indicación autorizada (FT 4.1)
Resumen estructurado de la sección 4.1, con viñetas para cada
indicación si hay varias.

### Mecanismo de acción (FT 5.1)
Resumen breve (3-5 frases) de la farmacodinámica.

### Informe de Posicionamiento Terapéutico
- Si el medicamento tiene IPT (`docs[]` con `tipo=3`): indica
  fecha del documento y la URL completa para descargar el PDF.
  **No intentes descargar el PDF** — el IPT no está en el endpoint
  de documentos segmentados, solo está disponible como PDF en la URL
  proporcionada por la API.
- Si **no** tiene IPT publicado: indícalo explícitamente. La
  ausencia de IPT no implica falta de eficacia — AEMPS solo
  publica IPT para medicamentos seleccionados (innovaciones de
  alto impacto presupuestario, biosimilares en sus primeras
  inclusiones, principios activos huérfanos seleccionados).

### Documentación adicional disponible
Lista los demás documentos del array `docs[]` (FT, Prospecto, Plan de
Gestión de Riesgos) con sus URLs.

### Notas de seguridad posteriores
Si las hay, lista cronológica con fecha + asunto + URL. Marca con ⚠️
las que puedan afectar al posicionamiento (restricciones de uso,
nuevas contraindicaciones).

Cierra con una nota de uso: "El IPT representa el posicionamiento
oficial del Ministerio de Sanidad/AEMPS en el momento de su
publicación. Verifique siempre la fecha y la existencia de notas
posteriores que puedan haber actualizado el criterio."
"""


# ---------------------------------------------------------------------------
# 8 · Farmacia + paciente — kit visual y multimedia para counseling
# ---------------------------------------------------------------------------
async def material_visual_paciente(nregistro: str) -> str:
    """Reúne el material visual y multimedia oficial de un medicamento para
    explicárselo a un paciente: fotos de la caja y de la forma
    farmacéutica, vídeos de uso (inhaladores, plumas, autoinyectores),
    material informativo segregado por audiencia.

    Caso de uso: farmacia comunitaria u hospital — counseling al
    paciente sobre cómo usar correctamente un dispositivo de
    administración complejo.
    """
    return f"""\
Reúne el material visual y multimedia oficial AEMPS del medicamento
`nregistro={nregistro}` para counseling al paciente.

Pasos:

1. `obtener_medicamento(nregistro="{nregistro}")` y extrae:
   - Nombre comercial, presentación, forma farmacéutica.
   - El array `fotos[]`: cada entrada tiene `tipo` (`materialas` =
     foto de la caja / acondicionamiento secundario,
     `formafarmac` = foto de la forma farmacéutica) y `url`.
   - El flag `materialesInf` (booleano).
2. **Solo si** `materialesInf == true`:
   - `listar_materiales(nregistro=["{nregistro}"])` para confirmar
     la disponibilidad.
   - `obtener_materiales(nregistro="{nregistro}")` para traer el
     contenido completo: `listaDocsPaciente[]`,
     `listaDocsProfesional[]`, y muy importante el campo `video`
     (URL — solo presente cuando el material está disponible en
     formato vídeo, típico de inhaladores, dispositivos de
     insulina, autoinyectores tipo EpiPen, plumas
     precargadas, etc.).
3. **No descargues** las imágenes ni los PDFs — limita la salida a
   las URLs oficiales de AEMPS (los clientes MCP las renderizan
   directamente cuando saben).

Devuelve la salida con esta estructura:

### Identificación rápida
Nombre comercial · Forma farmacéutica · Dosis.

### 📷 Imágenes oficiales
- **Caja / envoltorio** (`tipo=materialas`): {{URL}}
- **Forma farmacéutica** (`tipo=formafarmac`): {{URL}}

(Si solo hay una de las dos, indícalo. Si no hay imágenes en absoluto,
indica "Sin imágenes oficiales disponibles".)

### 📄 Material informativo para el paciente
Si `listaDocsPaciente` tiene contenido: lista cada documento con su
nombre y URL oficial. Estos son los materiales redactados
específicamente para que el paciente entienda cómo usar el
medicamento (no son el prospecto — son guías visuales / pictogramas /
tarjetas de paciente que la AEMPS exige a los laboratorios para
ciertos productos de uso complejo o riesgo).

### 🎥 Vídeo de instrucciones
Si el campo `video` está presente: incluye la URL como enlace
destacado. Indica brevemente qué tipo de dispositivo cubre (inhalador,
pluma, autoinyector, etc.) infiriéndolo del nombre y la forma
farmacéutica.

### 📋 Material para el profesional sanitario (referencia)
Si `listaDocsProfesional` tiene contenido: lista breve. Estos
materiales no van al paciente, pero el farmacéutico puede consultarlos.

### Sin material multimedia disponible
Si `materialesInf == false` y no hay `fotos[]`, indica que para este
medicamento la AEMPS no exige material visual adicional al prospecto
estándar. Sugiere revisar la sección 6.6 de la ficha técnica
("Precauciones especiales de eliminación y manipulación") para
instrucciones de uso.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# 9 · No-especialista — resumen llano + alertas + disclaimer obligatorio
# ---------------------------------------------------------------------------
async def info_medicamento_para_no_sanitarios(nombre_o_cn: str) -> str:
    """Resumen en lenguaje llano de un medicamento para un usuario no
    sanitario (paciente, periodista, programador construyendo sobre el
    server). Incluye fotos, alertas activas y disclaimer obligatorio.

    Caso de uso: usuario general que ha oído hablar de un medicamento
    y quiere entender qué es. **Crítico**: el prompt instruye al LLM a
    NUNCA dar consejo médico — todo termina con "consulte a su médico
    o farmacéutico".
    """
    return f"""\
El usuario quiere información sobre el medicamento "{nombre_o_cn}".
Este flujo está pensado para una **persona sin formación sanitaria**
(paciente, familiar, periodista). El registro y el lenguaje deben
ser accesibles, sin jerga médica.

Pasos:

1. Determina si "{nombre_o_cn}" es un código nacional (todo dígitos)
   o un nombre comercial:
   - Si numérico: `obtener_presentacion(cn=["{nombre_o_cn}"])` →
     extrae el `nregistro`.
   - Si texto: `buscar_medicamentos(nombre="{nombre_o_cn}", pagina=1)`.
     Toma el primer resultado **comercializado** (`comerc=true`); si
     no hay ninguno comercializado, toma el primer autorizado.
     Extrae su `nregistro`.
2. `obtener_medicamento(nregistro=…)` para traer la ficha completa.
3. `doc_contenido(tipo_doc=2, nregistro=…, seccion="2", format="txt")`
   para la sección 2 del **prospecto** ("Qué es y para qué se utiliza").
   Esta sección está redactada para pacientes — es la fuente correcta
   para una explicación llana, no la ficha técnica (que está escrita
   para profesionales sanitarios).
4. Si el medicamento tiene `notas=true`:
   `listar_notas(nregistro=[…])` y, si hay alertas activas recientes,
   `obtener_notas(nregistros=[…])`.

Devuelve la salida en **5 bloques cortos**, sin tecnicismos:

### 💊 Qué es
Una frase identificando el medicamento (nombre comercial + para qué
se prescribe en términos generales). No menciones principios activos
salvo que sean necesarios para entender la indicación.

### 🩺 Para qué se usa
Resumen llano de la sección 2 del prospecto, en 3-5 viñetas. Si la
sección 2 menciona indicaciones técnicas, "tradúcelas" a lenguaje
cotidiano.

### 📷 Cómo es
Si hay fotos disponibles (`fotos[]` del medicamento): incluye URLs.
Una de la **caja** (`tipo=materialas`) y otra de la **pastilla**
(`tipo=formafarmac`), si existen ambas. Esto ayuda al usuario a
confirmar visualmente que es el producto correcto.

### ⚠️ Alertas oficiales activas
Si hay notas de seguridad activas: lista cada una con fecha + un
resumen de **una frase** del asunto + la URL al PDF oficial AEMPS.
Si **no** hay alertas activas, indícalo explícitamente: "No hay
alertas de seguridad activas publicadas por la AEMPS para este
medicamento a la fecha de la consulta".

### 📚 Dónde leer más
- Enlace al **prospecto completo** (campo `docs[]` con `tipo=2`, o
  construye `https://cima.aemps.es/cima/dochtml/p/{{nregistro}}/Prospecto.html`).
- Enlace a la página oficial del medicamento en CIMA:
  `https://cima.aemps.es/cima/publico/detalle.html?nregistro={{nregistro}}`.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# 10 · Hospital + farmacia + paciente — interacciones documentadas en FT 4.5
# ---------------------------------------------------------------------------
async def comprobar_interaccion_principios_activos(
    principios_activos: list[str],
) -> str:
    """Comprueba si la sección 4.5 (Interacciones) de las fichas técnicas
    AEMPS menciona interacciones cruzadas entre los principios activos
    indicados.

    Caso de uso: revisión preliminar de interacciones para una
    combinación de fármacos. **NO sustituye una herramienta clínica
    formal de detección de interacciones** (BOT PLUS, Lexicomp,
    Stockley, Micromedex, etc.) — solo busca menciones textuales en la
    documentación oficial AEMPS, lo que es un lower bound, no un
    upper bound, de las interacciones potenciales.
    """
    if len(principios_activos) < 2:
        return "Error: se necesitan al menos 2 principios activos para buscar interacciones."
    if len(principios_activos) > 5:
        return "Error: máximo 5 principios activos por consulta (límite de tokens)."
    listado = ", ".join(f'"{p}"' for p in principios_activos)
    n_pares = len(principios_activos) * (len(principios_activos) - 1) // 2
    return f"""\
Comprueba interacciones potenciales **documentadas en fichas técnicas
AEMPS** entre los siguientes principios activos: {listado}.

Pasos:

1. Para cada principio activo, localiza un medicamento representativo
   comercializado:
   `buscar_medicamentos(practiv1="<principio>", comerc=1, pagina=1)`.
   Toma el primer resultado y guarda su `nregistro` y `nombre`.

2. Para cada pareja de principios activos (A, B), busca menciones
   cruzadas en la sección 4.5 (Interacciones) de la ficha técnica:
   `buscar_en_ficha_tecnica(reglas=[
       {{"seccion": "4.5", "texto": "<principio_B>", "contiene": 1}}
   ])`. Repite con A y B intercambiados (la mención puede estar solo
   en una dirección).

3. Para cada medicamento que aparezca como match: extrae el párrafo
   relevante de la sección 4.5:
   `doc_contenido(tipo_doc=1, nregistro="<nregistro>", seccion="4.5", format="txt")`.
   Recorta a las 3-6 frases que mencionan el otro principio activo
   (no copies la sección entera, suele ser muy larga).

Devuelve la salida con esta estructura:

### Resumen
- Combinaciones revisadas: {n_pares}.
- Interacciones documentadas en FT AEMPS: N.

### Detalle por combinación
Para cada par A↔B, una sub-sección:

#### A ↔ B
- ✅ "Sin menciones cruzadas en sección 4.5 de las fichas técnicas
  consultadas" — si no hay nada.
- ⚠️ Si hay menciones: para cada match, indica:
  - Medicamento: nombre comercial · nregistro · laboratorio.
  - Párrafo relevante (3-6 frases) de la sección 4.5.
  - URL a la FT completa.

### ⚠️ Limitaciones (CRÍTICO — incluir SIEMPRE)
- Esta búsqueda solo cubre menciones textuales en la sección 4.5 de
  la ficha técnica oficial AEMPS de **un medicamento representativo**
  por principio activo. **NO sustituye** una herramienta clínica
  formal de detección de interacciones (BOT PLUS / Bot Plus Web,
  Lexicomp, Stockley's Drug Interactions, Micromedex, UpToDate
  Lexicomp).
- **Una ausencia de mención NO implica ausencia de interacción** —
  significa solo que el medicamento concreto consultado no la
  documenta en su FT. Otros medicamentos con el mismo principio
  activo pueden documentarla.
- Las interacciones farmacocinéticas / farmacodinámicas dependen de
  dosis, vía, paciente, función renal/hepática, comorbilidad,
  polifarmacia. **Siempre consulta a un farmacéutico clínico o
  médico** antes de tomar decisiones de prescripción, sustitución o
  desprescripción.
{PATIENT_FACING_DISCLAIMER}"""


# ---------------------------------------------------------------------------
# Public API — register all prompts onto a FastMCP server instance
# ---------------------------------------------------------------------------
ALL_PROMPTS: tuple[tuple[str, str, PromptFn], ...] = (
    (
        "identificar_cn",
        "Identifica un medicamento por su Código Nacional (CN) y devuelve "
        "una tarjeta resumen lista para mostrar en mostrador de farmacia: "
        "nombre, presentación, autorización, comercialización, alertas "
        "activas, suministro, fotos oficiales y enlaces a documentación "
        "AEMPS. Caso de uso: farmacia comunitaria.",
        identificar_cn,
    ),
    (
        "equivalencias_genericas",
        "Encuentra medicamentos equivalentes (mismo principio activo, "
        "dosis y forma farmacéutica) a partir de un nregistro AEMPS, "
        "filtrando por comercializados con problemas de suministro "
        "actualizados. Caso de uso: sustitución durante desabastecimiento.",
        equivalencias_genericas,
    ),
    (
        "vigilancia_paciente",
        "Revisión de notas de seguridad AEMPS activas para una lista de "
        "nregistros (la cartera de medicación de un paciente). Agrupa por "
        "criticidad y enlaza el PDF oficial. Caso de uso: farmacia "
        "hospitalaria, alineado con EMA GVP Module VI.",
        vigilancia_paciente,
    ),
    (
        "comparar_fichas_tecnicas",
        "Compara dos o más medicamentos sección a sección de la ficha "
        "técnica (4.1 Indicaciones, 4.2 Posología, 4.3 Contraindicaciones, "
        "4.4 Advertencias, 4.5 Interacciones, 4.8 Reacciones adversas por "
        "defecto). Devuelve tabla wide-format. Caso de uso: comité de "
        "farmacia hospitalaria, análisis competitivo en industria.",
        comparar_fichas_tecnicas,
    ),
    (
        "auditar_cartera_laboratorio",
        "Snapshot regulatorio completo de la cartera de un laboratorio "
        "titular: métricas globales, áreas terapéuticas (ATC), triángulo "
        "negro, top 5 con notas activas, riesgos abiertos de suministro, "
        "presencia de Informe de Posicionamiento Terapéutico (IPT). Caso "
        "de uso: business intelligence pharma, due diligence.",
        auditar_cartera_laboratorio,
    ),
    (
        "monitorizar_cambios_cartera",
        "Detecta cambios regulatorios (alta, baja, modificación de FT, "
        "prospecto, comercialización, notas de seguridad) sobre una lista "
        "de nregistros desde una fecha dada. Caso de uso: regulatory "
        "affairs revisando mensualmente.",
        monitorizar_cambios_cartera,
    ),
    (
        "informe_posicionamiento_terapeutico",
        "Recupera el Informe Público de Evaluación (IPE/IPT) de un "
        "medicamento (cuando AEMPS lo ha publicado), junto con la "
        "indicación autorizada (FT 4.1) y el mecanismo de acción (FT 5.1). "
        "Indica claramente si el IPT no existe — su ausencia no implica "
        "falta de eficacia. Caso de uso: comité de farmacia hospitalaria, "
        "market access en industria.",
        informe_posicionamiento_terapeutico,
    ),
    (
        "material_visual_paciente",
        "Reúne el material visual y multimedia oficial AEMPS de un "
        "medicamento: fotos de la caja y de la forma farmacéutica, "
        "vídeos de uso (inhaladores, plumas de insulina, autoinyectores), "
        "material informativo segregado por audiencia (paciente vs "
        "profesional sanitario). Caso de uso: counseling al paciente.",
        material_visual_paciente,
    ),
    (
        "info_medicamento_para_no_sanitarios",
        "Resumen en lenguaje llano de un medicamento para un usuario sin "
        "formación sanitaria (paciente, familiar, periodista, programador "
        "construyendo sobre el server). 5 bloques: qué es, para qué se usa, "
        "cómo es (fotos), alertas activas, dónde leer más. Cierra con "
        "disclaimer obligatorio: no es consejo médico. Caso de uso: "
        "público general que quiere entender un medicamento sin pedirle "
        "al LLM que actúe como consultor clínico.",
        info_medicamento_para_no_sanitarios,
    ),
    (
        "comprobar_interaccion_principios_activos",
        "Comprueba si la sección 4.5 (Interacciones) de las fichas técnicas "
        "AEMPS menciona interacciones cruzadas entre 2-5 principios activos. "
        "Es una búsqueda textual sobre documentación oficial — NO sustituye "
        "una herramienta clínica formal (BOT PLUS, Lexicomp, Stockley, "
        "Micromedex). Caso de uso: revisión preliminar de polifarmacia en "
        "farmacia hospitalaria, validación de combinaciones para protocolos.",
        comprobar_interaccion_principios_activos,
    ),
)
