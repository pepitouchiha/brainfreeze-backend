---
id: BE-004
title: Modelo y endpoints CRUD de Inventario (insumos)
area: backend
status: done
priority: medium
depends_on: [BE-001, BE-002]
created_by: planner
---

## Objetivo

Llevar el control de insumos (hielo, jarabes de sabor, vasos, cucharas,
toppings a granel, etc.) replicando la pantalla "Inventario" del mockup:
lista de insumos con stock actual, mínimo y un estado derivado.

## Alcance

- Modelo `Insumo`: `id`, `nombre`, `categoria_id` (FK, reutiliza Categoría),
  `stock` (cantidad actual), `stock_minimo`.
- `estado` NO se guarda como campo editable manualmente: se **deriva** en cada
  respuesta comparando `stock` vs `stock_minimo` (ej. `stock <= 0` → 'Crítico',
  `stock <= stock_minimo` → 'Bajo', si no → 'OK') — replica la lógica del
  mockup (`tagStyleFor`). Documenta los umbrales exactos que uses.
- Endpoint para ajustar stock (sumar/restar cantidad, ej. al recibir mercancía
  o registrar merma), no solo un PUT que reemplaza el número a ciegas.
- Endpoint de listado debe soportar traer solo los insumos con estado distinto
  de 'OK' (para el contador "con stock bajo o crítico" del dashboard).

## Criterios de aceptación

- [ ] CRUD de insumos vía API.
- [ ] `estado` se calcula en el backend, nunca se recibe como input directo del
      cliente.
- [ ] Endpoint para ajustar stock con una cantidad delta (positiva o negativa),
      no solo sobrescritura directa.
- [ ] `GET /insumos?solo_alertas=true` (o similar) devuelve solo los que están
      en 'Bajo' o 'Crítico'.

## Notas de implementación

### Archivos creados/tocados

- `backend/app/models/insumo.py` (nuevo): modelo `Insumo` (`id`, `nombre`,
  `categoria_id` FK a `categorias.id`, `stock` y `stock_minimo` como `Float`).
  Incluye las constantes `ESTADO_CRITICO`/`ESTADO_BAJO`/`ESTADO_OK` y la
  función pura `calcular_estado(stock, stock_minimo)` que deriva el estado
  (no es una columna de la tabla — ver umbrales abajo).
- `backend/app/schemas/insumo.py` (nuevo): `EstadoInsumo` (enum con los
  valores literales `'Crítico'`/`'Bajo'`/`'OK'`), `InsumoCreate`,
  `InsumoUpdate` (sin campo `stock` — ver decisión abajo), `AjusteStock`
  (`cantidad: float`, rechaza 0), `InsumoOut` (incluye `estado` calculado).
- `backend/app/routers/insumos.py` (nuevo): `GET /insumos` (con
  `solo_alertas: bool` como query param), `GET /insumos/{id}`,
  `POST /insumos`, `PUT/PATCH /insumos/{id}` (edita `nombre`/`categoria_id`/
  `stock_minimo`, nunca `stock` directamente),
  `POST /insumos/{id}/ajustar-stock` (delta), `DELETE /insumos/{id}`.
- `backend/app/db/base_all.py`: se agregó el import de `Insumo`.
- `backend/app/main.py`: se registró `insumos.router`.
- `backend/app/routers/categorias.py`: se completó la migración del patrón
  `has_table()`/SQL crudo (iniciada en BE-003 para productos) reemplazando
  también el conteo de insumos por una consulta ORM real (`_contar_insumos`).
  Ya no queda ningún uso de `inspect(engine).has_table()` ni `text()` en este
  router — ver sección dedicada abajo.

### Umbrales exactos del estado derivado (`calcular_estado`)

Replican `tagStyleFor` del mockup, documentados en `app/models/insumo.py`:
- `stock <= 0` → **`'Crítico'`**
- `0 < stock <= stock_minimo` → **`'Bajo'`**
- `stock > stock_minimo` → **`'OK'`**

