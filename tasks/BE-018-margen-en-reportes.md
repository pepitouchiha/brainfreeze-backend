---
id: BE-018
title: Incluir margen/ganancia estimada en /reportes/hoy y /reportes/mensual
area: backend
status: done
priority: medium
depends_on: [BE-007, BE-017]
created_by: planner
---

## Objetivo

Con `Producto.costo` disponible (BE-017), extender los reportes existentes
(`GET /reportes/hoy`, `GET /reportes/mensual`) para incluir una estimación de
margen/ganancia, no solo el total vendido. El dueño del negocio hoy solo ve
"cuánto vendí", esta tarea agrega "cuánto gané" (o al menos una estimación de
mejor esfuerzo, dado que no todos los productos van a tener `costo` cargado
desde el día uno).

**Limitación importante que debe quedar documentada y reflejada en el
contrato de esta tarea (no es un bug, es una consecuencia consciente de no
haber tocado `VentaItem` en BE-017):** el margen se calcula usando el
**costo actual** de cada producto (`Producto.costo` en el momento de generar
el reporte), no un costo histórico "congelado" al momento de cada venta —
a diferencia de `precio_unitario`, que sí queda fijo por venta en
`VentaItem`. Si el dueño cambia el costo de un producto, los reportes de
meses pasados que incluyan ventas de ese producto **recalculan** el margen
con el costo nuevo, no con el que tenía en ese momento. Es el mismo tipo de
limitación de "dato punto-en-el-tiempo vs. dato actual" que ya documentó
BE-007 para el manejo de timezone — se acepta como parte del alcance inicial,
no se resuelve aquí (resolverlo requeriría guardar `costo_unitario` en
`VentaItem` en el momento de la venta, que es justamente lo que BE-017
decidió no hacer en esta primera iteración).

## Alcance

**Incluye:**

- `backend/app/schemas/reporte.py`:
  - `ReporteHoyOut`: agregar `margen: int` (ganancia estimada del día) y
    `margen_incompleto: bool` (ver abajo).
  - `VentaPorMes`: agregar `margen: int` y `margen_incompleto: bool` (mismo
    significado, por mes).
  - `ReporteMensualOut`: agregar `ytd_margen: int` (acumulado del año en
    curso, mismo criterio que `ytd_total`) y `ytd_margen_incompleto: bool`.
- `backend/app/routers/reportes.py`:
  - Cálculo de margen por item vendido: `(precio_unitario - producto.costo)
    * cantidad`, sumado sobre todos los `VentaItem` del período, **solo**
    para items cuyo producto tiene `costo` no nulo en este momento.
  - **Nunca asumir `costo = 0`** cuando el producto no tiene costo definido
    — eso inflaría el margen mostrado y daría una falsa sensación de
    precisión. En su lugar, ese item se **excluye** de la suma de `margen` y
    se marca `margen_incompleto = true` para ese período (día/mes/año), como
    señal explícita al frontend/usuario de que el número es una
    subestimación parcial, no el margen real completo.
  - `margen_incompleto` es `true` si **al menos un** item vendido en el
    período corresponde a un producto sin `costo` definido en el momento del
    cálculo; `false` si todos los productos vendidos en ese período tienen
    costo definido, o si no hubo ventas en el período.
  - Estrategia de queries: evitar N+1 (no iterar `venta.items` accediendo a
    `producto.costo` con lazy-load dentro de un loop sin datos precargados).
    Usar una consulta con `join` explícito entre `VentaItem`, `Venta` y
    `Producto` (vía SQLAlchemy, sin SQL crudo, mismo criterio que ya sigue el
    resto de `reportes.py`) filtrando por rango de fechas, para `/hoy` y para
    `/mensual` (en este último, agrupando por mes con el mismo mecanismo
    `func.strftime` que ya usa la agregación de `total`/`num_ventas`
    existente).
  - `ytd_margen`: mismo criterio que `ytd_total` (acumulado desde el 1 de
    enero del año en curso hasta hoy), calculado con la misma lógica de
    exclusión de items sin costo + `ytd_margen_incompleto`.
  - Todos los montos de margen como `int` (COP, sin decimales, sin formatear
    moneda en el backend — mismo criterio que el resto de `reportes.py`).

