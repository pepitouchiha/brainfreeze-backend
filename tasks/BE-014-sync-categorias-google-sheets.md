---
id: BE-014
title: Generalizar sheets_service.py para múltiples hojas con upsert y sincronizar Categorías
area: backend
status: done
priority: medium
depends_on: [BE-012, BE-013]
created_by: planner
---

## Objetivo

BE-012/BE-013 (`done`) dejaron `backend/app/services/sheets_service.py` sincronizando
**ventas** como un log de eventos de solo-append (`append_row` por cada venta nueva,
nunca se modifica una fila ya escrita — tiene sentido porque una venta, una vez
creada, es inmutable). El dueño del negocio quiere extender el mismo mecanismo de
backup a **Categorías**, **Productos** e **Insumos**, pero estos tres modelos sí se
editan después de creados (`PUT`/`PATCH`, y en el caso de insumos también
`POST /insumos/{id}/ajustar-stock`). Un log de solo-append para estos catálogos
generaría filas duplicadas y desactualizadas cada vez que se edite un registro, lo
cual no sirve como backup útil — lo que el dueño necesita es que la hoja refleje el
**estado actual** de cada categoría/producto/insumo, una fila por ID, actualizada in
place cuando el registro cambia.

Esta tarea es la primera de tres (seguida por productos e insumos en tareas
separadas) y hace dos cosas: (1) generaliza la infraestructura de
`sheets_service.py` para soportar múltiples hojas dentro del mismo spreadsheet, cada
una con su propio caché de worksheet/encabezados, y un mecanismo de **upsert por
ID** reutilizable; y (2) usa esa infraestructura para sincronizar Categorías, como
caso más simple para validar el patrón antes de replicarlo en BE-015 (productos) y
BE-016 (insumos).

## Alcance

**Incluye:**

