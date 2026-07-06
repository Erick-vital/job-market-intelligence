from __future__ import annotations

import json

import pytest

from app.services.job_file_parser import JobFileParseError, parse_job_file


def test_parse_linkedin_csv_export():
    csv_text = (
        "source,capture_method,saved_at,captured_at,source_job_id,source_url,title,company,location,posted_text,description,page_url,detail_text,card_text\n"
        'linkedin_jobs,browser_extension_visible_detail,2026-07-01T10:00:00Z,2026-07-01T10:00:00Z,5555,https://www.linkedin.com/jobs/view/5555/,Backend Engineer,DataCo,Remoto,hace 2 días,"Python FastAPI AWS",https://www.linkedin.com/jobs/,detail,card\n'
    )

    jobs, skipped = parse_job_file(csv_text.encode("utf-8"), "linkedin_jobs_session.csv")

    assert skipped == 0
    assert len(jobs) == 1
    assert jobs[0].company == "DataCo"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].source_job_id == "5555"
    assert "Python FastAPI AWS" in jobs[0].matching_text()


def test_parse_jsonl_export_skips_invalid_records():
    records = [
        {"title": "SRE", "company": "OpsCo", "description": "AWS Lambda", "source_job_id": "7777"},
        {"title": "", "company": ""},
    ]
    jsonl = "\n".join(json.dumps(record) for record in records) + "\n"

    jobs, skipped = parse_job_file(jsonl.encode("utf-8"), "session.jsonl")

    assert len(jobs) == 1
    assert skipped == 1
    assert jobs[0].title == "SRE"


def test_empty_file_returns_parse_error():
    with pytest.raises(JobFileParseError, match="empty"):
        parse_job_file(b"", "empty.csv")


def test_csv_without_company_title_returns_parse_error():
    with pytest.raises(JobFileParseError, match="company.*title"):
        parse_job_file(b"foo,bar\n1,2\n", "bad.csv")