`estado` **no es una columna de la tabla `insumos`**: se calcula en cada
respuesta (`_a_out` en el router) a partir de `stock`/`stock_minimo` leídos
de la DB, nunca se acepta como input en `InsumoCreate`/`InsumoUpdate` — así
se cumple el criterio "estado se calcula en el backend, nunca se recibe como
input directo del cliente" de forma estructural (el campo ni siquiera existe
en esos schemas de entrada).

### Decisiones tomadas

- **`stock`/`stock_minimo` como `Float`, no `Integer`**: el alcance menciona
  insumos como hielo, jarabes de sabor, vasos, cucharas, toppings a granel.
  Algunos (jarabes, hielo a granel) se miden razonablemente en unidades
  fraccionarias (litros, kg); otros (vasos, cucharas) son unidades enteras
  pero un `Float` los representa igual de bien (10.0). Se prefirió `Float`
  sobre forzar `Integer` para no bloquear el caso fraccionario, ya que la
  tarea no especifica unidad de medida por insumo (no se pidió un campo
  `unidad`, así que no se agregó — sería scope creep).
- **`stock` NO es editable vía `PUT`/`PATCH`, solo vía `POST
  .../ajustar-stock`**: el criterio de aceptación pide "un endpoint para
  ajustar stock con una cantidad delta..., no solo sobrescritura directa".
  Se decidió ir más allá de "no *solo*" y eliminar directamente el campo
  `stock` de `InsumoUpdate` — así la única forma de cambiar el stock existente
  es a través del endpoint de ajuste (delta), evitando que un cliente
  sobrescriba el número a ciegas por error o carrera. `stock` sigue siendo
  aceptado en `InsumoCreate` para fijar el valor inicial al dar de alta un
  insumo. Si el equipo de frontend necesita "corregir" un stock a un valor
  exacto en vez de sumar/restar, puede calcular el delta necesario
  (`valor_deseado - stock_actual`) y mandarlo a `ajustar-stock`.
- **`ajustar-stock` rechaza que el resultado quede negativo (400)**: no
  estaba explícito en el alcance, pero un stock físico no puede ser negativo;
  se decidió bloquear en vez de permitir valores negativos silenciosos (que
  además romperían la semántica de "Crítico" en `calcular_estado`, ya
  cubierta por `stock <= 0`). Documentado aquí como decisión de diseño no
  especificada por el dueño del negocio, análogo a como BE-005 documentó su
  regla de transición de mesas.
- **`AjusteStock.cantidad` rechaza 0**: un ajuste de 0 no tiene efecto y
  probablemente es un error del cliente; se devuelve 422 en vez de aceptarlo
  silenciosamente como no-op.
- **`GET /insumos?solo_alertas=true`**: filtra en Python después de calcular
  el estado de cada insumo (no en SQL), porque el estado no es una columna
  de la DB — es la forma más simple y correcta dado que el volumen esperado
  de insumos de un negocio de este tamaño es bajo; no se optimiza
  prematuramente con lógica SQL condicional replicando los umbrales.
- **`categoria_id` obligatorio, validado contra `Categoria` existente**:
  mismo criterio que en `Producto` (BE-003), por consistencia.
- **`GET /insumos/{id}`**: igual que en BE-003, no estaba explícito en los
  criterios pero se agregó por ser parte natural de un CRUD completo.
- **`response_model=None` en `DELETE`**: mismo ajuste ya conocido de
  BE-002/BE-005/BE-003.
- **Sin bloqueo de `DELETE` por relación con `Venta`**: los insumos no se
  descuentan automáticamente por ventas en esta tarea (eso sería lógica de
  BE-006, fuera de alcance); no se agregó ningún chequeo relacionado.

### Migración completa del patrón `has_table()` en `categorias.py` (evaluación pedida)

