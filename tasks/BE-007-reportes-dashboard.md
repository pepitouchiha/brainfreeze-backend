---
id: BE-007
title: Endpoints de reportes (Dashboard y Contabilidad)
area: backend
status: done
priority: medium
depends_on: [BE-004, BE-006]
created_by: planner
---

## Objetivo

Dar de comer a las pantallas Dashboard y Contabilidad del mockup, que
muestran: ventas de hoy por hora, ventas mensuales (con tickets estimados y
ticket promedio), total acumulado del año, y alertas de stock bajo/crítico.

## Alcance

- `GET /reportes/hoy`: total vendido hoy, número de ventas, desglose por hora
  del día (basado en `creado_en` de las ventas).
- `GET /reportes/mensual`: total por mes (últimos N meses, ej. 12), número de
  tickets (ventas) y ticket promedio por mes.
- `GET /reportes/anual` (o incluir `ytd_total` dentro de `/reportes/mensual`):
  acumulado del año en curso.
- `GET /reportes/alertas-stock`: reutiliza el filtro de BE-004
  (`solo_alertas=true`) para devolver insumos en estado 'Bajo' o 'Crítico'.
- Todos los montos en COP, sin inventar formato de moneda en el backend — el
  backend devuelve números, el formateo a texto ("$ 12.000") es responsabilidad
  del frontend.

## Criterios de aceptación

- [ ] `GET /reportes/hoy` refleja correctamente ventas creadas en el día
      actual, agrupadas por hora.
- [ ] `GET /reportes/mensual` agrupa correctamente ventas por mes calendario.
- [ ] Ticket promedio = total del mes / número de ventas del mes (evitar
      división por cero si no hay ventas ese mes).
- [ ] `GET /reportes/alertas-stock` coincide con lo que devuelve
      `GET /insumos?solo_alertas=true` de BE-004.

## Notas de implementación

Archivos creados:
- `backend/app/schemas/reporte.py`: `VentaPorHora`, `ReporteHoyOut`, `VentaPorMes`,
  `ReporteMensualOut`.
- `backend/app/routers/reportes.py`: router `/reportes` con `dependencies=[Depends(require_auth)]`
  (mismo patrón que el resto de routers, requiere JWT vía `Authorization: Bearer <token>`).

Archivos modificados:
- `backend/app/main.py`: se registra `reportes.router`.

Endpoints implementados:
- `GET /reportes/hoy` — Filtra `Venta` con `creado_en` entre `time.min` y `time.max`
  de `date.today()` (mismo patrón de filtrado por fecha que ya usa
  `GET /ventas?desde=&hasta=`, sin conversión de timezone: `creado_en` se trata
  como hora "de servidor", consistente con el resto del backend). Devuelve
  `total`, `num_ventas` y `por_hora`: un array de **24 buckets fijos (0-23)**,
  cada uno con `total` y `num_ventas`, aunque no haya ventas en esa hora (se
  rellenan en 0) — decisión para que el frontend pueda graficar sin tener que
  rellenar huecos. Se agrega en memoria (Python), no en SQL, porque el volumen
  de ventas de un día de un solo local es bajo y evita depender de
  `strftime('%H', ...)` específico de SQLite.
- `GET /reportes/mensual?meses=12` — Devuelve los últimos N meses calendario
  (default 12, `1 <= meses <= 60`) terminando en el mes actual, incluyendo
  meses sin ventas con `total=0`, `num_ventas=0`, `ticket_promedio=0.0` (evita
  división por cero, criterio de aceptación). La agregación por mes usa
  `func.strftime('%Y', ...)` / `strftime('%m', ...)` de SQLite vía SQLAlchemy
  `group_by`, filtrando desde el 1 de enero del año más antiguo dentro del
  rango solicitado para no agregar sobre toda la tabla. `ticket_promedio =
  total / num_ventas` cuando `num_ventas > 0`, si no `0.0`.
  Se incluyó `ytd_total` (acumulado del año en curso, desde el 1 de enero
  hasta hoy) dentro de esta misma respuesta en lugar de crear
  `GET /reportes/anual` separado, tal como lo permite el alcance de la tarea
  ("o incluir ytd_total dentro de /reportes/mensual"). `ytd_total` se calcula
  con una query independiente (`SUM(total) WHERE creado_en >= 1-ene-actual`),
  no depende de si esos meses están dentro de la ventana `meses` solicitada.
- `GET /reportes/alertas-stock` — Reutiliza directamente la función
  `listar_insumos(solo_alertas=True, db=db)` de `app/routers/insumos.py` (no
  se duplicó la lógica de filtrado/estado) para garantizar que la respuesta
  sea idéntica byte a byte a `GET /insumos?solo_alertas=true`, tal como pide
  el criterio de aceptación.

Todos los montos se devuelven como enteros (COP, sin decimales, igual que
`Venta.total`/`Producto.precio`); `ticket_promedio` es `float` porque puede no
ser un entero exacto. No se formatea moneda en el backend.

No se implementó un endpoint de "productos más vendidos" porque no está en el
`## Alcance` ni en `## Criterios de aceptación` de esta tarea (fuera de
scope; si se necesita, debería salir como tarea nueva del planner).

