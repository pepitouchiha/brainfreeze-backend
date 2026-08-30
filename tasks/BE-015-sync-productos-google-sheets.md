---
id: BE-015
title: Sincronizar Productos a Google Sheets (creación y actualización, upsert por ID)
area: backend
status: done
priority: medium
depends_on: [BE-014]
created_by: planner
---

## Objetivo

Extender el backup de mejor esfuerzo a Google Sheets (BE-012/013/014) para cubrir
el catálogo de **Productos**, reutilizando la infraestructura genérica que deja
BE-014 (`_get_worksheet(worksheet_name)`, `_ensure_headers(worksheet, headers)`,
`_upsert_row_by_id(worksheet, headers, entity_id, row_values)`). Cada producto debe
quedar representado por **una sola fila** en la hoja `Productos` del spreadsheet
`BrainFreeze POS`, que se actualiza in place cuando el producto cambia (precio,
estado, sabor, tamaño, categoría) en vez de acumular una fila nueva por cada
edición — igual filosofía que categorías en BE-014, distinta de ventas (que sigue
siendo un log append-only).

## Alcance

**Incluye:**

1. **`backend/app/services/sheets_service.py`** (extender, no reescribir el
   refactor de BE-014):
   - Constante `_HEADERS_PRODUCTOS = ["ID Producto", "Nombre", "Categoría",
     "Precio", "Estado", "Sabor", "Tamaño"]`.
   - Nueva función pública `sync_producto_to_sheets(producto: dict[str, Any]) ->
     None`: resuelve la hoja `config.SHEETS_WORKSHEET_PRODUCTOS` vía
     `_get_worksheet(...)`, arma `row_values = [producto["id"], producto["nombre"],
     producto["categoria_nombre"], producto["precio"], producto["estado"],
     producto.get("sabor") or "", producto.get("tamano") or ""]` y llama a
     `_upsert_row_by_id(worksheet, _HEADERS_PRODUCTOS, producto["id"], row_values)`.
     Mismo patrón de captura total de excepciones que `sync_categoria_to_sheets` /
     `sync_venta_to_sheets` (nunca propaga).
   - **`imagen_base64` del producto NO se incluye** en ninguna columna ni se pasa
     dentro del diccionario que llega a esta función — son blobs potencialmente
     grandes, no aportan valor como backup legible en una hoja de cálculo y
     podrían exceder límites de tamaño de celda de Google Sheets. Esto debe
     cumplirse tanto en el wiring del router (punto 3) como en esta función.

2. **Wiring en `backend/app/routers/productos.py`**:
   - `crear_producto` y `actualizar_producto` (esta última cubre tanto `PUT` como
     `PATCH`, ya que comparten la misma función): agregar `background_tasks:
     BackgroundTasks` a la firma de ambas. Después de `db.refresh(producto)` y
     antes del `return`, si `config.SHEETS_SYNC_ENABLED` es `True`, construir el
     diccionario plano con `id`, `nombre`, `precio`, `estado`, `sabor`, `tamano`
     (todos primitivos ya materializados) más `categoria_nombre`: resolver el
     nombre de la categoría del producto — revisar si se puede obtener sin una
     query nueva (ej. reutilizando/ajustando `_validar_categoria` para que
     retorne el objeto `Categoria` ya cargado, y reusarlo en ambos endpoints) o,
     si no es directo con el código actual, aceptar una query puntual adicional
     (`db.get(Categoria, producto.categoria_id).nombre`) dentro de esa misma rama
     condicional — es aceptable dado que solo corre cuando el flag está activo y
     es backup de mejor esfuerzo, no path crítico de la request. Documentar la
     decisión tomada en notas de implementación. Encolar con
     `background_tasks.add_task(sync_producto_to_sheets, ese_dict)`.
   - Con el flag en `False` (default): ninguna de estas ramas se evalúa, cero
     trabajo extra ni queries adicionales de resolución de categoría.
   - `eliminar_producto` no se toca (mismo criterio que `eliminar_categoria` en
     BE-014: la fila queda huérfana en la hoja, backup de mejor esfuerzo).

**No incluye (fuera de alcance):**
- Sincronizar la eliminación de productos (ver arriba).
- Incluir `imagen_base64` en la hoja, de ninguna forma (ver punto 1).
- Migrar/backfill retroactivo de productos ya existentes en `brainfreeze.db`.
- Crear la hoja `Productos` en el spreadsheet real — la crea el usuario a mano
  siguiendo la documentación (ya generalizada en BE-014, esta tarea solo agrega
  la mención específica de `Productos` si falta).
