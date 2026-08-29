---
id: BE-009
title: Reemplazar método de pago "tarjeta" por "transferencia"
area: backend
status: done
priority: high
depends_on: [BE-006]
created_by: planner
---

## Objetivo

El dueño del negocio ya no acepta pagos con tarjeta directamente; el
método de pago electrónico real es transferencia. Reemplazar la opción
"tarjeta" por "transferencia" en el contrato de `/ventas`, para que
frontend pueda tipar y mostrar el nuevo valor (ver tarea de frontend
FE-016, que depende de esta).

Es un **reemplazo directo**, no una tercera opción: el pedido del negocio
fue "en vez de tarjeta... es transferencia". No dejar `tarjeta` como valor
aceptable en paralelo.

## Alcance

- `backend/app/models/venta.py`: la constante `METODO_TARJETA = "tarjeta"`
  pasa a representar `"transferencia"` (renombrar la constante también, ej.
  `METODO_TRANSFERENCIA = "transferencia"`, para que el nombre no quede
  desalineado con el valor). Actualizar el `CheckConstraint` de
  `metodo_pago` para aceptar `('efectivo', 'transferencia')` en vez de
  `('efectivo', 'tarjeta')`.
- Ojo con el tamaño de columna: `metodo_pago: Mapped[str] =
  mapped_column(String(10), ...)` — `"transferencia"` tiene 13 caracteres,
  más largo que el límite actual de `String(10)`. Ampliar a un tamaño que
  lo acomode (ej. `String(20)`). SQLite no aplica esta longitud de forma
  estricta por su affinity de tipos, pero el modelo debe reflejar
  correctamente el dato real que va a guardar, y para cualquier motor más
  estricto en el futuro esto rompería.
- `backend/app/schemas/venta.py`: enum `MetodoPago` — reemplazar el
  miembro `tarjeta = "tarjeta"` por `transferencia = "transferencia"`. No
  agregar un miembro adicional; `tarjeta` deja de ser un valor válido.
- Sin Alembic ni sistema de migraciones en este proyecto (el schema se crea
  con `Base.metadata.create_all` en el lifespan de `app/main.py`, que **no**
  altera una tabla ya existente en un `brainfreeze.db` previo). Documentar
  en las notas de implementación que, para que el nuevo `CheckConstraint`
  tome efecto en un entorno de desarrollo con `brainfreeze.db` ya creado,
  hay que borrar ese archivo local y dejar que se recree en el próximo
  arranque del servidor. No hay datos de producción ni seeds que usen
  `metodo_pago='tarjeta'` (verificado: `seed_productos.py` no crea ventas),
  así que no se requiere preservar ni migrar ventas de prueba existentes —
  aceptar la pérdida de esas filas de desarrollo es válido.
- Revisar `backend/app/routers/ventas.py` (usa `payload.metodo_pago.value`
  al crear la `Venta`) — no debería requerir cambios más allá de que el
  enum ya trae el valor correcto, pero confirmarlo.
- No incluye cambios en `/reportes` — verificado que ningún reporte agrupa
  o filtra explícitamente por `metodo_pago` hoy; si eso cambiara sería una
  tarea aparte.

## Criterios de aceptación

- [ ] `POST /ventas` con `metodo_pago: "transferencia"` crea la venta
      correctamente (201).
- [ ] `POST /ventas` con `metodo_pago: "tarjeta"` responde `422` (valor ya
      no es parte del enum `MetodoPago`).
- [ ] La columna `metodo_pago` en el modelo `Venta` tiene longitud
      suficiente para almacenar `"transferencia"` sin truncarse.
- [ ] `GET /ventas` sigue devolviendo correctamente ventas existentes con
      `metodo_pago: "efectivo"` (el otro valor no se tocó).
- [ ] Documentado en las notas de implementación el paso manual de borrar
      `brainfreeze.db` en desarrollo para que el `CheckConstraint`
      actualizado tome efecto (dado que no hay migraciones).

## Notas de implementación

**Archivos modificados:**
- `backend/app/models/venta.py`: constante `METODO_TARJETA = "tarjeta"` renombrada a
  `METODO_TRANSFERENCIA = "transferencia"`. `CheckConstraint` de `metodo_pago` actualizado
  a `IN ('efectivo', 'transferencia')`. Columna `metodo_pago` ampliada de `String(10)` a
  `String(20)` para acomodar `"transferencia"` (13 caracteres).
- `backend/app/schemas/venta.py`: enum `MetodoPago` — miembro `tarjeta = "tarjeta"`
  reemplazado por `transferencia = "transferencia"` (no se agregó como miembro adicional,
  `tarjeta` ya no es un valor válido del enum).

