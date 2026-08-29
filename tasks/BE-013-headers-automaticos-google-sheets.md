---
id: BE-013
title: Insertar automáticamente la fila de encabezados en Google Sheets cuando la hoja esté vacía
area: backend
status: done
priority: low
depends_on: [BE-012]
created_by: planner
---

## Objetivo

BE-012 (`done`) ya sincroniza cada venta a la hoja `Ventas_Diarias` vía
`worksheet.append_row([...])`, en este orden exacto de columnas: `id`
("ID Venta"), `creado_en` ("Fecha"), `metodo_pago` ("Método de pago"),
`mesa_id` ("Mesa"), `total` ("Total"), `items_resumen` ("Productos"). El
usuario ya probó esto de punta a punta contra su Google Sheet real
("BrainFreeze POS" / pestaña "Ventas_Diarias") y confirmó que las filas de
venta se insertan correctamente.

Hoy el usuario tiene que escribir la fila de encabezados a mano la primera
vez. Si algún día recrea el spreadsheet desde cero, pierde esos encabezados
hasta que los vuelva a escribir manualmente. Esta tarea agrega ese único
comportamiento: si la hoja está vacía, insertar automáticamente la fila de
encabezados antes de insertar la primera venta.

## Alcance

**Incluye**, todo dentro de `backend/app/services/sheets_service.py`:

1. **Detección de "hoja vacía"**: usar `worksheet.acell('A1').value` (una
   sola llamada de lectura a la API) y tratar como "vacía" cuando el valor
   sea `None` o cadena vacía. No usar `get_all_values()` (trae toda la hoja,
   más caro) ni `worksheet.row_count` (es el tamaño configurado de la grilla,
   no indica si hay contenido).

2. **Inserción del encabezado** cuando la hoja esté vacía: insertar primero
   la fila exacta `["ID Venta", "Fecha", "Método de pago", "Mesa", "Total",
   "Productos"]` (mismo orden y mismo texto que ya usa el usuario a mano —
   no inventar nombres de columna nuevos), y **después** la fila de la venta
   actual, en la misma llamada a `sync_venta_to_sheets` que disparó la
   detección. Usar `insert_row([...], index=1)` (o `append_row` si al leer
   el código concluyes que es equivalente en una hoja realmente vacía;
   documenta la elección en notas de implementación).

3. **Caché a nivel de módulo para no repetir la verificación en cada venta**:
   la llamada a `acell('A1')` es una llamada extra a la API de Sheets: no
   debe ejecutarse en cada venta, solo hasta que se resuelva una vez (haya
   insertado encabezados o haya confirmado que ya existían) dentro del
   tiempo de vida del proceso. Dos formas válidas de lograrlo, evalúa cuál
   encaja mejor con el código actual y justifica tu elección en las notas de
   implementación:
   - (a) una variable de módulo nueva (ej. `_headers_checked: bool`, al
     estilo de `_worksheet`), seteada a `True` después del primer intento
     (exitoso o fallido) de verificar/insertar encabezados; o
   - (b) hacer la verificación dentro de `_get_worksheet()`, en la rama que
     solo se ejecuta la primera vez que se resuelve el `Worksheet` (antes de
     asignarlo a `_worksheet`) — esto reutiliza el mecanismo de caché que ya
     existe sin agregar un segundo flag, pero exige que un fallo en la
     verificación de encabezados no impida retornar el `worksheet` resuelto
     (la venta debe poder sincronizarse igual).
   En cualquiera de las dos, una vez verificado/intentado en este proceso,
   llamadas subsecuentes a `sync_venta_to_sheets` no deben volver a leer
   `acell('A1')` ni reevaluar la inserción de encabezados.

4. **Manejo de errores**: si la inserción de encabezados falla por cualquier
   motivo (red, permisos, `APIError`, lo que sea), debe comportarse igual
   que el resto del módulo (ver BE-012): loguear con `logger.warning`/
   `logger.exception` según corresponda y **no** dejar escapar la excepción
   hacia quien llama. Un fallo al insertar encabezados nunca debe impedir
   que se intente el `append_row` de la fila de la venta en esa misma
   llamada.

**No incluye (fuera de alcance):**
- Cambiar el orden, nombres o formato de las columnas existentes de la fila
  de venta — eso es de BE-012 y ya está validado por el usuario contra su
  Sheet real; esta tarea no lo toca.
