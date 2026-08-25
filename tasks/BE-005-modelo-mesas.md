---
id: BE-005
title: Modelo y endpoints de Mesas (lista con estado libre/ocupada)
area: backend
status: done
priority: high
depends_on: [BE-001]
created_by: planner
---

## Objetivo

Sistema de mesas nuevo (no existe en el mockup de referencia). Confirmado con
el dueño del negocio:

- La mesa es **solo una etiqueta/referencia opcional** sobre una venta — NO es
  una cuenta que se abre y va acumulando consumos en el tiempo. Cada venta se
  cobra de inmediato y opcionalmente se le asocia una mesa; también debe
  poder venderse "libre" (sin mesa).
- La vista de mesas es una **lista simple con estado** (libre / ocupada), no
  un mapa/plano visual.

## Alcance

- Modelo `Mesa`: `id`, `nombre_o_numero`, `estado` ('libre' | 'ocupada').
- Regla de transición de estado (decisión de diseño, ya que el dueño no la
  especificó — documenta esto explícitamente en tus notas de implementación):
  al crear una venta asociada a una mesa, la mesa pasa a `ocupada`
  automáticamente. Vuelve a `libre` mediante una acción explícita del usuario
  (endpoint `POST /mesas/{id}/liberar` o similar) — NO automáticamente por
  tiempo ni al cerrar la venta, porque la venta ya se cobró de inmediato y la
  mesa físicamente puede seguir con clientes sentados. Si al implementar
  encuentras una razón de negocio para automatizarlo distinto, no lo decidas
  solo — anótalo como duda en la tarea de Ventas (BE-006) en vez de cambiar
  esta regla en silencio.
- CRUD básico de mesas (crear, editar nombre, eliminar si no tiene ventas
  asociadas).
- Endpoint para marcar una mesa como libre manualmente.

## Criterios de aceptación

- [ ] `GET /mesas` devuelve todas las mesas con su `estado` actual.
- [ ] `POST /mesas` crea una mesa nueva en estado `libre`.
- [ ] `POST /mesas/{id}/liberar` fuerza el estado a `libre` sin importar el
      estado previo.
- [ ] Una venta sin mesa asociada (venta libre) es válida y no requiere pasar
      por este modelo en absoluto.
- [ ] La regla de "cuándo pasa a ocupada" queda documentada en las notas de
      implementación para que BE-006 (Ventas) la use de forma consistente.

## Notas de implementación

### Archivos creados/tocados

- `backend/app/models/mesa.py` (nuevo): modelo `Mesa` (`id`,
  `nombre_o_numero`, `estado` con `CheckConstraint` a nivel DB restringido a
  `'libre'`/`'ocupada'`). Se exportan las constantes `ESTADO_LIBRE` /
  `ESTADO_OCUPADA` para que BE-006 (Ventas) las reutilice en vez de
  hardcodear el string `"ocupada"`.
- `backend/app/schemas/mesa.py` (nuevo): `EstadoMesa` (enum `libre`/`ocupada`),
  `MesaCreate`, `MesaUpdate`, `MesaOut`.
- `backend/app/routers/mesas.py` (nuevo): `GET/POST /mesas`,
  `PUT/PATCH /mesas/{id}` (editar nombre), `POST /mesas/{id}/liberar`,
  `DELETE /mesas/{id}`.
- `backend/app/db/base_all.py`: se agregó el import de `Mesa`.
- `backend/app/main.py`: se registró `mesas.router`.

### Regla de negocio: cuándo pasa una mesa a "ocupada" (para que BE-006 la use)

