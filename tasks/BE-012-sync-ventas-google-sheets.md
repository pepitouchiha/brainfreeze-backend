---
id: BE-012
title: Sincronizar cada venta a Google Sheets en background (backup/dashboard de solo lectura)
area: backend
status: done
priority: medium
depends_on: []
created_by: planner
---

## Objetivo

Cada venta creada vía `POST /ventas` debe replicarse, en segundo plano y sin
afectar la respuesta al cliente, a una hoja de Google Sheets (`Ventas_Diarias`)
que sirve como backup externo y dashboard de solo lectura para el dueño del
negocio. La autenticación es OAuth de cuenta personal de Gmail (flujo
"Aplicación de escritorio" vía `gspread.oauth`), **no** una cuenta de servicio
— el dueño autoriza una vez su propio Gmail y de ahí en adelante el backend
reutiliza esa autorización sin volver a interactuar con un navegador.

Este diseño ya fue acordado con el usuario fuera del sistema de tareas;
`requirements.txt` (`gspread`, `google-auth`, `google-auth-oauthlib`) y
`.gitignore` (`credentials.json`, `authorized_user.json`) ya están
preparados. Esta tarea es la implementación real contra el código de
`backend/app/routers/ventas.py`, no un ejemplo ilustrativo.

**Importante para quien la implemente:** el usuario todavía NO tiene su
`credentials.json` real (falta que lo genere en Google Cloud Console). Por lo
tanto el criterio "probar end-to-end contra un Google Sheet real" **no** es
alcanzable en esta tarea y no debe bloquearla — ver la sección de
verificación abajo para lo que sí se puede y se debe probar ahora.

## Alcance

**Incluye:**

1. **`backend/app/services/sheets_service.py`** (nuevo módulo; la carpeta
   `app/services/` no existe todavía, crearla con su `__init__.py` si el
   resto del proyecto usa paquetes explícitos — revisar cómo están
   estructurados `routers/`/`schemas/` para mantener la misma convención).
   - Función pública `sync_venta_to_sheets(venta: dict) -> None`.
   - Autenticación con `gspread.oauth(credentials_filename=..., authorized_user_filename=...)`
     usando las rutas de `core/config.py` (nunca `gspread.service_account`).
   - El cliente autenticado (y el objeto `Spreadsheet`/`Worksheet` si tiene
     sentido) se cachea en una variable a nivel de módulo, para no
     reautenticar en cada venta.
   - Hace `append_row` sobre la worksheet `SHEETS_WORKSHEET_NAME` del
     spreadsheet `SHEETS_SPREADSHEET_NAME`.
   - Si `SHEETS_AUTHORIZED_USER_FILE` no existe en disco al momento de
     llamar la función: no debe intentar `gspread.oauth(...)` (eso
     dispararía el flujo interactivo que abre navegador y espera input —
     inaceptable dentro de una `BackgroundTask` de un proceso servidor, se
     quedaría colgado un hilo del threadpool). En ese caso, loguear un
     `warning` claro indicando que falta correr
     `python -m app.scripts.setup_google_sheets` y retornar sin más.
   - Debe capturar **todas** las excepciones posibles y nunca propagarlas:
     `requests.exceptions.ConnectionError`/`Timeout`, `gspread.exceptions.SpreadsheetNotFound`,
     `gspread.exceptions.WorksheetNotFound`, `gspread.exceptions.APIError`,
     `google.auth.exceptions.GoogleAuthError`, y un `except Exception` final
     de red de seguridad. Cada rama debe loguear con suficiente contexto
     (qué falló) usando el `logging` estándar de Python — nunca dejar que
     una excepción de este módulo llegue a quien lo llama.

2. **Config nueva en `backend/app/core/config.py`** (mismo patrón
   `os.getenv(...)` con default que ya usa el archivo, sin introducir
   `pydantic-settings` ni nada nuevo):
   - `SHEETS_SYNC_ENABLED: bool` — parseado desde string (`"true"`/`"false"`,
     case-insensitive), default `False`.
   - `SHEETS_SPREADSHEET_NAME: str`, default `"BrainFreeze POS"`.
   - `SHEETS_WORKSHEET_NAME: str`, default `"Ventas_Diarias"`.
   - `SHEETS_CREDENTIALS_FILE: Path` (o `str`), default
     `BASE_DIR / "credentials.json"`.
   - `SHEETS_AUTHORIZED_USER_FILE: Path` (o `str`), default
     `BASE_DIR / "authorized_user.json"`.

