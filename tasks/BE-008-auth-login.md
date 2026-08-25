---
id: BE-008
title: Autenticación simple (login del dueño del negocio)
area: backend
status: done
priority: medium
depends_on: [BE-001]
created_by: planner
---

## Objetivo

Replicar la pantalla de Login del mockup (email/password) con algo real pero
simple: el negocio lo usa una sola persona (el dueño), no hace falta un
sistema de roles/permisos.

## Alcance

- Un único usuario administrador (o una tabla `Usuario` mínima si prefieres
  dejar la puerta abierta a agregar empleados más adelante sin rediseñar —
  decide con criterio, sin sobre-construir roles/permisos que nadie pidió).
- Password hasheado (ej. bcrypt/passlib), nunca en texto plano.
- `POST /auth/login` recibe email/password, devuelve un token (JWT simple) que
  el frontend usa para llamadas subsecuentes.
- Middleware/dependencia de FastAPI que proteja el resto de endpoints
  (categorías, productos, inventario, mesas, ventas, reportes) exigiendo el
  token — excepto `/health` y `/auth/login`.
- Comando o script simple para crear/establecer el usuario inicial (no hace
  falta una pantalla de "registro" pública).

## Criterios de aceptación

- [ ] `POST /auth/login` con credenciales correctas devuelve un token válido.
- [ ] `POST /auth/login` con credenciales incorrectas responde 401, sin
      filtrar si el email existe o no (mismo mensaje genérico).
- [ ] Cualquier endpoint de negocio sin token responde 401.
- [ ] Existe una forma documentada de crear el usuario inicial (script,
      comando, o seed) sin exponer un endpoint público de registro.

## Notas de implementación

### Archivos creados/tocados

- `backend/app/models/usuario.py` (nuevo): modelo `Usuario` mínimo (`id`,
  `email` único, `password_hash`) — tabla, no un usuario hardcodeado, para
  no tener que rediseñar si más adelante se agregan empleados; hoy en la
  práctica solo se usa una fila (el dueño), sin ningún sistema de
  roles/permisos.
- `backend/app/core/security.py` (nuevo): `hash_password` / `verify_password`
  (bcrypt directo, no passlib), `create_access_token` (JWT), y la dependencia
  `require_auth` que valida el header `Authorization: Bearer <token>`.
- `backend/app/core/config.py`: se agregaron `JWT_SECRET_KEY`,
  `JWT_ALGORITHM` (`HS256` por defecto), `JWT_EXPIRE_MINUTES` (`480` por
  defecto), leídos desde `.env`/entorno igual que el resto de la config.
- `backend/app/schemas/auth.py` (nuevo): `LoginRequest` (email/password, sin
  `EmailStr` de pydantic para no sumar la dependencia `email-validator`;
  valida solo que tenga `@` y normaliza a minúsculas/trim), `TokenResponse`.
- `backend/app/routers/auth.py` (nuevo): `POST /auth/login`.
- `backend/app/scripts/crear_usuario.py` (nuevo) + `app/scripts/__init__.py`:
  script CLI para crear/actualizar (upsert) el usuario inicial sin exponer
  un endpoint de registro público.
- `backend/app/routers/categorias.py`: se agregó
  `dependencies=[Depends(require_auth)]` al `APIRouter` (protege los 4
  endpoints de BE-002).
- `backend/app/routers/mesas.py`: mismo cambio (protege los 5 endpoints de
  BE-005).
- `backend/app/db/base_all.py`: se agregó el import de `Usuario`.
- `backend/app/main.py`: se registró `auth.router`. `health.router` se dejó
  sin tocar (sigue público, como pide el alcance).
- `backend/requirements.txt`: se agregaron `pyjwt==2.9.0` y `bcrypt==4.2.0`.
  No se usó `passlib` porque su backend de bcrypt tiene problemas de
  compatibilidad conocidos con versiones recientes de la librería `bcrypt`
  (`passlib` 1.7.4 no reconoce `bcrypt` >= 4.1 correctamente); usar `bcrypt`
  directo evita esa capa y sus dependencias son mínimas
  (`hashpw`/`checkpw`). Tampoco se usó `python-jose` (más pesado, requiere
  `cryptography`) — `pyjwt` es suficiente para HS256 simétrico.
- `backend/.env.example`: se documentaron `JWT_SECRET_KEY`, `JWT_ALGORITHM`,
  `JWT_EXPIRE_MINUTES`.

### Decisiones tomadas

- **Un único modelo `Usuario` genérico** (no una tabla `AdminConfig` de una
  sola fila hardcodeada): mínimo esfuerzo hoy, no bloquea agregar empleados
  mañana sin migrar el esquema. No se agregó ningún campo de rol/permiso —
  eso sería sobre-construir algo que nadie pidió (el negocio lo usa una
  sola persona).
