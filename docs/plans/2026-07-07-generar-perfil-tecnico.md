# Generar Perfil Técnico Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Agregar en la sección Technical profile un flujo web para generar el perfil técnico canónico a partir de URLs de repos públicos o rutas locales de repos, reutilizando la lógica existente de `repo_evidence.jsonl -> technical_experience.json`.

**Architecture:** Mantener el stack actual FastAPI + Jinja2 + HTMX. Crear una capa de servicio nueva para resolver fuentes de repos, extraer evidencia técnica granular, escribir/actualizar `items/profile/repo_evidence.jsonl`, ejecutar la generación de `technical_experience.json`, y devolver un resumen HTML. La UI será un formulario HTMX dentro de `app/templates/index.html`, sin migrar todavía a Svelte.

**Tech Stack:** FastAPI, Pydantic, Jinja2, HTMX, Python stdlib, git CLI, pytest/TestClient.

---

## Decisión de producto

La funcionalidad debe tener un botón/formulario llamado “Generar perfil” dentro de la sección `Technical profile`.

El formulario aceptará dos tipos de fuente:

1. URLs de repos públicos, una por línea.
   - Ejemplo: `https://github.com/user/repo`
   - El backend clona cada repo en un directorio temporal y analiza archivos tracked.

2. Rutas locales, una por línea.
   - Ejemplo: `/home/erickesc/repos/automation_api`
   - Esto permite analizar repos privados sin subirlos ni exponer credenciales.

El submit debe generar o actualizar:

- `items/profile/repo_evidence.jsonl`
- `items/profile/technical_experience.json`

Opcional para una fase posterior:

- actualizar `items/profile/technical_experience.md`
- actualizar `items/profile/skill_taxonomy.yaml`

Para esta primera versión, recomiendo NO generar Markdown narrativo automáticamente, porque requiere más criterio humano y puede sobre-escribir una narrativa curada.

---

## Alcance v1 recomendado

### Incluido

- Formulario HTMX en Technical profile.
- Endpoint web: `POST /ui/profile/generate`.
- Endpoint API JSON: `POST /api/profile/generate`.
- Request schema con `public_repo_urls` y `local_repo_paths`.
- Validación de input:
  - al menos una fuente;
  - URLs deben ser `https://...`;
  - rutas locales deben existir y ser directorios;
  - cada fuente debe ser un repo Git o tener archivos analizables.
- Servicio para analizar repos y crear evidencia heurística.
- Servicio para escribir JSONL de evidencia.
- Reutilizar la lógica del script existente para generar `technical_experience.json`.
- Respuesta con resumen:
  - repos analizados;
  - señales detectadas;
  - paths actualizados;
  - warnings/errores por repo.
- Tests unitarios/integración.
- Documentación breve en README o docs.

### Fuera de alcance v1

- No Svelte todavía.
- No análisis LLM del código.
- No login GitHub ni repos privados remotos.
- No edición visual del perfil generado.
- No generación automática del Markdown humano salvo que el usuario lo pida explícitamente.
- No ejecución de código de los repos analizados.

---

## Diseño de datos

### Request schema

Agregar a `app/schemas/job_matching.py` o, mejor, crear `app/schemas/profile_generation.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProfileGenerateRequest(BaseModel):
    public_repo_urls: list[str] = Field(default_factory=list)
    local_repo_paths: list[str] = Field(default_factory=list)
    append_evidence: bool = True

    @field_validator("public_repo_urls", "local_repo_paths", mode="before")
    @classmethod
    def split_textarea_lines(cls, value):
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return value or []
```

### Response schema

```python
class ProfileGenerateRepoSummary(BaseModel):
    source: str
    source_type: str
    status: str
    signals: list[str] = []
    evidence_count: int = 0
    warning: str | None = None


class ProfileGenerateResponse(BaseModel):
    status: str
    repos_analyzed: int
    evidence_rows_written: int
    technical_profile_path: str
    evidence_path: str
    repos: list[ProfileGenerateRepoSummary]
```

### Evidence JSONL shape

Reutilizar el shape documentado:

```json
{"repo":"/path-or-url","signal":"fastapi_project","paths":["app/routes","app/services"],"capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high","notes":"FastAPI app with route/service separation."}
```

---

## Heurísticas v1 para extraer evidencia

Crear `app/services/profile_evidence.py`.

