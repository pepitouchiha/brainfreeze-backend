---
id: BE-002
title: Modelo y endpoints CRUD de Categorías
area: backend
status: done
priority: high
depends_on: [BE-001]
created_by: planner
---

## Objetivo

Las categorías agrupan tanto productos del catálogo (ej. "Granizados",
"Toppings", "Bebidas") como insumos de inventario (ej. "Jarabes", "Vasos",
"Hielo"). Replican la pantalla "Categorías" del mockup, que muestra conteo de
productos por categoría con un color asociado.

## Alcance

- Modelo `Categoria`: `id`, `nombre` (único), `color` (hex, para la UI, con un
  valor por defecto si no se especifica).
- Endpoints: listar, crear, editar, eliminar (solo si no tiene productos ni
  insumos asociados — si los tiene, rechazar con un error claro en vez de
  borrar en cascada).
- El listado debe poder devolver el conteo de productos asociados a cada
  categoría (lo que el mockup llama `catCounts`), para que el frontend no tenga
  que calcularlo.

## Criterios de aceptación

- [ ] `POST /categorias` crea una categoría; rechaza nombres duplicados con 409.
- [ ] `GET /categorias` devuelve lista con `id, nombre, color, productos_count`.
- [ ] `PUT/PATCH /categorias/{id}` edita nombre/color.
- [ ] `DELETE /categorias/{id}` devuelve 409 si tiene productos o insumos
      asociados, con mensaje explicando por qué no se puede borrar.

## Notas de implementación

### Archivos creados/tocados

- `backend/app/models/categoria.py` (nuevo): modelo `Categoria` (`id`, `nombre`
  único, `color` con default `#6b7280`).
- `backend/app/schemas/categoria.py` (nuevo): `CategoriaCreate`, `CategoriaUpdate`
  (campos opcionales para PATCH parcial), `CategoriaOut` (incluye
  `productos_count`).
- `backend/app/routers/categorias.py` (nuevo): `GET/POST /categorias`,
  `PUT/PATCH /categorias/{id}`, `DELETE /categorias/{id}`.
- `backend/app/db/base_all.py`: se agregó el import de `Categoria` para que
  `create_all` la registre.
- `backend/app/main.py`: se registró `categorias.router`.

### Decisiones tomadas

