from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.models.job_matching import JobMatchResult, JobPosting
from app.services.profile_matcher import _searchable, score_job
from app.services.settings import get_llm_api_key, get_llm_base_url, get_llm_default_model, get_llm_model, get_llm_provider

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


@dataclass(frozen=True)
class OpenAiCompatibleCvProvider:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int = 90

    async def generate_markdown(self, *, prompt: str) -> str:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _cv_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        return await _post_and_extract_openai_chat_completion(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
            provider="openai_compatible",
            model=self.model,
        )


@dataclass(frozen=True)
class AnthropicCvProvider:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int = 90

    async def generate_markdown(self, *, prompt: str) -> str:
        endpoint = self.base_url.rstrip("/") + "/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "system": _cv_system_prompt(),
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return await _post_and_extract_anthropic_message(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
            provider="anthropic",
            model=self.model,
        )


def _build_provider(*, provider: str, api_key: str, model: str, base_url: str):
    if provider == "anthropic":
        return AnthropicCvProvider(api_key=api_key, model=model, base_url=base_url)
    if provider in {"openai", "openai_compatible"}:
        return OpenAiCompatibleCvProvider(api_key=api_key, model=model, base_url=base_url)
    raise CvGenerationProviderError(f"Unsupported LLM provider: {provider}")