La extracción debe ser conservadora. Mejor pocos signals correctos que muchos inflados.

Signals mínimos:

1. Python backend/API
   - Detectar: `pyproject.toml`, `requirements.txt`, `app/main.py`, imports FastAPI/Flask/Django.
   - Capability: `backend_python_api_design`
   - Skills: `Python`, `FastAPI` si aplica.

2. Tests
   - Detectar: `tests/`, `pytest`, `unittest`, archivos `test_*.py`.
   - Capability: `test_driven_backend_development` o `automated_testing`
   - Skills: `pytest`, `Python`.

3. Persistence
   - Detectar: SQLite, SQLAlchemy, migrations, `*.sqlite` ignorar runtime si no tracked, modelos DB.
   - Capability: `local_persistence_and_data_modeling`
   - Skills: `SQLite`, `SQLAlchemy` si aplica.

4. LLM/agent integrations
   - Detectar: `openai`, `anthropic`, `llm`, `agents`, `tools`, `prompts`.
   - Capability: `llm_and_agent_workflow_integration`
   - Skills: `LLM APIs`, `OpenAI-compatible APIs`, `Anthropic` si aplica.

5. Automation/workflows/scripts
   - Detectar: `scripts/`, cron docs, pipelines, CLI commands.
   - Capability: `automation_workflow_orchestration`
   - Skills: `Python`, `CLI automation`.

6. Frontend/UI
   - Detectar: Jinja2, HTMX, React, Svelte, Vue, TypeScript, CSS.
   - Capability: `frontend_ui_development`
   - Skills según framework detectado.

7. Browser extension
   - Detectar: `manifest.json`, `content_scripts`, extension dirs.
   - Capability: `browser_extension_development`
   - Skills: `JavaScript`, `Browser Extensions`.

8. DevOps/IaC
   - Detectar: Dockerfile, docker-compose, GitHub Actions, systemd, Terraform.
   - Capability: `deployment_and_operations`
   - Skills: `Docker`, `GitHub Actions`, `systemd`, `Terraform`.

---

## Task 1: Extraer la lógica del script generador a un servicio reusable

**Objective:** Poder llamar la generación de `technical_experience.json` desde web/API sin ejecutar subprocess.

**Files:**
- Modify: `scripts/generate_technical_experience.py`
- Create: `app/services/technical_profile_generation.py`
- Test: `tests/test_technical_profile_generator.py`

**Step 1: Crear test de servicio**

Agregar un test que llame una función Python directa, no `subprocess`:

```python
def test_generate_technical_profile_service_from_evidence(tmp_path):
    evidence = tmp_path / "repo_evidence.jsonl"
    output = tmp_path / "technical_experience.json"
    evidence.write_text(
        '{"repo":"demo","signal":"fastapi_project","capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high"}\n',
        encoding="utf-8",
    )

    result = generate_technical_profile(evidence_path=evidence, output_path=output)

    assert result.output_path == output
    assert result.capabilities_count == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["capabilities"][0]["id"] == "backend_python_api_design"
```

**Step 2: Implementar dataclass y función**

En `app/services/technical_profile_generation.py`:

```python
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class TechnicalProfileGenerationResult:
    output_path: Path
    evidence_path: Path
    capabilities_count: int


def generate_technical_profile(*, evidence_path: Path, output_path: Path) -> TechnicalProfileGenerationResult:
    rows = []
    if evidence_path.exists():
        for line in evidence_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    by_capability: dict[str, list[dict]] = {}
    skills_by_capability: dict[str, Counter[str]] = {}
    for row in rows:
        for capability in row.get("capabilities", []) or [row.get("signal", "general_capability")]:
            by_capability.setdefault(capability, []).append(row)
            skills_by_capability.setdefault(capability, Counter()).update(row.get("skills", []))

    capabilities = []
    for capability_id, capability_rows in sorted(by_capability.items()):
        skills = [name for name, _ in skills_by_capability[capability_id].most_common(12)]
        capabilities.append({
            "id": capability_id,
            "name": capability_id.replace("_", " ").title(),
            "level": "working",
            "confidence": _confidence(capability_rows),
            "evidence_type": "repo-evidenced",
            "summary": "Capability inferred from repo evidence. Edit this summary before using publicly.",
            "skills": skills,
            "evidence_refs": sorted({str(row.get("repo", "")) for row in capability_rows if row.get("repo")}),
            "cv_phrases": [],
        })

    output = {
        "version": "generated.v1",
        "updated_at": date.today().isoformat(),
        "purpose": "Canonical technical profile generated from repo evidence.",
        "supporting_skill": "docs/technical-profile-evidence-skill.md",
        "sources": [str(evidence_path)],
        "capabilities": capabilities,
        "job_matching_guidance": {"prioritize": [], "deprioritize": []},
        "update_rules": ["Review generated summaries manually before using for job matching."],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return TechnicalProfileGenerationResult(
        output_path=output_path,
        evidence_path=evidence_path,
        capabilities_count=len(capabilities),
    )


def _confidence(rows: list[dict]) -> str:
    values = {str(row.get("confidence", "")).lower() for row in rows}
    if "high" in values:
        return "high"
    if "medium_high" in values:
        return "medium_high"
    if "medium" in values:
        return "medium"
    return "low"
```