- Cualquier cambio a `_upsert_row_by_id`/`_get_worksheet`/`_ensure_headers` más
  allá de usarlos — si algo de esa infraestructura resulta insuficiente para este
  caso, es una señal de que BE-014 quedó incompleta y debe ajustarse ahí, no
  duplicar lógica aquí.

## Criterios de aceptación

- [ ] Con `SHEETS_SYNC_ENABLED=false` (default): `POST /productos`,
      `PUT /productos/{id}` y `PATCH /productos/{id}` responden exactamente igual
      que hoy, sin `BackgroundTask` encolada ni resolución adicional de
      `categoria_nombre`.
- [ ] Con `SHEETS_SYNC_ENABLED=true` sin credenciales en disco: crear/actualizar
      un producto sigue respondiendo con el código de estado correcto (`201`/`200`)
      y el body de siempre, sin excepción sin capturar, con el warning esperado
      en logs.
- [ ] `sync_producto_to_sheets` nunca propaga una excepción, verificado con al
      menos dos escenarios de fallo simulados.
- [ ] **Upsert por ID** (verificable con mocks): crear un producto → fila nueva
      (con encabezados si la hoja estaba vacía); actualizar ese mismo producto
      (cambiando precio y estado) → misma cantidad de filas, fila existente
      reflejando los valores nuevos; crear un segundo producto → fila adicional
      sin afectar la del primero.
- [ ] La fila en Sheets **nunca** contiene el valor de `imagen_base64` — verificar
      por lectura de código que el diccionario armado en el router y los
      `row_values` de `sync_producto_to_sheets` no incluyen ese campo en ninguna
      forma, y confirmar con una prueba donde un producto con `imagen_base64` no
      vacío se sincroniza y la fila resultante solo tiene las 7 columnas
      esperadas (`ID Producto, Nombre, Categoría, Precio, Estado, Sabor, Tamaño`).
  - [ ] `sabor`/`tamano` nulos se representan como celda vacía (`""`), no como el
      string literal `"None"` ni causan excepción.
- [ ] El nombre de la categoría (`categoria_nombre`) corresponde a la categoría
      real del producto en el momento de la sincronización, incluso si el
      producto cambió de categoría en la misma actualización que dispara el sync.
- [ ] El diccionario pasado a `background_tasks.add_task(sync_producto_to_sheets, ...)`
      contiene solo primitivos, nunca el objeto ORM `Producto` ni `Categoria`.
- [ ] Se reutiliza `_get_worksheet`/`_ensure_headers`/`_upsert_row_by_id` de
      BE-014 sin duplicar su lógica dentro de `sync_producto_to_sheets` —
      verificable por lectura de código.
- [ ] `backend/README.md` menciona explícitamente la hoja `Productos` (nombre
      configurable vía `SHEETS_WORKSHEET_PRODUCTOS`, ya documentada como variable
      en BE-014) como parte del setup necesario para esta sincronización.

## Notas de implementación

**Archivos tocados:**

- `backend/app/services/sheets_service.py` (extendido, sin reescribir el
  refactor de BE-014).
- `backend/app/routers/productos.py` (wiring).
- `backend/README.md` (documentación, secciones "Sincronización a Google
  Sheets" y tabla de variables de entorno — la mención a `Productos` ya
  existía como placeholder desde BE-014, se actualizó para reflejar que ya
  está implementado, no pendiente).
- `backend/.env.example`: no requirió cambios, las 3 variables
  (`SHEETS_WORKSHEET_CATEGORIAS`, `SHEETS_WORKSHEET_PRODUCTOS`,
  `SHEETS_WORKSHEET_INSUMOS`) ya se agregaron en BE-014.
- `backend/app/core/config.py`: no requirió cambios, `SHEETS_WORKSHEET_PRODUCTOS`
  (default `"Productos"`) ya existía desde BE-014.

**Decisiones tomadas:**