Cómo probarlo (backend con venv en `backend/.venv`):
```
cd backend
./.venv/Scripts/python.exe -m app.scripts.crear_usuario test@brainfreeze.com "Test123456"
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```
```
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@brainfreeze.com","password":"Test123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s http://127.0.0.1:8000/reportes/hoy -H "Authorization: Bearer $TOKEN"
curl -s "http://127.0.0.1:8000/reportes/mensual?meses=6" -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:8000/reportes/alertas-stock -H "Authorization: Bearer $TOKEN"
```

Verificación manual realizada en esta sesión (servidor local levantado,
datos de prueba creados vía `POST /categorias`, `POST /productos`,
`POST /insumos` con estados OK/Bajo/Crítico, `POST /ventas` para ventas de
hoy, e inserción directa de ventas con `creado_en` de meses anteriores para
poblar el reporte mensual):
- `GET /reportes/hoy` reflejó correctamente 3 ventas ($72.000 total) en el
  bucket de la hora en que se crearon, y 0 en el resto de las 24 horas.
- `GET /reportes/mensual?meses=12` devolvió 12 meses (sep-2025 a ago-2026),
  con `total`/`num_ventas`/`ticket_promedio` correctos en los meses con datos
  (jun, jul, ago-2026) y `0`/`0`/`0.0` en los meses sin ventas; `ytd_total`
  sumó únicamente los meses de 2026 ($117.000), excluyendo correctamente una
  venta de prueba fechada en agosto-2025.
- `GET /reportes/mensual?meses=0` devolvió `422` (validación `ge=1`).
- `GET /reportes/alertas-stock` devolvió exactamente los mismos 2 insumos
  (Hielo=Crítico, Leche=Bajo) que `GET /insumos?solo_alertas=true`, en el
  mismo orden.
- Todos los endpoints devolvieron `401` sin header `Authorization`.

## Revisión

**Veredicto: `done`**

Revisión hecha leyendo `backend/app/routers/reportes.py`, `backend/app/schemas/reporte.py`,
`backend/app/routers/insumos.py`, `backend/app/models/venta.py` y `backend/app/routers/ventas.py`,
y verificando en vivo contra un backend real (uvicorn + SQLite limpia, usuario y JWT reales, sin
reutilizar los reportes de la sesión de implementación):

- `GET /reportes/hoy`: probado sin ventas (24 buckets en 0) y con 3 ventas creadas vía
  `POST /ventas` — el total ($48.000) y `num_ventas` (3) cayeron correctamente en el bucket de
  la hora en que se crearon, resto en 0.
- `GET /reportes/mensual`: insertadas ventas históricas directamente en SQLite (jul-2026,
  ene-2026, y una de ago-2025 para probar el corte de año). `meses=12` devolvió correctamente
  sep-2025→ago-2026 con `total`/`num_ventas`/`ticket_promedio` exactos en los meses con datos y
  `0`/`0`/`0.0` en los vacíos (sin división por cero). `ytd_total` = 103.000 (solo meses de 2026),
  excluyendo correctamente la venta de ago-2025. `meses=0` → `422`, `meses=61` → `422` (límite
  `le=60` funciona). `meses=1` devolvió solo el mes actual.
- `GET /reportes/alertas-stock`: creados 3 insumos (Bajo/Bajo/OK) y comparado byte a byte contra
  `GET /insumos?solo_alertas=true` — resultado idéntico (reutiliza `listar_insumos` directamente,
  sin duplicar lógica de estado, tal como describen las notas).
- Todos los endpoints devuelven `401` sin `Authorization`.
- No hay SQL crudo (usa SQLAlchemy `func.strftime` con bind params), type hints completos,
  Pydantic para output, separación router/schema razonable, sin secretos ni paths hardcodeados.
- Decisión de omitir "productos más vendidos": correcta. Ni el `## Objetivo` ni el `## Alcance`
  de esta tarea lo mencionan, y las vistas `DashboardView.vue`/`ContabilidadView.vue` en el
  frontend todavía no consumen nada de eso (siguen siendo placeholders) — no hay scope real que
  quedara descubierto.

**Observación menor (no bloqueante):** `reporte_hoy` compara `Venta.creado_en` (guardado como
UTC vía `datetime.now(timezone.utc)`, ver `app/models/venta.py:28`) contra `date.today()`, que es
hora local del servidor — si el servidor corre en una zona horaria con offset grande (p. ej.
UTC-6, como el entorno de esta revisión), una venta hecha cerca de medianoche local puede caer en
el "hoy" o "ayer" incorrecto según a qué lado de medianoche UTC caiga. No es un bug introducido
por esta tarea: es el mismo patrón que ya usa `GET /ventas?desde=&hasta=` en `ventas.py:26-29`
(patrón preexistente, documentado explícitamente en las notas de implementación como decisión
consciente de consistencia). Lo dejo anotado por si el planner decide estandarizar el manejo de
timezone en una tarea aparte, pero no amerita `changes-requested` para esta tarea puntual.