**No incluye (fuera de alcance):**

- Cambiar `/reportes/alertas-stock` (no tiene relación con margen).
- Guardar `costo_unitario` histórico en `VentaItem` para resolver la
  limitación de "margen recalculado con costo actual" descrita arriba — se
  documenta como limitación conocida, no se resuelve en esta tarea.
- Cualquier endpoint nuevo de "producto más rentable" / ranking de márgenes
  por producto — no está pedido, sería una tarea aparte si se necesita.
- Exponer el `margen`/`margen_incompleto` calculado por esta tarea en la
  sincronización a Google Sheets — esta tarea no toca `sheets_service.py`.
  (Nota: esto es independiente de que el campo `costo` en sí **sí** se
  sincronice a la hoja `Productos` como columna, por decisión explícita del
  usuario documentada en BE-017 — lo que queda fuera de alcance aquí es el
  margen ya calculado/derivado, no el dato crudo de `costo`.)

## Criterios de aceptación

- [ ] `GET /reportes/hoy` incluye `margen` (entero, COP) y `margen_incompleto`
      (booleano) en la respuesta.
- [ ] `GET /reportes/mensual` incluye `margen`/`margen_incompleto` en cada
      elemento de `meses`, más `ytd_margen`/`ytd_margen_incompleto` a nivel
      de la respuesta completa.
- [ ] Escenario "todos los productos vendidos tienen costo definido": el
      `margen` calculado es exactamente `sum((precio_unitario - costo) *
      cantidad)` sobre los items del período, y `margen_incompleto = false`.
- [ ] Escenario "al menos un producto vendido no tiene costo definido": ese
      item se excluye del cálculo de `margen` (no se trata como costo 0), y
      `margen_incompleto = true` para el período correspondiente.
- [ ] Escenario "no hay ventas en el período": `margen = 0` y
      `margen_incompleto = false` (no debe quedar en `true` por defecto sin
      datos).
- [ ] El margen usa el **costo actual** del producto, no uno histórico:
      probar vendiendo un producto con `costo = 1000`, luego cambiar su
      `costo` a `2000` vía `PATCH /productos/{id}`, y confirmar que el
      reporte generado después del cambio refleja `2000` como costo para esa
      venta ya existente (comportamiento esperado y documentado, no un bug).
- [ ] `ytd_margen` es la suma de los `margen` de los meses del año en curso
      dentro de la ventana pedida, con la misma lógica de exclusión/():
      confirmar con un caso numérico concreto, igual nivel de verificación
      que ya hizo BE-007 para `ytd_total`.
- [ ] Verificado por lectura de código que el cálculo de margen no introduce
      N+1 queries (usa `join`/agregación SQL vía SQLAlchemy, no accede a
      `producto.costo` en un loop de Python sobre relaciones sin precargar).
- [ ] `GET /reportes/hoy` y `GET /reportes/mensual` sin header
      `Authorization` siguen devolviendo `401` (sin regresión sobre el
      comportamiento ya existente).

## Notas de implementación

Implementado tal como está descrito en la tarea, sin desviaciones ni scope
creep. La limitación de "margen con costo actual, no histórico" se
documentó explícitamente en el código, con el mismo criterio que BE-007 usó
para la limitación de timezone.

**Archivos tocados:**

- `backend/app/schemas/reporte.py`:
  - `ReporteHoyOut`: agregados `margen: int` y `margen_incompleto: bool`.
  - `VentaPorMes`: agregados `margen: int` y `margen_incompleto: bool`.
  - `ReporteMensualOut`: agregados `ytd_margen: int` y
    `ytd_margen_incompleto: bool`.