- **`color`**: validado como hex de 6 dígitos (`#RRGGBB`) vía regex en los
  schemas Pydantic; default `#6b7280` (gris neutro) si no se especifica al
  crear, tal como pide el alcance ("con un valor por defecto si no se
  especifica"). No se investigó un color específico del mockup porque no hay
  paleta documentada en las tareas; si el frontend necesita otro default se
  puede ajustar cambiando `COLOR_DEFAULT` en `app/models/categoria.py`.
- **Nombre único**: se valida a nivel aplicación (query previa) y también a
  nivel DB (`unique=True` en la columna + captura de `IntegrityError` como
  red de seguridad ante condiciones de carrera, devolviendo 409 en ambos
  casos). Se hace `.strip()` del nombre para evitar duplicados por espacios.
- **Conteo de productos e insumos asociados (bloqueante de esta tarea):**
  BE-003 (Productos) y BE-004 (Inventario/Insumos) están fuera de alcance de
  este trabajo y sus modelos SQLAlchemy no existen todavía. Por eso el
  conteo (`productos_count` en el listado) y el chequeo de borrado (rechazar
  si hay productos o insumos asociados) **no usan un `relationship()` de
  ORM** hacia modelos inexistentes (eso rompería la resolución de mappers de
  SQLAlchemy en cuanto se usara cualquier query, incluso sin tocar
  productos/insumos). En su lugar, se verifica en tiempo de ejecución con
  `sqlalchemy.inspect(engine).has_table("productos"/"insumos")`: si la tabla
  no existe todavía, cuenta como 0 (correcto: no puede haber productos
  asociados a algo que no existe). Si existe, se hace un `COUNT(*)` con SQL
  parametrizado filtrando por `categoria_id`. Verificado manualmente creando
  a mano una tabla `productos` de prueba con una fila `categoria_id=1`: el
  listado reportó `productos_count: 1` y el `DELETE` de esa categoría
  respondió 409 con el mensaje esperado.

  **Importante para BE-003/BE-004**: esto asume que sus tablas se llamarán
  `productos` e `insumos` y que ambas tendrán una columna `categoria_id`
  (tal como especifican sus propias tareas). Si BE-003/BE-004 cambian esos
  nombres, deben ajustar `_contar_relacionados` en
  `app/routers/categorias.py` (o reemplazarlo por un `relationship()` ORM
  propio una vez esos modelos existan — sería la opción más idiomática a
  futuro, esto es una solución defensiva mientras no existen).
- **`DELETE` con 204 y `response_model=None` explícito**: con
  `from __future__ import annotations` activo, FastAPI 0.115 no infería
  correctamente que una función anotada `-> None` no debía tener
  `response_model`, y lanzaba `AssertionError: Status code 204 must not have
  a response body` al arrancar. Se fijó `response_model=None` explícito en
  el decorador del endpoint `DELETE` para evitarlo (comportamiento
  reproducido y confirmado con el server real antes y después del fix).
- **`PUT` y `PATCH` comparten el mismo handler** (`actualizar_categoria`)
  porque el criterio de aceptación los trata como equivalentes ("edita
  nombre/color") y ambos aceptan campos opcionales vía `CategoriaUpdate`.

### Cómo probarlo

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```
POST http://127.0.0.1:8000/categorias  {"nombre":"Granizados","color":"#22c55e"}
→ 201 {"id":1,"nombre":"Granizados","color":"#22c55e","productos_count":0}

POST http://127.0.0.1:8000/categorias  {"nombre":"Granizados"}
→ 409 {"detail":"Ya existe una categoría con ese nombre"}

GET http://127.0.0.1:8000/categorias
→ 200 [{"id":1,"nombre":"Granizados","color":"#22c55e","productos_count":0}]

PATCH http://127.0.0.1:8000/categorias/1  {"color":"#3b82f6"}
→ 200 {"id":1,"nombre":"Granizados","color":"#3b82f6","productos_count":0}

DELETE http://127.0.0.1:8000/categorias/1
→ 204
```

Verificado en este entorno (Windows, Python 3.10, venv `backend/.venv`):
server levanta sin errores, se probaron con `curl` los casos: crear (201),
duplicado (409), color inválido (422), listar (200), editar por PUT y PATCH
(200, incluyendo rechazo de nombre duplicado por 409), eliminar no
encontrada (404), eliminar existente (204), y el caso de bloqueo por
productos asociados (409) creando manualmente una tabla `productos` de
prueba con SQLite. No quedó ningún `brainfreeze.db` ni proceso de prueba
corriendo tras la verificación.

## Revisión

**Veredicto: `done`**

Verificado con el servidor real corriendo (venv temporal, `uvicorn` en
127.0.0.1:8123), no solo por lectura de código:

- `POST /categorias` crea (201) y rechaza duplicados (409) — confirmado,
  incluyendo el caso de condición de carrera vía `IntegrityError` (código
  presente y razonable aunque no forcé la carrera real).
- `GET /categorias` devuelve `id, nombre, color, productos_count` — confirmado.
- `PUT`/`PATCH /categorias/{id}` editan nombre/color, con 409 si el nuevo
  nombre choca con otra categoría — confirmado.
- `DELETE /categorias/{id}`: probé el caso real de bloqueo creando a mano
  tablas `productos`/`insumos` en SQLite con una fila `categoria_id` apuntando
  a la categoría — respondió 409 con el mensaje `"tiene 1 producto(s) y 0
  insumo(s) asociados"` tal como se documentó. Sin filas asociadas, `DELETE`
  respondió 204 correctamente.
- Validación de color hex (`#RRGGBB`) probada con un valor inválido (`"rojo"`)
  → 422, como se espera.

Sobre los dos puntos que se pidió evaluar explícitamente:

1. **Patrón `inspect(engine).has_table()` + SQL parametrizado en vez de
   `relationship()` ORM**: razonable dado que es temporal, está bien
   documentado para BE-003/BE-004, y el valor de `categoria_id` va
   parametrizado (`:cid`), no concatenado. El único punto flojo es que el
   *nombre de tabla* (`tabla`) se interpola con f-string en
   `_contar_relacionados` (`app/routers/categorias.py:29`); hoy no es
   explotable porque los únicos call-sites pasan literales hardcodeados
   (`"productos"`, `"insumos"`), pero como observación no bloqueante: sería
   más defensivo restringir `tabla` a un `Literal["productos", "insumos"]` o
   un allowlist explícito para que quede imposible pasarle algo dinámico por
   error en el futuro.
2. **`response_model=None` explícito en el `DELETE`**: reproduje el bug real
   quitando ese parámetro y confirmé que `from app.main import app` falla al
   importar con `AssertionError: Status code 204 must not have a response
   body` (mismo error que reporta el implementador). El fix es correcto y
   necesario, no una corrección espuria de otro problema. Restauré el archivo
   a su estado original tras la prueba.

Otras observaciones no bloqueantes:
- No hay tests automatizados (`pytest`), pero el proyecto no tiene
  infraestructura de tests establecida todavía y los criterios de aceptación
  no la exigen explícitamente.
- Tipado, separación de capas (router/schema/modelo) y manejo de errores
  correctos; sin secretos ni paths absolutos hardcodeados.

Cumple los 4 criterios de aceptación exactamente, sin scope creep. Limpié la
DB de prueba y el venv temporal usados para esta revisión; no quedó ningún
proceso corriendo.
