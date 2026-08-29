---
id: BE-010
title: Campo de imagen de producto codificada en base64
area: backend
status: done
priority: medium
depends_on: [BE-003]
created_by: planner
---

## Objetivo

Permitir asociar una imagen a cada producto para que se muestre en el
catálogo del POS y en la lista de administración. Decisión explícita del
dueño del negocio: la imagen se guarda embebida en la base de datos SQLite
codificada en base64, no como archivo en disco ni en storage externo — no
se cuestiona esta decisión, solo se implementa (ver tarea de frontend
FE-017, que depende de esta y sube/lee el archivo desde el navegador).

## Alcance

- `backend/app/models/producto.py`: agregar columna nueva `imagen_base64:
  Mapped[str | None] = mapped_column(Text, nullable=True)` (importar `Text`
  de `sqlalchemy`). Nullable — un producto sin imagen sigue siendo válido.
- Contrato de datos: `imagen_base64` almacena el **Data URL completo**
  exactamente como lo genera `FileReader.readAsDataURL` en el navegador
  (ej. `data:image/png;base64,iVBORw0KG...`), no solo el payload base64
  crudo. Esto permite que el frontend lo use directamente como
  `<img :src="producto.imagen_base64">` sin reconstruir el prefijo. El
  backend no decodifica ni valida que el contenido sea una imagen real
  válida (fuera de alcance de este MVP) — solo aplica las dos validaciones
  descritas abajo.
- `backend/app/schemas/producto.py`:
  - `ProductoCreate` y `ProductoUpdate`: agregar `imagen_base64: str | None
    = Field(default=None)`, con un `field_validator` que:
    1. Si no es `None`, exige que empiece con el prefijo `data:image/`
       (rechazar con `ValueError` en caso contrario → 422).
    2. Si no es `None`, rechaza (`ValueError` → 422) si supera una longitud
       máxima razonable — sugerido **700,000 caracteres** (equivalente a
       ~512KB de imagen original antes de la inflación ~33% de base64).
       Esto es defensa en profundidad: el frontend (FE-017) también valida
       tamaño antes de enviar, pero el backend no debe confiar únicamente
       en esa validación de cliente.
  - `ProductoOut`: agregar `imagen_base64: str | None` para que se
    devuelva en las respuestas de `GET /productos` y `GET /productos/{id}`.
- No incluye: compresión ni redimensionado de la imagen en el backend, ni
  un endpoint separado para subir imágenes (se manda dentro del mismo
  payload de crear/editar producto), ni cambios a `Insumo`/`Categoria`.

## Criterios de aceptación

- [ ] `Producto` tiene una columna `imagen_base64` (`Text`, nullable).
- [ ] `POST /productos` y `PATCH /productos/{id}` aceptan `imagen_base64`
      como campo opcional; si se omite, el producto se crea/actualiza
      igual que antes (sin regresión).
- [ ] Un `imagen_base64` que no empieza con `data:image/` es rechazado con
      `422` y un mensaje claro.
- [ ] Un `imagen_base64` que supera el límite de longitud documentado es
      rechazado con `422` y un mensaje claro (probar con un string de
      prueba que exceda el límite, no hace falta una imagen real).
- [ ] `GET /productos` y `GET /productos/{id}` incluyen `imagen_base64` en
      la respuesta (`null` si el producto no tiene imagen).
- [ ] Un producto creado antes de esta tarea (sin la columna poblada) sigue
      siendo legible vía `GET /productos` con `imagen_base64: null`, sin
      romper la deserialización.

## Notas de implementación

**Archivos modificados:**
- `backend/app/models/producto.py`: agregada columna `imagen_base64: Mapped[str | None] =
  mapped_column(Text, nullable=True)` (import de `Text` agregado a la lista de imports de
  `sqlalchemy`).
- `backend/app/schemas/producto.py`:
  - Constante `IMAGEN_BASE64_MAX_LENGTH = 700_000` y función privada compartida
    `_validar_imagen_base64` con las dos validaciones pedidas (prefijo `data:image/` y
    longitud máxima), reutilizada por `ProductoCreate` y `ProductoUpdate` vía
    `field_validator("imagen_base64")` en cada uno, para no duplicar la lógica. Ambos
    lanzan `ValueError` (→ 422 automático de FastAPI/Pydantic) en los dos casos de rechazo.
  - `ProductoCreate.imagen_base64: str | None = Field(default=None)`.
  - `ProductoUpdate.imagen_base64: str | None = Field(default=None)`.
  - `ProductoOut.imagen_base64: str | None` agregado para incluirlo en las respuestas.