Con `Insumo` ya existente en esta tarea, se completó la migración iniciada en
BE-003: `app/routers/categorias.py` ya no tiene ningún uso de
`sqlalchemy.inspect(engine).has_table()` ni `text()`/SQL crudo. Tanto
`_contar_productos` como `_contar_insumos` son ahora consultas ORM directas
(`db.query(func.count(Modelo.id)).filter(Modelo.categoria_id == categoria_id)`),
importando `Producto` e `Insumo` directamente. Se eliminaron los imports de
`inspect`/`text`/`engine` del router, que ya no se usan.

Se decidió completar la migración (en vez de dejar el helper genérico
`_contar_relacionados` "por si acaso") porque:
- Ya no hay ninguna tabla relevante para `categorias.py` que no exista como
  modelo — el patrón defensivo ya cumplió su propósito temporal documentado
  en BE-002/BE-005 y ahora es código muerto si se mantiene.
- Resuelve el punto no bloqueante que el reviewer de BE-002 señaló (nombre de
  tabla interpolado por f-string en SQL crudo) de raíz, no con un allowlist
  parche.
- El costo de la migración es bajo (2 funciones casi idénticas, ambas ya
  usadas en `_a_out` y en `eliminar_categoria`) y mejora tipado/legibilidad.

No se tocó nada de `mesas.py`: su chequeo `_contar_ventas` con
`has_table("ventas")` se deja intacto porque `Venta` (BE-006) sigue sin
existir y está explícitamente fuera del alcance de esta tarea — es
responsabilidad de BE-006 migrarlo cuando ese modelo se cree, siguiendo el
mismo criterio aplicado aquí.

### Cómo probarlo

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```
POST http://127.0.0.1:8000/categorias  {"nombre":"Jarabes","color":"#8b5cf6"}
→ 201 {"id":1,...}

POST http://127.0.0.1:8000/insumos
  {"nombre":"Jarabe Fresa","categoria_id":1,"stock":10,"stock_minimo":3}
→ 201 {"id":1,...,"stock":10.0,"stock_minimo":3.0,"estado":"OK"}

POST http://127.0.0.1:8000/insumos
  {"nombre":"Hielo","categoria_id":1,"stock":0,"stock_minimo":10}
→ 201 {...,"estado":"Crítico"}

GET http://127.0.0.1:8000/insumos?solo_alertas=true
→ 200 [ ...solo 'Bajo'/'Crítico'... ]

POST http://127.0.0.1:8000/insumos/1/ajustar-stock  {"cantidad":-5}
→ 200 {...,"stock":5.0,...}

POST http://127.0.0.1:8000/insumos/1/ajustar-stock  {"cantidad":-9999}
→ 400 {"detail":"El ajuste dejaría el stock en ..., no puede ser negativo"}

PATCH http://127.0.0.1:8000/insumos/1  {"stock_minimo":1}
→ 200 (edita solo stock_minimo; "stock" en el body es ignorado porque el
        schema InsumoUpdate no lo declara)

DELETE http://127.0.0.1:8000/categorias/1
→ 409 (tiene insumos asociados)

DELETE http://127.0.0.1:8000/insumos/1
→ 204
```

Verificado en este entorno (Windows, Python 3.10, venv `backend/.venv`):
server real levantado con `uvicorn` en 127.0.0.1:8124 (no solo lectura de
código), con JWT real obtenido vía `/auth/login`. Se probaron con `curl`:
crear categoría, crear insumo con categoría inválida (404), crear insumos en
los tres estados posibles y confirmar que `estado` viene correcto en cada
caso (`OK`, `Bajo`, `Crítico` con stock=0), `GET /insumos` completo,
`GET /insumos?solo_alertas=true` (devuelve únicamente `Bajo`/`Crítico`),
`POST /insumos/{id}/ajustar-stock` sumando (200, estado recalculado a `OK`),
restando a un valor que dejaría stock negativo (400, mensaje con el valor
resultante), `cantidad=0` (422), `PATCH` de `stock_minimo` (200) y confirmé
que enviar `"stock"` en el body de `PATCH` no tiene ningún efecto (el schema
no lo acepta), `GET /insumos/{id}` inexistente (404), `DELETE /insumos/{id}`
(204), `DELETE /categorias/{id}` bloqueado por insumos asociados (409, con
conteo correcto). También verifiqué que no hubo regresión en BE-002/BE-003
tras completar la migración de `categorias.py`: creé un producto después de
la migración y `productos_count` siguió reflejándose correctamente en
`GET /categorias` junto con el conteo de insumos. Confirmé además que
`GET /insumos` sin header `Authorization` responde 401 (protegido con
`require_auth`, igual que `/categorias` y `/mesas`). No quedó ningún
`brainfreeze.db` ni proceso de prueba corriendo tras la verificación.

