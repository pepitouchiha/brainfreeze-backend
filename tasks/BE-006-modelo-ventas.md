---
id: BE-006
title: Modelo y endpoints de Ventas (POS, mesa opcional, método de pago)
area: backend
status: done
priority: high
depends_on: [BE-001, BE-003, BE-005]
created_by: planner
---

## Objetivo

Registrar ventas replicando el flujo de la pantalla "Ventas" del mockup:
carrito de productos, total, método de pago (Efectivo / Tarjeta), con la
mesa como campo opcional (ver BE-005 — venta libre si no se especifica mesa).

## Alcance

- Modelo `Venta`: `id`, `mesa_id` (nullable, FK a Mesa), `metodo_pago`
  ('efectivo' | 'tarjeta'), `total` (COP), `creado_en`.
- Modelo `VentaItem`: `id`, `venta_id`, `producto_id`, `cantidad`,
  `precio_unitario` (snapshot del precio al momento de la venta — no leer el
  precio actual del producto después, para que reportes históricos no cambien
  si el precio del producto se actualiza más adelante).
- `POST /ventas` recibe: lista de items (`producto_id`, `cantidad`),
  `metodo_pago`, `mesa_id` opcional. El backend calcula el total a partir de
  los precios actuales de los productos (no confíes en un total que mande el
  cliente).
- Si `mesa_id` viene en la venta, marcar esa mesa como `ocupada` (según la
  regla definida en BE-005).
- Descontar del inventario los insumos consumidos: **NO** lo incluyas en este
  MVP salvo que sea trivial — si implementar recetas (qué insumos consume cada
  producto) requiere diseño adicional no cubierto, dócumentalo como una tarea
  futura sugerida en tus notas en vez de improvisar un sistema de recetas
  completo aquí.
- Endpoint para listar ventas con filtros básicos (por fecha, por mesa).

## Criterios de aceptación

- [ ] `POST /ventas` crea una venta con sus items, calcula el total en el
      servidor (ignora cualquier total que mande el cliente).
- [ ] Una venta sin `mesa_id` se crea correctamente (venta libre).
- [ ] Una venta con `mesa_id` válido marca esa mesa como `ocupada`.
- [ ] `POST /ventas` con un `producto_id` o `mesa_id` inexistente responde 404
      con mensaje claro, sin crear registros parciales.
- [ ] `GET /ventas` permite filtrar al menos por rango de fecha.
- [ ] El precio unitario queda "congelado" en `VentaItem` al momento de la
      venta.

## Notas de implementación

**Archivos creados:**
- `backend/app/models/venta.py`: modelos `Venta` (`id`, `mesa_id` nullable FK a
  `mesas.id`, `metodo_pago`, `total`, `creado_en`) y `VentaItem` (`id`,
  `venta_id` FK, `producto_id` FK a `productos.id`, `cantidad`,
  `precio_unitario`). `metodo_pago` usa `CheckConstraint` igual que
  `estado` en `Mesa`/`Producto`, con constantes `METODO_EFECTIVO` /
  `METODO_TARJETA` exportadas. Relación `Venta.items` con
  `cascade="all, delete-orphan"`.
- `backend/app/schemas/venta.py`: `MetodoPago` (enum), `VentaItemCreate`,
  `VentaCreate` (con validador que exige al menos un item), `VentaItemOut`,
  `VentaOut`.
- `backend/app/routers/ventas.py`: `GET /ventas` (filtros opcionales `desde`,
  `hasta` — por fecha, comparando contra `Venta.creado_en` con
  `datetime.combine(fecha, time.min/max)` — y `mesa_id`) y `POST /ventas`.
  Router protegido con `dependencies=[Depends(require_auth)]`, igual patrón
  que el resto.

**Archivos modificados:**
- `backend/app/db/base_all.py`: importa `Venta`/`VentaItem` para que
  `create_all` cree las tablas.
- `backend/app/main.py`: registra `ventas.router`.
- `backend/app/routers/mesas.py`: `_contar_ventas` migrado de
  `inspect(engine).has_table("ventas")` + SQL crudo a una query ORM real
  (`db.query(func.count(Venta.id)).filter(Venta.mesa_id == mesa_id)`), igual
  patrón que `_contar_productos`/`_contar_insumos` en `categorias.py`. Ya no
  hace falta el chequeo condicional de existencia de tabla porque el modelo
  `Venta` existe desde esta tarea; se eliminó el import de `inspect`/`text`/
  `engine` que ya no se usan en ese archivo.

