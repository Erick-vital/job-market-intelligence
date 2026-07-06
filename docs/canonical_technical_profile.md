# Perfil técnico canónico

Este documento explica cómo crear y actualizar el perfil técnico canónico de the user para los flujos de `job-market-intelligence`.

Archivos principales:

- Perfil humano:
  - `./items/profile/technical_experience.md`
- Perfil machine-readable:
  - `./items/profile/technical_experience.json`
- Evidencia granular:
  - `./items/profile/repo_evidence.jsonl`
- Taxonomía de skills:
  - `./items/profile/skill_taxonomy.yaml`

Skill de apoyo:

- `docs/technical-profile-evidence-skill.md`

## Qué es

El perfil técnico canónico es una base de capacidades técnicas, no documentación de proyectos.

Sirve para que `job-market-intelligence` pueda:

- generar CVs personalizados;
- comparar ofertas laborales contra experiencia real;
- detectar gaps de skills;
- preparar historias para entrevistas;
- elegir qué proyectos/evidencia mencionar para una vacante.

## Qué no es

No es:

- documentación interna de cada repo;
- lista de endpoints;
- changelog;
- inventario completo de funcionalidades;
- CV final;
- README alternativo.

Ejemplo de mala abstracción:

- “Integración de un proveedor externo en un endpoint backend”.

Eso describe una funcionalidad puntual.

Ejemplo de buena abstracción:

- “Integración de proveedores externos en servicios backend testables”.
- “Automatización backend con outputs persistidos e inspeccionables”.
- “Procesamiento de archivos y workflows internos con FastAPI”.

## Principio central

Extraer capacidades generales desde evidencia concreta.

Repo feature:

- Endpoint de transcripción.

Capacidad general:

- Integrar proveedores externos.
- Procesar archivos desde APIs.
- Persistir resultados y metadata.
- Manejar errores upstream.
- Escribir tests de servicios/endpoints.

Repo feature:

- `AGENTS.md`.

Capacidad general:

- Trabajo asistido por agentes con convenciones de proyecto.

Repo feature:

- `agent_router.py` + `llm_router.py`.

Capacidad general:

- Integración programática de agentes/modelos en pipelines Python.

## Estructura recomendada del Markdown

El archivo `technical_experience.md` debe mantenerse compacto y de alto nivel.

Secciones recomendadas:

1. Propósito.
2. Resumen técnico.
3. Capacidades principales.
4. Lectura por repo.
5. Cómo usarlo para matching laboral.
6. Reglas para generación de CVs.
7. Gaps de evidencia.
8. Cómo actualizarlo.

Cada capacidad debe incluir:

- nivel;
- confianza;
- resumen general;
- evidencia resumida;
- señales técnicas;
- frases CV-ready.

Evitar:

- describir cada endpoint;
- listar cada script;
- explicar cada pipeline;
- copiar documentación existente;
- usar nombres de features como si fueran capacidades.

## Estructura recomendada del JSON

El archivo `technical_experience.json` debe ser consumible por endpoints.

Debe incluir:

- `version`;
- `updated_at`;
- `purpose`;
- `supporting_skill`;
- `sources`;
- `capabilities`;
- `job_matching_guidance`;
- `update_rules`.

Cada capability debe tener:

```json
{
  "id": "backend_python_api_design",
  "name": "Backend Python and API design",
  "level": "strong",
  "confidence": "high",
  "evidence_type": "repo-evidenced",
  "summary": "...",
  "skills": ["Python", "FastAPI"],
  "evidence_refs": ["/path/to/repo"],
  "cv_phrases": ["..."]
}
```

## Estructura recomendada de repo_evidence.jsonl

`repo_evidence.jsonl` sí puede ser más granular, pero debe seguir siendo evidencia, no documentación.

Una línea por señal:

```json
{"repo":"/path/to/repo","signal":"fastapi_project","paths":["app/routes","app/services"],"capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high","notes":"FastAPI app with route/service separation."}
```

Reglas:

- Usar paths reales.
- No inventar skills que no estén respaldadas.
- Si una señal es débil, marcar `confidence: low` o `medium`.
- Si se buscó algo y no apareció, se puede registrar como `negative_signal`.

## Niveles de evidencia

Usar estos niveles:

- `high`: código, tests o documentación clara en repo.
- `medium_high`: componente real pero alcance limitado.
- `medium`: evidencia parcial o indirecta.
- `low`: solo mención o convención.
- `declared-in-base-cv`: viene del CV base, no de repo.
- `negative_signal`: se buscó evidencia y no apareció.

## Cómo agregar un nuevo repo

1. Revisar estructura tracked del repo.

Comando sugerido:

```bash
git -C /path/to/repo ls-files
```

2. Buscar señales generales:

- lenguajes;
- frameworks;
- API/backend;
- tests;
- Docker/IaC/CI-CD;
- cloud configs;
- agentes/LLMs;
- pipelines;
- colas/jobs;
- persistencia;
- docs operativas.

3. Traducir features a capacidades.

No escribir:

- “Este repo genera imágenes para blog”.

Sí escribir:

- “Pipeline automatizado de generación/publicación de contenido”.
- “Orquestación liviana de workflows multi-step”.

4. Agregar líneas en `repo_evidence.jsonl`.

5. Decidir si la nueva data realmente cambia el perfil.

Es válido hacer una actualización pequeña, solo agregar evidencia en `repo_evidence.jsonl`, o no cambiar el perfil si el repo solo repite capacidades ya cubiertas. No forzar cambios grandes por cada repo nuevo.

6. Actualizar `technical_experience.json` si aparece una capacidad nueva, sube la confianza de una existente o cambia el guidance de matching.

7. Actualizar `technical_experience.md` solo si cambia la narrativa general.

## Cómo actualizar con una nueva oferta laboral

Una oferta laboral no debe modificar automáticamente el perfil.

Usarla para:

- detectar gaps;
- priorizar qué capacidades mencionar;
- buscar qué evidencia falta;
- decidir qué repos analizar después.

Solo actualizar el perfil si la oferta te hace descubrir una experiencia real que ya existe pero no estaba registrada.

## Cómo actualizar con experiencia laboral no repo

Si la experiencia viene de CV base, notas personales o memoria laboral, marcarla como:

- `declared-in-base-cv`, o
- `declared-professional-experience`.

No mezclarla con `repo-evidenced`.

Ejemplo:

```json
{
  "id": "aws_professional_experience",
  "evidence_type": "declared-in-base-cv",
  "confidence": "medium_until_repo_evidence_added"
}
```

## Cuándo crear una nueva capacidad

Crear una nueva capacidad solo si:

- aparece en más de un repo;
- o es muy importante para matching laboral;
- o cambia cómo se debería presentar el perfil técnico;
- o no cabe naturalmente en capacidades existentes.

Si es solo una funcionalidad de un repo, dejarla en `repo_evidence.jsonl`.

## Cuándo elevar confianza

Elevar confianza cuando aparece evidencia más fuerte.

Ejemplos:

- De `declared-in-base-cv` a `repo-evidenced` si aparece un repo con Terraform/AWS real.
- De `medium` a `high` si hay código + tests + docs.
- De `low` a `medium` si una mención en README se complementa con scripts reales.

## Gaps actuales conocidos

En la versión 0.2, faltan repos/evidencia fuerte para:

- Terraform/IaC;
- Dockerfile/docker-compose;
- GitHub Actions/Azure DevOps workflows;
- Kubernetes;
- AWS configs reales;
- observabilidad formal;
- auth/security avanzada.

## Checklist de actualización

Antes de terminar una actualización:

- [ ] El Markdown sigue siendo compacto y de alto nivel.
- [ ] No se duplicó documentación de endpoints/repos.
- [ ] El JSON es válido.
- [ ] El JSONL es válido línea por línea.
- [ ] Cada skill fuerte tiene evidencia.
- [ ] Se distingue repo-evidenced vs declared-in-base-cv.
- [ ] Se mencionan gaps cuando aplique.
- [ ] Si se agregó una capacidad nueva, existe en Markdown y JSON.
- [ ] Si solo se agregó evidencia granular, basta con JSONL.

## Validación rápida

```bash
python3 - <<'PY'
import json, pathlib
base = pathlib.Path('./items/profile')
json.load(open(base / 'technical_experience.json', encoding='utf-8'))
for i, line in enumerate(open(base / 'repo_evidence.jsonl', encoding='utf-8'), 1):
    if line.strip():
        json.loads(line)
print('ok')
PY
```