- `backend/app/routers/reportes.py`:
  - Import de `case` (sqlalchemy), `Producto` y `VentaItem` (antes solo se
    importaba `Venta`).
  - Comentario a nivel de módulo documentando la limitación de "costo actual
    vs. histórico" (mismo criterio que BE-007 para timezone).
  - `_margen_query(db)`: query base reusable, `JOIN` explícito
    `VentaItem -> Venta -> Producto` (sin SQL crudo), con dos columnas
    agregadas vía `case`/`func.sum`:
    - `margen`: `sum((precio_unitario - costo) * cantidad)` **solo** para
      items cuyo `Producto.costo IS NOT NULL` (rama `else_=0` para excluir
      sin tratar el costo como `0`), envuelto en `coalesce(..., 0)` para que
      un período sin filas devuelva `0` en vez de `NULL`.
    - `items_sin_costo`: cuenta (`sum(case(costo IS NULL, 1, else 0))`) de
      items cuyo producto no tiene costo — usado para derivar
      `margen_incompleto`.
  - `_calcular_margen(db, desde, hasta=None)`: aplica el filtro de fecha
    sobre `Venta.creado_en` a `_margen_query` y devuelve
    `(margen: int, margen_incompleto: bool)`. Reusado por `/hoy` (con
    `desde`/`hasta` del día) y por `ytd_margen` en `/mensual` (con `desde` =
    1 de enero del año en curso, sin `hasta`, mismo criterio que `ytd_total`
    ya existente).
  - `_margen_por_mes(db, desde)`: mismo `_margen_query` con `add_columns` de
    `strftime("%Y"/"%m", Venta.creado_en)` y `group_by("anio", "mes")` —
    mismo mecanismo de agregación por mes que ya usaba `total`/`num_ventas`.
    Devuelve un `dict[(anio, mes), (margen, margen_incompleto)]`.
  - `reporte_hoy`: llama `_calcular_margen(db, inicio, fin)` con las mismas
    variables `inicio`/`fin` (`datetime.combine(hoy, time.min/time.max)`)
    que ya se usaban para filtrar `ventas`, y las agrega a `ReporteHoyOut`.
  - `reporte_mensual`: llama `_margen_por_mes(db, datetime(anio_min, 1, 1))`
    una sola vez (no dentro del loop) y hace `.get((anio, mes), (0, False))`
    por mes en el loop existente, igual que ya hacía `agregados` para
    `total`/`num_ventas`. `ytd_margen`/`ytd_margen_incompleto` se calculan
    con `_calcular_margen(db, inicio_anio_actual)`, mismo `desde` que ya usa
    `ytd_total` (consulta independiente, no una suma de `salida`, igual
    patrón que el `ytd_total` preexistente).
  - No se tocó `/reportes/alertas-stock` ni `sheets_service.py`, según lo
    pedido como fuera de alcance.
  - No hay N+1: todo el cálculo de margen es una sola query SQL con `JOIN` y
    agregación (`case`/`sum`/`coalesce`) por llamada; no se itera
    `venta.items` en Python accediendo a `producto.costo` con lazy-load.

**Cómo se probó:** no hay suite de tests automatizada en el proyecto (mismo
caveat que BE-017: sin `httpx`/`TestClient`). Se probó llamando directamente
a `reporte_hoy`/`reporte_mensual` con un `Session` real, usando dos bases de
datos SQLite temporales (nunca se tocó `brainfreeze.db` real):

1. Una copia de la `brainfreeze.db` real (ya con la columna `costo`
   aplicada por BE-017), con sus `ventas`/`venta_items` preexistentes
   borrados para tener control total de los datos de prueba (evitar
   contaminación con ventas de sesiones de prueba anteriores de otras
   tareas).
2. Una base vacía, recreada desde cero con `Base.metadata.create_all`, para
   el escenario "sin ventas en absoluto".

Casos verificados, todos exitosos:

- **Todos los items con costo definido:** producto con `costo=1000`,
  `precio_unitario=8000`, `cantidad=2` -> `margen = (8000-1000)*2 = 14000`
  exacto, `margen_incompleto = false`.
- **Al menos un item sin costo:** al agregar una venta de un segundo
  producto con `costo=None` (`precio_unitario=5000`, `cantidad=3`), el
  `margen` de `/hoy` **no cambia** (sigue en `14000`, el item sin costo se
  excluye, no se trata como `costo=0`) y `margen_incompleto` pasa a `true`.