1. **`sync_producto_to_sheets`** (`sheets_service.py`): exactamente como
   describe el alcance — `_HEADERS_PRODUCTOS = ["ID Producto", "Nombre",
   "Categoría", "Precio", "Estado", "Sabor", "Tamaño"]`, resuelve
   `config.SHEETS_WORKSHEET_PRODUCTOS` vía `_get_worksheet`, arma
   `row_values` con `producto.get("sabor") or ""` / `producto.get("tamano")
   or ""` (nunca el string literal `"None"`) y delega en
   `_upsert_row_by_id` — no se duplicó nada de esa lógica. Mismo `try` con
   las 6 ramas de excepción que ya usan `sync_venta_to_sheets`/
   `sync_categoria_to_sheets` (`SpreadsheetNotFound`, `WorksheetNotFound`,
   `APIError`, `GoogleAuthError`, `ConnectionError`/`Timeout`, `Exception`
   genérica con `logger.exception`), nunca propaga.
2. **`imagen_base64` nunca llega a Sheets**: ni el diccionario armado en el
   router (`_producto_dict_para_sheets`) ni `sync_producto_to_sheets` tocan
   ese campo en ninguna forma — verificable por lectura de código, y
   confirmado con una prueba donde un producto con `imagen_base64` no
   vacío se sincroniza y la fila resultante solo tiene las 7 columnas
   esperadas.
3. **Resolución de `categoria_nombre` sin query extra en el caso común**:
   se cambió la firma de `_validar_categoria(db, categoria_id)` para que
   retorne el objeto `Categoria` ya cargado (antes retornaba `None`, solo
   validaba existencia) en vez de duplicar la búsqueda. No hay otros
   llamadores de esa función fuera de `productos.py` (hay una función
   homónima independiente en `insumos.py`, sin relación, no se tocó).
   - En `crear_producto`: la categoría ya se obtiene de
     `_validar_categoria(db, payload.categoria_id)` para la validación
     existente — se reutiliza ese mismo objeto para `categoria_nombre`,
     cero queries adicionales.
   - En `actualizar_producto`: si `payload.categoria_id` viene en el
     request, se reutiliza el objeto ya validado (refleja la categoría
     *nueva*, cumpliendo el criterio de aceptación de que el nombre
     corresponda a la categoría real incluso si cambió en la misma
     actualización). Si `payload.categoria_id` **no** viene (el producto no
     cambia de categoría en ese request), se hace una query puntual
     adicional reutilizando la misma `_validar_categoria(db,
     producto.categoria_id)` (en vez de un `db.get` crudo separado, para no
     duplicar la lógica de "buscar y validar categoría") — esta rama solo
     corre dentro del `if config.SHEETS_SYNC_ENABLED:`, así que con el flag
     en `False` no se ejecuta.
4. **`_producto_dict_para_sheets(producto, categoria_nombre)`**: helper
   privado en `productos.py` que arma el diccionario plano (`id`, `nombre`,
   `categoria_nombre`, `precio`, `estado`, `sabor`, `tamano` — todos
   primitivos ya materializados, nunca el objeto ORM) compartido entre
   `crear_producto` y `actualizar_producto` para no duplicar la
   construcción del payload en los dos endpoints.
5. **`actualizar_producto` cubre `PUT` y `PATCH`** (mismo decorador doble
   ya existente, sin cambios en ese patrón) — se agregó
   `background_tasks: BackgroundTasks` a la firma una sola vez, cubre
   ambos métodos.
6. **`eliminar_producto` no se tocó**, según alcance (mismo criterio que
   `eliminar_categoria` en BE-014: fila huérfana en Sheets, backup de
   mejor esfuerzo).

**Pruebas realizadas** (no hay `pytest` instalado en el proyecto — mismo
diagnóstico que BE-012/013/014 — se usó `unittest.mock` vía scripts ad-hoc
en el scratchpad de la sesión, más pruebas contra el servidor real):

1. **Upsert por ID correcto** (mock de `Worksheet` con backing store en
   memoria): crear producto A (con `sabor`/`tamano` set) en hoja vacía →
   2 filas (headers `_HEADERS_PRODUCTOS` + fila de A con los 7 valores
   correctos); actualizar A (mismo ID, precio y estado distintos) → sigue
   en 2 filas, fila de A con los valores nuevos, resto de columnas
   intactas; crear producto B con `sabor=None`/`tamano=None` → 3 filas,
   fila de A intacta, fila de B con columnas de sabor/tamaño como `""`
   (no `"None"`, no excepción). Caso borde adicional: sincronizar un ID
   sin fila existente en la hoja (ej. sync activado después de que el
   producto ya existía en SQLite) → se inserta como fila nueva en vez de
   fallar.
