from __future__ import annotations

import json
from pathlib import Path

from app.schemas.profile_generation import ProfileGenerateRequest
from app.services.profile_evidence import analyze_repo_for_evidence
from app.services.profile_generation import ProfileGenerationService
from app.services.settings import JobMatchingSettings
from app.services.technical_profile_generation import generate_technical_profile


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
    assert "FastAPI" in data["capabilities"][0]["skills"]


def test_analyze_repo_detects_fastapi_tests_and_browser_extension(tmp_path):
    repo = tmp_path / "demo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "browser_extension").mkdir()
    (repo / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi", "pytest"]\n', encoding="utf-8")
    (repo / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo / "tests" / "test_api.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (repo / "browser_extension" / "manifest.json").write_text('{"manifest_version": 3}', encoding="utf-8")

    rows = analyze_repo_for_evidence(repo_path=repo, repo_label=str(repo))

    signals = {row.signal for row in rows}
    assert "fastapi_project" in signals
    assert "automated_testing" in signals
    assert "browser_extension" in signals


def test_profile_generation_service_writes_evidence_and_profile(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi", "pytest"]\n', encoding="utf-8")
    (repo / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo / "tests" / "test_api.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    profile_path = tmp_path / "items" / "profile" / "technical_experience.json"
    settings = JobMatchingSettings(
        data_dir=tmp_path / "data",
        jobs_items_dir=tmp_path / "items" / "jobs",
        profile_json_path=profile_path,
        skill_taxonomy_path=tmp_path / "items" / "profile" / "skill_taxonomy.yaml",
    )

    result = ProfileGenerationService(settings=settings).generate_profile(
        ProfileGenerateRequest(local_repo_paths=[str(repo)], public_repo_urls=[])
    )

    assert result.status == "completed"
    assert result.repos_analyzed == 1
    assert result.evidence_rows_written >= 2
    assert Path(result.evidence_path).exists()
    assert Path(result.technical_profile_path).exists()
    data = json.loads(Path(result.technical_profile_path).read_text(encoding="utf-8"))
    capability_ids = {cap["id"] for cap in data["capabilities"]}
    assert "backend_python_api_design" in capability_ids


def test_profile_generation_request_splits_textarea_lines():
    request = ProfileGenerateRequest(
        public_repo_urls="https://github.com/a/b\n\nhttps://github.com/c/d",
        local_repo_paths="/tmp/one\n/tmp/two",
    )

    assert request.public_repo_urls == ["https://github.com/a/b", "https://github.com/c/d"]
    assert request.local_repo_paths == ["/tmp/one", "/tmp/two"]