**Decisiones de diseño:**
- `POST /ventas`: primero se valida que exista la mesa (si se envía
  `mesa_id`) y que existan **todos** los productos referenciados en `items`
  (dedupe por `producto_id` para no golpear la DB más de una vez por
  producto repetido), y solo después de que todas las validaciones pasan se
  construyen los objetos `VentaItem`/`Venta` y se hace un único
  `db.add` + `db.commit`. Así se garantiza que un 404 (mesa o producto
  inexistente) no deja registros parciales, sin necesidad de un rollback
  explícito.
- El total se calcula 100% en el servidor sumando `producto.precio *
  cantidad` con el precio **actual** del producto en el momento de la venta;
  cualquier `total` que mande el cliente en el payload es ignorado (el
  schema `VentaCreate` ni siquiera tiene ese campo, así que Pydantic lo
  descarta silenciosamente si viene en el body).
- `precio_unitario` en `VentaItem` es un snapshot: se copia el precio del
  producto al crear la venta y nunca se vuelve a leer desde `Producto`, por
  lo que un cambio de precio posterior no afecta ventas históricas (probado
  manualmente: ver sección de pruebas).
- Si `mesa_id` viene en el payload, se marca `mesa.estado = ESTADO_OCUPADA`
  (constante importada de `app.models.mesa`, según lo documentado por
  BE-005) dentro de la misma transacción que crea la venta. La liberación
  de la mesa sigue siendo exclusivamente `POST /mesas/{id}/liberar`, no se
  tocó ese endpoint.
