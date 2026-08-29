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
| `SHEETS_SYNC_ENABLED` | Activa la sincronización de ventas a Google Sheets (default: `false`) |
| `SHEETS_SPREADSHEET_NAME` | Nombre del spreadsheet de Google Sheets (default: `BrainFreeze POS`) |
| `SHEETS_WORKSHEET_NAME` | Nombre de la hoja dentro del spreadsheet (default: `Ventas_Diarias`) |
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

## Sincronización de ventas a Google Sheets (backup/dashboard de solo lectura)

Cada venta creada vía `POST /ventas` puede replicarse en segundo plano a una
hoja de Google Sheets (`Ventas_Diarias`), como backup externo y dashboard de
solo lectura para el dueño del negocio. Es un backup de mejor esfuerzo, no la
fuente de verdad — si Sheets no responde, se pierde ese registro puntual y la
venta sigue quedando en SQLite normalmente. Autenticación OAuth de cuenta
personal de Gmail (no cuenta de servicio):

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
   el backend reutiliza en cada venta sin volver a interactuar con un
   navegador.
3. Activa `SHEETS_SYNC_ENABLED=true` en tu `.env`. Asegúrate de que exista un
   spreadsheet llamado `BrainFreeze POS` (o el valor de
   `SHEETS_SPREADSHEET_NAME`) con una hoja `Ventas_Diarias` (o el valor de
   `SHEETS_WORKSHEET_NAME`), compartido/accesible con la cuenta de Gmail que
   autorizaste.

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
