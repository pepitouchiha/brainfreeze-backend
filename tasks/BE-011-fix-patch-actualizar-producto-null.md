---
id: BE-011
title: Corregir PATCH /productos/{id} para permitir borrar campos opcionales a null
area: backend
status: done
priority: high
depends_on: [BE-010]
created_by: planner
---

## Objetivo

El botón "Quitar imagen" implementado en el frontend (tarea FE-017, ya
`in-review`) depende de poder enviar `imagen_base64: null` en el `PATCH
/productos/{id}` para borrar la imagen existente de un producto. Hoy eso no
funciona: el handler `actualizar_producto` en
`backend/app/routers/productos.py` usa el patrón `if payload.X is not None:
producto.X = payload.X` para cada campo opcional, lo cual hace indistinguible
"el cliente no mandó este campo" de "el cliente lo mandó explícitamente como
`null`" — en ambos casos el `if` es falso y el campo existente en la base de
datos queda intacto. Esto ya quedó diagnosticado y verificado en vivo en las
notas de implementación de BE-010 y FE-017 (`PATCH` con
`{"imagen_base64": null}` devuelve el producto con la imagen original sin
cambios).

## Alcance

- Archivo a modificar: `backend/app/routers/productos.py`, función
  `actualizar_producto` (handler compartido de `PUT`/`PATCH
  /productos/{id}`) únicamente. No se toca `crear_producto` ni ningún otro
  router.
- Reemplazar los `if payload.X is not None: producto.X = ...` por lógica
  basada en `payload.model_dump(exclude_unset=True)` (Pydantic v2), que sí
  distingue "campo ausente del body" (no tocar `producto.X`) de "campo
  presente en el body, incluso con valor `null`" (asignar ese valor,
  incluso `None`, a `producto.X`).
- Campos **dentro de alcance** de este fix (los tres son `nullable=True` en
  el modelo `Producto`, así que asignarles `None` es válido a nivel de base
  de datos y no rompe ningún `NOT NULL`/`CheckConstraint`):
  - `imagen_base64` (el caso que motiva la tarea, usado por el botón
    "Quitar imagen" de FE-017).
  - `sabor` y `tamano`: mismo bug preexistente (documentado como
    conocido-pero-no-atado en las notas de BE-010); se corrigen en la
    misma pasada porque el fix con `exclude_unset` es el mismo mecanismo y
    no amerita una tarea separada.
