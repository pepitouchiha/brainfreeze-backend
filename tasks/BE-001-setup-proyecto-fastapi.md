---
id: BE-001
title: Setup inicial del proyecto FastAPI + SQLite
area: backend
status: done
priority: high
depends_on: []
created_by: planner
---

## Objetivo

Dejar listo el esqueleto del backend para que las siguientes tareas (categorías,
productos, inventario, mesas, ventas, reportes) se implementen sobre una base
consistente, sin que cada una tenga que decidir estructura de carpetas, conexión
a base de datos o configuración desde cero.

## Alcance

Incluye:
- Estructura de carpetas (routers/, models/, schemas/, db/ o equivalente razonable).
- Conexión a SQLite (archivo local, ej. `brainfreeze.db`) vía SQLAlchemy (u otra
  librería que justifiques en tus notas).
- Creación de tablas a partir de los modelos (a nivel dev basta con
  `create_all` al arrancar; no hace falta Alembic todavía).
- Endpoint de salud (`GET /health` o similar) para verificar que el server y la
  DB responden.
- CORS habilitado para que el frontend (Vue en otro puerto, ej. 5173) pueda
  consumir la API en desarrollo.
- Locale/moneda: los montos se manejan en **pesos colombianos (COP)** — sin
  decimales fraccionarios de centavo en la práctica del negocio, pero no asumas
  que el modelo de datos debe ser entero forzado; usa tu criterio (ej. `Numeric`
  o `int` en centavos/pesos, documenta la decisión).

No incluye: ningún modelo de dominio específico (eso lo cubren BE-002 en
adelante), ni autenticación (cubierta en BE-008).

## Criterios de aceptación

- [x] `uvicorn` levanta el server sin errores y `GET /health` responde 200.
- [x] La base SQLite se crea automáticamente si no existe.
- [x] CORS permite requests desde el origen del frontend en desarrollo.
- [x] Estructura de carpetas documentada brevemente en las notas de
      implementación para que el resto de tareas la sigan.
- [x] `requirements.txt` (o `pyproject.toml`) con las dependencias fijadas.

## Notas de implementación

### Estructura de carpetas

Todo el backend vive en `backend/`, con el paquete de la app en `backend/app/`:

```
backend/
  requirements.txt        # dependencias fijadas (fastapi, uvicorn, sqlalchemy)
  .env.example             # variables de entorno soportadas (DATABASE_URL, CORS_ORIGINS)
  .gitignore                # ignora .venv/, __pycache__, brainfreeze.db, .env
  app/
    main.py                 # crea la app FastAPI, registra CORS, create_all en startup, incluye routers
    core/
      config.py             # lectura de configuración desde variables de entorno (DATABASE_URL, CORS_ORIGINS)
    db/
      session.py            # engine + SessionLocal + dependencia get_db() para inyectar Session en endpoints
      base.py                # Base declarativa (DeclarativeBase) de la que heredan los modelos SQLAlchemy
      base_all.py            # punto único de importación de todos los modelos, para que create_all los detecte
    routers/
      health.py               # GET /health, hace SELECT 1 contra la DB para verificar conexión real
    models/                    # (vacío) aquí van los modelos SQLAlchemy de BE-002 en adelante
    schemas/                   # (vacío) aquí van los schemas Pydantic de entrada/salida
```

Convención para las próximas tareas (BE-002+): cada modelo nuevo hereda de
`app.db.base.Base`, vive en `app/models/<nombre>.py`, y se importa en
`app/db/base_all.py` (hay un ejemplo comentado) para que
`Base.metadata.create_all()` lo registre al arrancar. Los routers nuevos se
agregan en `app/routers/<recurso>.py` y se incluyen con
`app.include_router(...)` en `app/main.py`. Los schemas Pydantic van en
`app/schemas/<recurso>.py`.

### Decisiones tomadas

- **ORM**: SQLAlchemy 2.0 (estilo `DeclarativeBase`), por ser el estándar de
  facto con FastAPI y no requerir dependencias adicionales de config
  (se evitó `pydantic-settings` para no sumar una dependencia nueva; la
  configuración se lee directo de `os.getenv` en `app/core/config.py`).
