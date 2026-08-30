---
id: BE-016
title: Sincronizar Insumos a Google Sheets (creación, actualización y ajuste de stock, upsert por ID)
area: backend
status: done
priority: medium
depends_on: [BE-014]
created_by: planner
---

## Objetivo

Extender el backup de mejor esfuerzo a Google Sheets (BE-012/013/014) para cubrir
**Insumos**, el catálogo con mayor riesgo si se pierde (niveles de stock cambian
seguido y, a diferencia de productos/categorías, no son reconstruibles
retroactivamente de memoria si se pierde `brainfreeze.db`). Igual que en BE-014/
BE-015, cada insumo queda representado por **una sola fila** en la hoja `Insumos`
del spreadsheet `BrainFreeze POS`, actualizada in place. A diferencia de productos y
categorías, insumos tiene **tres** endpoints que deben disparar el sync: crear,
actualizar (`PUT`/`PATCH`) y `POST /insumos/{id}/ajustar-stock` — este último es el
que más importa cubrir, porque es el mecanismo principal por el que cambia el
stock día a día.

## Alcance

**Incluye:**

1. **`backend/app/services/sheets_service.py`** (extender la infraestructura de
   BE-014, no duplicarla):
   - Constante `_HEADERS_INSUMOS = ["ID Insumo", "Nombre", "Categoría", "Stock",
     "Stock mínimo", "Estado"]`.
   - Nueva función pública `sync_insumo_to_sheets(insumo: dict[str, Any]) -> None`:
     resuelve la hoja `config.SHEETS_WORKSHEET_INSUMOS` vía `_get_worksheet(...)`,
     arma `row_values = [insumo["id"], insumo["nombre"], insumo["categoria_nombre"],
     insumo["stock"], insumo["stock_minimo"], insumo["estado"]]` (el `estado` es
     el string derivado de `calcular_estado(stock, stock_minimo)` — `"Crítico"` /
     `"Bajo"` / `"OK"` — no un booleano ni un código numérico) y llama a
     `_upsert_row_by_id(worksheet, _HEADERS_INSUMOS, insumo["id"], row_values)`.
     Mismo patrón de captura total de excepciones que las demás funciones
     `sync_*_to_sheets` (nunca propaga).

2. **Wiring en `backend/app/routers/insumos.py`**, en **los tres** endpoints que
   mutan un insumo:
   - `crear_insumo`, `actualizar_insumo` y `ajustar_stock`: agregar
     `background_tasks: BackgroundTasks` a la firma de los tres. Después de
     `db.refresh(insumo)` y antes del `return`, si `config.SHEETS_SYNC_ENABLED` es
     `True`, construir el diccionario plano con `id`, `nombre`, `stock`,
     `stock_minimo`, `estado` (usar `calcular_estado(insumo.stock,
     insumo.stock_minimo)`, ya importado en el router, para mantener el mismo
     valor que ve el usuario en `InsumoOut`) más `categoria_nombre` resuelto con
     el mismo criterio que en BE-015 (reutilizar el objeto `Categoria` ya cargado
     por `_validar_categoria` si es directo, o una query puntual dentro de esa
     rama condicional si no lo es). Encolar con
     `background_tasks.add_task(sync_insumo_to_sheets, ese_dict)`.
   - En `ajustar_stock` específicamente: el sync debe reflejar el `nuevo_stock`
     ya persistido (después de `db.commit()`/`db.refresh(insumo)`), nunca el
     stock previo al ajuste.
   - Con el flag en `False` (default): ninguna de estas tres ramas se evalúa.
   - `eliminar_insumo` no se toca (mismo criterio que `eliminar_categoria`/
     `eliminar_producto`: la fila queda huérfana, backup de mejor esfuerzo).

**No incluye (fuera de alcance):**
- Sincronizar la eliminación de insumos.
- Cualquier lógica de alertas o notificación basada en `estado` (`"Crítico"`/
  `"Bajo"`) dentro de Sheets — la hoja solo refleja el dato, no dispara nada.
- Debounce/agrupación de sincronizaciones si `ajustar-stock` se llama muchas veces
  seguidas en poco tiempo para el mismo insumo — cada llamada al endpoint encola
  su propia `BackgroundTask` de forma independiente, tal como ya hace el patrón
  existente para ventas; si esto genera demasiadas llamadas a la API de Sheets en
  escenarios de uso intensivo, es una optimización de una tarea de seguimiento
  futura, no de esta.
