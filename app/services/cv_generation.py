from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.job_matching import JobMatchResult, JobPosting
from app.services.llm_generation import LlmGenerationProviderError, LlmGenerationService
from app.services.profile_matcher import load_profile, score_job, searchable
from app.services.profile_taxonomy import unique

logger = logging.getLogger(__name__)


class CvGenerationProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GeneratedCv:
    markdown: str
    path: Path
    matched_capabilities: list[str]
    provider: str = "openai_compatible"
    model: str = ""


def _cv_system_prompt() -> str:
    return (
        "You are an ATS-aware resume writer. Generate concise, truthful, well-structured Markdown CV drafts. "
        "Never invent employers, degrees, certifications, metrics, or personal data."
    )


async def generate_targeted_cv(
    *,
    profile_json_path: Path,
    output_dir: Path,
    job: JobPosting,
    taxonomy_yaml_path: Path | None = None,
    api_key: str | None = None,
    language: str = "en",
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> GeneratedCv:
    profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
    profile_index = load_profile(profile_json_path, taxonomy_yaml_path)
    match = score_job(job, profile_index)
    matched_capabilities = _matched_capabilities(profile, job, match)
    prompt = _build_prompt(profile=profile, job=job, match=match, matched_capabilities=matched_capabilities, language=language)
    logger.info(
        "cv generation prompt built",
        extra={
            "provider": provider,
            "model_supplied": bool(model),
            "base_url_supplied": bool(base_url),
            "language": language,
            "company": job.company,
            "title": job.title,
            "matched_capability_count": len(matched_capabilities),
            "matched_skill_count": len(match.matched_skills),
        },
    )
    try:
        llm_result = await LlmGenerationService().generate_text(
            system_prompt=_cv_system_prompt(),
            prompt=prompt,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.2,
            max_tokens=2000,
        )
    except LlmGenerationProviderError as exc:
        raise CvGenerationProviderError(str(exc), status_code=exc.status_code) from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"cv_{_slug(job.company)}_{_slug(job.title)}_{uuid.uuid4().hex[:8]}.md"
    path.write_text(llm_result.text, encoding="utf-8")
    return GeneratedCv(markdown=llm_result.text, path=path, matched_capabilities=matched_capabilities, provider=llm_result.provider, model=llm_result.model)


def _matched_capabilities(profile: dict[str, Any], job: JobPosting, match: JobMatchResult) -> list[str]:
    text = searchable(job.matching_text())
    matched_skill_names = {searchable(skill) for skill in match.matched_skills}
    scored: list[tuple[int, str]] = []
    for cap in profile.get("capabilities") or []:
        cap_skills = {searchable(str(skill)) for skill in cap.get("skills") or []}
        skill_hits = len(cap_skills & matched_skill_names)
        summary_hits = sum(1 for token in searchable(str(cap.get("summary") or "")).split() if len(token) >= 4 and token in text)
        score = skill_hits * 3 + min(summary_hits, 3)
        if score > 0:
            scored.append((score, str(cap.get("name") or cap.get("id") or "Capability")))
    return [name for _, name in sorted(scored, reverse=True)[:5]]


def _build_prompt(
    *,
    profile: dict[str, Any],
    job: JobPosting,
    match: JobMatchResult,
    matched_capabilities: list[str],
    language: str,
) -> str:
    language_name = "Spanish" if (language or "en").lower().startswith("es") else "English"
    cv_phrases = _cv_phrases_for_match(profile, match)
    profile_payload = {
        "purpose": profile.get("purpose"),
        "matched_capabilities": matched_capabilities,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "cv_phrases": cv_phrases,
        "capabilities": profile.get("capabilities", []),
    }
    return (
        "Generate a targeted CV draft in Markdown for the job below.\n\n"
        "Privacy and truthfulness rules:\n"
        "- Use only the evidence, capabilities, skills, and CV phrases provided in the canonical profile.\n"
        "- Do not invent employers, dates, degrees, certifications, metrics, clients, or personal/contact data.\n"
        "- If the profile does not support a claim, omit it or phrase it conservatively.\n"
        "- Keep the CV useful and ATS-aware, but evidence-backed.\n"
        "- Return only Markdown; do not wrap it in code fences.\n\n"
        f"Output language: {language_name}.\n"
        f"Generated at: {datetime.now(UTC).isoformat(timespec='seconds')}\n\n"
        "Target job:\n"
        "```json\n"
        f"{json.dumps({'company': job.company, 'title': job.title, 'location': job.location, 'description': job.description}, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Deterministic match context:\n"
        "```json\n"
        f"{json.dumps({'fit_score': match.fit_score, 'fit_level': match.fit_level, 'reasons': match.reasons}, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Canonical technical profile context:\n"
        "```json\n"
        f"{json.dumps(profile_payload, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Suggested structure:\n"
        "# Targeted CV\n"
        "## Professional Summary\n"
        "## Core Skills\n"
        "## Selected Experience / Evidence\n"
        "## Relevant Projects or Capabilities\n"
        "## Notes for customization\n"
    )


def _cv_phrases_for_match(profile: dict[str, Any], match: JobMatchResult) -> list[str]:
    matched = {searchable(skill) for skill in match.matched_skills}
    phrases: list[str] = []
    for cap in profile.get("capabilities") or []:
        cap_skills = {searchable(str(skill)) for skill in cap.get("skills") or []}
        if cap_skills & matched:
            phrases.extend(str(phrase) for phrase in cap.get("cv_phrases") or [] if str(phrase).strip())
    return unique(phrases)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "item").lower()).strip("-")
    return slug[:40] or "item"
