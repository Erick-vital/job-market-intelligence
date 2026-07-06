---
name: technical-profile-evidence
description: Use when updating a canonical technical profile from repos, CVs, job posts, or work-history notes. Extract general capabilities and evidence without turning the profile into repo documentation.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [technical-profile, cv, job-matching, evidence, automation-api]
    related_skills: [automation-api-development]
---

# Technical Profile Evidence

## Overview

Use this skill to update a canonical technical profile for `job-market-intelligence`.

The profile is a capabilities/evidence layer for CV tailoring, job matching, interview prep and skill-gap analysis. It is not documentation for each repo and not a feature inventory.

Primary files:

- Human profile: `./items/profile/technical_experience.md`
- Machine-readable profile: `./items/profile/technical_experience.json`
- Granular evidence: `./items/profile/repo_evidence.jsonl`
- Skill taxonomy: `./items/profile/skill_taxonomy.yaml`
- Process documentation: `./documentation/perfil_tecnico_canonico.md`

## When to Use

Use when:

- the user asks to add a repo to his technical profile.
- the user asks to update the profile with new work experience.
- A job post reveals a gap and you need to check whether the user already has evidence.
- A CV-generation or job-matching flow needs better profile data.
- You need to decide whether a skill is repo-evidenced or only declared in the base CV.

Do not use for:

- Documenting endpoint behavior.
- Writing a README.
- Summarizing every script in a repo.
- Generating a final CV directly.

## Core Principle

Translate concrete repo evidence into general capabilities.

Bad profile entry:

- "Built a external provider integration endpoint."

Better capability:

- "Integrated external providers into testable Python backend services."
- "Processed uploaded files through backend automation workflows."
- "Persisted automation outputs and metadata for later retrieval."

Bad profile entry:

- "Created a LinkedIn post image flow."

Better capability:

- "Built recurring content automation pipelines with queue workers and inspectable artifacts."

## Evidence Types

Use these labels consistently:

- `repo-evidenced`: direct code, tests or docs in a repo.
- `declared-in-base-cv`: appears in `./items/CVs/base_cv.md` but was not verified in repos yet.
- `declared-professional-experience`: the user stated it or it comes from work history, but repo evidence is not available.
- `negative_signal`: looked for evidence and did not find it.

## Confidence Levels

- `high`: code + tests or strong docs exist.
- `medium_high`: real component exists but scope is limited.
- `medium`: partial or indirect evidence.
- `low`: only a mention, convention or weak signal.
- `medium_until_repo_evidence_added`: useful for declared CV experience that needs repo support.

## Updating From a Repo

1. Read repo instructions first if present: `AGENTS.md`, `README.md`, docs.
   Completion: you understand what kind of project it is and any safety rules.

2. Inspect tracked files, not random generated artifacts.
   Recommended command:
   `git -C /path/to/repo ls-files`
   Completion: you have a file list and know the major directories/configs.

3. Identify capability signals, not features.
   Look for:
   - languages and frameworks;
   - backend/API structure;
   - tests;
   - provider integrations;
   - agents/LLMs;
   - pipelines/stages;
   - queues/workers;
   - persistence/indexing;
   - Docker/IaC/CI-CD/cloud configs;
   - runbooks/operation docs.
   Completion: each signal maps to a general capability.

4. Add granular evidence to `repo_evidence.jsonl`.
   Completion: every new JSONL line is valid JSON and includes paths.

5. Decide whether the new data warrants profile changes.
   It is valid to make a tiny update, only add JSONL evidence, or make no profile change when the repo mostly repeats capabilities already covered. Do not force large edits just because new data was provided.
   Completion: you can state whether the repo changed the capability profile, only reinforced existing evidence, or added no meaningful signal.

6. Update `technical_experience.json` only when:
   - a new capability appears;
   - confidence changes;
   - skills list changes materially;
   - job-matching guidance changes.
   Completion: JSON validates.

7. Update `technical_experience.md` only when the narrative changes.
   Completion: Markdown remains compact and high-level.

## Capability Shape

Use this shape in `technical_experience.json`:

```json
{
  "id": "backend_python_api_design",
  "name": "Backend Python and API design",
  "level": "strong",
  "confidence": "high",
  "evidence_type": "repo-evidenced",
  "summary": "Creates Python backend APIs and internal services...",
  "skills": ["Python", "FastAPI"],
  "evidence_refs": ["/path/to/repo"],
  "cv_phrases": ["Built Python/FastAPI backend services..."]
}
```

## JSONL Evidence Shape

Use one line per signal:

```json
{"repo":"/path/to/repo","signal":"fastapi_project","paths":["app/routes","app/services"],"capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high","notes":"FastAPI app with route/service separation."}
```

Rules:

- `paths` must be real relative or absolute paths seen in the repo.
- `capabilities` should reference capability IDs in `technical_experience.json` when possible.
- `notes` should explain why this is evidence, not what every feature does.
- Keep feature-level detail in `repo_evidence.jsonl`, not in the Markdown.

## CV/Job Matching Rules

When the profile is used for matching:

1. Prefer `repo-evidenced` capabilities.
2. Use `declared-in-base-cv` skills, but do not invent details.
3. If a job requires a skill with only weak evidence, mark it as a gap or lower-confidence match.
4. If a job post reveals a likely skill not in the profile, search repos before adding it.
5. Do not update the profile just because a job post mentions a skill; update only if the user has evidence/experience.

## Common Pitfalls

1. Turning the profile into repo documentation.
   Fix: ask "what general capability does this demonstrate?"

2. Overfitting to endpoint names.
   Fix: convert endpoint functionality into backend patterns.

3. Mixing declared experience and repo evidence.
   Fix: always set `evidence_type`.

4. Inflating agent experience.
   Fix: `AGENTS.md` alone is low/medium evidence; routers, tools, telemetry, skills and running flows are stronger.

5. Adding too many capabilities.
   Fix: if it is only one repo feature, add JSONL evidence only.

6. Forcing large updates for every new repo.
   Fix: if the repo only reinforces existing capabilities, make a small JSONL-only update or no profile update.

7. Forgetting negative evidence.
   Fix: if you looked for IaC/Docker/CI-CD and found none, record a `negative_signal` if relevant.

## Verification Checklist

- [ ] `technical_experience.md` is high-level and not endpoint documentation.
- [ ] `technical_experience.json` parses as JSON.
- [ ] `repo_evidence.jsonl` parses line by line.
- [ ] New evidence has real paths.
- [ ] Capabilities have `evidence_type` and `confidence`.
- [ ] Declared CV experience is not treated as repo-evidenced.
- [ ] Gaps are explicit when important.
- [ ] Process documentation still matches the files.

## Validation Command

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