- Migrar/backfill retroactivo de insumos ya existentes en `brainfreeze.db`.
- Crear la hoja `Insumos` en el spreadsheet real — la crea el usuario a mano.
- Cualquier cambio a `_upsert_row_by_id`/`_get_worksheet`/`_ensure_headers` más
  allá de usarlos (misma nota que BE-015: si la infraestructura de BE-014 no
  alcanza, se ajusta ahí).

## Criterios de aceptación

- [ ] Con `SHEETS_SYNC_ENABLED=false` (default): `POST /insumos`,
      `PUT`/`PATCH /insumos/{id}` y `POST /insumos/{id}/ajustar-stock` responden
      exactamente igual que hoy, sin `BackgroundTask` encolada.
- [ ] Con `SHEETS_SYNC_ENABLED=true` sin credenciales en disco: los tres
      endpoints siguen respondiendo con su código de estado y body normales, sin
      excepción sin capturar, con el warning esperado en logs.
- [ ] `sync_insumo_to_sheets` nunca propaga una excepción, verificado con al
      menos dos escenarios de fallo simulados.
- [ ] **Upsert por ID** (verificable con mocks): crear un insumo → fila nueva (con
      encabezados si la hoja estaba vacía); actualizar `stock_minimo`/`nombre` vía
      `PUT` → misma fila actualizada, sin duplicar; llamar
      `ajustar-stock` con una cantidad positiva y luego con una negativa → la fila
      del insumo refleja el `stock` final tras cada ajuste, siempre la misma fila
      (no se crea una fila nueva por cada ajuste).
- [ ] El `estado` sincronizado a Sheets coincide exactamente con el que devuelve
      el endpoint en `InsumoOut.estado` para ese mismo insumo en ese momento
      (`"Crítico"`, `"Bajo"` u `"OK"`, calculado con `calcular_estado`) —
      verificar al menos un caso de transición de estado (ej. un ajuste de stock
      que lleva el insumo de `"OK"` a `"Bajo"`) reflejado correctamente en la fila.
- [ ] `ajustar_stock` con un ajuste que dejaría el stock negativo sigue devolviendo
      `400` como hoy, y en ese caso **no** se encola ninguna sincronización a
      Sheets (no hay `db.commit()` exitoso ni `db.refresh()` en esa rama de
      error, así que no debe haber ninguna llamada a `sync_insumo_to_sheets`).
- [ ] El diccionario pasado a `background_tasks.add_task(sync_insumo_to_sheets, ...)`
      contiene solo primitivos, nunca el objeto ORM `Insumo` ni `Categoria`.
- [ ] Se reutiliza `_get_worksheet`/`_ensure_headers`/`_upsert_row_by_id` de
      BE-014 sin duplicar su lógica — verificable por lectura de código.
- [ ] `backend/README.md` menciona explícitamente la hoja `Insumos` (nombre
      configurable vía `SHEETS_WORKSHEET_INSUMOS`, ya documentada como variable en
      BE-014) como parte del setup necesario, y aclara que el ajuste de stock
      (`ajustar-stock`), no solo la creación/edición, dispara la sincronización.

## Notas de implementación

**Archivos tocados:**

- `backend/app/services/sheets_service.py`: extendido (sin reescribir el
  refactor de BE-014/015) con `_HEADERS_INSUMOS` y
  `sync_insumo_to_sheets(insumo: dict[str, Any]) -> None`. También se
  actualizó el docstring del módulo (mencionaba "Insumos" como pendiente de
  tareas posteriores) para reflejar que ya está implementado.
- `backend/app/routers/insumos.py` (wiring en `crear_insumo`,
  `actualizar_insumo` y `ajustar_stock`).