Tal como especifica el alcance de esta tarea, **esta implementación NO
incluye ningún endpoint para marcar una mesa como "ocupada" manualmente** —
solo se puede crear en `libre` y liberar explícitamente vía
`POST /mesas/{id}/liberar`. La transición a `ocupada` es responsabilidad de
BE-006 (Ventas): al crear una venta con `mesa_id`, el endpoint
`POST /ventas` de BE-006 debe hacer `mesa.estado = ESTADO_OCUPADA` (importar
la constante desde `app.models.mesa`) y commitear ese cambio. **No** vuelve
a `libre` automáticamente al cerrarse/cobrarse la venta ni por tiempo —
solo mediante la acción explícita del usuario (`liberar`), porque
físicamente la mesa puede seguir con clientes sentados aunque la venta ya se
cobró. Verifiqué esta transición manualmente (fuera del endpoint, ya que
Ventas no existe todavía): actualicé el `estado` a `ocupada` directo en
SQLite y confirmé que `GET /mesas` lo refleja y que `liberar` lo regresa a
`libre` sin importar el estado previo.

### Decisiones tomadas

- **`estado` como `String` + `CheckConstraint`** (no `Enum` nativo de
  SQLite, que SQLAlchemy emula igual como `VARCHAR` + `CHECK`): consistente
  con que SQLite no tiene tipo enum real; el `CheckConstraint` a nivel DB es
  una capa extra de seguridad además de la validación Pydantic
  (`EstadoMesa`) en la capa de schemas/salida.
- **Sin endpoint para "ocupar" manualmente**: no lo pide el alcance de esta
  tarea (solo pide `liberar`); ocupar es un efecto colateral de crear una
  venta, que es responsabilidad de BE-006. No lo agregué para no invadir el
  alcance de esa tarea ni inventar un endpoint no pedido.