**Step 3: Simplificar el script**

`generate_technical_experience.py` debe importar `generate_technical_profile` y conservar CLI compatibility.

**Step 4: Verificar**

Run:

```bash
uv run pytest tests/test_technical_profile_generator.py -q
```

Expected: pass.

---

## Task 2: Crear analizador conservador de repos

**Objective:** Convertir un repo local ya resuelto en filas de evidencia JSONL.

**Files:**
- Create: `app/services/profile_evidence.py`
- Test: `tests/test_profile_evidence.py`

**Step 1: Crear tests con repos fake**

Casos mínimos:

- repo con `pyproject.toml` + `app/main.py` con FastAPI => `fastapi_project`.
- repo con `tests/test_api.py` => `automated_testing`.
- repo con `manifest.json` => `browser_extension`.

**Step 2: Implementar modelos internos**

```python
@dataclass(frozen=True)
class RepoEvidenceRow:
    repo: str
    signal: str
    paths: list[str]
    capabilities: list[str]
    skills: list[str]
    confidence: str
    notes: str

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
```

**Step 3: Implementar `analyze_repo_for_evidence(repo_path: Path, repo_label: str)`**

Reglas:

- Preferir `git -C repo ls-files` si existe `.git`.
- Si no es git, caminar archivos excluyendo `.venv`, `node_modules`, `.git`, `__pycache__`, `dist`, `build`.
- Leer solo archivos pequeños de texto para buscar imports/patrones.
- Nunca ejecutar código del repo.

**Step 4: Verificar**

Run:

```bash
uv run pytest tests/test_profile_evidence.py -q
```

Expected: pass.

---

## Task 3: Resolver fuentes: URLs públicas y rutas locales

**Objective:** Aceptar URLs públicas clonables y rutas locales privadas de forma segura.

**Files:**
- Modify: `app/services/profile_evidence.py`
- Test: `tests/test_profile_evidence.py`

**Step 1: Tests**

- Local path inexistente => warning/status `failed`.
- Local path existente => status `completed`.
- URL no-https => validation error o failed.

**Step 2: Implementar resolver**

Crear función:

```python
def resolve_profile_sources(public_repo_urls: list[str], local_repo_paths: list[str]) -> list[ResolvedRepoSource]:
    ...
```

Para URLs:

- aceptar solo `https://`.
- clonar con `git clone --depth 1 URL tempdir`.
- usar `tempfile.TemporaryDirectory()`.
- capturar errores de git y devolver warning, no tumbar todo el batch.

Para rutas locales:

- `Path(path).expanduser().resolve()`.
- validar `exists()` y `is_dir()`.
- no restringir a `/home/erickesc/repos` porque el usuario puede tener privados en otra ruta.
- no exponer contenido de archivos en logs.

**Step 3: Verificar**

Run:

```bash
uv run pytest tests/test_profile_evidence.py -q
```

Expected: pass.

---

## Task 4: Crear servicio orquestador de generación de perfil

**Objective:** Analizar múltiples fuentes, escribir evidencia y regenerar `technical_experience.json`.

**Files:**
- Create: `app/services/profile_generation.py`
- Modify: `app/services/settings.py` si hace falta exponer paths existentes.
- Test: `tests/test_profile_generation_service.py`

**Step 1: Test principal**

Debe crear un repo fake local, llamar el servicio y verificar:

- `repo_evidence.jsonl` contiene líneas nuevas;
- `technical_experience.json` existe;
- la respuesta resume repos y evidence count.

**Step 2: Implementar servicio**

```python
@dataclass
class ProfileGenerationService:
    settings: JobMatchingSettings

    async def generate_profile(self, request: ProfileGenerateRequest) -> ProfileGenerateResponse:
        ...
```

Responsabilidades:

- resolver fuentes;
- analizar cada repo;
- escribir evidencia;
- regenerar profile JSON;
- loggear boundaries sin contenido sensible;
- devolver resumen.

**Step 3: Política append/replace**

Para v1 usar `append_evidence=True` por defecto.

Si `append_evidence=False`, sobrescribir `repo_evidence.jsonl`.

Nota: append puede duplicar evidencia si se corre varias veces. Para v1 aceptable, pero mejor agregar dedupe simple por `(repo, signal, paths)`.

**Step 4: Verificar**

Run:

```bash
uv run pytest tests/test_profile_generation_service.py -q
```

Expected: pass.

---

## Task 5: Agregar endpoint API JSON

**Objective:** Exponer generación desde `/api/profile/generate`.

**Files:**
- Modify: `app/routes/api.py`
- Create/Modify: `app/schemas/profile_generation.py`
- Test: `tests/test_api_and_web.py`

**Step 1: Test API**

Agregar test con override del servicio o repo fake:

```python
def test_generate_profile_api_from_local_repo(tmp_path):
    ...
    response = TestClient(app).post(
        "/api/profile/generate",
        json={"local_repo_paths": [str(repo)], "public_repo_urls": []},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
```

**Step 2: Implementar route**

```python
@router.post("/profile/generate", response_model=ProfileGenerateResponse)
async def generate_profile(payload: ProfileGenerateRequest) -> ProfileGenerateResponse:
    service = build_profile_generation_service_from_env()
    return await service.generate_profile(payload)
```

**Step 3: Logs**

Loggear:

- número de URLs;
- número de paths locales;
- evidence rows;
- paths de outputs.

No loggear contenido de código ni secrets.

**Step 4: Verificar**

Run:

```bash
uv run pytest tests/test_api_and_web.py -q
```

Expected: pass.

---

## Task 6: Agregar endpoint HTMX web

**Objective:** Permitir submit desde el formulario de Technical profile.

**Files:**
- Modify: `app/routes/web.py`
- Create: `app/templates/partials/profile_generation.html`
- Test: `tests/test_api_and_web.py`

**Step 1: Test HTMX**

```python
def test_generate_profile_htmx_form_from_local_repo(tmp_path):
    response = TestClient(app).post(
        "/ui/profile/generate",
        data={"local_repo_paths": str(repo), "public_repo_urls": ""},
    )
    assert response.status_code == 200
    assert "Profile generated" in response.text
```

**Step 2: Route web**

`POST /ui/profile/generate` debe aceptar `Form(default="")` para ambos textareas.

**Step 3: Partial HTML**

`app/templates/partials/profile_generation.html` debe mostrar:

- estado general;
- número de repos;
- evidencia escrita;
- path del JSON generado;
- path del JSONL;
- warnings por repo.

**Step 4: Verificar**

Run:

```bash
uv run pytest tests/test_api_and_web.py::test_generate_profile_htmx_form_from_local_repo -q
```

Expected: pass.

---

## Task 7: Agregar formulario en Technical profile

**Objective:** Mostrar el botón “Generar perfil” en la UI actual.

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/styles.css` si hace falta.
- Test: `tests/test_api_and_web.py`

**Step 1: Agregar HTML en sección `#profile`**

Agregar debajo de los profile files:

```html
<section class="profile-generator">
  <h3>Generar perfil desde repos</h3>
  <p class="muted">Agrega URLs públicas o rutas locales. Las rutas locales permiten analizar repos privados sin subirlos.</p>
  <form hx-post="/ui/profile/generate" hx-target="#results" hx-swap="innerHTML">
    <label>URLs de repos públicos, una por línea
      <textarea name="public_repo_urls" rows="4" placeholder="https://github.com/user/repo"></textarea>
    </label>
    <label>Rutas locales de repos, una por línea
      <textarea name="local_repo_paths" rows="4" placeholder="/home/erickesc/repos/private-repo"></textarea>
    </label>
    <label class="checkbox-row">
      <input type="checkbox" name="append_evidence" value="true" checked />
      Agregar evidencia al archivo existente
    </label>
    <button type="submit">Generar perfil</button>
  </form>
</section>
```

