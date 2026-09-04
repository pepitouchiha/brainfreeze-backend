---
id: BE-019
title: Publicar la app de Google OAuth (Sheets) para evitar expiración del token cada 7 días
area: backend
status: pending
priority: high
depends_on: [BE-012]
created_by: planner
---

## Objetivo

El OAuth client ID usado para la sincronización a Google Sheets
(`SHEETS_SYNC_ENABLED=true`) fue autorizado el 2026-09-04 con la app en
estado **"Pruebas" (Testing)** en Google Cloud Console. Mientras la app
esté en ese estado, Google expira el refresh token guardado en
`backend/authorized_user.json` cada **7 días**, sin importar el uso — es
decir, la sincronización a Sheets dejará de funcionar sola alrededor del
**2026-09-11** si no se resuelve esto antes.

El resto del sistema (ventas, inventario, mesas, etc.) no se ve afectado
por esto: la sincronización a Sheets es de "mejor esfuerzo" y sus fallos
solo se loguean como warning (ver `sheets_service.py`), nunca rompen la
API. Lo único que se pierde si el token expira es el respaldo automático
a la hoja de cálculo.

El equipo de BrainFreeze quedó instalado y corriendo en el PC del cliente
(entrega de equipo el 2026-09-04); la publicación de la app OAuth se debe
terminar de gestionar de forma remota desde la cuenta de Google
(`andresfit15@gmail.com`), sin necesidad del PC del cliente — **excepto**
por el último paso (ver Alcance).

## Alcance

Publicar la app OAuth de "Pruebas" a "En producción" en Google Cloud
Console, para que el refresh token deje de expirar cada 7 días.

**Ya hecho (2026-09-04):**
- Repo público `brainfreeze-legal` (github.com/pepitouchiha/brainfreeze-legal)
  con `index.html`, `privacy.html`, `terms.html` — página principal,
  política de privacidad y términos de servicio de BrainFreeze.
- GitHub Pages activado sobre ese repo (branch `main`, `/root`), publicado en
  `https://pepitouchiha.github.io/brainfreeze-legal/`.
- Propiedad `https://pepitouchiha.github.io/brainfreeze-legal/` verificada en
  Google Search Console con la cuenta `andresfit15@gmail.com` (método
  archivo HTML, `googleb6088f8891db89fb.html`, commiteado en el repo).
- Campos de "Marca" en la pantalla de consentimiento de OAuth completados
  (nombre de la app `BrainFreeze`, correo de asistencia, enlaces a las 3
  páginas de arriba).

**Pendiente:**
- [ ] Que Google Cloud Console reconozca la verificación de dominio hecha en
  Search Console (al 2026-09-04 seguía marcando "El sitio web de tu página
  principal no está registrado a tu nombre" pese a la cuenta y el dominio
  coincidir — probablemente un retraso de sincronización entre ambos
  productos de Google, puede tardar horas). Reintentar el flujo de
  "verificar marca" / "Publicar aplicación" periódicamente.
- [ ] Confirmar que el dominio `pepitouchiha.github.io` quedó agregado en
  "Dominios autorizados" de la pantalla de consentimiento.
- [ ] Una vez el estado pase de "Pruebas" a "En producción": **volver a
  correr `python -m app.scripts.setup_google_sheets` físicamente en el PC
  del cliente** (o vía acceso remoto tipo AnyDesk/TeamViewer) para generar
  un `authorized_user.json` nuevo bajo la app ya publicada. Publicar la app
  no renueva por sí solo un token ya emitido en modo Pruebas — hace falta
  una nueva autorización interactiva para que el token deje de expirar a
  los 7 días.

## Criterios de aceptación

- [ ] La pantalla de consentimiento de OAuth en Cloud Console muestra
      estado "En producción".
- [ ] `backend/authorized_user.json` en el PC del cliente fue regenerado
      *después* de que la app quedó en producción.
- [ ] Una sincronización real (crear/editar una categoría, producto, insumo
      o venta) se refleja en el spreadsheet `BrainFreeze POS` sin errores en
      el log del backend, corriendo varios días después sin intervención
      manual (confirma que el token no expiró).

## Notas de implementación

(pendiente — sin implementar todavía, ver checklist de arriba)
