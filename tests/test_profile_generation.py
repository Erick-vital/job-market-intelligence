from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.schemas.profile_generation import ProfileGenerateRequest
from app.services.profile_evidence import analyze_repo_for_evidence
from app.services.profile_generation import ProfileGenerationService
from app.services.settings import JobMatchingSettings
from app.services.technical_profile_generation import LlmGenerationResult, generate_technical_profile, generate_technical_profile_with_skill


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
    taxonomy = output.parent / "skill_taxonomy.yaml"
    assert taxonomy.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["capabilities"][0]["id"] == "backend_python_api_design"
    assert "FastAPI" in data["capabilities"][0]["skills"]
    assert "core" in taxonomy.read_text(encoding="utf-8")


class FakeProfileLlmService:
    def __init__(self):
        self.calls: list[dict[str, str]] = []

    async def generate_text(self, *, system_prompt: str, prompt: str, provider: str | None = None, model: str | None = None, base_url: str | None = None, api_key: str | None = None, temperature: float = 0.2, max_tokens: int | None = None) -> LlmGenerationResult:
        self.calls.append({"system_prompt": system_prompt, "prompt": prompt})
        return LlmGenerationResult(
            text=json.dumps(
                {
                    "version": "generated.v1",
                    "purpose": "Canonical technical profile generated with the documented skill.",
                    "supporting_skill": "docs/technical-profile-evidence-skill.md",
                    "capabilities": [
                        {
                            "id": "backend_python_api_design",
                            "name": "Backend Python API design",
                            "level": "strong",
                            "confidence": "high",
                            "evidence_type": "repo-evidenced",
                            "summary": "Creates testable Python/FastAPI backend APIs from repo evidence.",
                            "skills": ["Python", "FastAPI"],
                            "evidence_refs": ["demo"],
                            "cv_phrases": ["Built testable Python/FastAPI backend APIs."],
                        }
                    ],
                    "job_matching_guidance": {"prioritize": ["repo-evidenced capabilities"], "deprioritize": []},
                    "update_rules": ["Use documented skill rules."],
                }
            ),
            provider="fake",
            model="fake-model",
        )


def test_generate_technical_profile_with_skill_uses_llm_prompt_and_skill_doc(tmp_path, caplog):
    evidence = tmp_path / "repo_evidence.jsonl"
    output = tmp_path / "technical_experience.json"
    skill_doc = tmp_path / "technical-profile-evidence-skill.md"
    evidence.write_text(
        '{"repo":"demo","signal":"fastapi_project","capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high","notes":"FastAPI app."}\n',
        encoding="utf-8",
    )
    skill_doc.write_text("# Technical Profile Evidence\nTranslate concrete repo evidence into general capabilities.", encoding="utf-8")
    fake_llm = FakeProfileLlmService()

    caplog.set_level("INFO")
    result = asyncio.run(
        generate_technical_profile_with_skill(
            evidence_path=evidence,
            output_path=output,
            skill_path=skill_doc,
            llm_service=fake_llm,
        )
    )

    assert result.output_path == output
    assert result.generation_mode == "llm"
    assert result.llm_provider == "fake"
    assert result.llm_model == "fake-model"
    assert fake_llm.calls
    assert "Translate concrete repo evidence into general capabilities" in fake_llm.calls[0]["prompt"]
    assert "fastapi_project" in fake_llm.calls[0]["prompt"]
    assert any(r.message == "technical profile llm generation completed" for r in caplog.records)
    assert any(getattr(r, "generation_mode", None) == "llm" for r in caplog.records)
    taxonomy = output.parent / "skill_taxonomy.yaml"
    assert taxonomy.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["supporting_skill"] == "docs/technical-profile-evidence-skill.md"
    assert data["capabilities"][0]["summary"] == "Creates testable Python/FastAPI backend APIs from repo evidence."


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


def test_profile_generation_service_writes_evidence_and_profile(tmp_path, caplog):
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

    caplog.set_level("INFO")

    result = asyncio.run(
        ProfileGenerationService(settings=settings, use_llm=False).generate_profile(
            ProfileGenerateRequest(local_repo_paths=[str(repo)], public_repo_urls=[])
        )
    )

    assert result.status == "completed"
    assert result.repos_analyzed == 1
    assert result.evidence_rows_written >= 2
    assert Path(result.evidence_path).exists()
    assert Path(result.technical_profile_path).exists()
    assert Path(result.technical_profile_path).with_name("skill_taxonomy.yaml").exists()
    assert any(r.message == "profile generation completed" for r in caplog.records)
    assert any(getattr(r, "technical_profile_generation_mode", None) == "deterministic" for r in caplog.records)
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