- **Conexión SQLite**: `sqlite:///<ruta absoluta a backend/brainfreeze.db>`
  por defecto (calculada desde `BASE_DIR` en `config.py`, no depende del
  directorio desde el que se lance `uvicorn`), configurable vía
  `DATABASE_URL`. Se usa `connect_args={"check_same_thread": False}` porque
  SQLite por defecto solo permite el hilo que abrió la conexión — necesario
  para que funcione con el pool de conexiones de SQLAlchemy bajo FastAPI.
- **Creación de tablas**: `Base.metadata.create_all(bind=engine)` en el
  evento `startup` de `main.py`. Es idempotente (no falla si las tablas ya
  existen) y suficiente para esta fase de desarrollo, tal como indica el
  alcance de la tarea (sin Alembic todavía).
- **CORS**: orígenes permitidos configurables vía `CORS_ORIGINS` (lista
  separada por comas), con default `http://localhost:5173,http://127.0.0.1:5173`
  para cubrir el puerto por defecto de Vite (FE-001) tanto en desarrollo.
- **Moneda (COP)**: esta tarea no crea modelos de dominio, así que no hay
  columnas monetarias todavía. Dejo la decisión documentada aquí para que
  BE-002 en adelante la sigan: usar `Integer` en SQLAlchemy para representar
  pesos colombianos enteros (sin fracciones de centavo), evitando `Float`
  (impreciso) y sin necesidad de `Numeric`/`Decimal` porque el negocio no
  maneja centavos. Si alguna tarea futura necesita fracciones, debe
  justificarlo explícitamente y no asumir este default.
- **Dependencias fijadas** en `requirements.txt`: `fastapi==0.115.0`,
  `uvicorn[standard]==0.30.6`, `sqlalchemy==2.0.35`. No se agregó
  `pydantic-settings`, `alembic` ni librerías de auth (fuera de alcance,
  auth es BE-008).

### Cómo probarlo

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Luego:

```
GET http://127.0.0.1:8000/health
→ 200 {"status":"ok","database":"ok"}
```

Verificado en este entorno (Windows, Python 3.10.11, venv en
`backend/.venv`): el server levanta sin errores, `GET /health` responde
`200 {"status":"ok","database":"ok"}`, y `backend/brainfreeze.db` se crea
automáticamente al iniciar (no existía antes de correr `uvicorn`). El
archivo `.env.example` documenta las variables soportadas; si no hay `.env`,
se usan los defaults (SQLite local + orígenes de Vite en 5173).

### Dudas / seguimiento sugerido (no bloqueante para esta tarea)

- BE-006 menciona descuento de inventario por receta de producto — ya está
  marcado ahí mismo como fuera de alcance del MVP, solo lo confirmo aquí
  porque toca la capa de modelos que se monta sobre esta base.

### Corrección post-revisión (changes-requested → in-review)

Se corrigieron los dos hallazgos de la revisión anterior:

1. **`.env` ignorado (bloqueante)**: `app/core/config.py` nunca invocaba
   `load_dotenv()`, así que aunque `python-dotenv` estuviera instalado
   (transitivamente vía `uvicorn[standard]`), nada lo llamaba y las
   variables de `.env` nunca se aplicaban. Se agregó `python-dotenv==1.0.1`
   explícito a `requirements.txt` (ya no se depende del extra transitivo de
   `uvicorn[standard]`) y se agregó `load_dotenv(BASE_DIR / ".env")` al
   inicio de `config.py`, antes de los `os.getenv(...)`. Se usa la ruta
   absoluta vía `BASE_DIR` (no `load_dotenv()` sin argumentos) para que siga
   sin depender del directorio desde el que se lance `uvicorn`, consistente
   con la decisión ya tomada para `DATABASE_URL`.
