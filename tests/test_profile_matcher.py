from __future__ import annotations

import json
from pathlib import Path

from app.services.job_file_parser import parse_job_file
from app.services.profile_matcher import load_profile, rank_matches, score_job

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "items/profile/technical_experience.json"
TAXONOMY = ROOT / "items/profile/skill_taxonomy.yaml"


def _job(title: str, description: str):
    jobs, _ = parse_job_file(json.dumps({"title": title, "company": "Acme", "description": description}).encode(), "job.jsonl")
    return jobs[0]


def test_load_profile_uses_yaml_taxonomy_and_aliases():
    profile = load_profile(PROFILE, TAXONOMY)
    job = _job("API Engineer", "Build restful services with Python")
    result = score_job(job, profile)
    assert "REST APIs" in result.matched_skills
    assert "Python" in result.matched_skills


def test_python_fastapi_aws_job_scores_high():
    profile = load_profile(PROFILE, TAXONOMY)
    job = _job("Backend Python Engineer", "Build Python FastAPI REST APIs with AWS Lambda, S3, SQLite and automation workflows.")
    result = score_job(job, profile)
    assert result.fit_score >= 0.5
    assert result.fit_level in {"good", "strong"}
    assert {"Python", "FastAPI", "Lambda"}.issubset(set(result.matched_skills))


def test_frontend_only_job_stays_below_threshold():
    profile = load_profile(PROFILE, TAXONOMY)
    job = _job("Frontend React Developer", "React CSS mobile UI design and frontend-only components.")
    result = score_job(job, profile)
    assert result.fit_score < 0.42
    assert rank_matches([result], min_score=0.42, max_matches=4) == []