- `backend/README.md` (sección "Sincronización a Google Sheets": la mención
  a `Insumos` ya existía como placeholder desde BE-014/015, se actualizó
  para reflejar que está implementado y que `ajustar-stock` también
  dispara la sincronización; y el paso 3 del setup, donde antes decía "La
  hoja `Insumos` se documenta en la tarea de seguimiento que la
  sincroniza").
- `backend/.env.example` y `backend/app/core/config.py`: no requirieron
  cambios, `SHEETS_WORKSHEET_INSUMOS` (default `"Insumos"`) ya existía
  desde BE-014.

**Decisiones tomadas:**

1. **`sync_insumo_to_sheets`** (`sheets_service.py`): exactamente como
   describe el alcance — `_HEADERS_INSUMOS = ["ID Insumo", "Nombre",
   "Categoría", "Stock", "Stock mínimo", "Estado"]`, resuelve
   `config.SHEETS_WORKSHEET_INSUMOS` vía `_get_worksheet`, arma
   `row_values` leyendo `insumo["estado"]` tal cual (ya viene como el
   string `"Crítico"`/`"Bajo"`/`"OK"` calculado por el router, no se
   recalcula en el service) y delega en `_upsert_row_by_id` — no se
   duplicó nada de esa lógica. Mismo `try` con las 6 ramas de excepción
   que `sync_producto_to_sheets`/`sync_categoria_to_sheets`
   (`SpreadsheetNotFound`, `WorksheetNotFound`, `APIError`,
   `GoogleAuthError`, `ConnectionError`/`Timeout`, `Exception` genérica con
   `logger.exception`), nunca propaga.
2. **`calcular_estado` reutilizada, no reimplementada**: el router ya
   importaba `calcular_estado` de `app.models.insumo` (usada en `_a_out`
   para `InsumoOut.estado`). El helper `_insumo_dict_para_sheets` llama a
   la misma función (`calcular_estado(insumo.stock, insumo.stock_minimo)`)
   para construir el `estado` que va a Sheets, garantizando que sea
   exactamente el mismo valor que ve el usuario en la respuesta del
   endpoint para ese mismo insumo/momento. `sheets_service.py` no importa
   ni reimplementa esa lógica de umbrales en ningún punto.
3. **`_validar_categoria(db, categoria_id) -> Categoria`**: se cambió su
   firma (antes retornaba `None`, solo validaba existencia y lanzaba 404)
   para que retorne el objeto `Categoria` ya cargado, igual criterio que
   BE-015 aplicó en `productos.py`. Es una función independiente y sin
   relación con la homónima de `productos.py` (cada router tiene la suya),
   así que este cambio no afecta a productos.
   - `crear_insumo`: la categoría ya se obtiene de
     `_validar_categoria(db, payload.categoria_id)` para la validación
     existente — se reutiliza ese mismo objeto para `categoria_nombre`,
     cero queries adicionales.
   - `actualizar_insumo`: si `payload.categoria_id` viene en el request,
     se reutiliza el objeto ya validado (refleja la categoría *nueva*,
     verificado con prueba). Si no viene, se hace una query puntual
     adicional reutilizando `_validar_categoria(db,
     insumo.categoria_id)` — esta rama solo corre dentro del
     `if config.SHEETS_SYNC_ENABLED:`, con el flag en `False` no se
     ejecuta.
   - `ajustar_stock`: este endpoint nunca tocaba `Categoria` antes de esta
     tarea (no valida ni cambia la categoría del insumo). Se agregó una
     query puntual con `_validar_categoria(db, insumo.categoria_id)`,
     dentro del `if config.SHEETS_SYNC_ENABLED:`, para resolver
     `categoria_nombre` — con el flag en `False`, cero trabajo extra
     (mismo criterio que crear/actualizar).
4. **`_insumo_dict_para_sheets(insumo, categoria_nombre)`**: helper
   privado en `insumos.py` que arma el diccionario plano (`id`, `nombre`,
   `categoria_nombre`, `stock`, `stock_minimo`, `estado` — todos
   primitivos ya materializados, `estado` vía `calcular_estado`, nunca el
   objeto ORM) compartido entre los tres endpoints para no duplicar la
   construcción del payload.
5. **`ajustar_stock` refleja el `nuevo_stock` persistido**: el dict para
   Sheets se construye después de `db.commit()`/`db.refresh(insumo)`, leyendo
   `insumo.stock` (ya actualizado en memoria por el ORM tras el refresh),
   nunca el stock previo al ajuste — verificado con prueba de transición de
   estado (`OK` → `Bajo`).
6. **Caso borde crítico — `ajustar_stock` con stock resultante negativo**:
   la validación (`if nuevo_stock < 0: raise HTTPException(400, ...)`)
   ocurre *antes* de `insumo.stock = nuevo_stock`, `db.commit()` y
   `db.refresh()`; el bloque de sync está después de esas tres líneas, así
   que en la rama de error nunca se alcanza — no hay ninguna llamada a
   `sync_insumo_to_sheets` en ese caso (verificado con prueba y con
   servidor real, contando warnings de `WorksheetNotFound` en logs).
7. **`eliminar_insumo` no se tocó**, según alcance (mismo criterio que
   `eliminar_categoria`/`eliminar_producto`: fila huérfana en Sheets,
   backup de mejor esfuerzo).

**Pruebas realizadas** (no hay `pytest` instalado en el proyecto — mismo
diagnóstico que BE-012/013/014/015 — se usó `unittest.mock` vía scripts
ad-hoc en el scratchpad de la sesión, más pruebas contra el servidor real):

1. **Upsert por ID correcto** (mock de `Worksheet` con backing store en
   memoria, `test_upsert_por_id_crear_actualizar_ajustar`): crear insumo
   (id 101) en hoja vacía → 2 filas (headers `_HEADERS_INSUMOS` + fila con
   los 6 valores correctos, estado `"OK"`); actualizar `nombre`/
   `stock_minimo` → sigue en 2 filas, misma fila con valores nuevos;
   ajuste de stock positivo (+30) → misma fila, `stock` actualizado, sin
   fila nueva; ajuste de stock negativo (-45, transición `OK`→`Bajo`) →
   misma fila, `stock` y `estado` reflejando el cambio; crear un segundo
   insumo (id 202) → fila adicional, primera fila intacta.
2. **`sync_insumo_to_sheets` nunca propaga excepciones**
   (`test_nunca_propaga_excepciones`): 4 escenarios simulados
   (`SpreadsheetNotFound` en `_get_worksheet`, `ConnectionError` de red,
   `RuntimeError` genérico en `_get_worksheet`, `APIError` durante
   `worksheet.find`) — en los 4 casos la función retornó normalmente sin
   propagar nada (se logueó el warning/excepción correspondiente).
3. **Sin credenciales en disco** (`test_sin_credenciales_en_disco`): con
   `SHEETS_AUTHORIZED_USER_FILE` mockeado a no existir, `_get_worksheet`
   real retorna `None` y `sync_insumo_to_sheets` retorna sin excepción.
4. **Wiring del router, con `FakeDB`/`BackgroundTasks` reales**
   (`test_be016_router.py`):
   - Flag `False`: `crear_insumo(...)` → `len(bg.tasks) == 0`,
     `sync_insumo_to_sheets` nunca se llama.
   - Flag `True`, `crear_insumo`: el dict encolado en
     `background_tasks.add_task` tiene exactamente las 6 claves esperadas
     (`id, nombre, categoria_nombre, stock, stock_minimo, estado`), ningún
     valor es un objeto ORM (`Insumo`/`Categoria`).
   - `actualizar_insumo` cambiando `categoria_id` en el mismo request → el
     dict encolado trae el nombre de la categoría **nueva**, no la vieja.
   - `actualizar_insumo` sin tocar `categoria_id` → resuelve correctamente
     la categoría **actual** del insumo (no una incorrecta), junto con el
     resto de campos actualizados (`nombre`).
   - `ajustar_stock` con ajuste que provoca transición `OK`→`Bajo`
     (`stock=10, stock_minimo=8, cantidad=-5` → `stock=5`) → el `InsumoOut`
     devuelto y el dict encolado a Sheets coinciden exactamente en
     `estado` (`"Bajo"`) y `stock` (`5`, el valor final, no el previo).
   - `ajustar_stock` con `cantidad` que dejaría el stock negativo → lanza
     `HTTPException(400)`, `db.committed == 0` (no hubo commit exitoso),
     `len(bg.tasks) == 0` y `sync_insumo_to_sheets` nunca se llamó.
5. **Contra el servidor real, en background** (`uvicorn` puerto 8016, `.env`
   real del proyecto con `SHEETS_SYNC_ENABLED=true` y
   `credentials.json`/`authorized_user.json` reales ya presentes desde
   BE-012/014/015 — prueba end-to-end real contra
   `gspread.oauth`/`client.open` reales, no solo mocks). Usuario de prueba
   `test-be016@brainfreeze.com` creado vía `crear_usuario.py`:
   - `POST /insumos` (categoría existente `id=5`) → `201`, `estado: "OK"`.
   - `PATCH /insumos/{id}` (`stock_minimo`) → `200`, `estado` sigue `"OK"`.
   - `POST /insumos/{id}/ajustar-stock` con `+5` → `200`, `stock` reflejado.
   - `POST /insumos/{id}/ajustar-stock` con `-10` (deja el stock en 5,
     `stock_minimo=8`) → `200`, `estado: "Bajo"` (transición `OK`→`Bajo`
     confirmada end-to-end).
   - `POST /insumos/{id}/ajustar-stock` con `-999` → `400 Bad Request`
     (`"El ajuste dejaría el stock en -994.0, no puede ser negativo"`).
   - En los logs del servidor aparecieron exactamente **4** líneas
     `No se encontró la hoja 'Insumos' dentro del spreadsheet 'BrainFreeze
     POS'.` — una por cada una de las 4 mutaciones exitosas (crear, PATCH,
     ajuste +5, ajuste -10) y **ninguna** para el ajuste que devolvió
     `400` — confirma en vivo, contando las llamadas reales a
     `sync_insumo_to_sheets` vía sus logs, que el caso borde crítico de la
     tarea se cumple: la mutación que falla con `400` no encola ningún
     sync.
   - Se limpió el insumo de prueba con `DELETE /insumos/2` → `204`.
   - El usuario de prueba `test-be016@brainfreeze.com` se dejó en
     `brainfreeze.db` (mismo criterio que los usuarios de prueba de
     tareas anteriores).

**Pendiente explícito**: igual que en BE-014/015 con `Categorias`/
`Productos`, la prueba end-to-end contra el Google Sheet real del usuario
confirmó que la infraestructura de autenticación/spreadsheet funciona
correctamente, pero **la hoja `Insumos` todavía no existe** en el
spreadsheet `BrainFreeze POS` del usuario — falta que la cree manualmente
(mismo nombre que `SHEETS_WORKSHEET_INSUMOS`, default `"Insumos"`) para
que la sincronización de insumos escriba filas reales; hasta entonces,
cada creación/actualización/ajuste de stock loguea el `warning` de
`WorksheetNotFound` visto arriba sin afectar la respuesta al cliente. Una
vez creada la hoja, no hace falta ningún cambio de código adicional.

## Revisión

**Veredicto: `done`**

Revisión por lectura de código de `backend/app/services/sheets_service.py`,
`backend/app/routers/insumos.py`, `backend/app/models/insumo.py`,
`backend/app/schemas/insumo.py`, `backend/app/core/config.py` y
`backend/README.md`, más comparación directa con el patrón ya aprobado en
BE-014/BE-015 (`sync_categoria_to_sheets`/`sync_producto_to_sheets`,
`_validar_categoria` en `productos.py`). `python -m py_compile` sobre los dos
archivos tocados no arrojó errores; no hay `ruff`/`mypy` instalados en el
entorno (mismo diagnóstico que tareas anteriores).

Verificación puntual de los criterios de aceptación:

1. **`estado` reutilizado, no reimplementado**: `_insumo_dict_para_sheets`
   (`insumos.py:24-32`) llama a `calcular_estado(insumo.stock,
   insumo.stock_minimo)` — la misma función usada en `_a_out` para
   `InsumoOut.estado` (línea 42) — y devuelve el string plano (`"Crítico"`/
   `"Bajo"`/`"OK"`), no el enum `EstadoInsumo`. `sheets_service.py` no
   importa ni reimplementa umbrales de stock en ningún punto. Como
   `EstadoInsumo(str, Enum)` tiene los mismos valores que retorna
   `calcular_estado`, el string en el dict de sync y el `.value` de
   `InsumoOut.estado` coinciden exactamente para el mismo insumo/momento.
2. **Caso borde crítico (`ajustar_stock` con stock negativo)**: confirmado
   en `insumos.py:137-145` — el `raise HTTPException(400, ...)` ocurre
   antes de `insumo.stock = nuevo_stock`, `db.commit()` y `db.refresh()`;
   el bloque `if config.SHEETS_SYNC_ENABLED:` está después de esas tres
   líneas y nunca se alcanza en la rama de error. No hay ninguna llamada a
   `sync_insumo_to_sheets` en ese caso.
3. **Reutilización de infraestructura de BE-014**: `sync_insumo_to_sheets`
   (`sheets_service.py:282-321`) sigue exactamente el mismo esqueleto que
   `sync_producto_to_sheets`/`sync_categoria_to_sheets` — resuelve
   `_get_worksheet(config.SHEETS_WORKSHEET_INSUMOS)`, arma `row_values` en
   el orden de `_HEADERS_INSUMOS` y delega en `_upsert_row_by_id`, sin
   duplicar `_ensure_headers`/lógica de columnas/upsert.
4. **Manejo de excepciones**: mismas 6 ramas (`SpreadsheetNotFound`,
   `WorksheetNotFound`, `APIError`, `GoogleAuthError`,
   `ConnectionError`/`Timeout`, `Exception` genérica con
   `logger.exception`) que las demás `sync_*_to_sheets`; ninguna se
   re-lanza.
5. **`SHEETS_SYNC_ENABLED=false`**: en los tres endpoints, tanto el
   `background_tasks.add_task` como cualquier trabajo adicional
   (resolución de `categoria_nombre` vía query puntual en
   `actualizar_insumo`/`ajustar_stock` cuando no hay un objeto `Categoria`
   ya cargado) están dentro del `if config.SHEETS_SYNC_ENABLED:` — con el
   flag en `False` no hay queries ni trabajo extra más allá del que ya
   existía antes de esta tarea.
6. **Dict solo con primitivos**: `_insumo_dict_para_sheets` construye
   `id`/`nombre`/`categoria_nombre`/`stock`/`stock_minimo`/`estado`, todos
   valores ya materializados (`int`/`str`/`float`), nunca el objeto ORM
   `Insumo` ni `Categoria`.
7. **`categoria_nombre` correcto en los tres endpoints**: `crear_insumo`
   reutiliza el objeto `Categoria` ya cargado por `_validar_categoria`
   (cero queries extra); `actualizar_insumo` usa la categoría *nueva* si
   `payload.categoria_id` viene en el request, o resuelve la actual con una
   query puntual si no; `ajustar_stock` resuelve la categoría actual del
   insumo (antes no tocaba `Categoria`, ahora sí, solo dentro del `if`).
   Mismo criterio que `_validar_categoria` en `productos.py` (BE-015):
   confirmado por lectura, son funciones independientes por router.
8. **`ajustar_stock` refleja `nuevo_stock` persistido**: el dict de sync se
   arma leyendo `insumo.stock` después de `db.commit()`/`db.refresh()`
   (`insumos.py:143-150`), nunca el valor previo al ajuste.
9. **`eliminar_insumo` no se tocó**: correcto según alcance, mismo criterio
   que `eliminar_categoria`/`eliminar_producto`.
10. **README**: la sección "Sincronización a Google Sheets" documenta la
    hoja `Insumos` (`SHEETS_WORKSHEET_INSUMOS`, default `"Insumos"`) y
    aclara explícitamente que `POST /insumos/{id}/ajustar-stock` también
    dispara la sincronización, no solo creación/edición
    (`README.md:111-117`, `README.md:149-150`).

Sin hallazgos bloqueantes. Nota menor, no bloqueante: en `actualizar_insumo`
y `ajustar_stock`, la resolución de `categoria_nombre` vía
`_validar_categoria(db, insumo.categoria_id)` post-commit podría en teoría
lanzar `HTTPException(404)` si la categoría referenciada ya no existe,
devolviendo un 404 al cliente pese a que la mutación ya se persistió. En la
práctica esto es inalcanzable porque `eliminar_categoria`
(`categorias.py:126-135`) rechaza con `409` el borrado de cualquier
categoría con insumos asociados, garantizando la integridad referencial; es
el mismo patrón ya aceptado en BE-015 para `productos.py`, así que no se
marca como hallazgo de esta tarea.