- `backend/app/routers/productos.py`:
  - `crear_producto`: pasa `imagen_base64=payload.imagen_base64` al construir `Producto`.
  - `actualizar_producto` (PUT/PATCH compartido): agrega
    `if payload.imagen_base64 is not None: producto.imagen_base64 = payload.imagen_base64`,
    siguiendo exactamente el mismo patrón que ya usan `sabor`/`tamano`/`nombre`/etc. en ese
    endpoint.

**Decisión de diseño (documentar comportamiento heredado del patrón existente, no
introducido por esta tarea):** al igual que el resto de campos opcionales del `PATCH`
(`sabor`, `tamano`, etc.), no hay forma de *borrar* una imagen ya asignada enviando
`imagen_base64: null` — el `if ... is not None` de `actualizar_producto` ignora nulls
explícitos igual que para los demás campos. Es consistente con el patrón ya establecido en
el router antes de esta tarea; si se necesita poder limpiar la imagen explícitamente,
requeriría un mecanismo aparte (ej. sentinel value o `exclude_unset`) que afectaría a todos
los campos opcionales del endpoint, no solo a este — lo señalo por si el planner quiere
evaluarlo, pero no lo até a esta tarea para evitar scope creep.

**Nota fuera del alcance textual de la tarea pero necesaria para que funcione en
desarrollo:** igual que documenta BE-009 para el cambio de `CheckConstraint`, este proyecto
no usa Alembic — el schema se crea con `Base.metadata.create_all`, que **no** altera una
tabla `productos` ya existente para agregarle la columna nueva `imagen_base64`. Sobre un
`brainfreeze.db` previo a esta tarea, la columna nueva no aparecería sin borrar el archivo y
dejar que se recree. Esto ya se resolvió como parte del cierre conjunto de BE-009: se detuvo
el uvicorn de desarrollo (puerto 8000) y se borró `backend/brainfreeze.db` (ver notas de
BE-009 para el detalle del proceso). Al recrearse desde cero en el próximo arranque, la
tabla `productos` incluirá la columna `imagen_base64` correctamente.

**Cómo se probó:**
Validación end-to-end con un uvicorn real en el puerto 8099 contra una SQLite temporal
aislada (no la de desarrollo), autenticado con JWT real:
1. `POST /productos` sin `imagen_base64` → `201`, `"imagen_base64":null` en la respuesta (sin
   regresión respecto al comportamiento previo).
2. `POST /productos` con `imagen_base64: "data:image/png;base64,iVBORw0KGgo="` → `201`, el
   valor se devuelve íntegro.
3. `POST /productos` con `imagen_base64: "iVBORw0KGgo="` (sin el prefijo `data:image/`) →
   `422`.
4. `POST /productos` con `imagen_base64` de 700,001 caracteres (por encima del límite de
   700,000) → `422`.
5. `PATCH /productos/{id}` agregando `imagen_base64` a un producto que no tenía → `200`, el
   producto actualizado la refleja.
6. `GET /productos` y `GET /productos/{id}` incluyen `imagen_base64` en cada producto
   (`null` en el que no la tiene, el Data URL completo en los que sí).
7. Un producto creado antes de esta tarea (es decir, la fila del test 1, creada sin
   `imagen_base64` en el payload y por ende con la columna en `NULL` en la fila) se leyó sin
   problema vía `GET /productos/1` con `"imagen_base64":null`, confirmando que no rompe la
   deserialización de filas preexistentes sin esa columna poblada.

La instancia de prueba en el puerto 8099 se detuvo y los archivos temporales se eliminaron
al terminar.

## Revisión

**Veredicto: done**

Verificado por lectura de código y end-to-end contra el servidor real:

- `app/models/producto.py`: columna `imagen_base64: Mapped[str | None] =
  mapped_column(Text, nullable=True)` presente, tal como se pidió.
- `app/schemas/producto.py`: `_validar_imagen_base64` compartida entre
  `ProductoCreate`/`ProductoUpdate` valida prefijo `data:image/` y longitud
  máxima de 700,000 caracteres; `ProductoOut.imagen_base64` expuesto.
- Probado en vivo: `POST /productos` con Data URL válido → `201` con el
  valor íntegro; `POST /productos` con `imagen_base64: "iVBORw0KGgo="` (sin
  prefijo) → `422` con mensaje claro; `GET /productos`/`GET
  /productos/{id}` incluyen el campo (`null` cuando no hay imagen).
- El hallazgo que esta misma tarea señaló ("PATCH con `imagen_base64: null`
  no borra la imagen") ya fue corregido por BE-011 (revisado por separado,
  también `done`) — no es una regresión pendiente sobre esta tarea, es
  trabajo de seguimiento ya cerrado.

Sin hallazgos nuevos. Cumple los 6 criterios de aceptación.
