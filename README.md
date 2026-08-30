# BrainFreeze — Backend

API REST para BrainFreeze, un sistema de punto de venta para una heladería/granizadería: catálogo de productos, control de inventario, gestión de mesas, registro de ventas y reportes de contabilidad.

Construido con **FastAPI + SQLAlchemy 2.0 + SQLite**, autenticación por **JWT**.

## Stack

- Python 3.10+
- FastAPI 0.115
- SQLAlchemy 2.0 (estilo `DeclarativeBase`)
- SQLite (archivo local, sin servidor de DB externo)
- Autenticación: JWT (`pyjwt`) + hashing de contraseñas con `bcrypt`

## Estructura

```
app/
  main.py              # app FastAPI, CORS, lifespan (create_all), registro de routers
  core/
    config.py           # configuración desde variables de entorno (.env)
    security.py          # hashing de password + emisión/verificación de JWT
  db/
    session.py            # engine + SessionLocal + get_db()
    base.py                # Base declarativa
    base_all.py             # punto único de importación de todos los modelos
  models/                    # modelos SQLAlchemy (Categoria, Producto, Insumo, Mesa, Venta, Usuario...)
  schemas/                    # schemas Pydantic de entrada/salida
  routers/                     # endpoints por recurso (auth, categorias, productos, insumos, mesas, ventas, reportes, health)
  scripts/                      # utilidades de línea de comandos (crear_usuario, seed_productos)
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # y ajustar valores si hace falta
```

Levantar el servidor:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

La base SQLite (`brainfreeze.db`) se crea automáticamente al arrancar. Verificar que todo funciona:

```
GET http://127.0.0.1:8000/health
→ 200 {"status":"ok","database":"ok"}
```

## Variables de entorno

Ver `.env.example`:

| Variable             | Descripción                                                        |
|----------------------|---------------------------------------------------------------------|
| `DATABASE_URL`       | URL de conexión SQLAlchemy (default: SQLite local)                 |
| `CORS_ORIGINS`       | Orígenes permitidos, separados por coma (default: Vite en 5173)    |
| `JWT_SECRET_KEY`     | Secreto para firmar los tokens JWT — **cambiar en producción**     |
| `JWT_ALGORITHM`      | Algoritmo de firma (default: `HS256`)                              |
| `JWT_EXPIRE_MINUTES` | Minutos de validez del token (default: `480`)                      |
| `SHEETS_SYNC_ENABLED` | Activa la sincronización a Google Sheets (default: `false`) |
| `SHEETS_SPREADSHEET_NAME` | Nombre del spreadsheet de Google Sheets (default: `BrainFreeze POS`) |
| `SHEETS_WORKSHEET_NAME` | Nombre de la hoja de ventas dentro del spreadsheet (default: `Ventas_Diarias`) |
| `SHEETS_WORKSHEET_CATEGORIAS` | Nombre de la hoja de categorías dentro del spreadsheet (default: `Categorias`) |
| `SHEETS_WORKSHEET_PRODUCTOS` | Nombre de la hoja de productos dentro del spreadsheet (default: `Productos`) |
| `SHEETS_WORKSHEET_INSUMOS` | Nombre de la hoja de insumos dentro del spreadsheet (default: `Insumos`) |
| `SHEETS_CREDENTIALS_FILE` | Ruta al `credentials.json` de OAuth (default: `credentials.json` en la raíz de `backend/`) |
| `SHEETS_AUTHORIZED_USER_FILE` | Ruta donde se guarda el token autorizado (default: `authorized_user.json` en la raíz de `backend/`) |

## Crear un usuario

No hay endpoint público de registro. El usuario inicial (y cualquier otro) se crea/actualiza vía script:

```powershell
.\.venv\Scripts\python -m app.scripts.crear_usuario admin@brainfreeze.com "MiPasswordSegura123"
```

## Datos de ejemplo

```powershell
.\.venv\Scripts\python -m app.scripts.seed_productos
```

## Sincronización a Google Sheets (backup/dashboard de solo lectura)

Cada venta creada vía `POST /ventas`, cada categoría creada/actualizada vía
`POST`/`PUT`/`PATCH /categorias`, cada producto creado/actualizado vía
`POST`/`PUT`/`PATCH /productos` y cada insumo creado/actualizado/ajustado vía
`POST`/`PUT`/`PATCH /insumos` y `POST /insumos/{id}/ajustar-stock`, puede
replicarse en segundo plano a una hoja de Google Sheets dentro del mismo
spreadsheet, como backup externo y dashboard de solo lectura para el dueño del
negocio. Es un backup de mejor esfuerzo, no la fuente de verdad — si Sheets no
responde, se pierde esa sincronización puntual y el registro sigue quedando en
SQLite normalmente. Autenticación OAuth de cuenta personal de Gmail (no cuenta
de servicio):