- Ninguna variable de configuración nueva en `core/config.py` ni en
  `.env.example` — el nombre de las columnas de encabezado va fijo en
  código, igual que ya está fijo el orden de la fila de venta.
- Reintentar la inserción de encabezados en llamadas posteriores dentro del
  mismo proceso si el primer intento falló (se cachea el intento, no el
  éxito — ver punto 3).
- Migrar o reescribir encabezados existentes con texto distinto al esperado
  (si `A1` ya tiene *algún* valor, se asume que la hoja ya tiene sus propios
  encabezados o datos, y no se toca).

## Criterios de aceptación

- [ ] Con una hoja de prueba vacía (`acell('A1').value` es `None` o `""`):
      una llamada a `sync_venta_to_sheets(venta)` produce, en orden, primero
      la fila de encabezados exacta `["ID Venta", "Fecha", "Método de pago",
      "Mesa", "Total", "Productos"]` y luego la fila de la venta — dos filas
      en total, encabezado antes que la venta.
- [ ] Con una hoja de prueba que ya tiene contenido en `A1` (headers ya
      puestos por el usuario o por una sincronización previa): una llamada a
      `sync_venta_to_sheets(venta)` **no** inserta ninguna fila de
      encabezado, solo agrega la fila de la venta.
- [ ] Dentro de un mismo proceso, `acell('A1')` se llama como máximo una vez
      en total a lo largo de múltiples invocaciones de
      `sync_venta_to_sheets` (verificable con un mock contando invocaciones):
      la segunda, tercera, etc. venta sincronizada en el mismo proceso no
      vuelve a leer `A1` ni reevalúa si hay que insertar encabezados,
      independientemente de si el primer intento insertó encabezados,
      confirmó que ya existían, o falló.
- [ ] Si la inserción de encabezados falla (simular con mock lanzando
      `gspread.exceptions.APIError` u otra excepción al insertar la fila de
      encabezado): se loguea la advertencia correspondiente, la excepción no
      se propaga hacia el llamador de `sync_venta_to_sheets`, y el
      `append_row` de la fila de la venta se intenta de todas formas en esa
      misma llamada.
- [ ] No existe ningún escenario reproducible en el que se inserten
      encabezados duplicados en una hoja que ya los tenía (cubierto por el
      segundo criterio, pero verificar explícitamente que no hay una
      ventana de carrera dentro de la misma llamada — no aplica
      concurrencia real dado que es un solo hilo por venta, pero confirmar
      por lectura de código).
- [ ] El formato y orden de la fila de venta (`append_row` con
      `[id, creado_en, metodo_pago, mesa_id, total, items_resumen]`)
      permanece exactamente igual a como lo dejó BE-012 — no se reordenan ni
      renombran columnas de venta como efecto colateral de este cambio.
- [ ] Con `SHEETS_SYNC_ENABLED=false` (default): sin cambios de
      comportamiento respecto a hoy — esta lógica nueva solo se ejecuta
      dentro del camino que ya dependía del flag en `True`.
