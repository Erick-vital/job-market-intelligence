from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.models.job_matching import JobPosting
from app.routes import api as api_route
from app.routes import web as web_route
from app.services import llm_generation
from app.services.cv_generation import generate_targeted_cv
from app.services.job_matching import JobMatchingService
from app.services.profile_generation import ProfileGenerationService
from app.services.settings import JobMatchingSettings, get_llm_model

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PROFILE = FIXTURES / "technical_experience.json"
FIXTURE_TAXONOMY = FIXTURES / "skill_taxonomy.yaml"


def _service(tmp_path):
    settings = JobMatchingSettings(
        data_dir=tmp_path / "data",
        jobs_items_dir=tmp_path / "items",
        profile_json_path=FIXTURE_PROFILE,
        skill_taxonomy_path=FIXTURE_TAXONOMY,
        min_score=0.42,
    )
    return JobMatchingService(settings=settings)


def _profile_service(tmp_path):
    settings = JobMatchingSettings(
        data_dir=tmp_path / "data",
        jobs_items_dir=tmp_path / "items" / "jobs",
        profile_json_path=tmp_path / "items" / "profile" / "technical_experience.json",
        skill_taxonomy_path=tmp_path / "items" / "profile" / "skill_taxonomy.yaml",
        min_score=0.42,
    )
    return ProfileGenerationService(settings=settings, use_llm=False)


def _fake_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi", "pytest"]\n', encoding="utf-8")
    (repo / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo / "tests" / "test_api.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return repo


class FakeOpenAiResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("provider error")

    def json(self):
        return self.payload


class FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        return FakeOpenAiResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "# Targeted CV\n\n## Professional Summary\nModel-generated CV for Backend Python Engineer.\n\n## Experience\n- Built Python/FastAPI services with structured schemas, tests, and persistence.\n"
                        }
                    }
                ]
            }
        )


class FakeAnthropicResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("provider error")

    def json(self):
        return self.payload


class FakeAnthropicAsyncClient:
    calls: list[dict] = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        return FakeAnthropicResponse(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "# Targeted CV\n\n## Professional Summary\nAnthropic-generated CV for Backend Python Engineer.\n\n## Experience\n- Built Python/FastAPI services with structured schemas, tests, and persistence.\n",
                    }
                ]
            }
        )


class FallbackAnthropicAsyncClient:
    calls: list[dict] = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        request = httpx.Request("POST", url)
        if json["model"] == "not-a-real-model":
            response = httpx.Response(404, request=request, json={"error": {"message": "model not found"}})
            response.raise_for_status()
        return httpx.Response(
            200,
            request=request,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": "# Targeted CV\n\n## Professional Summary\nFallback Anthropic CV.\n",
                    }
                ]
            },
        )


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
    assert "Manual match" in home.text
    assert "Generate CV" in home.text
    assert "Actualizar perfil" in home.text
    assert "Rutas locales" in home.text
    assert "Perfil" in home.text
    assert "Backend Python API Design" in home.text
    csv_text = (
        "source_job_id,title,company,description\n"
        "1,Backend Python Engineer,Acme,Python FastAPI REST APIs AWS Lambda SQLite\n"
    )
    response = client.post("/ui/jobs/import", files={"file": ("jobs.csv", csv_text.encode(), "text/csv")})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Analysis complete" in response.text