2. **`@app.on_event("startup")` deprecado (no bloqueante)**: migrado a
   `lifespan` con `@asynccontextmanager` en `app/main.py`. `app = FastAPI(...)`
   ahora recibe `lifespan=lifespan`, y ese context manager hace
   `Base.metadata.create_all(bind=engine)` antes del `yield`. Se removió el
   decorador `on_event` y su import implícito quedó igual (no se tocó nada
   más de la app).

Archivos modificados: `backend/requirements.txt`, `backend/app/core/config.py`,
`backend/app/main.py`.

**Verificación (reproduciendo exactamente el escenario del reviewer)**, en
`backend/.venv` (Windows, Python 3.10.11):

```powershell
cd backend
.\.venv\Scripts\pip install -r requirements.txt   # instala python-dotenv==1.0.1 explícito
```

Con `backend/.env` conteniendo `CORS_ORIGINS=http://example-test:9999`:

```powershell
.\.venv\Scripts\python -c "from app.core import config; print(config.CORS_ORIGINS)"
# -> ['http://example-test:9999']   (antes del fix devolvía el default)
```

Sin `.env` (borrado), se confirma que se preserva el comportamiento por
defecto:

```powershell
.\.venv\Scripts\python -c "from app.core import config; print(config.CORS_ORIGINS)"
# -> ['http://localhost:5173', 'http://127.0.0.1:5173']
```

También se verificó que el server sigue levantando sin errores y sin el
`DeprecationWarning` de `on_event`:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --port 8123
```

```
GET http://127.0.0.1:8123/health
→ 200 {"status":"ok","database":"ok"}
```

`brainfreeze.db` se crea automáticamente al arrancar (verificado que no
existía antes de correr el server). No quedó ningún `.env` de prueba ni
`brainfreeze.db` en el repo tras la verificación.

## Revisión

**Veredicto: `changes-requested`**

Verificado en este entorno (Windows, Python 3.10.11, venv `backend/.venv`):
- `uvicorn app.main:app` levanta sin errores, `GET /health` responde
  `200 {"status":"ok","database":"ok"}`, y `backend/brainfreeze.db` se crea
  automáticamente al arrancar. ✅
- CORS: el default (`http://localhost:5173,http://127.0.0.1:5173`) está
  correctamente aplicado vía `CORSMiddleware`. ✅
- Estructura de carpetas y convención para BE-002+ documentadas con claridad
  en las notas. ✅
- `requirements.txt` con versiones fijadas (`fastapi==0.115.0`,
  `uvicorn[standard]==0.30.6`, `sqlalchemy==2.0.35`). ✅
- Sin SQL crudo, sin secretos hardcodeados, sin paths absolutos de máquina
  local (`BASE_DIR` se calcula relativo al archivo). ✅
- Type hints presentes en todo el código (`config.py`, `session.py`,
  `health.py`, `main.py`). ✅

### Hallazgo bloqueante

**`backend/app/core/config.py` nunca carga el archivo `.env`.** El código
lee configuración solo con `os.getenv(...)` directo, sin ninguna llamada a
`load_dotenv()` en ningún punto del arranque, y el comando documentado en
"Cómo probarlo" (`python -m uvicorn app.main:app --reload --port 8000`) no
usa `--env-file`, que es la única forma en que `uvicorn` cargaría un `.env`
automáticamente. Verificado reproduciendo el escenario: creé `backend/.env`
con `CORS_ORIGINS=http://example-test:9999` (siguiendo exactamente
`.env.example`) y `config.CORS_ORIGINS` siguió devolviendo el default
(`['http://localhost:5173', 'http://127.0.0.1:5173']`) — el archivo `.env`
se ignora por completo.

Esto no es solo la duda de estilo que se dejó abierta en "Dudas / seguimiento
sugerido" (si fijar `python-dotenv` explícito vs. depender del extra
transitivo de `uvicorn[standard]`) — es un bug funcional: aunque
`python-dotenv` sí está instalado (transitivamente, vía
`uvicorn[standard]`), **nadie lo invoca**, así que da igual si la dependencia
es explícita o transitiva mientras no haya un `load_dotenv()` en el arranque.
El mecanismo de configuración vía `.env` que documentan las notas
("si no hay `.env`, se usan los defaults" implica que si *hay* `.env` se
debería usar) no funciona hoy, y como esta tarea es la base de la que
depende toda tarea futura para leer configuración (`DATABASE_URL`,
`CORS_ORIGINS`, y presumiblemente secretos de auth en BE-008), este hueco se
va a heredar silenciosamente en cada tarea downstream si no se corrige aquí.