- [ ] Las pruebas anteriores se validan con pruebas propias del
      backend-dev (mocks de `gspread`/`Worksheet`, o una hoja de prueba
      real si lo prefiere) **sin** depender de que el usuario intervenga.
      Si además se corre contra el Google Sheet real del usuario ("BrainFreeze
      POS" / "Ventas_Diarias", ya autorizado y configurado), documentarlo en
      notas de implementación, pero no es bloqueante para pasar a
      `in-review`.

## Notas de implementación

**Archivo tocado:** `backend/app/services/sheets_service.py` (único archivo,
según alcance de la tarea).

**Decisiones tomadas:**

1. **Detección de hoja vacía**: `worksheet.acell("A1").value` dentro de una
   función nueva `_ensure_headers(worksheet)`. Se trata como vacía cuando el
   valor es falsy (`None` o `""`), vía `if not worksheet.acell("A1").value`.

2. **Inserción de encabezados**: se usa `worksheet.insert_row(_HEADERS,
   index=1)` (no `append_row`) tal como sugiere la tarea, para garantizar
   explícitamente que la fila de encabezados quede en la posición 1 sin
   depender de que la hoja esté realmente vacía en runtime (evita ambigüedad
   si algún día `A1` está vacío pero hay contenido más abajo por algún motivo
   raro). `_HEADERS` es una constante de módulo con el texto exacto que ya usa
   el usuario a mano: `["ID Venta", "Fecha", "Método de pago", "Mesa",
   "Total", "Productos"]`.

3. **Caché**: se eligió la opción **(a)** del enunciado — una variable de
   módulo nueva `_headers_checked: bool`, seteada a `True` como *primera*
   instrucción dentro de `_ensure_headers` (antes de intentar
   `acell`/`insert_row`), no después de que el intento resuelva. Esto
   garantiza que se cachea el *intento* y no el éxito, incluso si el proceso
   se interrumpiera a mitad de la llamada (poco probable dado que es
   síncrono, pero más robusto por lectura de código). Se prefirió (a) sobre
   (b) porque mantiene `_get_worksheet()` enfocado únicamente en resolver la
   conexión/hoja (su responsabilidad actual), y separa con claridad la
   responsabilidad nueva ("verificar/insertar encabezados") en una función
   propia, sin acoplar un fallo de headers al camino de caché del worksheet
   en sí (que si fallara, sí debe reintentarse en la siguiente venta, a
   diferencia de los headers).

4. **Manejo de errores**: `_ensure_headers` tiene su propio bloque
   try/except que replica el mismo patrón de excepciones específicas ya
   usado en `sync_venta_to_sheets` (`APIError`, `GoogleAuthError`,
   `ConnectionError`/`Timeout`, y `Exception` genérica con
   `logger.exception`), y **nunca deja escapar la excepción**. Se llama
   desde dentro del `try` principal de `sync_venta_to_sheets`, justo después
   de obtener el `worksheet` y antes de armar `items_resumen`/`append_row`,
   de forma que un fallo en headers no impide que se siga ejecutando el
   `append_row` de la venta en la misma llamada.

**No se tocó** el orden/nombres de columnas de la fila de venta ni el flag
`SHEETS_SYNC_ENABLED` (verificado por lectura de código: el único lugar que
lo consulta es `app/routers/ventas.py:88`, sin cambios).

**Cómo se probó:** no hay carpeta `tests/` ni `pytest` instalado en el
proyecto (se verificó antes de escribir pruebas, para no agregar una
dependencia nueva fuera de alcance). Se validó con un script ad-hoc en el
scratchpad de la sesión (`unittest.mock`, librería estándar, sin
dependencias nuevas) que mockea `_get_worksheet()`/`Worksheet.acell` y
verifica, contra el código real de `sheets_service.py`:

- Hoja vacía (`acell` → `None`): 1 sola llamada a `acell`, `insert_row`
  llamado una vez con los 6 headers exactos y `index=1`, y luego
  `append_row` con la fila de venta en el orden/formato de BE-012 intacto.
- Hoja con headers puestos (`acell` → `"ID Venta"`): `insert_row` NO se
  llama, solo `append_row`.
- 3 ventas seguidas en el mismo proceso (hoja vacía en la primera): `acell`
  se llama una sola vez en total, `insert_row` una sola vez (primera venta),
  `append_row` 3 veces (una por venta) — confirma la caché del punto 3 y que
  no hay duplicación de headers.
- `insert_row` lanzando `gspread.exceptions.APIError`: se loguea
  `logger.warning`, la excepción no se propaga, `append_row` se intenta
  igual en esa misma llamada; y en una venta subsecuente dentro del mismo
  proceso no se reintenta (`acell`/`insert_row` siguen en 1), confirmando
  que se cachea el intento fallido y no solo el éxito.

No se probó contra el Google Sheet real del usuario ("BrainFreeze POS" /
"Ventas_Diarias") para esta tarea: la hoja real ya tiene headers puestos a
mano, así que una prueba ahí solo ejercitaría el escenario "ya tiene
encabezados" (cubierto por el mock del segundo escenario) y no aporta
cobertura adicional sin crear una hoja de prueba aparte; se deja como
opcional, no bloqueante, según indicó el criterio de aceptación
correspondiente.

**Para probarlo manualmente** (opcional): con `SHEETS_SYNC_ENABLED=true` y
una hoja de prueba nueva y vacía (spreadsheet/worksheet distinto al de
producción, cambiando `SHEETS_SPREADSHEET_NAME`/`SHEETS_WORKSHEET_NAME` en
`.env` temporalmente), crear una venta vía `POST /ventas` y confirmar en la
hoja que la fila 1 queda con los encabezados y la fila 2 con la venta.

## Revisión

**Veredicto: `done`**

Revisé `app/services/sheets_service.py` completo (no solo el diff) y
reproduje de forma independiente los 4 escenarios que dice haber probado el
backend-dev, con mocks propios (no reutilicé su script) contra el código real
del módulo (venv del proyecto, `gspread` instalado ahí):

1. **Hoja vacía**: `acell` se llama 1 vez, `insert_row(_HEADERS, index=1)` se
   llama 1 vez con el texto exacto, y luego `append_row` con
   `[1, '2026-08-29T00:00:00', 'efectivo', 2, 10.0, 'Cafe x1 ($10.0)']` — el
   orden/formato de la fila de venta de BE-012 queda intacto. Cumple
   criterio 1 y 6.
2. **Hoja con headers puestos** (`acell` → `"ID Venta"`): `insert_row` no se
   llama, solo `append_row`. Cumple criterio 2.
3. **3 ventas seguidas en el mismo proceso** (primera hoja vacía): `acell`
   se llama 1 sola vez en total, `insert_row` 1 sola vez, `append_row` 3
   veces. Cumple criterio 3 y confirma no hay duplicación de encabezados
   dentro del mismo proceso (criterio 5).
4. **Fallo al insertar headers** (`insert_row` lanza `gspread.exceptions.
   APIError`): se loguea `logger.warning`, la excepción no se propaga,
   `append_row` se intenta igual en esa misma llamada; en una segunda venta
   del mismo proceso no se reintenta `acell`/`insert_row` (ambos siguen en 1)
   — se cachea el intento fallido, no solo el éxito. Cumple criterio 4.
   Adicionalmente probé un quinto escenario no mencionado por el
   backend-dev: `acell()` en sí lanzando `RuntimeError` (no `APIError`) —
   cae en el `except Exception` genérico con `logger.exception`, no se
   propaga, y `append_row` se ejecuta igual. Confirma que ninguna excepción
   dentro de `_ensure_headers` puede escapar, sin importar en qué línea del
   try ocurra.

Verificación adicional de lectura de código:

- `SHEETS_SYNC_ENABLED` sigue consultándose únicamente en
  `app/routers/ventas.py:88`, sin tocar; `sync_venta_to_sheets` solo se
  agenda vía `background_tasks.add_task(...)` dentro de ese `if`. Con el
  flag en `false` la ruta nueva (`_ensure_headers`) ni se importa
  efectivamente en el flujo — sin cambio de comportamiento. Cumple
  criterio 7.
- No hay carpeta `tests/` ni `pytest` instalado en el venv del proyecto —
  confirmé ambas cosas de forma independiente, consistente con lo que
  reporta el backend-dev en notas de implementación.
- El manejo de excepciones en `_ensure_headers` replica el mismo orden y
  granularidad que ya usa `sync_venta_to_sheets` (`APIError` →
  `GoogleAuthError` → red → genérica), consistente con el estilo del
  módulo.
- El texto y orden de `_HEADERS` coincide exactamente con lo pedido:
  `["ID Venta", "Fecha", "Método de pago", "Mesa", "Total", "Productos"]`.

**Observación no bloqueante (no requiere cambios para `done`):** la
combinación check-then-act `if _headers_checked: return` / `_headers_checked
= True` (líneas 42-44) tiene, en teoría, una ventana de carrera si dos
`POST /ventas` llegan casi simultáneamente mientras la hoja sigue vacía: como
`sync_venta_to_sheets` se agenda vía `BackgroundTasks`, cada venta corre en
un hilo del threadpool de Starlette, y dos hilos distintos sí pueden
ejecutar `_ensure_headers` en paralelo (esto contradice ligeramente la
premisa de la tarea de que "no aplica concurrencia real dado que es un solo
hilo por venta" — es un hilo por venta, pero pueden ser dos hilos
simultáneos para dos ventas). El peor caso es insertar la fila de
encabezados duplicada una única vez en la vida útil del proceso (solo
mientras la hoja está vacía), nunca una excepción sin capturar. El mismo
patrón de riesgo ya existe hoy en el caché de `_worksheet` (no introducido
por esta tarea). Dado el impacto mínimo (backup de mejor esfuerzo, nunca
bloquea el flujo principal) y que replica un patrón preexistente en el
módulo, no lo considero bloqueante, pero lo dejo anotado por si se quiere
usar `threading.Lock()` en un futuro ajuste si se detectan encabezados
duplicados en producción.

El resto de los criterios de aceptación (alcance respetado — único archivo
tocado, sin nuevas variables de config, sin migración de headers existentes)
se verificó por lectura de código y coincide con lo documentado en notas de
implementación.