- **Ventas** (`Ventas_Diarias`): log de solo-append, una fila nueva por cada
  venta creada, nunca se sobrescribe una fila existente.
- **Categorías** (`Categorias`): una sola fila por categoría, actualizada in
  place (upsert por ID) cada vez que se crea o edita — no se duplica al
  editar.
- **Productos** (`Productos`): una sola fila por producto (columnas `ID
  Producto`, `Nombre`, `Categoría`, `Precio`, `Estado`, `Sabor`, `Tamaño`),
  mismo mecanismo de upsert por ID que categorías. `imagen_base64` **nunca**
  se incluye en la hoja (blobs potencialmente grandes, sin valor como backup
  legible).
- **Insumos** (`Insumos`): una sola fila por insumo (columnas `ID Insumo`,
  `Nombre`, `Categoría`, `Stock`, `Stock mínimo`, `Estado`), mismo mecanismo
  de upsert por ID que categorías/productos. Además de crear/editar el
  insumo, **`POST /insumos/{id}/ajustar-stock` también dispara la
  sincronización** (con el `stock` ya ajustado) — es el endpoint que más
  importa cubrir, porque es el mecanismo principal por el que cambia el
  stock día a día. `Estado` refleja el mismo cálculo (`Crítico`/`Bajo`/`OK`)
  que devuelve la API en `InsumoOut.estado`.

Si alguna de estas hojas no existe todavía dentro del spreadsheet, esa
entidad simplemente no se sincroniza (se loguea un `warning` de
`WorksheetNotFound`) — `_get_worksheet` solo busca hojas existentes, no las
crea automáticamente. Crea manualmente cada hoja que necesites dentro del
spreadsheet `BrainFreeze POS` (o el valor de `SHEETS_SPREADSHEET_NAME`) antes
de activar la sincronización correspondiente.

1. En [Google Cloud Console](https://console.cloud.google.com/), crea un
   proyecto (o reutiliza uno) y genera credenciales **OAuth client ID** tipo
   **"Aplicación de escritorio"**, usando tu cuenta personal de Gmail (la
   misma con la que vas a abrir/editar el spreadsheet). Descarga el JSON y
   guárdalo como `backend/credentials.json` (ya está en `.gitignore`, nunca se
   sube al repositorio).
2. Corre el script de autorización una sola vez (abre el navegador para que
   inicies sesión y autorices el acceso):

   ```powershell
   .\.venv\Scripts\python -m app.scripts.setup_google_sheets
   ```

   Esto genera `backend/authorized_user.json` (también en `.gitignore`), que
   el backend reutiliza en cada sincronización sin volver a interactuar con
   un navegador.
3. Activa `SHEETS_SYNC_ENABLED=true` en tu `.env`. Asegúrate de que exista un
   spreadsheet llamado `BrainFreeze POS` (o el valor de
   `SHEETS_SPREADSHEET_NAME`), compartido/accesible con la cuenta de Gmail
   que autorizaste, con una hoja `Ventas_Diarias` (o el valor de
   `SHEETS_WORKSHEET_NAME`) para ventas, una hoja `Categorias` (o el valor de
   `SHEETS_WORKSHEET_CATEGORIAS`) para categorías, una hoja `Productos` (o el
   valor de `SHEETS_WORKSHEET_PRODUCTOS`) para productos y una hoja `Insumos`
   (o el valor de `SHEETS_WORKSHEET_INSUMOS`) para insumos.

## Endpoints principales

- `POST /auth/login` — login, devuelve `{access_token, token_type}`
- `GET/POST/PUT/PATCH/DELETE /categorias` — CRUD de categorías
- `GET/POST/PUT/PATCH/DELETE /productos` — CRUD de productos (filtros `search`, `categoria_id`; incluye `imagen_base64` opcional como Data URL, y `sabor`/`tamano`/`imagen_base64` se pueden limpiar a `null` explícitamente en un `PATCH`)
- `GET/POST/PUT/PATCH/DELETE /insumos` + `POST /insumos/{id}/ajustar-stock` — inventario (el stock solo se mueve por ajuste explícito, nunca por edición directa)
- `GET/POST/PUT/PATCH/DELETE /mesas` + `POST /mesas/{id}/liberar` — gestión de mesas
- `GET/POST /ventas` — registro y consulta de ventas (total y precios se calculan siempre en el servidor; `metodo_pago` es `efectivo` o `transferencia`)
- `GET /reportes/hoy`, `GET /reportes/mensual`, `GET /reportes/alertas-stock` — reportes para dashboard/contabilidad

Todos los endpoints salvo `/health` y `/auth/login` requieren `Authorization: Bearer <token>`.

## Proyecto

Este backend se construyó de forma iterativa con un flujo planner → backend-dev → reviewer; el historial de tareas (objetivo, criterios de aceptación, decisiones tomadas y revisión) queda documentado en [`tasks/`](./tasks).