1. **Refactor de `backend/app/services/sheets_service.py`** (mismo archivo, sin
   archivos nuevos):
   - Reemplazar la variable de módulo `_worksheet: gspread.Worksheet | None` (única,
     hardcodeada a la hoja de ventas) por un caché **por nombre de hoja**, ej.
     `_worksheets: dict[str, gspread.Worksheet]`. `_get_worksheet(worksheet_name: str)
     -> gspread.Worksheet | None` pasa a recibir el nombre de la hoja como
     parámetro en vez de leer `config.SHEETS_WORKSHEET_NAME` fijo, y cachea por esa
     clave. El cliente autenticado (`gspread.oauth(...)`) y el `Spreadsheet` abierto
     (`client.open(config.SHEETS_SPREADSHEET_NAME)`) deben cachearse una sola vez a
     nivel de módulo (independiente del nombre de la hoja) y reutilizarse para
     resolver cualquier worksheet — no repetir `gspread.oauth(...)` ni
     `client.open(...)` por cada hoja distinta.
   - Reemplazar `_headers_checked: bool` (único) por un caché **por nombre de
     hoja**, ej. `_headers_checked: dict[str, bool]`, y generalizar
     `_ensure_headers(worksheet, headers: list[str])` para recibir la lista de
     encabezados como parámetro en vez de la constante fija `_HEADERS` de ventas.
     `sync_venta_to_sheets` debe seguir llamando a `_ensure_headers` pasando
     explícitamente su propia lista de encabezados (la misma constante de siempre,
     sin cambios de texto/orden).
   - Nueva función privada genérica `_upsert_row_by_id(worksheet, headers, entity_id,
     row_values) -> None`: busca una fila existente cuya primera columna coincida
     con `entity_id` (revisar el comportamiento real de `Worksheet.find`/`find` en
     la versión instalada, `gspread==6.1.2` — si retorna `None` o lanza
     `CellNotFound` cuando no hay coincidencia, y manejar ambos casos como "no
     existe, hay que insertar"); si encuentra la fila, sobrescribe ese rango
     completo (`A{fila}:{última_columna}{fila}`, calculando la última columna en
     base a `len(headers)`, no hardcodeada) con `row_values`; si no la encuentra,
     llama a `_ensure_headers(worksheet, headers)` y luego `worksheet.append_row(row_values)`.
     Esta función es la que usarán BE-015 y BE-016 además de esta tarea — no
     duplicar la lógica de upsert dentro de cada `sync_*_to_sheets`.
   - `sync_venta_to_sheets` **no** debe cambiar de comportamiento: sigue siendo
     append-only (nunca debe llamar a `_upsert_row_by_id`), solo se actualiza para
     usar las firmas generalizadas de `_get_worksheet(config.SHEETS_WORKSHEET_NAME)`
     y `_ensure_headers(worksheet, _HEADERS_VENTAS)`.
   - Nueva función pública `sync_categoria_to_sheets(categoria: dict[str, Any]) ->
     None`: resuelve la hoja `config.SHEETS_WORKSHEET_CATEGORIAS` vía
     `_get_worksheet(...)`, define `_HEADERS_CATEGORIAS = ["ID Categoria", "Nombre",
     "Color"]`, arma `row_values = [categoria["id"], categoria["nombre"],
     categoria["color"]]` y llama a `_upsert_row_by_id(worksheet, _HEADERS_CATEGORIAS,
     categoria["id"], row_values)`. Todo dentro de un único `try` que replica
     exactamente el mismo patrón de captura de excepciones que ya usa
     `sync_venta_to_sheets` (`SpreadsheetNotFound`, `WorksheetNotFound`, `APIError`,
     `GoogleAuthError`, `ConnectionError`/`Timeout`, `Exception` genérica con
     `logger.exception`) — nunca debe propagar una excepción hacia quien la llama.

2. **Config nueva en `backend/app/core/config.py`** (mismo patrón `os.getenv(...)`
   con default, sin introducir dependencias nuevas):
   - `SHEETS_WORKSHEET_CATEGORIAS: str`, default `"Categorias"`.
   - `SHEETS_WORKSHEET_PRODUCTOS: str`, default `"Productos"`.
   - `SHEETS_WORKSHEET_INSUMOS: str`, default `"Insumos"`.
   - Agregar los tres aunque `SHEETS_WORKSHEET_PRODUCTOS`/`SHEETS_WORKSHEET_INSUMOS`
     no se usen todavía en esta tarea (los usarán BE-015/BE-016), para dejar la
     configuración centralizada en un solo lugar y que esas tareas no tengan que
     volver a tocar `config.py`.
   - **No renombrar** `SHEETS_WORKSHEET_NAME` (la variable existente que usa
     ventas) — se mantiene igual por compatibilidad con instalaciones que ya la
     tengan configurada en su `.env`.

3. **Wiring en `backend/app/routers/categorias.py`**:
   - `crear_categoria`: agregar `background_tasks: BackgroundTasks` a la firma.
     Después de `db.refresh(categoria)` y antes del `return`, si
     `config.SHEETS_SYNC_ENABLED` es `True`, construir un diccionario plano
     (`id`, `nombre`, `color`, todos primitivos ya materializados) y encolar con
     `background_tasks.add_task(sync_categoria_to_sheets, ese_dict)`. Igual que en
     BE-012: con el flag en `False` (default) esa rama no debe evaluarse en
     absoluto.
   - `actualizar_categoria`: mismo patrón — agregar `background_tasks:
     BackgroundTasks`, y tras el `db.refresh(categoria)` exitoso encolar la misma
     tarea con el estado ya actualizado de la categoría.
   - `eliminar_categoria` **no** se toca en esta tarea (ver "No incluye").

**No incluye (fuera de alcance):**
- Sincronizar Productos o Insumos — eso es BE-015 y BE-016 respectivamente, que
  dependen de esta tarea para reutilizar `_upsert_row_by_id`/`_get_worksheet`/
  `_ensure_headers` ya generalizados.
- Sincronizar `eliminar_categoria`: si se borra una categoría, la fila
  correspondiente permanece en la hoja de Google Sheets (queda "huérfana" o
  desactualizada). Es una simplificación deliberada — es backup de mejor esfuerzo,
  no una réplica transaccional; el dueño puede borrar la fila a mano si le importa.
  Si en el futuro se necesita reflejar borrados, sería una tarea de seguimiento
  (mismo patrón que BE-013 fue seguimiento de BE-012).
- Crear la hoja `Categorias` dentro del spreadsheet real de Google — eso lo hace el
  usuario manualmente (o gspread la crea automáticamente si `client.open(...).worksheet(...)`
  falla con `WorksheetNotFound`... **no**: revisar el código actual, `_get_worksheet`
  no crea hojas, solo las busca; si no existe, se loguea `WorksheetNotFound` y no se
  sincroniza esa entidad. Documentar esto en el README igual que ya se documenta
  para `Ventas_Diarias`).
- Migrar/backfill retroactivo de categorías ya existentes en `brainfreeze.db` antes
  de esta tarea — solo se sincronizan creaciones/actualizaciones que ocurran a
  partir de que esta tarea esté desplegada y el flag activado.
- Reintentos automáticos o cola persistente si Sheets falla (igual que BE-012: se
  loguea y se pierde ese evento de sync puntual; la próxima creación/actualización
  de esa misma categoría lo corrige).
- Actualizar `backend/.env.example` y `backend/README.md` con las 3 variables
  nuevas de config y la sección de documentación — **sí incluido**, ver criterios
  de aceptación (esto sí es parte del alcance, se menciona aquí para que no se
  omita: la lista de "no incluye" de arriba es sobre funcionalidad, no sobre
  documentación).

## Criterios de aceptación

- [ ] Con `SHEETS_SYNC_ENABLED=false` (default): `POST /categorias` y
      `PUT`/`PATCH /categorias/{id}` responden exactamente igual que hoy (mismo
      código de estado, mismo body), sin encolar ninguna `BackgroundTask` ni tocar
      `gspread`/red/disco.
- [ ] Con `SHEETS_SYNC_ENABLED=true` pero sin `credentials.json`/`authorized_user.json`
      en disco: crear y actualizar una categoría sigue respondiendo `201`/`200`
      normalmente, sin excepción sin capturar ni `500`, con el warning esperado en
      los logs.
- [ ] `sync_categoria_to_sheets` nunca propaga una excepción, verificado con al
      menos dos escenarios de fallo simulados (además del caso "archivo ausente"
      del criterio anterior), igual que se validó para `sync_venta_to_sheets` en
      BE-012.
- [ ] **Upsert funciona correctamente** (verificable con mocks de `gspread`/
      `Worksheet`, sin depender de una hoja real):
      - Crear la categoría A (ID nuevo) en una hoja vacía → se inserta la fila de
        encabezados `["ID Categoria", "Nombre", "Color"]` y luego una fila con los
        datos de A (2 filas en total).
      - Actualizar la categoría A (mismo ID, `nombre`/`color` distintos) → la
        hoja sigue teniendo el mismo número de filas que antes (no se duplica A);
        la fila de A refleja los valores nuevos.
      - Crear la categoría B (ID distinto) después de A → se agrega una fila
        nueva para B, sin tocar la fila de A.
      - Actualizar una categoría cuyo ID no tiene fila existente en la hoja (caso
        borde: se activó el sync después de que esa categoría ya existía en
        SQLite) → se inserta como fila nueva en vez de fallar.
- [ ] El worksheet resuelto para `"Categorias"` se cachea independientemente del de
      `"Ventas_Diarias"`: sincronizar una venta y luego una categoría (o viceversa)
      en el mismo proceso no reautentica (`gspread.oauth`) ni reabre el spreadhseet
      (`client.open`) más de una vez en total, verificable con mocks contando
      invocaciones.
- [ ] `sync_venta_to_sheets` (BE-012/BE-013) sigue comportándose exactamente igual
      que antes de este refactor: sigue siendo append-only (nunca llama a
      `_upsert_row_by_id`), mismo formato/orden de columnas, mismos encabezados —
      confirmar por lectura de código y con al menos una prueba de regresión
      (mock) de que dos ventas seguidas siguen generando dos filas nuevas, nunca
      sobrescribiendo una fila existente.
- [ ] El diccionario pasado a `background_tasks.add_task(sync_categoria_to_sheets, ...)`
      contiene solo primitivos (`id`, `nombre`, `color`) materializados mientras la
      sesión de SQLAlchemy sigue viva, nunca el objeto ORM `Categoria`.
- [ ] `backend/.env.example` incluye las 3 variables nuevas
      (`SHEETS_WORKSHEET_CATEGORIAS=Categorias`, `SHEETS_WORKSHEET_PRODUCTOS=Productos`,
      `SHEETS_WORKSHEET_INSUMOS=Insumos`) sin comentar.
- [ ] `backend/README.md` documenta que además de `Ventas_Diarias`, el
      spreadsheet `BrainFreeze POS` debe tener una hoja `Categorias` (y menciona
      que `Productos`/`Insumos` vendrán en tareas posteriores) para que la
      sincronización de categorías funcione, y agrega las 3 filas nuevas a la
      tabla de variables de entorno.
- [ ] Se deja documentado en notas de implementación que la prueba end-to-end
      contra el Google Sheet real del usuario queda pendiente de que el usuario
      cree la hoja `Categorias` en su spreadsheet (o se documenta si ya la tiene y
      se probó).

## Notas de implementación

**Archivo tocado (refactor completo, mismo archivo):** `backend/app/services/sheets_service.py`.

**Decisiones tomadas:**

1. **Caché de cliente/spreadsheet/worksheet a 3 niveles**: `_client:
   gspread.Client | None` y `_spreadsheet: gspread.Spreadsheet | None`
   (ambos a nivel de módulo, independientes del nombre de hoja) más
   `_worksheets: dict[str, gspread.Worksheet]` (caché por nombre de hoja).
   `_get_worksheet(worksheet_name: str)` primero revisa el diccionario; si no
   está, resuelve `_client` (llamando `gspread.oauth(...)` solo si sigue en
   `None`) y `_spreadsheet` (llamando `client.open(...)` solo si sigue en
   `None`), y finalmente `spreadsheet.worksheet(worksheet_name)`, cacheando
   el resultado en `_worksheets[worksheet_name]`. Esto garantiza que
   `gspread.oauth`/`client.open` se llaman como máximo una vez por proceso
   sin importar cuántas hojas distintas se resuelvan (verificado en pruebas,
   ver abajo).
2. **`_headers_checked` pasa de `bool` único a `dict[str, bool]`**, con
   clave `worksheet.title` (no hace falta pasar el nombre de hoja por
   separado a `_ensure_headers`, ya que el objeto `Worksheet` ya lo expone
   vía `.title`, y coincide siempre con el nombre resuelto en
   `_get_worksheet`). `_ensure_headers(worksheet, headers: list[str])` ahora
   recibe la lista de encabezados como parámetro en vez de la constante fija
   `_HEADERS` — renombrada a `_HEADERS_VENTAS` para dejar espacio a
   `_HEADERS_CATEGORIAS` (y, en BE-015/016, `_HEADERS_PRODUCTOS`/
   `_HEADERS_INSUMOS`).
3. **`_upsert_row_by_id(worksheet, headers, entity_id, row_values)`**: usa
   `worksheet.find(str(entity_id), in_column=1)`. Se revisó el código fuente
   real de `gspread==6.1.2` instalado
   (`.venv/Lib/site-packages/gspread/worksheet.py`): en esta versión
   `Worksheet.find` **retorna `None`** cuando no hay coincidencia (nunca
   lanza `CellNotFound` — de hecho `gspread.exceptions.CellNotFound` ni
   siquiera existe como atributo en 6.1.2, se removió en algún punto de la
   historia de la librería). Para cumplir el pedido de "manejar ambos casos"
   sin romper con la versión instalada ni acoplarse a un símbolo que puede no
   existir, se arma dinámicamente `_CELL_NOT_FOUND_EXCEPTIONS: tuple[type[Exception],
   ...]` con `getattr(gspread.exceptions, "CellNotFound", None)` filtrando
   `None` — queda como tupla vacía en 6.1.2 (el `except _CELL_NOT_FOUND_EXCEPTIONS:`
   nunca se dispara, es sintácticamente válido con tupla vacía) y quedaría
   poblada automáticamente si en el futuro se actualiza a una versión de
   gspread que sí la lance. Además de eso, el código maneja explícitamente el
   caso `cell is None` (el real en la versión instalada) como "insertar".
   `worksheet.find` compara como string (`x.value == str_query`, confirmado
   leyendo `Worksheet._finder`), por eso se pasa siempre `str(entity_id)`
   aunque el ID sea un `int` en el dict de entrada.
4. **Cálculo de la última columna** (`_columna_a1`): usa
   `gspread.utils.rowcol_to_a1(1, len(headers))` (ej. `len(headers)=3` →
   `"C1"`) y le quita el sufijo numérico de fila con
   `re.sub(r"\d+$", "", ...)` para quedarse solo con la letra de columna
   (`"C"`), en vez de hardcodear el mapeo número→letra a mano.
5. **`sync_categoria_to_sheets`**: exactamente como describe el alcance —
   resuelve `config.SHEETS_WORKSHEET_CATEGORIAS`, arma
   `row_values = [categoria["id"], categoria["nombre"], categoria["color"]]`
   y delega en `_upsert_row_by_id`. Un único `try` con las mismas 6 ramas de
   excepción que ya usaba `sync_venta_to_sheets` (`SpreadsheetNotFound`,
   `WorksheetNotFound`, `APIError`, `GoogleAuthError`,
   `ConnectionError`/`Timeout`, `Exception` genérica con `logger.exception`).
6. **`sync_venta_to_sheets`**: solo se tocó lo mínimo para adaptarse a las
   firmas generalizadas (`_get_worksheet(config.SHEETS_WORKSHEET_NAME)`,
   `_ensure_headers(worksheet, _HEADERS_VENTAS)`) — el resto del cuerpo
   (`append_row` con el mismo orden/formato de columnas) queda sin cambios.
   Nunca llama a `_upsert_row_by_id` (verificado en pruebas, ver abajo).

**`backend/app/core/config.py`**: agregadas `SHEETS_WORKSHEET_CATEGORIAS`
(default `"Categorias"`), `SHEETS_WORKSHEET_PRODUCTOS` (default
`"Productos"`), `SHEETS_WORKSHEET_INSUMOS` (default `"Insumos"`), mismo
patrón `os.getenv` que el resto del archivo. `SHEETS_WORKSHEET_NAME` no se
tocó (compatibilidad con `.env` existentes).

**`backend/app/routers/categorias.py`**: `crear_categoria` y
`actualizar_categoria` reciben `background_tasks: BackgroundTasks`. En
ambos, después de `db.refresh(categoria)` y antes del `return`, si
`config.SHEETS_SYNC_ENABLED` es `True` se arma `categoria_dict = {"id":
categoria.id, "nombre": categoria.nombre, "color": categoria.color}` (solo
primitivos, mientras la sesión sigue viva) y se encola con
`background_tasks.add_task(sync_categoria_to_sheets, categoria_dict)`. Toda
la rama vive dentro del `if`, así que con el flag en `False` (default) no se
evalúa nada de esto. `eliminar_categoria` no se tocó, según alcance.

**`backend/.env.example`**: agregadas las 3 variables nuevas sin comentar
(`SHEETS_WORKSHEET_CATEGORIAS=Categorias`,
`SHEETS_WORKSHEET_PRODUCTOS=Productos`, `SHEETS_WORKSHEET_INSUMOS=Insumos`).

**`backend/README.md`**: sección renombrada a "Sincronización a Google
Sheets" (antes "...de ventas...") explicando la distinción append-only
(ventas) vs. upsert por ID (categorías, y productos/insumos en tareas
futuras), que `_get_worksheet` no crea hojas automáticamente (si falta,
se loguea `WorksheetNotFound` y esa entidad no se sincroniza), y que hace
falta crear manualmente la hoja `Categorias` (además de `Ventas_Diarias`) en
el spreadsheet para que esta tarea funcione. La tabla de variables de entorno
suma las 3 filas nuevas.

**Pruebas realizadas** (no hay `pytest` instalado en el proyecto — mismo
diagnóstico que BE-012/BE-013 — se usó `unittest.mock`, librería estándar,
vía scripts ad-hoc en el scratchpad de la sesión, más pruebas contra el
servidor real):

1. **Upsert correcto** (mock de `Worksheet` con backing store en memoria
   simulando filas reales): crear categoría A en hoja vacía → 2 filas
   (headers `["ID Categoria", "Nombre", "Color"]` + fila de A); actualizar A
   (mismo ID, nombre/color distintos) → sigue en 2 filas, fila de A con los
   valores nuevos; crear categoría B → 3 filas, fila de A intacta; actualizar
   un ID sin fila existente en la hoja (caso borde) → se inserta como fila
   nueva (4ta fila) en vez de fallar. Los 4 sub-escenarios del criterio de
   aceptación correspondiente pasaron.
2. **Caché de cliente/spreadsheet compartido + worksheet por hoja**: con
   `gspread.oauth` y `client.open` mockeados, se sincronizó una venta, luego
   una categoría, luego otra venta, en el mismo proceso →
   `gspread.oauth.call_count == 1`, `client.open.call_count == 1`,
   `spreadsheet.worksheet.call_count == 2` (una vez por nombre de hoja
   distinto: `Ventas_Diarias` y `Categorias`, cacheado en llamadas
   subsecuentes a la misma hoja).
3. **Regresión de `sync_venta_to_sheets`**: con `_upsert_row_by_id`
   mockeado, dos ventas seguidas → `_upsert_row_by_id.call_count == 0` (nunca
   se invoca desde el flujo de ventas) y la hoja de ventas queda con 3 filas
   (headers + 2 ventas), nunca sobrescribiendo una fila existente — confirma
   que sigue siendo append-only.
4. **`sync_categoria_to_sheets` nunca propaga excepciones**: 5 escenarios
   simulados con `gspread.oauth` lanzando `SpreadsheetNotFound`, `APIError`,
   `GoogleAuthError`, `requests.exceptions.ConnectionError`, y un
   `RuntimeError` genérico, más el escenario de `SHEETS_AUTHORIZED_USER_FILE`
   ausente — en los 6 casos la función retornó normalmente sin propagar
   nada.
5. **Flag en `False`**: se invocó `crear_categoria(...)` directamente (con
   una sesión de DB fake) parcheando `config.SHEETS_SYNC_ENABLED = False` →
   `len(background_tasks.tasks) == 0` y cero llamadas a
   `sync_categoria_to_sheets`/`_get_worksheet` — confirma que con el flag en
   `False` no se evalúa la rama ni se toca `gspread`.
6. **Contra el servidor real, en background** (`uvicorn`, puerto 8000,
   usuario de prueba `test-be014@brainfreeze.com` creado vía
   `crear_usuario.py`, siguiendo el mismo patrón que BE-012/BE-013):
   - `.env` real del proyecto ya tenía `SHEETS_SYNC_ENABLED=true` **y**
     `credentials.json`/`authorized_user.json` reales presentes en disco
     (el usuario completó el setup de BE-012 después de esa tarea) — esto
     permitió una prueba end-to-end real contra `gspread.oauth`/`client.open`
     reales, no solo mocks.
   - `POST /categorias` con `{"nombre":"BE014-Test","color":"#abcdef"}` →
     `201` normal, y en el log del servidor apareció exactamente `No se
     encontró la hoja 'Categorias' dentro del spreadsheet 'BrainFreeze
     POS'.` — confirma que el spreadsheet real sí abre correctamente
     (autenticación y `client.open` funcionan) pero la hoja `Categorias`
     **todavía no existe** en el spreadsheet del usuario (a diferencia de
     `Ventas_Diarias`, que sí existe desde BE-012/013).
   - `PATCH /categorias/6` (color distinto) → `200` normal, mismo log de
     `WorksheetNotFound` para `Categorias` — confirma que ni crear ni
     actualizar rompen nada aunque la hoja destino no exista todavía.
   - Se limpió la categoría de prueba con `DELETE /categorias/6` → `204`
     (no afecta Sheets, ya que la hoja `Categorias` no existe aún; si
     existiera, por diseño de esta tarea la fila quedaría huérfana, ver
     "No incluye").
   - El usuario de prueba `test-be014@brainfreeze.com` se dejó en
     `brainfreeze.db` (mismo criterio que `test-be012@brainfreeze.com`, que
     también sigue presente — no hay script de borrado de usuarios en el
     proyecto).

**Pendiente explícito**: la prueba end-to-end contra el Google Sheet real
del usuario confirmó que la infraestructura de autenticación/spreadsheet
funciona correctamente, pero **la hoja `Categorias` todavía no existe** en
el spreadsheet `BrainFreeze POS` del usuario — falta que el usuario la cree
manualmente (mismo nombre que `SHEETS_WORKSHEET_CATEGORIAS`, default
`"Categorias"`) para que la sincronización de categorías escriba filas
reales; hasta entonces, cada creación/actualización de categoría loguea el
`warning` de `WorksheetNotFound` visto arriba sin afectar la respuesta al
cliente. Una vez creada la hoja, no hace falta ningún cambio de código
adicional — el próximo `POST`/`PUT`/`PATCH /categorias` la sincronizará
normalmente (la próxima creación/actualización de una categoría existente
también la "recupera": ver caso borde #4 de la prueba de upsert).

## Revisión

**Veredicto: `done`.**

Revisé el código real (no solo las notas de implementación) y corrí mis propias
pruebas independientes con `unittest.mock` contra `app/services/sheets_service.py`
tal cual quedó en disco, sin confiar únicamente en lo reportado por
backend-dev.

1. **Generalización genuinamente reutilizable para BE-015/016**: leí
   `_get_worksheet`, `_ensure_headers`, `_upsert_row_by_id` y `_columna_a1` — los
   cuatro son completamente genéricos, sin ningún literal ni lógica específica de
   "categoría" filtrada adentro (esa lógica vive solo en
   `sync_categoria_to_sheets`, como debía ser). `_get_worksheet(worksheet_name)`
   cachea `_client`/`_spreadsheet` a nivel de módulo (independiente del nombre de
   hoja) y `_worksheets` por nombre, exactamente como pide el alcance.
   `config.py` ya trae `SHEETS_WORKSHEET_PRODUCTOS`/`SHEETS_WORKSHEET_INSUMOS`
   definidas (aunque sin uso todavía), así que BE-015/016 no necesitan volver a
   tocar `config.py`. Confirmé con test propio que resolver dos hojas distintas
   en el mismo proceso llama `gspread.oauth` y `client.open` una sola vez cada
   uno, y `spreadsheet.worksheet(...)` una vez por nombre distinto (cacheado en
   llamadas repetidas a la misma hoja) — ver T2 abajo.

2. **`sync_venta_to_sheets` sin cambio de comportamiento**: confirmado por
   lectura — sigue siendo `_get_worksheet(config.SHEETS_WORKSHEET_NAME)` +
   `_ensure_headers(worksheet, _HEADERS_VENTAS)` + `append_row(...)`, nunca
   invoca `_upsert_row_by_id`. `_HEADERS_VENTAS` mantiene texto/orden idéntico
   al `_HEADERS` que fijó BE-013 (`["ID Venta", "Fecha", "Método de pago",
   "Mesa", "Total", "Productos"]`, verificado contra
   `tasks/BE-013-headers-automaticos-google-sheets.md:265`). Con
   `_upsert_row_by_id` mockeado, dos ventas seguidas dieron
   `call_count == 0` y la hoja de ventas terminó con 3 filas (header + 2),
   nunca sobrescribiendo (T3).

3. **Manejo de excepciones nunca propaga hacia el router**: mismo patrón exacto
   que `sync_venta_to_sheets`/BE-012 (`SpreadsheetNotFound`, `WorksheetNotFound`,
   `APIError`, `GoogleAuthError`, `ConnectionError`/`Timeout`, `Exception`
   genérica con `logger.exception`) replicado en `sync_categoria_to_sheets`.
   Probé independientemente `APIError` durante `gspread.oauth`, un `RuntimeError`
   genérico, y `requests.exceptions.ConnectionError` (más el caso de
   `authorized_user.json` ausente) — los 4 escenarios retornaron normalmente sin
   propagar nada (T4a-c, T5).

4. **`SHEETS_SYNC_ENABLED=false` no toca red/disco**: confirmado por lectura de
   `categorias.py` — la construcción del dict y `background_tasks.add_task(...)`
   viven enteramente dentro de `if config.SHEETS_SYNC_ENABLED:` tanto en
   `crear_categoria` como en `actualizar_categoria`, igual que BE-012. Con el
   flag en `False` no se evalúa nada de esa rama.

5. **Claim técnico sobre `gspread==6.1.2`/`Worksheet.find` verificado contra la
   fuente real instalada** (`.venv/Lib/site-packages/gspread/worksheet.py`):
   confirmé que `find()` efectivamente retorna `None` en `StopIteration` (nunca
   lanza `CellNotFound`) y que `gspread.exceptions.CellNotFound` no existe como
   atributo en esta versión (`hasattr` da `False`) — el enfoque de
   `_CELL_NOT_FOUND_EXCEPTIONS` armado dinámicamente vía `getattr(...)` es
   correcto y no es un símbolo inventado. También confirmé en `_finder` que la
   comparación es `x.value == str_query` (string contra string), lo que
   justifica pasar siempre `str(entity_id)` en `_upsert_row_by_id` aunque el ID
   sea `int` en el dict — está bien hecho.

6. **Upsert por ID — los 4 sub-escenarios del criterio pasaron** con un
   `Worksheet` fake con backing store en memoria (no solo mock de llamadas):
   crear A en hoja vacía → 2 filas (headers + A); actualizar A (mismo ID) → sigue
   en 2 filas con valores nuevos, sin duplicar; crear B → 3 filas, A intacta;
   actualizar un ID sin fila existente → se inserta como fila nueva en vez de
   fallar (T1a-d).

7. **Dict pasado a `background_tasks.add_task`**: solo primitivos (`id`,
   `nombre`, `color`), materializados desde el objeto `Categoria` mientras la
   sesión sigue viva, nunca el ORM — confirmado en ambos endpoints de
   `categorias.py`.

8. **Documentación**: `backend/.env.example` trae las 3 variables nuevas sin
   comentar con los defaults correctos. `backend/README.md` documenta la
   distinción append-only (ventas) vs. upsert (categorías/productos/insumos),
   aclara que `_get_worksheet` no crea hojas automáticamente y que hace falta
   crear `Categorias` a mano, suma las 3 filas a la tabla de variables de
   entorno, y menciona que `Productos`/`Insumos` llegan en tareas de
   seguimiento.

9. **Estado real verificado**: `backend/.env` real ya tenía
   `SHEETS_SYNC_ENABLED=true` y credenciales reales desde el setup de BE-012 (no
   algo que esta tarea haya introducido) — coincide con lo documentado en
   "Pruebas realizadas" #6. Confirmé en `brainfreeze.db` que la categoría de
   prueba (`BE014-Test`) fue efectivamente eliminada y que el usuario de prueba
   `test-be014@brainfreeze.com` quedó (mismo patrón que `test-be012@...`, no hay
   script de borrado de usuarios en el proyecto).

No se usaron linters/type-checkers ni `pytest` (no están instalados en el
proyecto, mismo diagnóstico que BE-012/013); la verificación fue por lectura de
código fuente real (incluyendo el código de `gspread` instalado, no solo su
documentación) más pruebas dinámicas propias con `unittest.mock`, corridas
contra el módulo tal cual quedó en el repo.

No encontré hallazgos bloqueantes ni no bloqueantes. Todos los criterios de
aceptación se cumplen, la generalización es reutilizable sin necesidad de
reescritura para BE-015/016, y el pendiente explícito (crear la hoja
`Categorias` en el spreadsheet real del usuario) está correctamente declarado
como fuera de alcance de esta tarea.

**Status: `done`.**