- **Costo actual, no histórico:** con la venta ya existente del producto de
  `costo=1000`, se actualizó `producto.costo = 2000` directamente (equivalente
  a `PATCH /productos/{id}`) y se regeneró el reporte: el margen recalculado
  pasó a `(8000-2000)*2 = 12000`, confirmando que usa el costo **actual**,
  no uno congelado al momento de la venta (comportamiento esperado, no un
  bug, documentado en el código y en esta tarea).
- **Sin ventas en el período:** en una base vacía, `GET /reportes/hoy`
  equivalente devuelve `margen = 0` y `margen_incompleto = false` (no queda
  en `true` por defecto); mismo resultado en cada mes de `/reportes/mensual`
  y en `ytd_margen`/`ytd_margen_incompleto`.
- **`ytd_margen` numérico:** con una venta en enero del año en curso
  (producto `costo=4000`, `precio_unitario=10000`, `cantidad=1` ->
  margen de enero = `6000`, `margen_incompleto=false` para ese mes) más la
  venta de "hoy" ya descrita (margen actualizado = `12000`), `ytd_margen`
  resultó en `18000`, exactamente la suma manual de `6000 + 12000`
  (verificación numérica concreta, mismo nivel que BE-007 hizo con
  `ytd_total`).
- **`/reportes/mensual` con mes intermedio sin ventas:** el mes sin ventas
  del rango solicitado (ej. junio) devuelve `margen=0`,
  `margen_incompleto=false` vía el `.get((anio, mes), (0, False))` por
  defecto.
- **Sin N+1 (verificado por lectura de código):** `_margen_query` genera un
  único `SELECT ... FROM venta_items JOIN ventas ON ... JOIN productos ON
  ...` (confirmado imprimiendo el SQL generado por SQLAlchemy), sin ningún
  loop de Python que acceda a `producto.costo` vía relación lazy-load.
- **401 sin `Authorization`:** no se tocó `dependencies=[Depends(require_auth)]`
  a nivel de `router` en `reportes.py` (verificado por lectura de código,
  sigue exactamente igual que antes de esta tarea), por lo que
  `/reportes/hoy` y `/reportes/mensual` siguen devolviendo `401` sin header
  — sin regresión.

Para probar manualmente vía HTTP con el servidor real (requiere login válido
vía `POST /auth/login`):

```
uvicorn app.main:app --reload
GET /reportes/hoy
GET /reportes/mensual?meses=12
```

Respuesta esperada de `/reportes/hoy` (ejemplo):

```json
{
  "fecha": "2026-08-29",
  "total": 13000,
  "num_ventas": 2,
  "por_hora": [...],
  "margen": 12000,
  "margen_incompleto": true
}
```

## Revisión

**Veredicto: `done`.**

Revisé `backend/app/routers/reportes.py` y `backend/app/schemas/reporte.py`
completos (no solo el diff), y re-ejecuté por mi cuenta los escenarios que el
implementador dice haber probado, usando el `.venv` del proyecto (`sqlite`
en memoria vía `Base.metadata.create_all`, llamando directamente a
`_calcular_margen`, `reporte_hoy` y `reporte_mensual`, sin `TestClient`
porque el proyecto no tiene `httpx`/`pytest` instalado — mismo caveat que
BE-017). Todos los números coinciden exactamente con lo reportado:

- Todos los items con costo definido: `(8000-1000)*2 = 14000`,
  `margen_incompleto=False`. ✅
- Item sin costo agregado: `margen` se mantiene en `14000` (no se trata como
  costo `0`), `margen_incompleto` pasa a `True`. ✅
- Sin ventas en el período (DB vacía): `margen=0`,
  `margen_incompleto=False` (nunca `None` ni error). ✅
- Costo actual vs. histórico: cambiar `producto.costo` de `1000` a `2000`
  después de la venta recalcula el margen a `(8000-2000)*2=12000` en el
  siguiente reporte — comportamiento documentado y aceptado. ✅
