# Job Market Intelligence

Open-source local app for turning job postings into market intelligence, personalized opportunity scoring, and targeted application material.

The promise:

> Define a canonical technical profile once, then use it to evaluate job postings, understand market demand, detect skill gaps, and generate profile-backed CV drafts.

This repo is intentionally local-first. It is not a SaaS, does not scrape LinkedIn automatically, and does not require private credentials.

## Core concept: the canonical technical profile

The technical profile is the center of the project. Matching and CV generation both read the same profile files:

```text
items/profile/technical_experience.json
items/profile/technical_experience.md
items/profile/skill_taxonomy.yaml
items/profile/repo_evidence.jsonl
```

Think of the profile as a reusable evidence-backed representation of your capabilities:

```text
Repo evidence → Canonical technical profile → Job matching → Market report / CV draft
```

The included profile is sample data. Replace it with your own profile before using the app seriously.

Full process documentation:

- `docs/canonical_technical_profile.md`
- `docs/technical-profile-evidence-skill.md`

## What is included in the MVP

- FastAPI backend
- Jinja2 + HTMX web UI
- SQLite persistence
- CSV / JSONL job import
- Manual one-by-one job matching
- Deterministic job/profile scoring
- Batch summaries and Markdown reports
- Company signals
- Sample canonical technical profile
- Technical profile generator script
- Model-powered targeted CV draft generation in Markdown
- LinkedIn Jobs capture browser extension

## What is intentionally not included

- CRM
- Transcription endpoints
- Private provider integrations
- Automatic LinkedIn scraping
- Admin/systemd endpoints
- Personal data, private SQLite files, real job history, or private artifacts

## Quick start

```bash
cd job-market-intelligence
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8020
```

Open:

```text
http://127.0.0.1:8020
```

Health check:

```bash
curl http://127.0.0.1:8020/health
```

Run tests:

```bash
uv run pytest -q
```

## Main workflows

### 1. Batch job analysis from CSV/JSONL

From the web UI, upload:

```text
examples/sample_jobs.csv
```

Or call the API directly:

```bash
curl -X POST http://127.0.0.1:8020/api/jobs/import \
  -F "file=@examples/sample_jobs.csv" \
  -F "max_matches=8"
```

The app writes local artifacts under:

```text
data/job_market_intelligence.sqlite
items/jobs/
```

These generated runtime artifacts are ignored by git.

### 2. Manual one-by-one match

Use the `Manual match` section in the web UI when you want to check a single role without preparing a CSV.

API example:

```bash
curl -X POST http://127.0.0.1:8020/api/jobs/match \
  -H 'Content-Type: application/json' \
  -d '{
    "company": "Acme",
    "title": "Backend Python Engineer",
    "description": "Build Python FastAPI REST APIs with AWS Lambda and SQLite.",
    "location": "Remote Mexico"
  }'
```

The response returns one deterministic match with:

- fit score and fit level;
- matched skills;
- missing skills / cautions;
- plain-language reasons.

### 3. Generate a targeted CV draft

Use the `Generate CV` section in the web UI to paste a target job and create a model-written Markdown CV draft.

Configure your local LLM API key in a `.env` file at the repo root:

```bash
JMI_LLM_PROVIDER=anthropic
JMI_ANTHROPIC_API_KEY=sk-ant-...
# Optional: leave unset to use the provider default, or use a Claude Code label/API id.
# Supported Anthropic aliases: Sonnet-5, Fable, Opus, Haiku.
JMI_LLM_MODEL=Sonnet-5
# Optional; defaults to https://api.anthropic.com for Anthropic.
JMI_LLM_BASE_URL=
```

The app reads those values server-side and does not require them in each request. The model receives:

- the target job description;
- the canonical technical profile;
- deterministic match context;
- matched skills, gaps, and profile-backed `cv_phrases`.

Default provider settings:

```text
provider: openai_compatible
model: gpt-4o-mini
base_url: https://api.openai.com/v1

provider: anthropic
model: claude-sonnet-5
base_url: https://api.anthropic.com
```

You can also set those defaults globally with `JMI_LLM_PROVIDER`, `JMI_LLM_MODEL`, and `JMI_LLM_BASE_URL`. Request-level `provider`, `model`, and `base_url` values still override them. For Anthropic, friendly labels from Claude Code are normalized before calling the API: `Sonnet-5` -> `claude-sonnet-5`, `Fable` -> `claude-fable-5`, `Opus` -> `claude-opus-4-8`, and `Haiku` -> `claude-haiku-4-5-20251001`.

```bash
curl -X POST http://127.0.0.1:8020/api/cv/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "company": "Acme",
    "title": "Backend Python Engineer",
    "description": "Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
    "language": "en",
    "provider": "openai_compatible",
    "model": "gpt-4o-mini"
  }'
```

Generated CV drafts are saved under:

```text
items/cvs/
```

The CV generator is intentionally evidence-oriented: the prompt instructs the model to use only capabilities, skills, and CV phrases from the canonical profile and to avoid inventing employers, degrees, certifications, metrics, or personal data.

## Create or update your technical profile

Create or edit evidence lines in:

```text
items/profile/repo_evidence.jsonl
```

Each line is JSON, for example:

```json
{"repo":"my-api","signal":"fastapi_project","paths":["app/routes","app/services"],"capabilities":["backend_python_api_design"],"skills":["Python","FastAPI","SQLite"],"confidence":"high","notes":"FastAPI app with tests and persistence."}
```

Then generate the machine-readable profile:

```bash
uv run python scripts/generate_technical_experience.py \
  --evidence items/profile/repo_evidence.jsonl \
  --out items/profile/technical_experience.json
```

Recommended profile workflow:

1. Add repo-backed evidence to `repo_evidence.jsonl`.
2. Generate `technical_experience.json`.
3. Review and edit `technical_experience.md` for the human-readable version.
4. Update `skill_taxonomy.yaml` when a relevant skill should be detected by the matcher.
5. Re-run manual or batch matching to validate the profile.

## LinkedIn Jobs browser extension

The extension is in:

```text
browser_extensions/linkedin_jobs_capture
```

Install locally:

1. Open `chrome://extensions/`
2. Enable Developer Mode
3. Click `Load unpacked`
4. Select `browser_extensions/linkedin_jobs_capture`
5. Open LinkedIn Jobs manually
6. Save visible jobs during a session
7. Export as CSV or JSONL from the popup
8. Upload the export into this app

More details:

- `docs/linkedin_jobs_browser_extension.md`

Important: the extension does not make network calls, does not auto-scroll, and does not automate LinkedIn interactions. It is only a manual capture helper.

## Configuration

Optional environment variables:

```bash
JMI_DATA_DIR=./data
JMI_JOBS_ITEMS_DIR=./items/jobs
JMI_PROFILE_JSON_PATH=./items/profile/technical_experience.json
JMI_SKILL_TAXONOMY_PATH=./items/profile/skill_taxonomy.yaml
JMI_MIN_SCORE=0.42
JMI_LLM_API_KEY=sk-...
```

## Project layout

```text
app/
  main.py
  routes/
  services/
  schemas/
  models/
  templates/
  static/
browser_extensions/linkedin_jobs_capture/
docs/
examples/
items/profile/
items/cvs/          # generated locally, ignored by git
scripts/
tests/
```

## Product direction

Current flow:

```text
Profile → Manual or batch job input → Matching → Report / CV draft
```

Possible next features:

- editable profile form
- column mapping UI for arbitrary CSV files
- profile health dashboard
- richer market report
- report browser for historical batches
- company signals UI
- export report from the browser
- lightweight content ideas based on aggregate job signals
- optional LLM-assisted reranking, disabled by default

## License

MIT