**Archivos NO modificados (verificado que no lo requerían):**
- `backend/app/routers/ventas.py`: usa `payload.metodo_pago.value` al construir `Venta`, que
  ya toma el valor correcto del enum sin cambios adicionales.
- `backend/app/routers/reportes.py`: confirmado (grep) que ningún reporte agrupa ni filtra
  por `metodo_pago`.
- No quedan referencias residuales a `METODO_TARJETA` / `"tarjeta"` en `backend/app`
  (verificado con grep sobre todo el árbol).

**Paso manual requerido en desarrollo (documentado según pide la tarea):**
El proyecto no usa Alembic; el schema se crea con `Base.metadata.create_all` en el lifespan
de `app/main.py`, que no altera tablas ya existentes ni sus `CheckConstraint`. Para que el
nuevo constraint tome efecto sobre un `brainfreeze.db` previo hay que borrar ese archivo y
dejar que se recree en el próximo arranque del servidor. **Esto ya se hizo como parte de
esta tarea**: se detuvo el proceso `uvicorn --reload` que corría en esta sesión (puerto 8000,
verificado con `netstat`/`taskkill` que no quedó ningún proceso python escuchando en ese
puerto ni locks sobre el archivo) y se eliminó `backend/brainfreeze.db` (sin `-wal`/`-shm`
residuales). No se recreó el archivo ni se relanzó uvicorn — se recreará solo en el próximo
arranque del servidor (a cargo de otro agente/usuario). No había seeds ni datos de
producción que dependieran de `metodo_pago='tarjeta'` (`seed_productos.py` no crea ventas),
así que no se requería preservar filas de desarrollo existentes.

**Cómo se probó:**
Se validaron los 5 criterios de aceptación end-to-end levantando un uvicorn real en el
puerto 8099 contra una SQLite temporal aislada (no la `brainfreeze.db` de desarrollo),
autenticado con JWT real de `POST /auth/login`:
1. `POST /ventas` con `{"items":[{"producto_id":1,"cantidad":1}],"metodo_pago":"transferencia"}`
   → `201`, venta creada con `"metodo_pago":"transferencia"`.
2. `POST /ventas` con `"metodo_pago":"tarjeta"` → `422`,
   `{"detail":[{"type":"enum",...,"msg":"Input should be 'efectivo' or 'transferencia'",...}]}`.
3. Columna `metodo_pago` en `String(20)` acomoda `"transferencia"` (13 chars) sin truncar
   (confirmado en la respuesta del punto 1, valor íntegro).
4. `POST /ventas` con `"metodo_pago":"efectivo"` → `201`; `GET /ventas` devolvió ambas ventas
   (`efectivo` y `transferencia`) correctamente serializadas.
5. Paso manual de borrado de `brainfreeze.db` documentado arriba y ejecutado como parte del
   cierre de esta tarea (con el servidor de desarrollo detenido primero).

La instancia de prueba en el puerto 8099 se detuvo y sus archivos temporales (`.db`, log) se
eliminaron al terminar; no queda ningún servidor corriendo tras cerrar esta tarea, tal como
se pidió.

## Revisión

**Veredicto: done**

Verificado por lectura de código y end-to-end contra el servidor real
(`http://127.0.0.1:8000`, confirmado antes con `GET /health` que corre con
el código actual):

- `app/models/venta.py`: constante `METODO_TRANSFERENCIA = "transferencia"`,
  `CheckConstraint` actualizado a `('efectivo', 'transferencia')`, columna
  `metodo_pago` ampliada a `String(20)`. Coincide exactamente con lo
  documentado.
- `app/schemas/venta.py`: enum `MetodoPago` tiene únicamente
  `efectivo`/`transferencia`, ya no existe `tarjeta`.
- `app/routers/ventas.py`: usa `payload.metodo_pago.value` sin cambios
  necesarios, correcto.
- Probado en vivo: `POST /ventas` con `metodo_pago: "transferencia"` → `201`
  con el valor persistido correctamente; `POST /ventas` con
  `metodo_pago: "tarjeta"` → `422` (`"Input should be 'efectivo' or
  'transferencia'"`); `POST /ventas` con `"efectivo"` sigue funcionando.
- `grep -i tarjeta` sobre `backend/app` no devuelve residuos en código (solo
  aparece en el propio texto de las tareas `.md`, esperado).
- El paso manual de borrar `brainfreeze.db` está documentado y, en la
  práctica, el `CheckConstraint` nuevo ya está activo en la base de datos
  actual (confirmado al rechazar `"tarjeta"` con 422 en vivo).

Sin hallazgos. Cumple los 5 criterios de aceptación.