3. **Wiring en `backend/app/routers/ventas.py`, función `crear_venta`:**
   - Agregar el parámetro `background_tasks: BackgroundTasks` a la firma del
     endpoint.
   - Después de `db.refresh(venta)` y antes del `return venta`: si
     `SHEETS_SYNC_ENABLED` es `True`, construir un **diccionario plano** con
     tipos primitivos ya materializados (`str`/`int`/`float`), NUNCA pasar
     el objeto ORM `venta` ni `venta.items` a la tarea de fondo. Campos
     mínimos: `id`, `creado_en` (string ISO vía `.isoformat()`),
     `metodo_pago`, `mesa_id`, `total`, y una lista de items resumidos
     (`producto_id`, `cantidad`, `precio_unitario`, y el nombre del
     producto resuelto desde el diccionario `productos_por_id` que ya está
     en memoria en esa función — no hacer una query adicional). Encolar con
     `background_tasks.add_task(sync_venta_to_sheets, ese_dict)`.
   - Si `SHEETS_SYNC_ENABLED` es `False` (el default): el código no debe ni
     siquiera evaluar la rama que arma el diccionario ni llamar
     `background_tasks.add_task` — cero trabajo extra, cero import pesado de
     `gspread` disparado desde el flujo normal de creación de venta (el
     `import` del módulo `sheets_service` en la cabecera del router es
     aceptable; lo que no debe ocurrir es que el flag en `false` dispare
     conexión de red, lectura de archivos de credenciales, ni encolado de la
     tarea).