- Recetas / descuento de inventario de insumos por venta: **no
  implementado** en este MVP, tal como permite el alcance de la tarea.
  Requeriría un modelo adicional tipo `ProductoInsumo` (receta: qué
  insumos y en qué cantidad consume cada producto) que no existe todavía y
  que implica diseño propio (¿recetas por producto o por variante
  sabor/tamaño? ¿qué pasa si el insumo no alcanza — bloquear la venta o
  dejarlo en negativo?). Sugiero una tarea futura (p. ej. BE-00X "Recetas y
  descuento automático de inventario") en vez de improvisarlo aquí.
- Migración de `mesas.py` a query ORM real (pregunta abierta que dejó
  BE-005): se hizo. Ya no tiene sentido mantener el chequeo dinámico de
  `has_table`, porque el modelo `Venta` ya existe y está registrado en
  `base_all.py`; una query ORM directa es más simple, más segura (evita SQL
  crudo con `text()`) y consistente con el patrón ya usado en
  `categorias.py` y `productos.py`.
- `GET /ventas`: filtro de fecha inclusivo por día completo usando
  `datetime.combine(desde, time.min)` / `datetime.combine(hasta, time.max)`
  contra `Venta.creado_en` (guardado en UTC naive, mismo patrón que
  `Producto.creado_en`). No se agregó filtro por `metodo_pago` porque no lo
  pedía la tarea (evitar scope creep); si se necesita, es un filtro trivial
  de agregar después.

**Cómo probarlo:**

```
cd backend
./.venv/Scripts/python.exe -m app.scripts.crear_usuario admin@brainfreeze.com "Password123"
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

1. `POST /auth/login` con `{"email": "admin@brainfreeze.com", "password": "Password123"}` -> `access_token`.
2. Crear categoría, productos y (opcional) una mesa vía sus endpoints existentes.
3. `POST /ventas` con Authorization Bearer:
   ```json
   {
     "items": [{"producto_id": 1, "cantidad": 2}, {"producto_id": 2, "cantidad": 1}],
     "metodo_pago": "efectivo",
     "mesa_id": 1
   }
   ```
   Responde 201 con `total` calculado en servidor (ignora cualquier `total`
   enviado) y `items` con `precio_unitario` congelado. Si `mesa_id` viene,
   `GET /mesas` muestra esa mesa con `estado: "ocupada"`.
4. `POST /ventas` con `producto_id` o `mesa_id` inexistente -> 404, sin
   crear registros (verificado con `GET /ventas` antes/después).
5. `GET /ventas`, `GET /ventas?mesa_id=1`, `GET /ventas?desde=2026-08-25&hasta=2026-08-25`
   -> filtran correctamente.
6. Cambiar el precio de un producto (`PATCH /productos/{id}`) y volver a
   consultar `GET /ventas`: el `precio_unitario` de ventas anteriores no
   cambia.

Verificado end-to-end levantando el servidor real (uvicorn) contra una
SQLite temporal y probando los 4 flujos anteriores con `curl` (incluyendo
casos 404, 422 de `metodo_pago`/`items` vacíos, 401 sin token, y el 409 de
`DELETE /mesas/{id}` cuando tiene ventas asociadas).

## Revisión

**Veredicto: `done`**

Verificado end-to-end levantando el backend real (`uvicorn`, SQLite temporal
`brainfreeze_review_test.db`, borrada al terminar) y probando con `curl`
autenticado (JWT real de `POST /auth/login`) los flujos completos, sin
confiar únicamente en las notas del implementador:

- `POST /ventas` con `{"total": 1, ...}` en el payload -> el `total` devuelto
  fue `25000` (8000×2 + 9000×1 con los precios reales de los productos), el
  `total` enviado por el cliente fue ignorado. Confirma criterio 1.
- Venta sin `mesa_id` -> `201` con `mesa_id: null`. Confirma criterio 2.
- Venta con `mesa_id: 1` -> `GET /mesas` mostró la mesa con
  `"estado": "ocupada"` inmediatamente después. Confirma criterio 3.
- `producto_id: 999` inexistente -> `404 {"detail":"Producto 999 no
  encontrado"}`; `mesa_id: 999` inexistente -> `404 {"detail":"Mesa no
  encontrada"}`; en ambos casos `GET /ventas` mostró exactamente el mismo
  número de ventas que antes del intento (sin registros parciales). Confirma
  criterio 4.
- `GET /ventas?desde=2026-08-25&hasta=2026-08-25` trajo las ventas del día;
  `GET /ventas?desde=2026-08-26` (fecha futura) trajo `[]`;
  `GET /ventas?mesa_id=1` filtró correctamente. Confirma criterio 5.
- Se creó una venta con `producto_id=1` a precio `8000`, luego se hizo
  `PATCH /productos/1` subiendo el precio a `50000`, y se volvió a consultar
  `GET /ventas?mesa_id=1`: el `precio_unitario` del item siguió en `8000`.
  Confirma criterio 6 (congelado real, no solo en teoría).
- Casos adicionales probados: `401` sin token, `422` con `metodo_pago`
  inválido, `422` con `items: []`, y el caso crítico del refactor de
  `mesas.py`: `DELETE /mesas/1` con una venta asociada respondió `409` con
  el mismo mensaje que ya validaba BE-005 — el bloqueo sigue funcionando
  tras migrar `_contar_ventas` de `inspect(engine).has_table(...)` + SQL
  crudo a la query ORM (`db.query(func.count(Venta.id))...`). Revisé también
  que `mesas.py` ya no importa `inspect`/`text`/`engine` (código muerto
  eliminado correctamente).

Revisión de código (`backend/app/models/venta.py`,
`backend/app/schemas/venta.py`, `backend/app/routers/ventas.py`,
`backend/app/routers/mesas.py`, `backend/app/db/base_all.py`,
`backend/app/main.py`):
- Type hints completos, sin `Any`. Pydantic valida `items` no vacío,
  `cantidad > 0`, `metodo_pago` como enum cerrado.
- Sin SQL crudo en ningún punto tocado por esta tarea; todo vía ORM/SQLAlchemy
  Core con parámetros.
- Validación de mesa y de todos los productos (con dedupe por
  `producto_id`) ocurre completamente antes de construir `VentaItem`/`Venta`
  y antes del único `db.add`/`db.commit`, tal como documentan las notas —
  confirmado que efectivamente evita registros parciales, no solo por
  diseño sino por prueba real.
- Alcance respetado: no se improvisó un sistema de recetas/descuento de
  inventario; se documentó correctamente como tarea futura sugerida.
- `GET /ventas` no agrega filtro de `metodo_pago` (no lo pedía la tarea) —
  correcto, sin scope creep.
- Sin secretos ni paths absolutos hardcodeados.

No se encontraron hallazgos que bloqueen esta tarea. Nota menor sin impacto
en el veredicto: el proyecto no tiene suite de tests automatizados (pytest)
para ningún router, esta tarea no es la excepción — si el planner decide en
algún momento introducir tests, sería buen punto de partida dado que
`POST /ventas` es la lógica más compleja del backend hasta ahora.
