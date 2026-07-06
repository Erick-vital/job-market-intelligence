# Job Market Intelligence

Open-source local app for turning job postings into market intelligence and personalized opportunity scoring.

The promise:

> Upload a CSV/JSONL of job postings, define a canonical technical profile, and get fit scores, demanded skills, gaps, company signals, and an exportable report.

This repo is intentionally local-first. It is not a SaaS, does not scrape LinkedIn automatically, and does not require private credentials.

## What is included in the MVP

- FastAPI backend
- Jinja2 + HTMX web UI
- SQLite persistence
- CSV / JSONL job import
- Deterministic job/profile scoring
- Batch summaries and Markdown reports
- Company signals
- Sample canonical technical profile
- LinkedIn Jobs capture browser extension
- Technical profile generator script

## What is intentionally not included

- CRM
- Transcription endpoints
- Private provider integrations
- CV tailoring private flows
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

## Try the sample data

From the web UI, upload:

```text
examples/sample_jobs.csv
```

Or call the API directly:

```bash
curl -X POST http://127.0.0.1:8020/api/jobs/import   -F "file=@examples/sample_jobs.csv"   -F "max_matches=8"
```

The app writes local artifacts under:

```text
data/job_market_intelligence.sqlite
items/jobs/
```

These are ignored by git.

## Canonical technical profile

The matcher reads:

```text
items/profile/technical_experience.json
items/profile/skill_taxonomy.yaml
```

The included profile is sample data. Replace it with your own profile before using the app seriously.

### Generate a starter profile from evidence

Create or edit:

```text
items/profile/repo_evidence.jsonl
```

Each line is JSON, for example:

```json
{"repo":"my-api","signal":"fastapi_project","paths":["app/routes","app/services"],"capabilities":["backend_python_api_design"],"skills":["Python","FastAPI","SQLite"],"confidence":"high","notes":"FastAPI app with tests and persistence."}
```

Then run:

```bash
uv run python scripts/generate_technical_experience.py   --evidence items/profile/repo_evidence.jsonl   --out items/profile/technical_experience.json
```

Read the process docs:

- `docs/canonical_technical_profile.md`
- `docs/technical-profile-evidence-skill.md`

The copied skill explains how to translate concrete repo evidence into general capabilities without turning the profile into repo documentation.

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
scripts/
tests/
```

## Product direction

MVP flow:

```text
Profile → Upload jobs → Matching → Dashboard → Markdown report
```

Possible next features:

- editable profile form
- column mapping UI for arbitrary CSV files
- richer market report
- export report from the browser
- lightweight content ideas based on aggregate job signals
- optional LLM-assisted reranking, disabled by default

## License

MIT