def test_manual_match_api_scores_single_job(tmp_path):
    app.dependency_overrides[api_route.get_job_matching_service] = lambda: _service(tmp_path)
    response = TestClient(app).post(
        "/api/jobs/match",
        json={
            "company": "Acme",
            "title": "Backend Python Engineer",
            "description": "Build Python FastAPI REST APIs with AWS Lambda and SQLite.",
            "location": "Remote Mexico",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["match"]["company"] == "Acme"
    assert body["match"]["title"] == "Backend Python Engineer"
    assert body["match"]["fit_score"] >= 0.42
    assert "Python" in body["match"]["matched_skills"]


def test_manual_match_htmx_form_returns_single_result(tmp_path):
    app.dependency_overrides[web_route.get_job_matching_service] = lambda: _service(tmp_path)
    response = TestClient(app).post(
        "/ui/jobs/match",
        data={
            "company": "Acme",
            "title": "Backend Python Engineer",
            "description": "Build Python FastAPI REST APIs with AWS Lambda and SQLite.",
            "location": "Remote Mexico",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Manual match result" in response.text
    assert "Backend Python Engineer" in response.text
    assert "Python" in response.text


def test_generate_profile_api_from_local_repo(tmp_path):
    repo = _fake_repo(tmp_path)
    app.dependency_overrides[api_route.get_profile_generation_service] = lambda: _profile_service(tmp_path)
    response = TestClient(app).post(
        "/api/profile/generate",
        json={"local_repo_paths": [str(repo)], "public_repo_urls": [], "append_evidence": True},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["repos_analyzed"] == 1
    assert body["evidence_rows_written"] >= 2
    assert Path(body["evidence_path"]).exists()
    assert Path(body["technical_profile_path"]).exists()


def test_generate_profile_htmx_form_from_local_repo(tmp_path):
    repo = _fake_repo(tmp_path)
    app.dependency_overrides[web_route.get_profile_generation_service] = lambda: _profile_service(tmp_path)
    response = TestClient(app).post(
        "/ui/profile/generate",
        data={"local_repo_paths": str(repo), "public_repo_urls": "", "append_evidence": "true"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Perfil actualizado" in response.text
    assert "✓ Perfil actualizado" in response.text
    assert "profile-update-status" in response.text
    assert "fastapi_project" in response.text
    assert "technical_experience.json" in response.text


def test_generate_cv_api_returns_model_markdown_and_saves_file(tmp_path, monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("JMI_LLM_API_KEY", "sk-test-secret")
    app.dependency_overrides[api_route.get_job_matching_service] = lambda: _service(tmp_path)
    response = TestClient(app).post(
        "/api/cv/generate",
        json={
            "company": "Acme",
            "title": "Backend Python Engineer",
            "description": "Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
            "language": "en",
            "provider": "openai_compatible",
            "model": "gpt-test",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert "Model-generated CV" in body["markdown"]
    assert "Built Python/FastAPI services" in body["markdown"]
    assert Path(body["path"]).exists()
    assert body["provider"] == "openai_compatible"
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert FakeAsyncClient.calls[0]["json"]["model"] == "gpt-test"
    assert "sk-test-secret" not in body["markdown"]


def test_generate_cv_api_requires_llm_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("JMI_LLM_API_KEY", raising=False)
    monkeypatch.delenv("JMI_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JMI_ANTHROPIC_API_KEY", raising=False)
    app.dependency_overrides[api_route.get_job_matching_service] = lambda: _service(tmp_path)
    response = TestClient(app).post(
        "/api/cv/generate",
        json={
            "company": "Acme",
            "title": "Backend Python Engineer",
            "description": "Build Python FastAPI REST APIs.",
            "language": "en",
            "provider": "openai_compatible",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "Missing LLM API key" in response.json()["detail"]


def test_generate_targeted_cv_accepts_legacy_openai_api_key_env(tmp_path, monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.delenv("JMI_LLM_API_KEY", raising=False)
    monkeypatch.setenv("JMI_OPENAI_API_KEY", "sk-legacy-secret")
    job = JobPosting(
        company="Acme",
        title="Backend Python Engineer",
        description="Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
        location="Remote",
        source="manual",
        raw={"manual_entry": True},
    )
    generated = asyncio.run(
        generate_targeted_cv(
            profile_json_path=FIXTURE_PROFILE,
            taxonomy_yaml_path=FIXTURE_TAXONOMY,
            output_dir=tmp_path,
            job=job,
            api_key=None,
            provider="openai_compatible",
            language="en",
            model="gpt-test",
            base_url=None,
        )
    )
    assert generated.path.exists()
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer sk-legacy-secret"


def test_generate_targeted_cv_uses_env_model_and_base_url_defaults(tmp_path, monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("JMI_LLM_API_KEY", "sk-test-secret")
    monkeypatch.setenv("JMI_LLM_MODEL", "gpt-env-model")
    monkeypatch.setenv("JMI_LLM_BASE_URL", "https://example-provider.test/v1")
    job = JobPosting(
        company="Acme",
        title="Backend Python Engineer",
        description="Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
        location="Remote",
        source="manual",
        raw={"manual_entry": True},
    )
    generated = asyncio.run(
        generate_targeted_cv(
            profile_json_path=FIXTURE_PROFILE,
            taxonomy_yaml_path=FIXTURE_TAXONOMY,
            output_dir=tmp_path,
            job=job,
            api_key=None,
            provider="openai_compatible",
            language="en",
            model=None,
            base_url=None,
        )
    )
    assert generated.provider == "openai_compatible"
    assert generated.model == "gpt-env-model"
    assert FakeAsyncClient.calls[0]["json"]["model"] == "gpt-env-model"
    assert FakeAsyncClient.calls[0]["url"] == "https://example-provider.test/v1/chat/completions"
    assert Path(generated.path).exists()


def test_anthropic_model_aliases_match_api_ids(monkeypatch):
    monkeypatch.setenv("JMI_LLM_PROVIDER", "anthropic")
    assert get_llm_model("Sonnet-5", provider="anthropic") == "claude-sonnet-5"
    assert get_llm_model("Fable", provider="anthropic") == "claude-fable-5"
    assert get_llm_model("Opus", provider="anthropic") == "claude-opus-4-8"
    assert get_llm_model("Haiku", provider="anthropic") == "claude-haiku-4-5-20251001"


def test_generate_targeted_cv_supports_anthropic_without_base_url(tmp_path, monkeypatch):
    FakeAnthropicAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAnthropicAsyncClient)
    monkeypatch.setenv("JMI_LLM_API_KEY", "sk-ant-test-secret")
    job = JobPosting(
        company="Acme",
        title="Backend Python Engineer",
        description="Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
        location="Remote",
        source="manual",
        raw={"manual_entry": True},
    )
    generated = asyncio.run(
        generate_targeted_cv(
            profile_json_path=FIXTURE_PROFILE,
            taxonomy_yaml_path=FIXTURE_TAXONOMY,
            output_dir=tmp_path,
            job=job,
            api_key=None,
            provider="anthropic",
            language="en",
            model="claude-sonnet-5",
            base_url=None,
        )
    )
    assert generated.provider == "anthropic"
    assert generated.model == "claude-sonnet-5"
    assert FakeAnthropicAsyncClient.calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert FakeAnthropicAsyncClient.calls[0]["headers"]["x-api-key"] == "sk-ant-test-secret"
    assert "Anthropic-generated CV" in Path(generated.path).read_text(encoding="utf-8")


def test_generate_targeted_cv_falls_back_to_default_model_when_requested_alias_fails(tmp_path, monkeypatch):
    FallbackAnthropicAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FallbackAnthropicAsyncClient)
    monkeypatch.setenv("JMI_ANTHROPIC_API_KEY", "sk-ant-test-secret")
    monkeypatch.setenv("JMI_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("JMI_LLM_MODEL", "not-a-real-model")
    job = JobPosting(
        company="Acme",
        title="Backend Python Engineer",
        description="Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
        location="Remote",
        source="manual",
        raw={"manual_entry": True},
    )
    generated = asyncio.run(
        generate_targeted_cv(
            profile_json_path=FIXTURE_PROFILE,
            taxonomy_yaml_path=FIXTURE_TAXONOMY,
            output_dir=tmp_path,
            job=job,
            api_key=None,
            provider=None,
            language="en",
            model=None,
            base_url=None,
        )
    )
    assert generated.provider == "anthropic"
    assert generated.model == "claude-sonnet-5"
    assert len(FallbackAnthropicAsyncClient.calls) == 2
    assert FallbackAnthropicAsyncClient.calls[0]["json"]["model"] == "not-a-real-model"
    assert FallbackAnthropicAsyncClient.calls[1]["json"]["model"] == "claude-sonnet-5"
    assert "Fallback Anthropic CV" in Path(generated.path).read_text(encoding="utf-8")


def test_generate_cv_htmx_form_returns_model_markdown(tmp_path, monkeypatch):
    FakeAnthropicAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAnthropicAsyncClient)
    monkeypatch.setenv("JMI_LLM_API_KEY", "sk-test-secret")
    app.dependency_overrides[web_route.get_job_matching_service] = lambda: _service(tmp_path)
    response = TestClient(app).post(
        "/ui/cv/generate",
        data={
            "company": "Acme",
            "title": "Backend Python Engineer",
            "description": "Build Python FastAPI REST APIs, data pipelines, AWS Lambda, and SQLite automation.",
            "language": "en",
            "provider": "anthropic",
            "model": "claude-sonnet-5",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Generated CV" in response.text
    assert "Anthropic-generated CV" in response.text
    assert "Built Python/FastAPI services" in response.text