2. **7 columnas exactas, sin `imagen_base64`**: se sincronizó un
   diccionario de producto (tal como lo construiría el router, sin la
   clave `imagen_base64`) y se verificó que la fila resultante tiene
   exactamente 7 valores y ninguno corresponde a un data URL de imagen.
3. **`sync_producto_to_sheets` nunca propaga excepciones**: 4 escenarios
   simulados (`SHEETS_AUTHORIZED_USER_FILE` ausente,
   `gspread.oauth` lanzando `SpreadsheetNotFound`, `RuntimeError`
   genérico durante `worksheet.find`, `requests.exceptions.ConnectionError`)
   — en los 4 casos la función retornó normalmente sin propagar nada.
4. **Flag en `False`**: se invocó `crear_producto(...)` directamente (con
   una sesión de DB fake) parcheando `config.SHEETS_SYNC_ENABLED = False`
   → `len(background_tasks.tasks) == 0` y `sync_producto_to_sheets` nunca
   se llamó — confirma que con el flag en `False` no se evalúa la rama ni
   se resuelve `categoria_nombre` extra.
5. **Flag en `True`, dict pasado a `background_tasks.add_task` solo con
   primitivos y sin imagen**: se invocó `crear_producto(...)` con
   `imagen_base64` no vacío en el payload y una categoría mockeada → el
   diccionario encolado tiene exactamente las 7 claves esperadas
   (`id, nombre, categoria_nombre, precio, estado, sabor, tamano`), ningún
   valor es un objeto `MagicMock`/ORM, y `"imagen_base64"` no está entre
   las claves.
6. **`categoria_nombre` refleja el cambio de categoría en la misma
   actualización**: se invocó `actualizar_producto(...)` con
   `payload.categoria_id` apuntando a una categoría distinta de la actual
   del producto → el diccionario encolado trae el nombre de la categoría
   **nueva**, no la vieja.
7. **`categoria_nombre` se resuelve correctamente cuando la actualización
   no toca `categoria_id`**: se invocó `actualizar_producto(...)` sin
   `categoria_id` en el payload → se verificó que la query de resolución
   usa el `categoria_id` **actual** del producto (no uno nuevo/incorrecto)
   y el diccionario trae el nombre correcto, junto con `sabor`/`tamano`
   sin tocar.
8. **Contra el servidor real, en background** (`uvicorn`, puerto 8000,
   `.env` real del proyecto con `SHEETS_SYNC_ENABLED=true` y
   `credentials.json`/`authorized_user.json` reales ya presentes desde
   BE-012/014 — permitió una prueba end-to-end real contra
   `gspread.oauth`/`client.open` reales, no solo mocks). Usuario de prueba
   `test-be015@brainfreeze.com` creado vía `crear_usuario.py`:
   - `POST /productos` con `imagen_base64` no vacío, `categoria_id=5` →
     `201` normal con la imagen presente en la respuesta al cliente (como
     corresponde, la exclusión es solo hacia Sheets), y en el log del
     servidor apareció exactamente `No se encontró la hoja 'Productos'
     dentro del spreadsheet 'BrainFreeze POS'.` — confirma que la
     autenticación y apertura del spreadsheet real funcionan, pero la hoja
     `Productos` **todavía no existe** en el spreadsheet del usuario (a
     diferencia de `Categorias`, que según las notas de BE-014 tampoco
     existía a esa fecha — no se verificó de nuevo aquí, fuera de alcance
     de esta tarea).
   - `PATCH /productos/{id}` cambiando `categoria_id` (de 5 a 1),
     `precio` y `estado` en el mismo request → `200` normal, mismo log de
     `WorksheetNotFound` para `Productos` — confirma que ni crear ni
     actualizar rompen nada aunque la hoja destino no exista todavía.
   - Se limpió el producto de prueba con `DELETE /productos/16` → `204`.
   - El usuario de prueba `test-be015@brainfreeze.com` se dejó en
     `brainfreeze.db` (mismo criterio que los usuarios de prueba de
     tareas anteriores).

**Pendiente explícito**: igual que en BE-014 con la hoja `Categorias`, la
prueba end-to-end contra el Google Sheet real del usuario confirmó que la
infraestructura de autenticación/spreadsheet funciona correctamente, pero
**la hoja `Productos` todavía no existe** en el spreadsheet `BrainFreeze
POS` del usuario — falta que la cree manualmente (mismo nombre que
`SHEETS_WORKSHEET_PRODUCTOS`, default `"Productos"`) para que la
sincronización de productos escriba filas reales; hasta entonces, cada
creación/actualización de producto loguea el `warning` de
`WorksheetNotFound` visto arriba sin afectar la respuesta al cliente. Una
vez creada la hoja, no hace falta ningún cambio de código adicional.

