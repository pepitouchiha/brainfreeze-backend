---
id: BE-017
title: Agregar costo de compra/producción a Producto (base para calcular margen)
area: backend
status: done
priority: medium
depends_on: [BE-003]
created_by: planner
---

## Objetivo

Hoy el sistema solo registra el precio de **venta** de un producto
(`Producto.precio`) y, en cada venta, el precio de venta vigente en ese
momento (`VentaItem.precio_unitario`). No existe ningún dato de cuánto le
cuesta al negocio comprar o producir ese producto, así que es imposible
calcular margen/ganancia — solo se sabe cuánto se vendió, no cuánto costó.

**Decisión de alcance (tomada por el planner, documentada para que quede
registrada igual que el patrón de BE-012):** existen dos formas de trackear
el costo — (a) un campo `costo` directo en `Producto` (precio de compra o
producción, unitario, simple), o (b) un modelo de receta/BOM (`Insumo.costo_unitario`
+ tabla de relación producto↔insumos con cantidades, para derivar el costo del
producto sumando sus insumos). Se elige la opción **(a)** como alcance
inicial: hoy `Producto` e `Insumo` son entidades completamente independientes
(no existe ninguna relación entre ellas en el modelo de datos), un insumo no
se descuenta automáticamente al vender un producto, y el stock de insumos se
ajusta manualmente vía `POST /insumos/{id}/ajustar-stock`. Construir una
receta/BOM real implicaría una tabla de relación nueva, UI de composición de
receta y bastante más trabajo de diseño de producto que no se justifica para
esta primera iteración. Esta decisión se registra aquí explícitamente; el
modelo de receta/BOM queda como posible fase futura, **no** planificada en
esta tarea ni en ninguna otra actual.

## Alcance

**Incluye:**

- `backend/app/models/producto.py`: agregar columna nueva `costo: Mapped[int
  | None] = mapped_column(Integer, nullable=True, default=None)`. **Nullable**
  a propósito (a diferencia de `precio`, que es `nullable=False`): un producto
  puede existir sin costo definido todavía (ej. productos ya creados antes de
  esta tarea, o productos cuyo costo real el dueño todavía no calculó), y
  "costo desconocido" debe ser distinguible de "costo es cero" — no usar `0`
  como default implícito. Mismo criterio de tipo que `precio` (`Integer`, COP
  sin decimales, sin formatear moneda en el backend).
- `backend/app/schemas/producto.py`:
  - `ProductoCreate.costo: int | None = Field(default=None, ge=0)`.
  - `ProductoUpdate.costo: int | None = Field(default=None, ge=0)`.
  - `ProductoOut.costo: int | None`.
  - `ge=0` rechaza costos negativos con `422` (a diferencia de `precio`, que
    usa `gt=0` porque un precio de venta cero no tiene sentido de negocio;
    `costo=0` sí es válido, ej. insumos donados o de costo irrelevante).