4. **Script de setup `backend/app/scripts/setup_google_sheets.py`**,
   siguiendo la convención de `crear_usuario.py`/`seed_productos.py`
   (docstring de módulo con instrucciones de uso vía
   `python -m app.scripts.setup_google_sheets`, función `main()` bajo
   `if __name__ == "__main__":`):
   - Llama a `gspread.oauth(credentials_filename=..., authorized_user_filename=...)`
     usando las mismas rutas de `core/config.py` — este script sí puede
     abrir navegador e interactuar, porque el dueño lo corre a propósito y
     de forma interactiva, nunca en medio de una venta real.
   - Al terminar exitosamente, imprime un mensaje claro (ej. "Autenticación
     completa. `authorized_user.json` guardado en `<ruta absoluta>`. Ya
     puedes activar `SHEETS_SYNC_ENABLED=true` en tu `.env`.").

5. **Documentación:**
   - `backend/.env.example`: agregar las 5 variables nuevas con el default
     seguro (`SHEETS_SYNC_ENABLED=false` sin comentar; las demás pueden ir
     comentadas o con su valor default explícito).
   - `backend/README.md`: sección breve nueva explicando (a) cómo obtener
     `credentials.json` (OAuth client ID tipo "Aplicación de escritorio" en
     Google Cloud Console, con la cuenta personal de Gmail del dueño — no
     cuenta de servicio), (b) correr `python -m app.scripts.setup_google_sheets`
     una vez, (c) activar `SHEETS_SYNC_ENABLED=true`. Añadir también la fila
     correspondiente a la tabla de variables de entorno existente en el
     README.

**No incluye (fuera de alcance):**
- Crear el `credentials.json` real ni el spreadsheet/hoja en Google Sheets —
  eso lo hace el usuario manualmente siguiendo la documentación de esta
  tarea.
- Retries automáticos, cola persistente, o reintentos si Sheets no responde
  — si falla, se loguea y se pierde ese registro puntual (es un backup de
  mejor esfuerzo, no la fuente de verdad; la fuente de verdad sigue siendo
  SQLite).
- Sincronización retroactiva de ventas ya existentes en `brainfreeze.db`
  antes de esta tarea.
- Cualquier endpoint o UI para consultar/gestionar el estado de la
  sincronización — el dashboard de solo lectura es el propio Google Sheet.

## Criterios de aceptación

- [ ] Con `SHEETS_SYNC_ENABLED=false` (o sin la variable en `.env`, usando el
      default): `POST /ventas` crea la venta exactamente igual que hoy
      (mismo `201`, mismo body de respuesta), sin encolar ninguna
      `BackgroundTask` y sin que el proceso intente leer
      `credentials.json`/`authorized_user.json` ni hacer ninguna llamada de
      red relacionada a Sheets.
- [ ] Con `SHEETS_SYNC_ENABLED=true` pero **sin** `credentials.json` ni
      `authorized_user.json` presentes en disco: `POST /ventas` sigue
      respondiendo `201` con la venta creada correctamente (la venta persiste
      en SQLite sin ningún cambio de comportamiento respecto a hoy), y en los
      logs del servidor aparece la advertencia esperada indicando que falta
      correr el script de setup — en ningún caso una excepción sin capturar,
      un `500`, ni un log de traceback crudo.
- [ ] `sync_venta_to_sheets` nunca propaga una excepción hacia quien la
      invoca, sea cual sea el tipo de fallo simulado (archivo de
      credenciales ausente, error de red, `SpreadsheetNotFound`,
      `WorksheetNotFound`, `APIError`, error de autenticación genérico) —
      verificar con al menos dos escenarios de fallo distintos además del
      caso de "archivo ausente" del criterio anterior.
- [ ] El diccionario que se pasa a `background_tasks.add_task(sync_venta_to_sheets, ...)`
      se construye con valores ya materializados (`str`/`int`/`float`)
      mientras la sesión de SQLAlchemy de la request todavía está viva,
      antes de la llamada a `add_task` — confirmar por lectura de código que
      en ningún punto se pasa el objeto ORM `venta` ni `venta.items`
      directamente a la tarea de fondo (evita `DetachedInstanceError` una
      vez cerrada la sesión).
- [ ] El cliente de `gspread` autenticado se cachea a nivel de módulo: dos
      llamadas sucesivas a `sync_venta_to_sheets` (en un escenario simulado
      donde sí hay `authorized_user.json` válido, aunque sea con un mock/stub
      de `gspread.oauth` para la verificación) no vuelven a invocar
      `gspread.oauth` en la segunda llamada.
- [ ] `python -m app.scripts.setup_google_sheets` existe, sigue la misma
      convención de CLI/docstring que `crear_usuario.py`/`seed_productos.py`,
      y al ejecutarse (puede probarse solo hasta el punto de que intenta
      abrir el flujo de `gspread.oauth`, dado que no hay `credentials.json`
      real todavía) no lanza un error de import ni de código antes de llegar
      a ese punto.
- [ ] `backend/.env.example` incluye las 5 variables nuevas con
      `SHEETS_SYNC_ENABLED=false` como default explícito.
- [ ] `backend/README.md` documenta el flujo completo de setup (obtener
      `credentials.json` como OAuth de escritorio con cuenta personal,
      correr el script, activar el flag) y la tabla de variables de entorno
      incluye las 5 nuevas filas.
- [ ] Se deja explícitamente documentado en las notas de implementación que
      la prueba end-to-end contra un Google Sheet real queda pendiente hasta
      que el usuario genere su `credentials.json` y corra el script de setup
      con su propia cuenta — no se marca como hecho algo que no se pudo
      verificar contra la API real de Google.

## Notas de implementación

**Archivos creados:**
- `backend/app/services/__init__.py` (paquete nuevo, siguiendo la convención de `routers/`/`schemas/`).
- `backend/app/services/sheets_service.py`: `sync_venta_to_sheets(venta: dict) -> None` + helper privado `_get_worksheet()` que hace la autenticación (`gspread.oauth`) y resuelve `spreadsheet.worksheet(...)`. El objeto `Worksheet` resultante se cachea en la variable de módulo `_worksheet`; si ya está seteada, no se vuelve a llamar `gspread.oauth`. Si `SHEETS_AUTHORIZED_USER_FILE` no existe, `_get_worksheet` loguea un `warning` indicando correr `python -m app.scripts.setup_google_sheets` y retorna `None` sin tocar `gspread.oauth` (evita el flujo interactivo colgando un hilo del threadpool). `sync_venta_to_sheets` envuelve toda la lógica en un único `try` con ramas específicas para `gspread.exceptions.SpreadsheetNotFound`, `WorksheetNotFound`, `APIError`, `google.auth.exceptions.GoogleAuthError`, `requests.exceptions.ConnectionError`/`Timeout`, y un `except Exception` final con `logger.exception` como red de seguridad — ninguna excepción se propaga.
- `backend/app/scripts/setup_google_sheets.py`: script CLI (`python -m app.scripts.setup_google_sheets`), misma convención de docstring/`main()` que `crear_usuario.py`. Valida primero que exista `SHEETS_CREDENTIALS_FILE` (si no, imprime instrucciones a `stderr` y sale con código 1, sin intentar `gspread.oauth`); si existe, llama `gspread.oauth(...)` (este sí puede abrir navegador, se corre a propósito). Al terminar imprime confirmación con la ruta absoluta de `authorized_user.json` y recuerda activar `SHEETS_SYNC_ENABLED=true`.

**Archivos modificados:**
- `backend/app/core/config.py`: 5 variables nuevas (`SHEETS_SYNC_ENABLED` bool parseado de string case-insensitive, default `False`; `SHEETS_SPREADSHEET_NAME` default `"BrainFreeze POS"`; `SHEETS_WORKSHEET_NAME` default `"Ventas_Diarias"`; `SHEETS_CREDENTIALS_FILE`/`SHEETS_AUTHORIZED_USER_FILE` como `Path`, default `BASE_DIR / "credentials.json"` / `BASE_DIR / "authorized_user.json"`), mismo patrón `os.getenv` que el resto del archivo.
- `backend/app/routers/ventas.py`: `crear_venta` ahora recibe `background_tasks: BackgroundTasks`. Después de `db.refresh(venta)` y antes del `return`, si `config.SHEETS_SYNC_ENABLED` es `True` se arma un diccionario plano (`id`, `creado_en` vía `.isoformat()`, `metodo_pago`, `mesa_id`, `total`, `items` con `producto_id`/`cantidad`/`precio_unitario`/`nombre_producto` resuelto de `productos_por_id` ya en memoria — sin query adicional) y se encola con `background_tasks.add_task(sync_venta_to_sheets, venta_dict)`. Toda esa rama vive dentro del `if`, así que con el flag en `False` (default) no se evalúa nada de esto ni se toca `gspread`/red/disco. El objeto ORM `venta`/`venta.items` nunca se pasa directamente a la tarea de fondo, solo el dict con tipos primitivos ya materializados mientras la sesión sigue viva.
- `backend/requirements.txt`: ya traía `gspread==6.1.2`, `google-auth==2.34.0`, `google-auth-oauthlib==1.2.1` (agregados antes de esta tarea); se instalaron en `.venv` (`pip install -r requirements.txt`) porque no estaban presentes.
- `backend/.env.example`: agregadas las 5 variables nuevas, `SHEETS_SYNC_ENABLED=false` sin comentar como default explícito.
- `backend/README.md`: nueva sección "Sincronización de ventas a Google Sheets" con el flujo completo (generar OAuth client ID de escritorio en Google Cloud Console con cuenta personal → correr el script de setup → activar el flag), más las 5 filas nuevas en la tabla de variables de entorno.

**Decisiones/supuestos:**
- El formato de fila en `append_row` es `[id, creado_en, metodo_pago, mesa_id, total, resumen_items]`, donde `resumen_items` es un string tipo `"Producto x2 ($5000); Otro x1 ($1500)"` armado a partir de la lista de items del dict. La tarea no especificó el formato exacto de columnas de la hoja `Ventas_Diarias`; si el dueño necesita columnas separadas por item (una fila por item, o columnas fijas por producto), avisar para ajustar — de momento prioricé una fila por venta con el resumen de items en una sola celda, ya que es lo más simple de mapear 1:1 con "cada venta creada... debe replicarse".
- `setup_google_sheets.py` valida la existencia de `SHEETS_CREDENTIALS_FILE` antes de llamar `gspread.oauth(...)` para dar un mensaje de error claro en vez de un `FileNotFoundError` crudo de la librería; esto es una decisión de UX del script interactivo, no afecta el criterio de aceptación (se verificó que el script no lanza error de import/código antes de llegar a ese punto — ver pruebas abajo).

**Pruebas realizadas** (servidor real corriendo en background, `http://127.0.0.1:8000`, más scripts standalone para los escenarios que requerían mockear `gspread` o cambiar el flag sin reiniciar el proceso en background):
1. `GET /health` → `200 {"status":"ok","database":"ok"}` antes y después de todos los cambios (confirmando que `--reload` cargó el código nuevo sin romper nada).
2. Instalación de dependencias: `.venv\Scripts\pip install -r requirements.txt` instaló `gspread`, `google-auth`, `google-auth-oauthlib` (no estaban presentes).
3. **`SHEETS_SYNC_ENABLED=false` (default, contra el servidor real en background):** `POST /ventas` con `{"metodo_pago":"efectivo","items":[{"producto_id":14,"cantidad":2}]}` (usuario de prueba `test-be012@brainfreeze.com` creado vía `crear_usuario.py`) → `201` con el mismo body de siempre.
4. **`SHEETS_SYNC_ENABLED=true`, sin `credentials.json`/`authorized_user.json` en disco:** como el proceso en background carga el `.env` una sola vez al arrancar (no se reinicia por cambios en `.env`), se verificó este escenario con un script standalone (`fastapi.testclient.TestClient` sobre la misma `app`, con `config.SHEETS_SYNC_ENABLED = True` seteado en memoria antes de importar el router) — `POST /ventas` devolvió `201` con la venta creada normalmente, y en el log apareció exactamente: `WARNING app.services.sheets_service: No se encontró 'authorized_user.json'. Corre 'python -m app.scripts.setup_google_sheets'...` — sin excepción sin capturar ni 500. (Se instaló `httpx` temporalmente en el `.venv` solo para poder usar `TestClient` en esta prueba puntual, y se desinstaló al terminar; no se agregó a `requirements.txt`.)
5. **`sync_venta_to_sheets` nunca propaga excepciones** — probado con `unittest.mock.patch` sobre `gspread.oauth` simulando 5 escenarios distintos: `SpreadsheetNotFound`, `APIError`, `GoogleAuthError`, `requests.exceptions.ConnectionError`, y una excepción genérica inesperada (`RuntimeError`) — en los 5 casos la función retornó normalmente sin propagar nada, cada una logueando la rama correspondiente (la genérica con `logger.exception`, que sí imprime traceback en el log pero no relanza la excepción).
6. **Caché del cliente/worksheet a nivel de módulo** — con `gspread.oauth` mockeado y `authorized_user.json` "presente" (archivo dummy), se llamó `sync_venta_to_sheets` dos veces seguidas: `gspread.oauth.call_count == 1` y `worksheet.append_row.call_count == 2`, confirmando que la segunda llamada reutiliza el worksheet cacheado.
7. `python -m app.scripts.setup_google_sheets` corrido sin `credentials.json` real → imprime el mensaje de instrucciones a `stderr` y sale con código 1 sin ningún error de import ni traceback.
8. Se revirtió cualquier cambio temporal a `.env` usado durante las pruebas (el `.env` real del proyecto quedó exactamente igual que antes de esta tarea, sin la variable `SHEETS_SYNC_ENABLED` — o sea, usando el default `False`).

**Pendiente explícito (fuera de alcance de esta tarea, como ya estaba acordado):** no se probó end-to-end contra un Google Sheet real ni contra `gspread.oauth` real, porque el usuario todavía no tiene su `credentials.json` generado en Google Cloud Console. Falta que el usuario: (1) genere el OAuth client ID de escritorio con su cuenta personal, (2) corra `python -m app.scripts.setup_google_sheets` para generar su `authorized_user.json`, y (3) active `SHEETS_SYNC_ENABLED=true` y verifique que las filas efectivamente aparecen en su spreadsheet `BrainFreeze POS` / hoja `Ventas_Diarias`. También queda pendiente confirmar con el usuario si el formato de una fila por venta con el resumen de items en una sola celda le sirve para su dashboard, o si prefiere una fila por item / columnas separadas.

## Revisión

**Veredicto: `done`.**

Revisé el código (no solo las notas) y corrí verificaciones propias, no solo confié
en lo reportado por la implementación:

1. **Regresión cero con `SHEETS_SYNC_ENABLED=false` (default real del `.env`)**:
   confirmé que `backend/.env` NO tiene ninguna de las 5 variables `SHEETS_*`
   (solo `.env.example` las documenta), por lo que se usa el default `False` de
   `app/core/config.py:28`. Hice `POST /ventas` contra el servidor real corriendo
   (`admin@brainfreeze.com`) y obtuve `201` con el body de siempre — la rama de
   `app/routers/ventas.py:88-105` está enteramente dentro del `if`, así que con
   el flag en `False` no se evalúa nada de esa rama (confirmado por lectura y
   por prueba empírica).

2. **`DetachedInstanceError` / dict materializado antes de `add_task`**: leí
   `crear_venta` línea por línea — el diccionario (`app/routers/ventas.py:89-104`)
   solo contiene primitivos (`venta.id`, `.isoformat()`, `metodo_pago`, `mesa_id`,
   `total`, y por cada item `producto_id/cantidad/precio_unitario` más
   `nombre_producto` resuelto de `productos_por_id` ya en memoria, sin query
   extra a `Producto`). Nunca se pasa el objeto ORM `venta` ni `venta.items` a
   `background_tasks.add_task` — solo el dict plano. Verifiqué esto también de
   forma independiente con un `TestClient` propio (parcheando
   `config.SHEETS_SYNC_ENABLED = True` en memoria y sin `authorized_user.json`
   en disco): `POST /ventas` devolvió `201` sin ningún `DetachedInstanceError`
   ni excepción, y el log mostró exactamente el `warning` esperado de
   `sheets_service`.
   - Nota menor no bloqueante: `venta.items` se accede después de
     `db.refresh(venta)` dentro de la rama del `if`; como `refresh()` sin
     `attribute_names` deja expiradas las relaciones, este acceso dispara un
     `SELECT` adicional a `venta_items` (solo cuando el flag está en `True`).
     No viola ningún criterio de aceptación (el "no hacer query adicional" del
     enunciado aplica a la resolución del nombre del producto, que sí evita
     una query extra usando `productos_por_id`), pero si en el futuro esto
     preocupa por volumen, se podría evitar pasando
     `attribute_names=["id", "creado_en", "metodo_pago", "mesa_id", "total"]`
     a `db.refresh(...)` para no expirar `items`.

3. **`sync_venta_to_sheets` nunca propaga excepciones**: además de las pruebas
   ya documentadas por la implementación, corrí mis propios escenarios contra
   `app/services/sheets_service.py` con `unittest.mock.patch`: (a) archivo
   `authorized_user.json` ausente → solo `warning`, sin excepción; (b)
   `gspread.oauth` lanzando `SpreadsheetNotFound` → solo `warning`, sin
   excepción; (c) `gspread.oauth` lanzando un `RuntimeError` genérico → cae en
   el `except Exception` final con `logger.exception` (traceback en el log,
   pero sin propagar); (d) caché de worksheet: dos llamadas seguidas con
   `gspread.oauth` mockeado → `oauth.call_count == 1`, `append_row.call_count
   == 2`. Los tres bloques de excepción (`SpreadsheetNotFound`,
   `WorksheetNotFound`, `APIError`) son independientes en la jerarquía de
   `gspread.exceptions` (todos heredan directo de `GSpreadException`), así que
   el orden de los `except` no tiene ambigüedad.

4. **Flag en `.env` real**: confirmado `false` (de hecho, ni siquiera está
   presente la variable en `backend/.env`, así que usa el default seguro). No
   quedaron `credentials.json`/`authorized_user.json` residuales en disco de
   las pruebas.

5. **`setup_google_sheets.py`**: no tiene efectos secundarios al importarse
   (todo vive bajo `if __name__ == "__main__":`), valida
   `SHEETS_CREDENTIALS_FILE` antes de intentar `gspread.oauth(...)` y sale con
   código 1 si falta, sin tocar el flujo interactivo. Sigue la convención de
   docstring/`main()` del resto de `app/scripts/`.

También verifiqué: `app/services/__init__.py` existe (paquete explícito,
consistente con `routers/`/`schemas/`); `requirements.txt` ya traía
`gspread`/`google-auth`/`google-auth-oauthlib`; `.gitignore` ya cubre
`credentials.json`/`authorized_user.json`; `README.md` documenta el flujo
completo y las 5 filas nuevas en la tabla de variables de entorno (líneas
65-69 y sección "Sincronización de ventas a Google Sheets"); `.env.example`
trae las 5 variables con `SHEETS_SYNC_ENABLED=false` explícito y sin comentar.

No se usaron linters/type-checkers (`ruff`/`mypy` no están instalados en este
proyecto ni en `requirements.txt`, y no hay suite de tests `pytest`), así que
la verificación fue por lectura de código + pruebas dinámicas propias descritas
arriba.

Todos los criterios de aceptación se cumplen. La única observación es la nota
menor (no bloqueante) sobre la query adicional de `venta.items` tras
`db.refresh`, y el pendiente ya declarado explícitamente en las notas de
implementación (prueba end-to-end real contra Google Sheets, que correctamente
queda fuera de alcance hasta que el usuario tenga su `credentials.json`).

**Status: `done`.**