## Revisión

**Veredicto: `done`**

Revisión de código completa contra los criterios de aceptación (no se pudo
correr `pytest`/`ruff`/`mypy` — no están instalados en el entorno, mismo
diagnóstico ya documentado en BE-012/013/014; se verificó todo por lectura
de código).

Archivos revisados:
- `backend/app/services/sheets_service.py` (líneas 44, 239-279)
- `backend/app/routers/productos.py` (completo)
- `backend/app/schemas/producto.py`, `backend/app/models/producto.py`
- `backend/app/core/config.py`
- `backend/README.md` (líneas 90-150)
- `backend/.env.example`

Checklist verificado:

1. **`imagen_base64` nunca llega a Sheets.** `_producto_dict_para_sheets`
   (productos.py:25-34) construye el dict con exactamente 7 claves
   primitivas (`id, nombre, categoria_nombre, precio, estado, sabor,
   tamano`); `sync_producto_to_sheets` (sheets_service.py:239-254) arma
   `row_values` con esas mismas 7 columnas. `imagen_base64` no aparece en
   ninguna de las dos funciones. Confirmado.
2. **`categoria_nombre` correcto en ambos casos de `actualizar_producto`.**
   Cuando `payload.categoria_id` viene en el request, se reutiliza el
   objeto `categoria` recién validado por `_validar_categoria` (refleja la
   categoría *nueva*, sin query extra respecto a la validación que ya
   existía). Cuando no viene, se resuelve con
   `_validar_categoria(db, producto.categoria_id)` — usa el `categoria_id`
   *actual* del producto ya refrescado tras el commit, dentro de la misma
   rama `if config.SHEETS_SYNC_ENABLED:`, así que no corre con el flag en
   `False`. Sin duplicación de lógica de validación (`_validar_categoria`
   ajustada para retornar `Categoria` en vez de `None`, sin otros llamadores
   fuera de `productos.py`; la homónima en `insumos.py` es independiente).
3. **Reutilización de infraestructura de BE-014.**
   `sync_producto_to_sheets` delega en `_get_worksheet` y
   `_upsert_row_by_id` sin reimplementar ninguna parte de esa lógica —
   mismo patrón exacto que `sync_categoria_to_sheets`.
4. **Manejo de excepciones.** Mismas 6 ramas (`SpreadsheetNotFound`,
   `WorksheetNotFound`, `APIError`, `GoogleAuthError`,
   `ConnectionError`/`Timeout`, `Exception` genérica con
   `logger.exception`) que `sync_categoria_to_sheets`/`sync_venta_to_sheets`
   — nunca propaga.
5. **`SHEETS_SYNC_ENABLED=false`.** Tanto `crear_producto` como
   `actualizar_producto` envuelven la construcción del dict y el
   `background_tasks.add_task(...)` dentro de
   `if config.SHEETS_SYNC_ENABLED:` — con el flag apagado no se resuelve
   `categoria_nombre` extra ni se toca red/disco.
6. **`sabor`/`tamano` nulos → `""`.** `producto.get("sabor") or ""` /
   `producto.get("tamano") or ""` en `sheets_service.py:251-252` — nunca el
   string `"None"`.
7. **Dict solo con primitivos hacia `background_tasks.add_task`.**
   Confirmado por tipos de `_producto_dict_para_sheets`: `int`, `str`,
   `str | None` — nunca el objeto ORM `Producto`/`Categoria`.
8. **`README.md`** documenta la hoja `Productos` (columnas, mecanismo de
   upsert, exclusión explícita de `imagen_base64`) en la sección de
   sincronización, y la tabla de variables de entorno ya incluye
   `SHEETS_WORKSHEET_PRODUCTOS`.
9. **`eliminar_producto`** no se tocó, consistente con el criterio ya
   aplicado a `eliminar_categoria` en BE-014.

Sin hallazgos bloqueantes. La tarea cumple los criterios de aceptación tal
como están definidos, sin scope creep relevante (el helper
`_producto_dict_para_sheets` es una extracción razonable, no una
abstracción prematura, dado que se usa en los dos endpoints).