- `backend/app/routers/productos.py`:
  - `crear_producto`: pasar `costo=payload.costo` al construir `Producto`.
  - `actualizar_producto`: `costo` es nullable, así que debe seguir
    exactamente el mismo patrón `campos_enviados = payload.model_dump(exclude_unset=True)`
    / `"campo" in campos_enviados` que ya usan `sabor`, `tamano` e
    `imagen_base64` desde BE-011 (para poder distinguir "no se envió `costo`
    en el body" de "se envió `costo: null` para borrarlo explícitamente") —
    **no** usar el patrón `is not None` que usan `nombre`/`precio`/`estado`,
    porque ese patrón no permite borrar el campo a `null`.
- **Decisión explícita del usuario (dueño del negocio), tomada tras consulta
  directa del planner sobre este punto exacto — mismo patrón de decisión
  registrada que BE-012:** a diferencia de la versión original de esta
  tarea, `costo` **sí** debe sincronizarse a Google Sheets como una columna
  más de la hoja `Productos`, igual que el resto de los campos (`nombre`,
  `categoria_nombre`, `precio`, `estado`, `sabor`, `tamano`). El usuario
  respondió textualmente: "creo que todo debería guardarse en el backup así
  sea sensible" — es una decisión suya sobre el alcance de su propio backup,
  no un juicio técnico a cuestionar. Como BE-015 (sync de productos a
  Sheets) ya está `done` e implementado, esta tarea también debe tocar el
  mismo módulo que BE-015 dejó armado:
  - `backend/app/services/sheets_service.py`: agregar `"Costo"` a
    `_HEADERS_PRODUCTOS` (al final de la lista, después de `"Tamaño"`) y
    agregar el valor de `costo` a `row_values` en `sync_producto_to_sheets`,
    en la misma posición. `costo` puede ser `None`: la celda debe quedar
    vacía (`""`), nunca el string literal `"None"` — mismo criterio que ya
    usan `sabor`/`tamano` en esa función.
  - `backend/app/routers/productos.py`: `_producto_dict_para_sheets`
    (helper de BE-015) debe incluir `costo` en el diccionario plano que
    arma, junto con el resto de campos (`id`, `nombre`, `categoria_nombre`,
    `precio`, `estado`, `sabor`, `tamano`).
- Mismo caveat operativo que BE-009/BE-010 (sin Alembic, `Base.metadata.create_all`
  no altera una tabla `productos` ya existente): documentar en notas de
  implementación el paso de borrar `brainfreeze.db` en desarrollo para que la
  columna `costo` aparezca en un entorno con base de datos preexistente.

**No incluye (fuera de alcance):**

- Modelo de receta/BOM (`Insumo.costo_unitario` + tabla de relación
  producto↔insumos) — ver decisión documentada arriba.
- Cálculo o exposición de margen/ganancia — eso es BE-018 (reportes), que
  depende de esta tarea.
- Cambios a `Insumo` (sigue sin ningún campo de costo).
- Cambios a `VentaItem`/`Venta` (el costo que se usa para margen en BE-018 es
  el costo **actual** del producto al momento de generar el reporte, no un
  costo histórico "congelado" al momento de la venta — ver la nota de
  limitación explícita en BE-018 sobre esto).
- Cambios al catálogo/formulario del frontend (ver tarea de frontend FE-025,
  que depende de esta).

## Criterios de aceptación

- [ ] `Producto` tiene una columna `costo` (`Integer`, `nullable=True`, sin
      default forzado a `0`).
- [ ] `POST /productos` sin `costo` en el body crea el producto igual que
      antes (sin regresión), con `costo: null` en la respuesta.
- [ ] `POST /productos` con `costo: 5000` crea el producto con ese costo.
- [ ] `POST /productos` con `costo: -1` responde `422`.
- [ ] `PATCH /productos/{id}` con `{"costo": 3000}` en un producto sin costo
      previo lo asigna; `GET /productos/{id}` posterior lo confirma.
- [ ] `PATCH /productos/{id}` con `{"costo": null}` en un producto que ya
      tenía costo lo borra a `null` (verificado con `GET` posterior, no solo
      en la respuesta del `PATCH`), siguiendo el mismo mecanismo que ya usan
      `sabor`/`tamano`/`imagen_base64`.
- [ ] `PATCH /productos/{id}` que **no** incluye la clave `costo` no altera
      el costo existente del producto.
- [ ] `GET /productos` y `GET /productos/{id}` incluyen `costo` en la
      respuesta (`null` cuando no está definido).
- [ ] Un producto creado antes de esta tarea sigue siendo legible vía
      `GET /productos` con `costo: null`, sin romper la deserialización.
- [ ] `costo` aparece como columna `"Costo"` en `_HEADERS_PRODUCTOS`
      (`sheets_service.py`) y en el diccionario que arma
      `_producto_dict_para_sheets` (`productos.py`) — verificable por
      lectura de código.
- [ ] Sincronizar un producto con `costo` definido (ej. `5000`) escribe ese
      valor en la columna `Costo` de la hoja `Productos`; sincronizar un
      producto con `costo: null` escribe la celda vacía (`""`), nunca el
      string literal `"None"`.
- [ ] Documentado en las notas de implementación el paso manual de borrar
      `brainfreeze.db` en desarrollo para que la columna nueva tome efecto.

## Notas de implementación

Implementado tal como está descrito en la tarea, sin desviaciones.

**Archivos tocados:**

- `backend/app/models/producto.py`: agregada columna `costo: Mapped[int | None] =
  mapped_column(Integer, nullable=True, default=None)`, mismo tipo (`Integer`)
  y sin default forzado a `0`, a diferencia de `precio`.
- `backend/app/schemas/producto.py`:
  - `ProductoCreate.costo: int | None = Field(default=None, ge=0)`.
  - `ProductoUpdate.costo: int | None = Field(default=None, ge=0)`.
  - `ProductoOut.costo: int | None` (sin default, como el resto de los campos
    de salida).
- `backend/app/routers/productos.py`:
  - `crear_producto`: pasa `costo=payload.costo` al construir `Producto`.
  - `actualizar_producto`: sigue el mismo patrón `exclude_unset` que
    `sabor`/`tamano`/`imagen_base64` (`"costo" in campos_enviados` ->
    `producto.costo = payload.costo`), permitiendo distinguir "no enviado"
    de "enviado como `null`" para poder borrar el costo explícitamente.
  - `_producto_dict_para_sheets`: agrega `"costo": producto.costo` al
    diccionario plano.
- `backend/app/services/sheets_service.py`:
  - `_HEADERS_PRODUCTOS`: agregado `"Costo"` al final (después de `"Tamaño"`).
  - `sync_producto_to_sheets`: agregado a `row_values`
    `producto.get("costo") if producto.get("costo") is not None else ""` —
    a propósito **no** se usa el patrón `producto.get("costo") or ""` que sí
    usan `sabor`/`tamano`, porque `costo=0` es un valor válido y `0 or ""`
    evaluaría a `""` (perdería el cero); con `is not None` se distingue
    correctamente "costo cero" de "costo desconocido" también en el backup
    de Sheets. Verificado manualmente que `costo=None -> ""`, `costo=5000 ->
    5000`, `costo=0 -> 0` (no vacío).

**Caveat operativo (SQLite sin Alembic), documentado según lo pedido por la
tarea:** como en BE-009/BE-010/BE-015/BE-016, `Base.metadata.create_all` no
altera una tabla `productos` ya existente en una base de datos preexistente
(`brainfreeze.db`). Verificado reproduciendo el error exacto
(`sqlite3.OperationalError: table productos has no column named costo`) al
intentar insertar contra una copia de la base de datos de desarrollo actual
sin recrearla. **Para que la columna `costo` tome efecto en un entorno de
desarrollo con base de datos preexistente, hay que borrar `brainfreeze.db`
manualmente antes de levantar el servidor** (se recreará automáticamente
gracias al `lifespan` de `app/main.py`, que corre `Base.metadata.create_all`
al arrancar). No se borró la `brainfreeze.db` real del repo como parte de
esta tarea (tiene 15 productos y varios usuarios de prueba de tareas
anteriores) — queda como paso manual a criterio de quien levante el entorno
localmente.

**Cómo se probó:** no hay suite de tests automatizada en el proyecto ni
`httpx` instalado (requerido por `TestClient`, y agregarlo sería una
dependencia nueva fuera de alcance), así que se probó llamando directamente
a las funciones del router (`crear_producto`, `actualizar_producto`,
`obtener_producto`, `listar_productos`) con un `Session` real contra una
base de datos SQLite temporal (copia con esquema fresco, recreada con
`Base.metadata.create_all` para simular el paso de borrar `brainfreeze.db`)
en `app/db/session.SessionLocal`, y `BackgroundTasks()` real (sin invocar
sync de Sheets porque `SHEETS_SYNC_ENABLED` es `false` por defecto). Casos
verificados, todos exitosos:

- `POST /productos` (llamado como `crear_producto(ProductoCreate(nombre=...,
  categoria_id=..., precio=1000), ...)`) sin `costo` -> `costo: None` en la
  respuesta.
- Con `costo=5000` -> `costo: 5000` en la respuesta.
- `ProductoCreate(..., costo=-1)` -> `pydantic.ValidationError` (equivalente
  al `422` de la API).
- `PATCH` (`actualizar_producto`) con `ProductoUpdate(costo=3000)` sobre un
  producto sin costo previo lo asigna; confirmado con `obtener_producto`
  posterior (no solo en la respuesta del PATCH).
- `PATCH` con `ProductoUpdate(costo=None)` sobre un producto que ya tenía
  `costo=5000` lo borra a `null`; confirmado con `obtener_producto`
  posterior.
- `PATCH` con `ProductoUpdate(nombre=...)` (sin incluir `costo` en el
  payload) no altera el `costo` existente (`exclude_unset` funciona
  correctamente).
- `listar_productos` incluye `costo` en todos los productos devueltos.
- Construcción de `row_values` de `sync_producto_to_sheets` probada de forma
  aislada (sin llamar a la API real de Google) con tres diccionarios de
  producto (`costo=5000`, `costo=None`, `costo=0`): confirma
  `_HEADERS_PRODUCTOS[-1] == "Costo"` y que la celda resultante es `5000`,
  `""` y `0` respectivamente (nunca el string `"None"`).

Para probar manualmente vía HTTP con el servidor real (requiere borrar
`brainfreeze.db` primero si ya existe, y un login válido vía
`POST /auth/login`):

```
uvicorn app.main:app --reload
POST /productos  {"nombre": "Malteada", "categoria_id": 1, "precio": 8000, "costo": 5000}
PATCH /productos/{id}  {"costo": null}
GET /productos/{id}
```

## Revisión

**Veredicto: `done`.**

Revisé código (modelo, schemas, router, `sheets_service.py`) y corrí pruebas
propias contra copias temporales de la `brainfreeze.db` real (que ya tiene la
columna `costo` aplicada por el orquestador), sin tocar la base real:

- `backend/app/models/producto.py`: `costo: Mapped[int | None] =
  mapped_column(Integer, nullable=True, default=None)` — tipo, nullability y
  ausencia de default forzado correctos. Confirmé con `PRAGMA table_info` que
  la tabla real ya tiene `costo INTEGER, notnull=0, dflt_value=None`,
  consistente con el modelo.
- `backend/app/schemas/producto.py`: `ProductoCreate.costo` y
  `ProductoUpdate.costo` con `Field(default=None, ge=0)`; `ProductoOut.costo:
  int | None`. Probé instanciando los schemas directamente:
  `costo=-1` lanza `ValidationError` (-> `422`), `costo` omitido -> `None`,
  `costo=0` -> `0` (aceptado, no rechazado por `ge=0` al ser inclusive).
- `backend/app/routers/productos.py`:
  - `crear_producto` pasa `costo=payload.costo` correctamente.
  - `actualizar_producto` usa el mismo patrón `exclude_unset` que
    `sabor`/`tamano`/`imagen_base64` (`"costo" in campos_enviados`), no el
    patrón `is not None` de `nombre`/`precio`/`estado`. Verifiqué con
    `model_dump(exclude_unset=True)`: `ProductoUpdate(nombre="y")` no incluye
    `"costo"`; `ProductoUpdate(costo=None)` sí incluye `{"costo": None}`;
    `ProductoUpdate(costo=3000)` incluye `{"costo": 3000}`.
  - `_producto_dict_para_sheets` incluye `"costo": producto.costo` en el
    diccionario, junto al resto de campos, reutilizando el helper de BE-015
    sin duplicarlo.
  - Corrí un flujo end-to-end real contra una copia de `brainfreeze.db`
    (invocando `crear_producto`/`actualizar_producto`/`obtener_producto`/
    `listar_productos` directamente, sin servidor HTTP):
    - crear sin `costo` -> `costo: None`.
    - crear con `costo=5000` -> `costo: 5000`.
    - `PATCH {"costo": 3000}` sobre producto sin costo previo -> confirmado
      con `GET` posterior.
    - `PATCH {"costo": null}` sobre producto con `costo=5000` -> lo borra a
      `null`, confirmado con `GET` posterior (no solo en la respuesta del
      PATCH).
    - `PATCH` sin la clave `costo` (solo `nombre`) -> el costo existente
      (`3000`) no se altera.
    - Los 15 productos preexistentes de la base real siguen siendo legibles
      vía `listar_productos`, todos con `costo: None`, sin error de
      deserialización.
- `backend/app/services/sheets_service.py`:
  - `_HEADERS_PRODUCTOS` termina en `"Costo"`, después de `"Tamaño"`,
    correcto.
  - `sync_producto_to_sheets` usa `producto.get("costo") if
    producto.get("costo") is not None else ""` (no el patrón `or ""` que
    perdería el cero). Probé la construcción de `row_values` con un
    `_get_worksheet`/`_upsert_row_by_id` monkeypateados (sin red real):
    `costo=5000 -> 5000`, `costo=None -> ""`, `costo=0 -> 0` — exactamente
    los tres casos pedidos, nunca el string `"None"` ni `""` para el cero
    real.
  - Manejo de excepciones sigue el mismo patrón que el resto del servicio
    (try/except específicos + `except Exception` genérico con `logger`,
    nunca propaga al router) — no se tocó ni se rompió ese bloque.
- Caveat operativo de SQLite sin Alembic documentado en notas de
  implementación, como pedía la tarea.

No encontré desviaciones del alcance ni scope creep. Todos los criterios de
aceptación están cumplidos y verificados (no solo por lectura de código, sino
ejecutando el flujo real contra la base de datos existente).
