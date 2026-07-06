from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import api as api_route
from app.routes import web as web_route
from app.services.job_matching import JobMatchingService
from app.services.settings import JobMatchingSettings

ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path):
    settings = JobMatchingSettings(
        data_dir=tmp_path / "data",
        jobs_items_dir=tmp_path / "items",
        profile_json_path=ROOT / "items/profile/technical_experience.json",
        skill_taxonomy_path=ROOT / "items/profile/skill_taxonomy.yaml",
        min_score=0.42,
    )
    return JobMatchingService(settings=settings)


def test_import_jobs_api_persists_and_returns_report(tmp_path):
    app.dependency_overrides[api_route.get_job_matching_service] = lambda: _service(tmp_path)
    csv_text = (
        "source_job_id,title,company,location,description\n"
        "1,Backend Python Engineer,Acme,Remote,Python FastAPI REST APIs AWS Lambda SQLite\n"
        "2,Frontend React Developer,WebCo,Remote,React CSS mobile UI\n"
    )
    response = TestClient(app).post("/api/jobs/import", files={"file": ("jobs.csv", csv_text.encode(), "text/csv")})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["processed"] == 2
    assert body["inserted"] == 2
    assert body["report"]["jobs_analyzed"] == 2
    assert Path(body["paths"]["report_markdown"]).exists()


def test_home_page_and_htmx_upload(tmp_path):
    app.dependency_overrides[web_route.get_job_matching_service] = lambda: _service(tmp_path)
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert "Turn job postings into market intelligence" in home.text
    csv_text = (
        "source_job_id,title,company,description\n"
        "1,Backend Python Engineer,Acme,Python FastAPI REST APIs AWS Lambda SQLite\n"
    )
    response = client.post("/ui/jobs/import", files={"file": ("jobs.csv", csv_text.encode(), "text/csv")})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Analysis complete" in response.text
    assert "Backend Python Engineer" in response.text