## Revisión

**Veredicto: `done`**

Verificado con servidor real (`uvicorn`), no solo lectura de código. Punto
crítico pedido explícitamente — que `estado`/`stock` no se puedan setear vía
`PUT`/`PATCH` — confirmado con un intento real de bypass:

```
PUT /insumos/1 {"stock": 99999, "estado": "Crítico", "stock_minimo": 5}
→ 200 {"id":1,...,"stock":10.0,"stock_minimo":5.0,"estado":"OK"}
```

`stock` se mantuvo en 10.0 (ignorado, no está en `InsumoUpdate`) y `estado`
igual se mantuvo en `"OK"` (el campo enviado fue ignorado silenciosamente por
Pydantic al no existir en el schema de entrada) — solo `stock_minimo` cambió.
Esto confirma que el bloqueo es estructural (el campo ni siquiera existe en
`InsumoUpdate`), no solo una validación que podría fallar en un caso límite.

Otros criterios verificados en vivo:

- `POST /insumos/{id}/ajustar-stock` con delta negativo funciona y recalcula
  `estado` correctamente (`OK`→`Bajo` al restar 5 de 10 con `stock_minimo=5`).
- Ajuste que dejaría stock negativo → 400 con mensaje claro.
- `cantidad=0` → 422 (rechazado por validador).
- `GET /insumos?solo_alertas=true` devuelve solo `Bajo`/`Crítico`, confirmado
  con datos reales.
- `DELETE /categorias/{id}` bloqueado (409) reflejando conteo de productos
  **e** insumos asociados juntos, confirmando que la migración conjunta con
  BE-003 no rompió nada.
- `GET /insumos` sin header `Authorization` → 401, protegido igual que el
  resto de routers.

Sobre las decisiones documentadas:

- **`stock`/`stock_minimo` como `Float`**: razonable dado que el alcance
  menciona insumos a granel (jarabes, hielo) sin especificar unidad; no se
  agregó campo `unidad` (hubiera sido scope creep no pedido). Correcto.
- **Migración completa de `has_table()`/SQL crudo en `categorias.py`**:
  revisado el archivo — ya no queda ningún `inspect`/`text` ahí, ambos
  conteos (`_contar_productos`, `_contar_insumos`) son ORM real. Confirmado
  en vivo que no rompió el flujo de BE-002 (bloqueo de DELETE con productos
  e insumos asociados, con conteo correcto de ambos).
- **`mesas.py` no tocado**: correcto dejarlo así — su `_contar_ventas` con
  `has_table("ventas")` sigue siendo necesario porque `Venta` (BE-006) no
  existe todavía; migrarlo ahora sería prematuro (no hay modelo que importar).
  Confirmado en vivo que `mesas.py` sigue funcionando sin regresión tras el
  refactor de `categorias.py` (listar/crear mesa probado).
- **Umbrales de `calcular_estado`**: documentados con precisión en el
  modelo y coinciden con lo descrito en el alcance de la tarea.

No se encontraron queries SQL crudas propias de esta tarea, ni credenciales
hardcodeadas. Tipado completo. Buena separación router/schema/modelo.

Todos los criterios de aceptación se cumplen. Se limpiaron los procesos y la
DB de prueba generados durante esta revisión.
