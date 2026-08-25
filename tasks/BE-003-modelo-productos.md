---
id: BE-003
title: Modelo y endpoints CRUD de Productos (catálogo de granizados)
area: backend
status: done
priority: high
depends_on: [BE-001, BE-002]
created_by: planner
---

## Objetivo

Catálogo de productos que se venden (granizados por sabor/tamaño, toppings,
bebidas, etc.), reemplazando el catálogo genérico de bar del mockup
(Mojito, Ron Bacardí...) por productos propios de un negocio de granizados.

## Alcance

- Modelo `Producto`: `id`, `nombre`, `categoria_id` (FK a Categoría), `precio`
  (en COP), `estado` ('disponible' / 'agotado' o similar — decide un enum
  simple y documéntalo), timestamps si te parece útil para reportes futuros.
- Modelo simple y plano: cada combinación sabor+tamaño es un producto
  independiente (ej. "Granizado Fresa Chico", "Granizado Fresa Grande") en vez
  de un sistema combinatorio de variantes — así se mantiene igual de simple que
  el mockup. Si consideras que hace falta separar sabor/tamaño como campos
  propios del producto (en vez de solo el nombre) para que reportes o el POS
  los aprovechen mejor, hazlo, pero no construyas un sistema de variantes
  combinatorias completo — no lo pidió el dueño del negocio.
- Endpoints CRUD + búsqueda por nombre (para el buscador de la pantalla
  Productos) + filtro por categoría.
- Semilla de datos de ejemplo (categorías + productos) coherente con
  granizados en vez de bar, para poder probar el resto del sistema — usa un
  script/endpoint de seed simple, no lo dejes solo como decisión implícita.

## Criterios de aceptación

- [ ] CRUD completo de productos vía API.
- [ ] `GET /productos?search=texto` filtra por nombre (case-insensitive,
      parcial).
- [ ] `GET /productos?categoria_id=X` filtra por categoría.
- [ ] Precio y estado se reflejan correctamente en las respuestas.
- [ ] Existe una forma de poblar datos de ejemplo de granizados (sabores,
      tamaños, toppings) documentada en las notas de implementación.

## Notas de implementación

### Archivos creados/tocados

- `backend/app/models/producto.py` (nuevo): modelo `Producto` (`id`, `nombre`,
  `categoria_id` FK a `categorias.id`, `precio` (COP, entero), `estado` con
  `CheckConstraint` restringido a `'disponible'`/`'agotado'`, `sabor` y
  `tamano` opcionales, `creado_en` con default `datetime.now(UTC)`). Se
  exportan `ESTADO_DISPONIBLE`/`ESTADO_AGOTADO` como constantes, siguiendo el
  mismo patrón que `Mesa`.
- `backend/app/schemas/producto.py` (nuevo): `EstadoProducto` (enum
  `disponible`/`agotado`), `ProductoCreate`, `ProductoUpdate`, `ProductoOut`.
- `backend/app/routers/productos.py` (nuevo): `GET /productos` (con `search` y
  `categoria_id` como query params opcionales), `GET /productos/{id}`,
  `POST /productos`, `PUT/PATCH /productos/{id}`, `DELETE /productos/{id}`.
- `backend/app/scripts/seed_productos.py` (nuevo): script idempotente de seed
  (ver sección "Semilla de datos" abajo).
- `backend/app/db/base_all.py`: se agregó el import de `Producto`.
- `backend/app/main.py`: se registró `productos.router`.
- `backend/app/routers/categorias.py`: se migró el conteo de productos
  (`productos_count` en el listado y el chequeo de borrado) de
  `_contar_relacionados` (SQL crudo + `inspect().has_table()`) a una consulta
  ORM real (`_contar_productos`, `db.query(func.count(Producto.id))...`), ya
  que el modelo `Producto` ahora existe. Ver sección "Decisión sobre el
  patrón `has_table()`" abajo para el detalle completo (incluye BE-004).

### Decisiones tomadas

- **`precio` como `Integer` (COP)**: en Colombia el peso no maneja
  centavos en el uso cotidiano de un negocio como este; se evita la
  imprecisión de `Float` para dinero. Si a futuro se requieren decimales,
  cambiar a `Numeric`.
- **`sabor` y `tamano` como columnas propias, opcionales**: el alcance de la
  tarea invita explícitamente a decidir esto. Se agregan como `String`
  nullable (no un sistema de variantes combinatorias) para que reportes
  futuros (BE-007) o el POS (BE-006/FE-007) puedan filtrar/agrupar por sabor
  o tamaño sin tener que parsear el campo `nombre` con texto libre. `nombre`
  sigue siendo el campo mostrado/buscable (ej. "Granizado Fresa Chico");
  `sabor`/`tamano` son metadata adicional, no reemplazan a `nombre`. Un
  producto que no aplique (ej. una bebida o un topping) simplemente los deja
  en `null`.