- **JWT simple (HS256, firma simétrica)**: `create_access_token` codifica
  `sub` (email) y `exp`. `require_auth` decodifica, valida la firma/expiración
  con `pyjwt`, y además vuelve a consultar la DB para confirmar que el
  usuario del `sub` todavía existe (por si se borra/renombra un usuario, un
  token viejo no debería seguir sirviendo indefinidamente hasta que expire
  solo). No se implementó revocación/logout de tokens (no lo pide la
  tarea) — el único mecanismo de invalidación hoy es la expiración
  (`JWT_EXPIRE_MINUTES=480`, 8h, pensado para cubrir un turno de trabajo) o
  cambiar `JWT_SECRET_KEY`.
- **`JWT_SECRET_KEY` con default inseguro (`dev-secret-change-me`)**: es
  solo para no romper el arranque en dev si no hay `.env`; igual que
  `DATABASE_URL`/`CORS_ORIGINS`, se puede sobreescribir por variable de
  entorno. **Duda/riesgo que dejo anotado**: no hay ningún chequeo que
  impida que este default llegue a producción; si el proyecto define un
  proceso de despliegue, valdría la pena que ese proceso falle el arranque
  si `JWT_SECRET_KEY` no está seteado explícitamente fuera de dev. No lo
  implementé porque el alcance de esta tarea es la fase de desarrollo y no
  hay todavía una noción de "entorno" (`ENV=production` etc.) en
  `app/core/config.py`.
- **Mensaje genérico de credenciales inválidas**: tanto email inexistente
  como password incorrecta devuelven exactamente el mismo 401
  `{"detail":"Credenciales inválidas"}`, verificado explícitamente con
  ambos casos para no filtrar si el email existe.
- **Protección vía `dependencies=[Depends(require_auth)]` a nivel de
  `APIRouter`** (no un middleware global de ASGI): más idiomático en FastAPI
  para excluir `/health` y `/auth/login` sin necesitar una lista de rutas
  excluidas a mano en un middleware — cada router de negocio (categorías,
  mesas, y los que vengan en BE-003/004/006/007) simplemente agrega esa
  dependencia al construir su `APIRouter`. Se protegieron aquí mismo los
  routers de `categorias` y `mesas` porque ya existen en el código (creados
  en esta misma sesión de trabajo, BE-002 y BE-005); los routers de BE-003,
  BE-004, BE-006 y BE-007 deberán agregar la misma
  `dependencies=[Depends(require_auth)]` cuando se implementen (dejo esto
  como nota explícita para esas tareas, ya que están fuera de mi alcance
  hoy).
- **`response_model=None` en el `DELETE`**: N/A aquí, esta tarea no agrega
  endpoints DELETE propios.
- **Sin `EmailStr` de Pydantic**: para no sumar `email-validator` como
  dependencia nueva solo por una validación de formato que no es crítica
  (el email real se valida por existencia contra la DB, no por regex
  estricta). Se normaliza a minúsculas y se hace trim tanto en el schema de
  login como en el script de creación de usuario, para que
  `admin@Brainfreeze.com` y `admin@brainfreeze.com` sean el mismo usuario.

### Cómo crear el usuario inicial

```powershell
cd backend
.\.venv\Scripts\python -m app.scripts.crear_usuario admin@brainfreeze.com "MiPasswordSegura123"
```

Es idempotente: si el email ya existe, actualiza la contraseña (upsert) en
vez de fallar. Exige contraseña de al menos 6 caracteres. No hay endpoint
HTTP de registro; esta es la única vía soportada.

### Cómo probarlo

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```
GET http://127.0.0.1:8000/health
→ 200 (público, sin token)

GET http://127.0.0.1:8000/categorias   (sin header Authorization)
→ 401 {"detail":"No autenticado"}

POST http://127.0.0.1:8000/auth/login  {"email":"admin@brainfreeze.com","password":"mal"}
→ 401 {"detail":"Credenciales inválidas"}

POST http://127.0.0.1:8000/auth/login  {"email":"admin@brainfreeze.com","password":"MiPasswordSegura123"}
→ 200 {"access_token":"<jwt>","token_type":"bearer"}

GET http://127.0.0.1:8000/categorias   -H "Authorization: Bearer <jwt>"
→ 200 [...]
```

