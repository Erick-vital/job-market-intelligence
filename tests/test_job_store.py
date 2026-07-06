from __future__ import annotations

import sqlite3

from app.services.job_file_parser import parse_job_file
from app.services.job_store import JobStore
from app.services.profile_matcher import JobMatchResult


def _job(source_job_id="123", description="Python FastAPI"):
    jobs, _ = parse_job_file(
        (
            "source_job_id,source_url,title,company,location,description\n"
            f"{source_job_id},https://www.linkedin.com/jobs/view/{source_job_id}/,Backend Engineer,Acme,Remote,{description}\n"
        ).encode(),
        "jobs.csv",
    )
    return jobs[0]


def _match(job, score=0.72):
    return JobMatchResult(
        job=job,
        fit_score=score,
        fit_level="strong",
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        reasons=["Menciona Python/FastAPI."],
        score_breakdown={"skill_overlap": 0.8},
    )


def test_store_inserts_job_and_item_files(tmp_path):
    store = JobStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    job = _job()
    result = store.save_batch(source_filename="jobs.csv", matches=[_match(job)], skipped_invalid=0, selected_matches=[])

    assert result.processed == 1
    assert result.inserted == 1
    assert result.updated_duplicates == 0
    saved = result.saved_jobs[0]
    assert saved.json_path.exists()
    assert saved.md_path.exists()
    assert saved.match_path.exists()
    assert (tmp_path / "data" / "job_market_intelligence.sqlite").exists()

    with sqlite3.connect(tmp_path / "data" / "job_market_intelligence.sqlite") as conn:
        count = conn.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]
    assert count == 1


def test_store_updates_duplicate_by_source_job_id(tmp_path):
    store = JobStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    first = _job(source_job_id="123", description="Python")
    second = _job(source_job_id="123", description="Python FastAPI AWS")

    store.save_batch(source_filename="first.csv", matches=[_match(first, 0.5)], skipped_invalid=0, selected_matches=[])
    result = store.save_batch(source_filename="second.csv", matches=[_match(second, 0.8)], skipped_invalid=0, selected_matches=[])

    assert result.inserted == 0
    assert result.updated_duplicates == 1
    with sqlite3.connect(tmp_path / "data" / "job_market_intelligence.sqlite") as conn:
        rows = conn.execute("SELECT COUNT(*), MAX(fit_score) FROM job_postings").fetchone()
    assert rows == (1, 0.8)


def test_store_creates_batch_summary_and_matches(tmp_path):
    store = JobStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    job = _job()
    match = _match(job)
    match.rank = 1

    result = store.save_batch(source_filename="jobs.csv", matches=[match], skipped_invalid=2, selected_matches=[match])

    assert result.batch_id.startswith("jobbatch_")
    assert result.summary_path.exists()
    assert result.matches_path.exists()
    assert result.summary["skipped_invalid"] == 2
    assert result.summary["matches_count"] == 1
