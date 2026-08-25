# Flujo de trabajo del equipo (Planner → Backend/Frontend → Reviewer)

Esta carpeta es el canal de comunicación entre los 4 sub-agentes del proyecto.
Toda coordinación pasa por archivos `.md` — ningún agente se comunica "directamente".

## Estructura

```
tasks/
  backend/   -> tareas para el agente backend-dev (FastAPI + SQLite)
  frontend/  -> tareas para el agente frontend-dev (Vue 3 + TypeScript)
```

Cada tarea es un archivo independiente: `tasks/<area>/<ID>-slug.md`
Ejemplo: `tasks/backend/BE-001-modelo-usuario.md`

## Plantilla de una tarea

```markdown
---
id: BE-001
title: Título corto de la tarea
area: backend            # backend | frontend
status: pending           # pending -> in-progress -> in-review -> done | changes-requested
priority: high             # high | medium | low
depends_on: []             # IDs de otras tareas, si aplica
created_by: planner
---

## Objetivo
Qué hay que lograr y por qué (contexto de negocio/funcional).

## Alcance
Qué SÍ incluye y qué NO incluye esta tarea.

## Criterios de aceptación
- [ ] Criterio verificable 1
- [ ] Criterio verificable 2

## Notas de implementación
(la llena el agente backend-dev / frontend-dev al terminar: decisiones tomadas,
archivos tocados, cómo probarlo)

## Revisión
(la llena el agente reviewer: veredicto y hallazgos)
```

## Ciclo de vida de `status`

1. `pending` — el planner creó la tarea, nadie la ha tomado.
2. `in-progress` — backend-dev/frontend-dev la está implementando.
3. `in-review` — implementación terminada, lista para el reviewer.
4. `done` — el reviewer la aprobó.
5. `changes-requested` — el reviewer encontró problemas; vuelve a `in-progress`
   una vez que backend-dev/frontend-dev la retoma.

## Reglas

- Solo el **planner** crea tareas nuevas y decide prioridad/dependencias.
- **backend-dev** solo toca archivos en `tasks/backend/` (y el código del backend).
- **frontend-dev** solo toca archivos en `tasks/frontend/` (y el código del frontend).
- **reviewer** no implementa nada: solo lee código, corre linters/tests si aplica,
  y escribe su veredicto en la sección `## Revisión` del archivo de tarea.