Verificado en este entorno (Windows, Python 3.10, venv `backend/.venv`,
`pyjwt`/`bcrypt` instalados vía `pip install -r requirements.txt`): server
levanta sin errores; se probaron con `curl` los casos: `/health` accesible
sin token (200); `/categorias` y `/mesas` sin token (401, "No autenticado");
`POST /auth/login` con password incorrecta (401, mensaje genérico) y con
email inexistente (401, **mismo** mensaje genérico); `POST /auth/login`
correcto (200, devuelve JWT); `/categorias` y `/mesas` con el token
recibido (200); `/categorias` con un token manipulado/inválido (401);
`POST /categorias` con token válido crea el recurso (201) confirmando que
el flujo completo funciona end-to-end sobre un endpoint ya protegido.
También se verificó que re-ejecutar `crear_usuario` con el mismo email
actualiza la contraseña (el login con la contraseña vieja pasa a fallar con
401 y con la nueva funciona). No quedó ningún `brainfreeze.db` ni proceso
de prueba corriendo tras la verificación.

## Revisión

**Veredicto: `done`**

Verificado con el servidor real corriendo (venv temporal con
`pip install -r requirements.txt`, `uvicorn` en 127.0.0.1:8123):

- `GET /health` accesible sin token (200) — confirmado.
- `GET /categorias` y `GET /mesas` sin header `Authorization` → 401
  `{"detail":"No autenticado"}` — confirmado.
- `python -m app.scripts.crear_usuario admin@brainfreeze.com "..."` crea el
  usuario correctamente (upsert, sin endpoint de registro público) —
  confirmado.
- `POST /auth/login` con password incorrecta → 401
  `{"detail":"Credenciales inválidas"}`.
- `POST /auth/login` con email inexistente → **exactamente el mismo** 401
  `{"detail":"Credenciales inválidas"}` — confirmado explícitamente
  comparando ambas respuestas byte a byte; no hay fuga de información sobre
  existencia del email (buena práctica anti user-enumeration confirmada).
- `POST /auth/login` correcto → 200 con JWT válido.
- Con el JWT, `GET /categorias` y `GET /mesas` → 200; sin él, 401. También
  probé el ciclo completo `POST /categorias` con token válido → 201.
- Confirmé que `/health` y `/auth/login` son las únicas rutas sin
  `dependencies=[Depends(require_auth)]` en `app/main.py`/routers, y que
  `categorias.router` y `mesas.router` sí lo tienen a nivel de `APIRouter`.

Sobre lo pedido explícitamente:

- **pyjwt + bcrypt en vez de passlib**: justificación de la incompatibilidad
  passlib/bcrypt>=4.1 es un problema real y conocido en el ecosistema Python;
  usar `bcrypt` directo (`hashpw`/`checkpw`) es una alternativa mínima y
  correcta, no una sobre-ingeniería. `pyjwt` es suficiente para HS256
  simétrico, no hay necesidad de `python-jose`.
- **Usuario inicial vía script, sin endpoint de registro**: cumple el
  criterio de aceptación tal cual ("sin exponer un endpoint público de
  registro"); el script es idempotente (upsert) y exige contraseña mínima de
  6 caracteres.
- **Mismo 401 genérico para credenciales incorrectas y email inexistente**:
  confirmado en vivo, ver arriba.
- **`/categorias` y `/mesas` protegidas, `/health` y `/auth/login`
  públicos**: confirmado en vivo.

Observaciones no bloqueantes (no impiden aprobar, pero vale dejarlas
anotadas):

1. `JWT_SECRET_KEY` con default inseguro (`dev-secret-change-me` en
   `app/core/config.py`) — el propio implementador ya lo señaló como riesgo
   pendiente. Coincido: aceptable para esta fase de desarrollo (no hay noción
   de entorno `production` todavía en el proyecto), pero antes de cualquier
   despliegue real debería fallar el arranque si no está seteado
   explícitamente por variable de entorno.
2. `LoginRequest.password` no tiene `max_length`; bcrypt trunca
   silenciosamente a 72 bytes (verifiqué esto directamente con
   `bcrypt==4.2.0`: no lanza excepción con contraseñas >72 bytes, simplemente
   ignora el resto). Riesgo bajo dado que es un solo usuario administrador,
   pero sería una mejora barata agregar `max_length=72` al schema para que el
   comportamiento sea explícito en vez de implícito.
3. Sin `EmailStr`/`email-validator`: decisión razonable y explícitamente
   justificada (evitar dependencia extra); la validación real ocurre contra
   la DB.
4. Sin tests automatizados — mismo comentario que BE-002/BE-005, no exigido
   por los criterios y el proyecto no tiene infraestructura de tests todavía.

Cumple los 4 criterios de aceptación exactamente. Limpié la DB de prueba y el
venv temporal usados para esta revisión; no quedó ningún proceso corriendo.