- **`categoria_id` obligatorio (`nullable=False`)**: el alcance dice "FK a
  Categoría" sin aclarar si es opcional; se decidió requerida porque el
  mockup agrupa todo por categoría y no tiene sentido un producto "suelto".
  Se valida que la categoría exista antes de crear/actualizar (404 si no
  existe) en vez de dejar que falle silenciosamente por la FK de SQLite (que
  además no siempre está habilitada por defecto).
- **`search` case-insensitive parcial**: se usa `func.lower(Producto.nombre).contains(search.lower())`
  (SQLite es case-insensitive con `LIKE` solo para ASCII por defecto; con
  `lower()` explícito en ambos lados se cubre tildes correctamente ya que
  Python normaliza la cadena de búsqueda del lado del cliente).
- **`GET /productos/{id}`**: no estaba en los criterios explícitos, pero un
  CRUD completo lo implica (edición desde el frontend típicamente necesita
  poder cargar un solo producto); se agregó por consistencia sin ser scope
  creep (es parte natural de "CRUD completo").
- **`DELETE` sin bloqueo por ventas asociadas**: a diferencia de Mesa/Categoría,
  no se agregó ningún chequeo de `Venta` (BE-006) antes de borrar un producto,
  porque no está en el alcance de esta tarea y `Venta` no existe todavía.
  Queda como nota para BE-006: si se requiere preservar historial de ventas,
  debería considerar impedir el borrado físico de productos referenciados (o
  usar borrado lógico vía `estado='agotado'` en vez de `DELETE`), siguiendo el
  mismo patrón `has_table()` que usaron BE-002/BE-005 mientras `Venta` no
  exista, y luego un `relationship()`/query ORM real una vez exista.
- **`response_model=None` en `DELETE`**: mismo ajuste necesario que en
  BE-002/BE-005 por la combinación de `from __future__ import annotations` +
  status 204 en FastAPI 0.115.

### Decisión sobre el patrón `has_table()` en `categorias.py` (evaluación pedida)

Se migró la parte de **productos** del chequeo en `app/routers/categorias.py`
de SQL crudo (`inspect(engine).has_table("productos")` + `text(...)`) a una
consulta ORM real contra el modelo `Producto` (`_contar_productos`), ya que
ahora existe y se puede importar sin romper la resolución de mappers de
SQLAlchemy. Se dejó **intacto** el chequeo de `insumos` con el patrón
`has_table()` porque ese modelo todavía no existe en esta tarea (lo agrega
BE-004, que también migrará esa parte). Razones para migrar ahora en vez de
esperar a que ambas partes se pudieran migrar juntas en BE-004:
- Es más idiomático y type-safe que SQL parametrizado con interpolación de
  nombre de tabla por f-string (el reviewer de BE-002 ya señaló esto último
  como punto flojo, aunque no bloqueante).
- No tiene costo/riesgo: el modelo `Producto` ya existe en este mismo commit
  de trabajo, así que no hay ventana en la que el código dependa de algo
  inexistente.
- Se mantiene `_contar_relacionados` (genérico, con `has_table()`) para
  `insumos` hasta que BE-004 lo elimine también.

### Semilla de datos de ejemplo (granizados)