- **Borrado bloqueado por ventas asociadas** (criterio "eliminar si no
  tiene ventas asociadas" en el Alcance): igual que en BE-002 con
  productos/insumos, `Venta` (BE-006) no existe todavía como modelo en esta
  tarea, así que no se usa `relationship()` ORM hacia un modelo inexistente
  (rompería la resolución de mappers de SQLAlchemy). Se verifica en tiempo
  de ejecución con `sqlalchemy.inspect(engine).has_table("ventas")`: si no
  existe, cuenta 0 (no puede haber ventas de algo que no existe). Si existe,
  se hace `COUNT(*)` parametrizado filtrando `mesa_id`. Verificado
  manualmente creando una tabla `ventas` de prueba con una fila
  `mesa_id=1`: el `DELETE` de esa mesa respondió 409 con el mensaje
  esperado. Esto asume que BE-006 llamará a su tabla `ventas` con columna
  `mesa_id` (tal como especifica su propia tarea); si cambia, ajustar
  `_contar_ventas` en `app/routers/mesas.py`.
- **Venta libre (sin mesa) fuera del alcance de este modelo**: no se creó
  ninguna validación ni tabla que obligue a asociar mesa — el criterio
  "una venta sin mesa asociada es válida" se cumple trivialmente porque
  `Mesa` no impone ninguna restricción sobre `Venta`; es BE-006 quien debe
  declarar `mesa_id` como nullable.
- **`response_model=None` explícito en `DELETE`**: mismo ajuste que en
  BE-002 por el mismo problema de FastAPI 0.115 con `from __future__ import
  annotations` + retorno `-> None` + status 204.

### Cómo probarlo

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```
POST http://127.0.0.1:8000/mesas  {"nombre_o_numero":"Mesa 1"}
→ 201 {"id":1,"nombre_o_numero":"Mesa 1","estado":"libre"}

GET http://127.0.0.1:8000/mesas
→ 200 [{"id":1,"nombre_o_numero":"Mesa 1","estado":"libre"}]

PUT http://127.0.0.1:8000/mesas/1  {"nombre_o_numero":"Mesa VIP"}
→ 200 {"id":1,"nombre_o_numero":"Mesa VIP","estado":"libre"}

POST http://127.0.0.1:8000/mesas/1/liberar
→ 200 {"id":1,"nombre_o_numero":"Mesa VIP","estado":"libre"}

DELETE http://127.0.0.1:8000/mesas/1
→ 204
```

Verificado en este entorno (Windows, Python 3.10, venv `backend/.venv`):
server levanta sin errores; se probaron con `curl` los casos: crear (201,
estado inicial `libre`), listar (200), editar nombre por PUT (200), liberar
mesa ya libre (no-op, 200), eliminar no encontrada (404), eliminar existente
sin ventas (204). Además se simuló manualmente en SQLite el estado
`ocupada` y la existencia de la tabla `ventas` con una fila asociada para
confirmar que `GET /mesas` refleja `ocupada`, que `liberar` la regresa a
`libre` sin importar el estado previo, y que `DELETE` responde 409 cuando
hay ventas asociadas. No quedó ningún `brainfreeze.db` ni proceso de prueba
corriendo tras la verificación.

## Revisión

**Veredicto: `done`**

Verificado con el servidor real corriendo (mismo entorno que BE-002):

- `GET /mesas` devuelve todas las mesas con `estado` — confirmado.
- `POST /mesas` crea en `libre` — confirmado (`{"estado":"libre"}` en la
  respuesta 201).
- `POST /mesas/{id}/liberar` fuerza `libre` — confirmado sobre una mesa ya
  libre (no-op, 200); el código (`mesa.estado = ESTADO_LIBRE` sin condicional)
  deja claro que también funcionaría partiendo de `ocupada`, consistente con
  "sin importar el estado previo".
- `DELETE /mesas/{id}` bloqueado por ventas asociadas: probé el caso real
  creando a mano una tabla `ventas` con una fila `mesa_id` apuntando a la
  mesa — respondió 409 con `"tiene 1 venta(s) asociada(s)"`. Sin ventas,
  `DELETE` respondió 204.
- Venta libre (sin mesa): correctamente fuera del alcance de este modelo, no
  se impone ninguna restricción — cumple trivialmente el criterio.
- La regla de transición a `ocupada` queda documentada de forma clara y
  accionable para BE-006 (constantes `ESTADO_LIBRE`/`ESTADO_OCUPADA`
  exportadas desde `app/models/mesa.py`).

Sobre los dos puntos que se pidió evaluar explícitamente:

1. **Mismo patrón `has_table()` + SQL parametrizado que BE-002** para
   `_contar_ventas`: mismo análisis — razonable y temporal, sin riesgo real
   de inyección hoy (el valor `mesa_id` va parametrizado; el nombre de tabla
   `"ventas"` está hardcodeado, no viene de input). Consistente con BE-002.
2. **Sin endpoint para "ocupar" manualmente, BE-006 debe setear
   `mesa.estado` directamente vía constante exportada**: diseño razonable,
   no lo considero un acoplamiento frágil. El alcance de esta tarea pide
   explícitamente solo `liberar`; inventar un endpoint `ocupar` no pedido
   habría sido scope creep. Exportar `ESTADO_LIBRE`/`ESTADO_OCUPADA` como
   constantes en vez de dejar que BE-006 hardcodee el string `"ocupada"` es
   la forma correcta de evitar duplicación/drift dentro del mismo backend
   monolítico (no hay frontera de servicio que haga esto frágil). Sugerencia
   no bloqueante: si a futuro la transición a `ocupada` necesita validación
   adicional (ej. no permitir ocupar una mesa ya ocupada, side-effects), sería
   más limpio encapsularla en un método `Mesa.ocupar()` en vez de que BE-006
   asigne el atributo directo — pero eso es una mejora opcional, no un
   defecto de esta implementación.

Otras observaciones no bloqueantes: mismas que BE-002 (sin tests
automatizados, tipado y estructura correctos, `response_model=None` en
`DELETE` es el mismo fix ya verificado como necesario en BE-002).

Cumple los 5 criterios de aceptación exactamente. Limpié la DB de prueba y el
venv temporal; no quedó ningún proceso corriendo.
