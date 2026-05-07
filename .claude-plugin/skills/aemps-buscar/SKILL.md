---
description: Localiza un medicamento autorizado en AEMPS por nombre, principio activo, ATC o CN. Usa cuando el usuario describe un fármaco pero no tiene CN/nregistro.
---

# /aemps-buscar — Buscar medicamento AEMPS

Recibirás del usuario una descripción libre tipo `"$ARGUMENTS"`. Tu trabajo es localizar el medicamento dentro del registro CIMA y devolver la ficha mínima útil.

## Procedimiento

1. **Decide el filtro adecuado** según lo que el usuario haya dado:
   - Si parece un Código Nacional (6 dígitos numéricos) → llama directamente a `obtener_presentacion(cn=[...])`.
   - Si parece un nregistro AEMPS (5–6 dígitos, formato registro) → `obtener_medicamento(nregistro=...)`.
   - Si es un nombre comercial o un principio activo → `buscar_medicamentos(nombre=...)` o `buscar_medicamentos(practiv1=...)`. Si la consulta menciona ATC, usa `atc=`.
2. Si el primer filtro no devuelve nada o devuelve >25 resultados, reintenta con el filtro siguiente más probable. Como máximo 3 reintentos antes de pedir aclaración al usuario.
3. Para cada hit (máximo 5 mostrados al usuario), reporta: nombre comercial, principio activo + dosis, forma farmacéutica + vía, laboratorio, estado de comercialización, y `nregistro` / CN.
4. Si hay >5 hits, indica el total y sugiere refinar (filtro adicional).

## Pautas de respuesta

- Cierra siempre con la fuente: `Datos: AEMPS CIMA — fecha: <hoy>`.
- Añade el descargo: `Esta información no constituye consejo médico; se proporciona solo a efectos informativos.`
- Nunca emitas recomendaciones clínicas, diagnóstico ni prescripción.
- Si encuentras flags relevantes (triángulo negro, huérfano, biosimilar, problema de suministro activo), destácalos en la respuesta.

Si necesitas el detalle completo de una presentación tras la búsqueda, llama a `obtener_medicamento(nregistro=...)` con el nregistro del hit más relevante.