`backend/app/scripts/seed_productos.py` — idempotente (usa `nombre` como
clave para no duplicar si se corre más de una vez; actualiza precio/sabor/
tamaño si ya existe). Crea:
- Categorías: "Granizados" (#22c55e), "Toppings" (#f59e0b), "Bebidas" (#3b82f6).
- 5 sabores (Fresa, Mora, Limón, Mango, Uva) × 2 tamaños (Chico $5000, Grande
  $8000) = 10 productos de Granizados.
- 3 toppings (Chispas de chocolate, Gomitas, Crema chantilly).
- 2 bebidas (Agua en botella, Gaseosa).

Total: 3 categorías, 15 productos.

Uso:
```powershell
cd backend
.\.venv\Scripts\python -m app.scripts.seed_productos
```

### Cómo probarlo

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```
POST http://127.0.0.1:8000/categorias  {"nombre":"Granizados","color":"#22c55e"}
→ 201 {"id":1,...}

POST http://127.0.0.1:8000/productos
  {"nombre":"Granizado Fresa Chico","categoria_id":1,"precio":5000,"sabor":"Fresa","tamano":"Chico"}
→ 201 {"id":1,"nombre":"Granizado Fresa Chico","categoria_id":1,"precio":5000,
        "estado":"disponible","sabor":"Fresa","tamano":"Chico","creado_en":"..."}

POST http://127.0.0.1:8000/productos  {"nombre":"X","categoria_id":999,"precio":5000}
→ 404 {"detail":"Categoría no encontrada"}

GET http://127.0.0.1:8000/productos?search=fresa
→ 200 [ ...solo el de Fresa... ]

GET http://127.0.0.1:8000/productos?categoria_id=1
→ 200 [ ...todos los de esa categoría... ]

PATCH http://127.0.0.1:8000/productos/1  {"estado":"agotado"}
→ 200 {..., "estado":"agotado"}

DELETE http://127.0.0.1:8000/categorias/1
→ 409 (tiene productos asociados)

DELETE http://127.0.0.1:8000/productos/1
→ 204
```

Verificado en este entorno (Windows, Python 3.10, venv `backend/.venv`):
server levantado con `uvicorn` real en 127.0.0.1:8123 (no solo lectura de
código). Se probaron con `curl` + JWT real (login contra `/auth/login`):
crear categoría, crear producto con categoría inválida (404), crear producto
válido (201, incluye `sabor`/`tamano`/`creado_en`), listar todos, filtro
`search` (parcial, case-insensitive), filtro `categoria_id`, `GET /productos/{id}`
(200 y 404), `PATCH` de estado (200), `productos_count` en `GET /categorias`
reflejando el conteo real vía ORM (2 tras crear 2 productos), `DELETE
/categorias/{id}` bloqueado por productos asociados (409), `DELETE
/productos/{id}` exitoso (204), y validación de `precio<=0` (422). También se
corrió `seed_productos.py` dos veces seguidas para confirmar idempotencia (no
duplica filas) y se verificó vía `GET /productos?search=granizado` que los 10
productos de granizados se crearon correctamente. Se confirmó además que la
respuesta HTTP cruda usa UTF-8 correctamente para "Limón" (el mojibake que
apareció en algunas salidas de consola durante las pruebas fue únicamente un
artefacto del codepage de la terminal de Windows al decodificar stdin, no un
bug de la API/DB — verificado inspeccionando los bytes crudos de la
respuesta). No quedó ningún `brainfreeze.db` ni proceso de prueba corriendo
tras la verificación.

## Revisión

**Veredicto: `done`**

Verificado con servidor real (`uvicorn` en `127.0.0.1:8321`, JWT real vía
`/auth/login`), no solo lectura de código:

- CRUD completo de `/productos` funciona (`POST`, `GET`, `GET /{id}`,
  `PUT/PATCH`, `DELETE`), con 404 correcto en categoría inexistente y en
  producto inexistente.
- `GET /productos?search=fresa` filtra parcial case-insensitive
  correctamente; `GET /productos?categoria_id=1` filtra por categoría.
- `precio`/`estado` se reflejan bien en las respuestas; `precio<=0` rechazado
  (`ProductoCreate.precio: Field(gt=0)`).
- `DELETE /categorias/{id}` bloqueado (409) con productos asociados —
  confirmado tras crear producto.
- `seed_productos.py` corrido dos veces seguidas contra una DB real: segunda
  corrida no duplicó filas (10 productos de granizados tras `search=granizado`,
  igual que la primera), confirma idempotencia real, no solo por lectura de
  código.
- `mesas.py` no fue tocado por esta tarea y sigue funcionando: `GET /mesas`,
  `POST /mesas` probados en vivo después del refactor de `categorias.py`, sin
  regresión.

Sobre las decisiones documentadas:

- **`sabor`/`tamano` opcionales**: el alcance invita explícitamente a esta
  decisión ("si consideras que hace falta separar sabor/tamaño... hazlo").
  No es scope creep: son columnas nullable simples, sin sistema de variantes
  combinatorias, consistente con lo pedido. Correcto.
- **Migración parcial de `has_table()` en `categorias.py`** (solo productos,
  dejando insumos con el patrón viejo hasta BE-004): revisado el código, es
  coherente y está bien acotado — no rompe nada porque `_contar_relacionados`
  genérico se mantuvo para insumos. Confirmado en vivo que el conteo de
  productos vía ORM funciona y no rompió el bloqueo de DELETE de categoría.
- `response_model=None` en `DELETE`, `GET /productos/{id}` agregado por
  consistencia de CRUD: razonable, no es scope creep.
- `categoria_id` obligatorio con validación 404 explícita: buena decisión,
  evita depender de integridad referencial de SQLite (que no siempre está
  habilitada).

No se encontraron queries SQL crudas ni credenciales hardcodeadas en el
código de esta tarea. Tipado completo con Pydantic + `Mapped[...]`. Código
limpio, sin abstracciones prematuras.

Todos los criterios de aceptación se cumplen. Se limpiaron los procesos y la
DB de prueba (`brainfreeze.db`) generados durante esta revisión.