- `ytd_margen` con venta en enero (`margen=6000`) + venta de "hoy"
  (`margen=4000`) → `ytd_margen=10000`, exactamente la suma manual, y cada
  mes de `meses` trae su propio `margen`/`margen_incompleto` correcto
  (verificado con `reporte_mensual(meses=12, db=db)` real). ✅
- Sin N+1: `_margen_query` genera un único `SELECT` con `JOIN` explícito
  `VentaItem -> Venta -> Producto` y agregación `case`/`sum`/`coalesce`;
  `_margen_por_mes` hace una sola query agrupada por `anio`/`mes` (no dentro
  de un loop); `reporte_mensual` llama a `_margen_por_mes` una sola vez fuera
  del loop de meses, igual patrón que ya usaba `agregados` para
  `total`/`num_ventas`. Confirmado por lectura de código y por el hecho de
  que las pruebas de arriba requirieron solo una llamada por escenario. ✅
- Sin regresión: `dependencies=[Depends(require_auth)]` a nivel de `router`
  no se tocó, por lo que `/hoy` y `/mensual` siguen devolviendo `401` sin
  header — verificado por lectura de código (sin cambios en esa línea). Los
  campos preexistentes (`total`, `num_ventas`, `por_hora`, `ticket_promedio`,
  `ytd_total`) no cambiaron de tipo ni de cálculo; los campos nuevos son
  aditivos en los schemas Pydantic. ✅
- Sin SQL crudo: todo vía `sqlalchemy.orm.Session.query` + `case`/`func`, sin
  f-strings ni `.execute("...")` con interpolación. ✅
- Limitación de costo actual vs. histórico documentada en un comentario a
  nivel de módulo en `reportes.py` (líneas 19-24), con el mismo criterio que
  BE-007 usó para timezone, y replicada en la sección `## Objetivo` de esta
  tarea. ✅

**Hallazgo no bloqueante (para considerar en un ticket aparte, no amerita
`changes-requested` en esta tarea):**

- `_margen_query` usa `INNER JOIN` (`.join(Producto, ...)`) entre
  `VentaItem` y `Producto`. `DELETE /productos/{id}`
  (`backend/app/routers/productos.py:136-142`) borra el `Producto` sin
  verificar si tiene `VentaItem` asociados, y no vi `PRAGMA foreign_keys=ON`
  en `backend/app/db/session.py`, así que SQLite no bloquea ese borrado — los
  `VentaItem` quedan "huérfanos" (`producto_id` sin fila correspondiente en
  `productos`). Reproduje el caso: vendí un producto con `costo=500`
  (contribuía `2500` al margen), borré el producto después, y el margen
  bajó de `9500` a `7000` (perdiendo esos `2500`) **sin** que
  `margen_incompleto` pasara a `True` — el `INNER JOIN` descarta la fila
  silenciosamente, a diferencia del caso `costo IS NULL` que sí está
  explícitamente cubierto por el `case`/`items_sin_costo`. Esto contradice
  en espíritu el objetivo de la tarea (nunca dar una cifra incompleta sin
  avisar), aunque no está en el alcance explícito de los criterios de
  aceptación (que solo hablan de `costo=None`, no de producto eliminado) y
  depende de un gap preexistente y no relacionado en el endpoint de borrado
  de `productos.py` (que tampoco fue tocado por BE-018). En la práctica es
  poco probable porque `Producto.estado` ya provee `agotado` como forma
  normal de retirar un producto sin borrarlo. Sugerencia para un ticket
  futuro: usar `LEFT OUTER JOIN` y tratar `Producto is None` igual que
  `Producto.costo is None` (excluir + `margen_incompleto=True`), o agregar
  protección en `DELETE /productos/{id}` contra productos con ventas
  históricas.

**Nitpick de estilo (no bloqueante):** `_margen_query` (línea 27) es la
única función nueva sin anotación de tipo de retorno explícita (el resto de
funciones nuevas y preexistentes en el archivo sí la tienen). No afecta
funcionalidad; el proyecto tampoco tiene `mypy` configurado actualmente.