async def _post_json(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
    provider: str,
    model: str,
) -> httpx.Response:
    logger.info(
        "cv provider request started",
        extra={"provider": provider, "model": model, "endpoint": endpoint, "timeout_seconds": timeout_seconds},
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(
                "cv provider request completed",
                extra={"provider": provider, "model": model, "endpoint": endpoint, "status_code": response.status_code},
            )
            return response
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        response_text = _safe_response_text(exc.response)
        logger.warning(
            "cv provider request returned error status",
            extra={
                "provider": provider,
                "model": model,
                "endpoint": endpoint,
                "status_code": status_code,
                "response_body": response_text,
            },
        )
        raise CvGenerationProviderError(
            f"CV provider request failed: {exc}. Response body: {response_text}",
            status_code=status_code,
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "cv provider request failed",
            extra={"provider": provider, "model": model, "endpoint": endpoint, "error": str(exc)},
        )
        raise CvGenerationProviderError(f"CV provider request failed: {exc}") from exc
    except RuntimeError as exc:
        logger.warning(
            "cv provider request failed",
            extra={"provider": provider, "model": model, "endpoint": endpoint, "error": str(exc)},
        )
        raise CvGenerationProviderError(f"CV provider request failed: {exc}") from exc


def _safe_response_text(response: httpx.Response | None, limit: int = 1000) -> str:
    if response is None:
        return ""
    text = response.text or ""
    return text[:limit]


async def _post_and_extract_openai_chat_completion(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
    provider: str,
    model: str,
) -> str:
    response = await _post_json(
        endpoint=endpoint,
        headers=headers,
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider=provider,
        model=model,
    )
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CvGenerationProviderError("CV provider returned an unexpected response shape") from exc
    content = str(content).strip()
    if not content:
        raise CvGenerationProviderError("CV provider returned empty content")
    return content + "\n"


async def _post_and_extract_anthropic_message(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
    provider: str,
    model: str,
) -> str:
    response = await _post_json(
        endpoint=endpoint,
        headers=headers,
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider=provider,
        model=model,
    )
    data = response.json()
    try:
        parts = data["content"]
    except (KeyError, TypeError) as exc:
        raise CvGenerationProviderError("Anthropic provider returned an unexpected response shape") from exc
    texts: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                texts.append(str(part["text"]))
    content = "".join(texts).strip()
    if not content:
        raise CvGenerationProviderError("CV provider returned empty content")
    return content + "\n"


async def generate_targeted_cv(
    *,
    profile_json_path: Path,
    output_dir: Path,
    job: JobPosting,
    api_key: str | None = None,
    language: str = "en",
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> GeneratedCv:
    profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
    profile_index = _profile_index_from_raw(profile)
    match = score_job(job, profile_index)
    matched_capabilities = _matched_capabilities(profile, job, match)
    prompt = _build_prompt(profile=profile, job=job, match=match, matched_capabilities=matched_capabilities, language=language)
    resolved_api_key = get_llm_api_key(api_key, provider=provider)
    resolved_provider = get_llm_provider(provider)
    requested_model = get_llm_model(model, provider=resolved_provider)
    default_model = get_llm_default_model(resolved_provider)
    resolved_model = requested_model
    resolved_base_url = get_llm_base_url(base_url, provider=resolved_provider)
    logger.info(
        "cv generation resolved llm config",
        extra={
            "provider": resolved_provider,
            "requested_model": requested_model,
            "default_model": default_model,
            "base_url": resolved_base_url,
            "language": language,
            "company": job.company,
            "title": job.title,
            "matched_capability_count": len(matched_capabilities),
            "matched_skill_count": len(match.matched_skills),
        },
    )
    llm_provider = _build_provider(
        provider=resolved_provider,
        api_key=resolved_api_key,
        model=resolved_model,
        base_url=resolved_base_url,
    )
    try:
        markdown = await llm_provider.generate_markdown(prompt=prompt)
    except CvGenerationProviderError as exc:
        if resolved_model != default_model and exc.status_code in {400, 404, 422}:
            logger.warning(
                "cv generation falling back to default model",
                extra={
                    "provider": resolved_provider,
                    "requested_model": resolved_model,
                    "fallback_model": default_model,
                    "status_code": exc.status_code,
                    "error": str(exc),
                },
            )
            fallback_provider = _build_provider(
                provider=resolved_provider,
                api_key=resolved_api_key,
                model=default_model,
                base_url=resolved_base_url,
            )
            markdown = await fallback_provider.generate_markdown(prompt=prompt)
            resolved_model = default_model
        else:
            logger.warning(
                "cv generation provider failed without fallback",
                extra={
                    "provider": resolved_provider,
                    "model": resolved_model,
                    "default_model": default_model,
                    "status_code": exc.status_code,
                    "error": str(exc),
                },
            )
            raise
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"cv_{_slug(job.company)}_{_slug(job.title)}_{uuid.uuid4().hex[:8]}.md"
    path.write_text(markdown, encoding="utf-8")
    return GeneratedCv(markdown=markdown, path=path, matched_capabilities=matched_capabilities, provider=resolved_provider, model=resolved_model)


def _profile_index_from_raw(profile: dict[str, Any]):
    from app.services.profile_matcher import ProfileIndex, SkillEntry

    skills: list[SkillEntry] = []
    terms: set[str] = set()
    summaries: list[str] = []
    for cap in profile.get("capabilities") or []:
        level = str(cap.get("level") or "").lower()
        confidence = str(cap.get("confidence") or "").lower()
        weight = 1.0
        if "strong" in level:
            weight += 0.25
        if "high" in confidence:
            weight += 0.15
        for skill in cap.get("skills") or []:
            skill_name = str(skill)
            skills.append(SkillEntry(name=skill_name, category=str(cap.get("id") or "profile"), aliases=[_searchable(skill_name)], weight=weight))
        summary = str(cap.get("summary") or "")
        summaries.append(f"{cap.get('name')}: {summary}")
        for token in _searchable(" ".join([str(cap.get("name") or ""), summary])).split():
            if len(token) >= 4:
                terms.add(token)
    return ProfileIndex(skills=skills, capability_terms=terms, summary="\n".join(summaries[:10]))


def _matched_capabilities(profile: dict[str, Any], job: JobPosting, match: JobMatchResult) -> list[str]:
    text = _searchable(job.matching_text())
    matched_skill_names = {_searchable(skill) for skill in match.matched_skills}
    scored: list[tuple[int, str]] = []
    for cap in profile.get("capabilities") or []:
        cap_skills = {_searchable(str(skill)) for skill in cap.get("skills") or []}
        skill_hits = len(cap_skills & matched_skill_names)
        summary_hits = sum(1 for token in _searchable(str(cap.get("summary") or "")).split() if len(token) >= 4 and token in text)
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
    matched = {_searchable(skill) for skill in match.matched_skills}
    phrases: list[str] = []
    for cap in profile.get("capabilities") or []:
        cap_skills = {_searchable(str(skill)) for skill in cap.get("skills") or []}
        if cap_skills & matched:
            phrases.extend(str(phrase) for phrase in cap.get("cv_phrases") or [] if str(phrase).strip())
    return _unique(phrases)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "item").lower()).strip("-")
    return slug[:40] or "item"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