**Acción sugerida:** agregar `python-dotenv` explícito a `requirements.txt`
y llamar `load_dotenv()` al inicio de `app/core/config.py` (antes de los
`os.getenv(...)`), resolviendo a la vez la duda que dejó el implementador.

### Hallazgo no bloqueante (para tener en cuenta en BE-002+)

- `app/main.py:22` usa `@app.on_event("startup")`, que FastAPI 0.115
  marca como deprecado (`DeprecationWarning: on_event is deprecated, use
  lifespan event handlers instead`, verificado corriendo el import con
  warnings activados). No rompe nada hoy, pero como este archivo es la base
  para los routers de las próximas tareas, conviene migrar a
  `lifespan` (context manager) antes de que se vuelva más costoso de cambiar.

Corregido el punto bloqueante del `.env`, esta tarea queda lista para
`done`.

---

### Re-revisión (2026-08-25) — Veredicto: `done`

Verifiqué directamente el código en `backend/app/` (no solo el reporte del
implementador) y reproduje ambos escenarios con el `.venv` ya existente en
`backend/.venv` (Windows, Python 3.10.11):

1. **Fix del `.env` (bloqueante anterior) — confirmado resuelto.**
   `backend/app/core/config.py:6,10` importa `from dotenv import load_dotenv`
   y llama `load_dotenv(BASE_DIR / ".env")` antes de los `os.getenv(...)`.
   `python-dotenv==1.0.1` está fijado explícito en `requirements.txt:4` (ya
   no depende del extra transitivo de `uvicorn[standard]`) y confirmé que
   está instalado en el venv (`pip show python-dotenv` → 1.0.1, coincide con
   el pin).

   Reproduje el escenario exacto de la revisión anterior: creé
   `backend/.env` con `CORS_ORIGINS=http://qa-review-test:4242` y corrí:
   ```
   python -c "from app.core import config; print(config.CORS_ORIGINS)"
   → ['http://qa-review-test:4242']
   ```
   Borré el `.env` y confirmé que vuelve al default:
   ```
   → ['http://localhost:5173', 'http://127.0.0.1:5173']
   ```
   El bug funcional que bloqueaba la tarea ya no existe.

2. **`@app.on_event("startup")` deprecado — confirmado migrado.**
   `backend/app/main.py` ya no tiene ningún `on_event` (grep sin resultados
   en `app/`); usa `@asynccontextmanager` + `lifespan` (líneas 15-18) que
   hace `Base.metadata.create_all(bind=engine)` antes del `yield`, y
   `FastAPI(title=..., lifespan=lifespan)` en la línea 21. Confirmé
   ejecutando `python -W error::DeprecationWarning -c "import app.main"`
   (exit 0, sin excepción) y también `python -W always -c "import app.main"`
   (sin salida de warnings). El `DeprecationWarning` de la revisión anterior
   ya no aparece.

3. **Regresión end-to-end.** Levanté el server real
   (`uvicorn app.main:app --port 8129`): arrancó sin errores ni warnings en
   el log (`Application startup complete`), `GET /health` respondió
   `200 {"status":"ok","database":"ok"}`, y `backend/brainfreeze.db` se creó
   automáticamente (no existía antes de arrancar). Detuve el proceso y
   eliminé el `.env` de prueba, `brainfreeze.db` y el log generado; el
   repo queda limpio, sin residuos de esta verificación.

Con ambos hallazgos de la revisión anterior corregidos y verificados en
código (no solo en el reporte), y sin encontrar hallazgos nuevos revisando
`config.py`, `main.py`, `session.py`, `health.py` y `requirements.txt`, la
tarea cumple los criterios de aceptación. Cambio `status` a `done`.
