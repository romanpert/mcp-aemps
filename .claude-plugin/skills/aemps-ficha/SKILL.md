---
description: Devuelve secciones específicas de la ficha técnica AEMPS de un medicamento (indicaciones, posología, contraindicaciones, interacciones, etc.). Usa cuando el usuario pregunta "qué dice la ficha de X sobre Y".
---

# /aemps-ficha — Sección de ficha técnica AEMPS

Recibirás del usuario un medicamento + (opcionalmente) la sección concreta en `"$ARGUMENTS"`. Devuelve el contenido textual de la sección.

## Procedimiento

1. **Resuelve identificador** (CN, nregistro, o nombre → busca con `buscar_medicamentos`).
2. **Identifica la sección solicitada**:
   - Si el usuario menciona un número (`4.1`, `4.2`…) → úsalo directamente.
   - Si menciona el concepto en lenguaje natural, mapéalo:
     - "indicaciones" / "para qué sirve" → `4.1`
     - "posología" / "dosis" → `4.2`
     - "contraindicaciones" → `4.3`
     - "advertencias" → `4.4`
     - "interacciones" → `4.5`
     - "embarazo" / "lactancia" → `4.6`
     - "conducción" → `4.7`
     - "reacciones adversas" / "efectos secundarios" → `4.8`
     - "farmacodinámica" / "mecanismo" → `5.1`
     - "farmacocinética" → `5.2`
   - Si no menciona sección → ofrece primero `doc_secciones(tipo_doc=1, nregistro=...)` para listarlas y pregunta cuál.
3. **Llama a `doc_contenido(tipo_doc=1, nregistro=..., seccion="<N.N>", format="json")`** y extrae el texto.
   - Si el usuario quiere el HTML completo (p.ej. para mostrarlo en un visor), usa `format="html"`.
   - Si necesita el texto plano, usa `format="txt"`.

## Formato de salida

- Cita la sección por su número y título oficial.
- Reproduce el texto AEMPS sin parafraseo. Cita literal entre `>` blockquote.
- Al final, enlaza con la URL oficial: `cima://docs/ficha-tecnica/<nregistro>/<seccion>` (recurso) o la URL pública AEMPS.

## Pautas

- Fuente al cierre: `Datos: AEMPS CIMA — Ficha técnica nregistro <X>, sección <N.N>, fecha: <hoy>`.
- Descargo: `Esta información no constituye consejo médico; se proporciona solo a efectos informativos. Consulte siempre a un profesional sanitario.`
- Si la sección está vacía o no existe para ese medicamento, dilo explícitamente y sugiere `doc_secciones` para ver qué secciones tiene.
- Nunca emitas conclusiones clínicas que no estén literalmente en el texto AEMPS.