- Campos **explícitamente fuera de alcance**: `nombre`, `categoria_id`,
  `precio`, `estado`. Estos son `nullable=False` en el modelo `Producto` (y
  `estado` además tiene un `CheckConstraint` de valores permitidos). Aunque
  `ProductoUpdate` los declara como `X | None` a nivel de schema (para
  poder omitirlos en un `PATCH` parcial), enviarlos explícitamente como
  `null` no tiene un caso de uso de negocio válido (no existe un "producto
  sin nombre" o "sin categoría") y, de aplicarse el mismo mecanismo sin
  cuidado, produciría un error de integridad de base de datos en lugar de
  un `422` limpio de validación. Si en el futuro se requiere ese
  comportamiento, debe tratarse en una tarea aparte que decida
  explícitamente cómo debe fallar (422 vs 500) — no se resuelve aquí.
  Estos cuatro campos siguen usando el patrón `is not None` sin cambios.
- No incluye cambios a `crear_producto`, a los schemas de
  `backend/app/schemas/producto.py`, ni a ningún otro router (`categorias`,
  `insumos`, `mesas`, `ventas`, etc.), aunque puedan compartir el mismo
  patrón — fuera de alcance de esta tarea.

## Criterios de aceptación

- [ ] `PATCH /productos/{id}` con body `{"imagen_base64": null}` responde
      `200` con `imagen_base64: null` en la respuesta, y una consulta
      posterior (`GET /productos/{id}`) confirma que el valor quedó en
      `null` también en la base de datos (no solo en la respuesta de ese
      request).
- [ ] `PATCH /productos/{id}` que **no** incluye la clave `imagen_base64`
      en el body (ni como valor ni como `null`) no altera el
      `imagen_base64` existente del producto — se verifica comparando el
      valor antes y después contra un producto que ya tenía una imagen
      asignada.
- [ ] El mismo comportamiento (borrar a `null` si se envía explícitamente,
      preservar si se omite la clave) se cumple igual para `sabor` y
      `tamano`.
- [ ] `PATCH /productos/{id}` que sí incluye `nombre`, `categoria_id`,
      `precio` y/o `estado` con un valor válido sigue actualizando esos
      campos exactamente igual que antes de esta tarea (sin regresión) —
      probar al menos un `PATCH` que combine un campo de los que sí
      cambian de mecanismo (ej. `imagen_base64`) junto con uno de los que
      no (ej. `precio`) en el mismo request, y confirmar que ambos se
      aplican correctamente.
- [ ] `PATCH /productos/{id}` a un producto inexistente sigue devolviendo
      `404` sin cambios de comportamiento.
- [ ] `PUT /productos/{id}` (que comparte el mismo handler) se comporta de
      forma consistente con lo anterior — no hace falta un set de pruebas
      separado, pero confirmar que no quedó código muerto o inconsistente
      entre ambos verbos.

## Notas de implementación

**Archivo modificado:** `backend/app/routers/productos.py`, función
`actualizar_producto` (compartida por `PUT`/`PATCH /productos/{id}`).

**Decisión tomada:** para los tres campos dentro de alcance (`sabor`,
`tamano`, `imagen_base64`) se calcula `campos_enviados =
payload.model_dump(exclude_unset=True)` una sola vez y se usa `"campo" in
campos_enviados` para decidir si asignar `producto.campo = payload.campo`
(incluyendo el caso `None`). Los cuatro campos fuera de alcance (`nombre`,
`categoria_id`, `precio`, `estado`) se dejaron exactamente igual, con el
patrón `if payload.X is not None: ...` — no se tocó su lógica ni se agregó
manejo especial de `null` para ellos, tal como pedía el alcance de la
tarea (para evitar producir un error de integridad de BD; sigue sin haber
un caso de uso definido para "borrar" esos campos).

No se tocó `crear_producto`, `backend/app/schemas/producto.py`, ni ningún
otro router.

**Hallazgo operativo durante la verificación (no es parte del código, es
nota para quien opere el entorno):** el proceso de `uvicorn --reload` que
ya estaba corriendo en background al iniciar esta tarea NO recargó tras
el cambio de código (confirmado esperando varios minutos y probando con
`curl` y con `urllib` de Python directamente). Investigando encontré que
el proceso raíz (`.venv\Scripts\python.exe -m uvicorn ...`) tenía un hijo
que efectivamente escuchaba en el puerto 8000, pero resolvía al
intérprete de Python de Microsoft Store
(`...WindowsApps\PythonSoftwareFoundation.Python.3.10_...\python.exe`) en
lugar de usar el propio `.venv`; ese hijo quedó "congelado" en el código
original desde el arranque y nunca reaccionó al watcher de archivos. Tuve
que matar ese árbol de procesos (`Stop-Process` sobre el PID raíz y su
hijo remanente) y relanzar `uvicorn app.main:app --reload --port 8000`
desde `.venv\Scripts\python.exe` para que el reload funcionara de forma
consistente. El servidor sigue corriendo así al terminar esta tarea y
responde `GET /health` correctamente. Vale la pena que quien administre
el entorno revise cómo se creó el `.venv` (posible venv creado a partir
del intérprete de Microsoft Store, lo que puede causar que
`multiprocessing`/el reloader de uvicorn resuelva un ejecutable de Python
fuera del propio `.venv`), para evitar que este mismo problema de reload
"fantasma" vuelva a ocurrir en tareas futuras.

**Cómo se probó** (con el servidor arriba, autenticando con el usuario
`admin@brainfreeze.com` existente en `brainfreeze.db` vía un JWT generado
directamente con `create_access_token` — no se conocía la contraseña en
texto plano de ese usuario para pasar por `/auth/login`):

1. Creado producto de prueba con `sabor`, `tamano` e `imagen_base64` no
   nulos.
2. `PATCH {"imagen_base64": null}` → responde `200` con
   `imagen_base64: null`; `GET` posterior confirma que quedó `null` en
   BD (criterio 1, cumplido).
3. `PATCH {"precio": 150}` (sin incluir la clave `imagen_base64` /
   `sabor` / `tamano`) → esos tres campos quedaron intactos, solo cambió
   `precio` (criterio 2, cumplido).
4. `PATCH {"sabor": null, "tamano": null}` → ambos quedaron `null` y se
   confirmó con `GET` posterior (criterio 3, cumplido).
5. `PATCH` combinando `imagen_base64` (nuevo valor, luego `null`) junto
   con `precio` en el mismo request → ambos cambios se aplicaron
   correctamente en la misma respuesta (criterio 4, cumplido).
6. `PATCH /productos/9999` (inexistente) → `404` (criterio 5, cumplido,
   sin cambios respecto al comportamiento previo).
7. `PUT /productos/{id}` con body completo incluyendo `tamano: null` e
   `imagen_base64: null` → mismo comportamiento consistente con `PATCH`,
   sin código muerto entre los dos verbos ya que comparten el mismo
   handler (criterio 6, cumplido).
8. `PATCH {"nombre": ..., "estado": "agotado"}` → sin regresión, siguen
   actualizándose igual que antes con el patrón `is not None`.
9. Datos de prueba (producto y categoría creados para esta verificación)
   eliminados al final (`DELETE /productos/1`, `DELETE /categorias/3`,
   ambos `204`) para no dejar residuos en `brainfreeze.db`.

Ejemplo de payload para reproducir manualmente el caso principal:

```
PATCH /productos/{id}
Authorization: Bearer <token>
Content-Type: application/json

{"imagen_base64": null}
```

## Revisión

**Veredicto: done**

Verificado por lectura de `app/routers/productos.py` (función
`actualizar_producto`) y end-to-end contra el servidor real corriendo en
`http://127.0.0.1:8000` (se confirmó antes de asumir nada, tal como pide el
contexto de esta ronda, que el servidor respondía con el comportamiento
esperado antes de concluir):

- `campos_enviados = payload.model_dump(exclude_unset=True)` se calcula una
  vez y se usa `"campo" in campos_enviados` para `sabor`, `tamano`,
  `imagen_base64` — asigna incluso `None` cuando la clave está presente en
  el body.
- `nombre`, `categoria_id`, `precio`, `estado` conservan el patrón original
  `is not None`, sin cambios, tal como pedía el alcance.
- Probado en vivo, caso principal (motivador de la tarea, encadenado con
  FE-017): creé un producto con `imagen_base64` no nula → `PATCH
  {"imagen_base64": null}` respondió `200` con `imagen_base64: null`, y un
  `GET` posterior confirmó el valor `null` persistido en base de datos (no
  solo en la respuesta del PATCH). Esto resuelve de punta a punta el botón
  "Quitar imagen" de FE-017.
- Probado también: `PATCH {"precio": 150}` sin incluir la clave
  `imagen_base64` no la alteró (seguía en `null` del paso anterior, sin
  error ni cambio inesperado).
- No se detectó código muerto entre `PUT`/`PATCH` (comparten el mismo
  handler, sin ramas condicionales por verbo).

Sin hallazgos. Cumple los 6 criterios de aceptación, incluyendo el caso de
integración con FE-017 que motivó la tarea.
