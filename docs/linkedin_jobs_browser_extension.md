# Extensión local para capturar LinkedIn Jobs

Ruta del proyecto:

`./browser_extensions/linkedin_jobs_capture`

Copia de prueba en Drive:

`./browser_extensions/linkedin_jobs_capture`

ZIP de prueba en Drive:

`./linkedin_jobs_capture_extension.zip`

## Objetivo

Esta extensión es una capa de captura manual asistida para LinkedIn Jobs.

La idea ya no es exportar un archivo por empleo, sino trabajar por sesión:

- navegas LinkedIn Jobs de forma manual
- cuando un empleo te interesa, pulsas `Guardar empleo visible`
- la extensión lo guarda localmente en la sesión actual
- al final exportas todo junto como un solo CSV o JSONL

## Cómo funciona por dentro

- La barra flotante vive dentro de la página de LinkedIn Jobs.
- Los registros se guardan en `chrome.storage.local`.
- No hace llamadas de red.
- No auto-scrollea ni automatiza clicks.
- El popup sólo sirve para revisar, exportar o limpiar la sesión.

## Qué incluye

### Barra flotante dentro de LinkedIn

La extensión inyecta una barra fija en la esquina inferior derecha con:

- contador de empleos guardados
- botón `Guardar empleo visible`
- botón `Limpiar sesión`
- mensaje de estado

### Popup de la extensión

El popup sirve para:

- refrescar el conteo acumulado
- exportar la sesión como CSV
- exportar la sesión como JSONL
- limpiar la sesión completa

## Permisos

La extensión usa únicamente:

- `activeTab`
- `scripting`
- `storage`

Y sólo actúa sobre:

- `https://www.linkedin.com/jobs/*`

## Flujo recomendado de uso

1. Instala o recarga la extensión en Chrome/Chromium.
2. Abre LinkedIn Jobs.
3. Navega manualmente por la lista o el panel de detalle.
4. Cuando un job te interese, pulsa `Guardar empleo visible`.
5. Repite con otros jobs durante la misma sesión.
6. Abre el popup de la extensión.
7. Pulsa `Actualizar` para ver el total acumulado.
8. Exporta como CSV o JSONL.
9. Si quieres empezar una sesión nueva, pulsa `Limpiar sesión`.

## Campos exportados

La sesión guarda campos como:

- `source`
- `capture_method`
- `captured_at`
- `saved_at`
- `source_job_id`
- `source_url`
- `title`
- `company`
- `location`
- `posted_text`
- `description`
- `raw.page_url`
- `raw.detail_text`
- `raw.card_text`

## Formatos de exportación

### CSV

- Un registro por fila.
- Útil para hojas de cálculo o importadores simples.
- Incluye columnas planas y columnas derivadas desde `raw.*`.

### JSONL

- Un objeto JSON por línea.
- Mejor para ingestión de Hermes y pipelines posteriores.
- Conserva mejor la estructura original del registro.

## Instalación

1. Abre `chrome://extensions/`
2. Activa `Modo de desarrollador`
3. Click en `Cargar descomprimida`
4. Selecciona:

`./browser_extensions/linkedin_jobs_capture`

## Exportación desde Drive

Si quieres cargar una copia desde Drive, usa:

`./browser_extensions/linkedin_jobs_capture`

## Mantenimiento / cambios

Cuando actualices el código de la extensión:

- vuelve a cargarla en `chrome://extensions/`
- vuelve a abrir la pestaña de LinkedIn Jobs
- si el popup no refleja lo guardado, pulsa `Actualizar`
- si quieres validar desde cero, usa `Limpiar sesión`

## Verificación rápida

Si la barra no aparece:

- recarga la pestaña de LinkedIn Jobs
- revisa que la URL esté dentro de `/jobs/`
- abre un empleo y deja visible el panel de detalle
- pulsa `Guardar empleo visible`

Si el contador no cambia:

- confirma que la extensión esté recargada en Chrome
- prueba `Actualizar` en el popup
- revisa que no hayas pulsado `Limpiar sesión`
- confirma que Chrome no haya bloqueado la extensión

Si exporta vacío pero la barra muestra registros:

- abre de nuevo el popup
- pulsa `Actualizar`
- verifica que la sesión siga en `chrome.storage.local`