**Step 2: Actualizar test home**

En `test_home_page_and_htmx_upload`, assert:

```python
assert "Generar perfil" in home.text
assert "Rutas locales" in home.text
```

**Step 3: Verificar**

Run:

```bash
uv run pytest tests/test_api_and_web.py::test_home_page_and_htmx_upload -q
```

Expected: pass.

---

## Task 8: Documentar el flujo

**Objective:** Que quede claro cómo usar la funcionalidad y sus límites.

**Files:**
- Modify: `README.md`
- Modify: `docs/canonical_technical_profile.md`

**Step 1: README**

Agregar sección breve:

```markdown
### Generate the technical profile from repos

From the web UI, use Technical profile -> Generar perfil.
You can provide public HTTPS Git repository URLs or local repository paths.
Local paths are useful for private repos because the app analyzes them locally.
The generator updates:

- `items/profile/repo_evidence.jsonl`
- `items/profile/technical_experience.json`

Review the generated profile before using it for CV generation or job matching.
```

**Step 2: Docs**

En `docs/canonical_technical_profile.md`, agregar que el botón es un helper heurístico y que el usuario debe revisar summaries/capabilities.

**Step 3: Verificar docs no rompen tests**

Run:

```bash
uv run pytest -q
```

Expected: all pass.

---

## Task 9: QA manual end-to-end

**Objective:** Probar el flujo real en servidor local.

**Files:**
- No code changes unless bugs appear.

**Step 1: Run server**

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8020
```

**Step 2: Open UI**

Go to:

```text
http://127.0.0.1:8020
```

**Step 3: Test local path**

Use:

```text
/home/erickesc/repos/job-market-intelligence
```

Click “Generar perfil”.

Expected:

- Response partial appears in `#results`.
- Shows at least one repo analyzed.
- Shows evidence rows written.
- `items/profile/technical_experience.json` updated.

**Step 4: Test API directly**

```bash
curl -X POST http://127.0.0.1:8020/api/profile/generate \
  -H 'Content-Type: application/json' \
  -d '{"local_repo_paths":["/home/erickesc/repos/job-market-intelligence"],"public_repo_urls":[],"append_evidence":true}'
```

Expected: JSON response with `status: completed`.

**Step 5: Validate generated files**

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

Expected: `ok`.

---

## Risks / Pitfalls

1. Inflar el perfil con señales débiles.
   - Mitigación: heurísticas conservadoras + confidence `medium`/`low`.

2. Duplicar evidencia cada vez que se presiona el botón.
   - Mitigación: dedupe por `(repo, signal, sorted(paths))` antes de escribir.

3. Clonar URLs maliciosas o lentas.
   - Mitigación: solo `https://`, `--depth 1`, timeout razonable, no ejecutar código.

4. Exponer información privada en logs.
   - Mitigación: loggear solo counts, paths de outputs y nombres de fuente; no contenido.

5. Sobrescribir perfil humano curado.
   - Mitigación: v1 solo actualiza JSONL + JSON; no tocar Markdown humano automáticamente.

6. Confundir “generar perfil” con “generar CV”.
   - Mitigación: copy claro en UI: esto actualiza evidencia/capacidades, no produce CV final.

---

## Orden recomendado de implementación

1. Refactor del generador existente a servicio reusable.
2. Analizador de repos locales con tests.
3. Resolver URLs públicas vía clone temporal.
4. Servicio orquestador.
5. API JSON.
6. HTMX endpoint + partial.
7. Formulario en `Technical profile`.
8. Docs.
9. QA end-to-end.

---

## Definition of Done

- `uv run pytest -q` pasa completo.
- Se puede abrir `/` y ver el botón “Generar perfil”.
- Se puede enviar una ruta local de repo y obtener resumen en la UI.
- Se puede llamar `/api/profile/generate` con JSON.
- `items/profile/repo_evidence.jsonl` sigue siendo JSONL válido.
- `items/profile/technical_experience.json` sigue siendo JSON válido.
- No se ejecuta código de repos analizados.
- No se toca `technical_experience.md` automáticamente.
