---
description: Resumen de alertas regulatorias AEMPS para uno o varios medicamentos: notas de seguridad, problemas de suministro y cambios recientes. Usa cuando el usuario quiere "estado regulatorio" o "alertas" de un fármaco.
---

# /aemps-vigilancia — Vigilancia regulatoria AEMPS

Recibirás del usuario uno o más identificadores (nregistro, CN o nombre del medicamento) en `"$ARGUMENTS"`. Devuelve un panel resumido de su estado regulatorio actual.

## Procedimiento

1. **Resuelve el identificador** a uno o varios `nregistro` AEMPS:
   - Si el input es nregistro o CN → úsalo directamente (`obtener_medicamento`/`obtener_presentacion`).
   - Si es texto libre → usa `buscar_medicamentos(nombre=...)`. Si hay >1 hit, pide al usuario que confirme antes de seguir.
2. **Notas de seguridad**: `listar_notas(nregistro=[<lista>])`. Reporta `num`, `ref`, `asunto`, `fecha` y la URL oficial AEMPS de cada nota. Si no hay notas, dilo explícitamente — la ausencia es información útil.
3. **Problemas de suministro activos**: `problemas_suministro(nregistro=[<lista>])`. Reporta `tipoProblemaSuministro`, fechas de inicio/fin, `activo`, observaciones. Indica el tipo en lenguaje natural (p.ej. tipo 4 = "Desabastecimiento temporal").
4. **Cambios regulatorios recientes**: `registro_cambios(nregistro=[<lista>])`. Filtra los últimos 90 días y agrupa por `tipoCambio` (1=Nuevo, 2=Baja, 3=Modificado) con las etiquetas `cambios` traducidas (`ft`=Ficha técnica, `prosp`=Prospecto, etc.).
5. **Materiales informativos** (opcional, solo si el usuario lo pide): `listar_materiales(nregistro=[<lista>])`.

## Formato de salida

Estructura por medicamento:

```
### <Nombre comercial> (nregistro <X>)
- Notas de seguridad: <N> activas, última: <fecha> — <asunto>
- Problemas de suministro: <activo|sin problemas>, tipo <N> — <fini> a <ffin>
- Cambios últimos 90 días: <resumen>
- Materiales informativos: <enlace o "ninguno">
```

## Pautas de respuesta

- Fuente al cierre: `Datos: AEMPS CIMA — fecha: <hoy>`.
- Descargo: `Esta información no constituye consejo médico; se proporciona solo a efectos informativos.`
- Nunca emitas recomendaciones clínicas. Las notas de seguridad se citan, no se interpretan.
- Si el usuario está oncall / responsable regulatorio, prioriza desabastecimientos activos y notas con `fecha` reciente al inicio del informe.
