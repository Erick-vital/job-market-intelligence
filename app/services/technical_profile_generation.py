from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from app.services.llm_generation import LlmGenerationProviderError, LlmGenerationService, LlmGenerationResult
from app.services.settings import MissingLlmApiKeyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TechnicalProfileGenerationResult:
    output_path: Path
    evidence_path: Path
    capabilities_count: int
    generation_mode: Literal["llm", "deterministic"]
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_fallback_reason: str | None = None


def generate_technical_profile(*, evidence_path: Path, output_path: Path) -> TechnicalProfileGenerationResult:
    rows = _read_evidence_rows(evidence_path)
    existing_profile = _read_existing_profile(output_path)
    existing_capabilities = {str(cap.get("id") or ""): cap for cap in existing_profile.get("capabilities") or []}
    by_capability: dict[str, list[dict[str, Any]]] = {}
    skills_by_capability: dict[str, Counter[str]] = {}

    for row in rows:
        capabilities = row.get("capabilities", []) or [row.get("signal", "general_capability")]
        for capability in capabilities:
            capability_id = str(capability or "general_capability")
            by_capability.setdefault(capability_id, []).append(row)
            skills_by_capability.setdefault(capability_id, Counter()).update(str(skill) for skill in row.get("skills", []))

    capabilities_payload = []
    for capability_id, capability_rows in sorted(by_capability.items()):
        existing = existing_capabilities.get(capability_id, {})
        generated_skills = [name for name, _ in skills_by_capability[capability_id].most_common(12)]
        existing_skills = [str(skill) for skill in existing.get("skills") or [] if str(skill).strip()]
        skills = _unique(generated_skills + existing_skills)[:16]
        existing_summary = str(existing.get("summary") or "")
        summary = existing_summary if existing_summary and "Capability inferred from repo evidence" not in existing_summary else "Capability inferred from repo evidence. Edit this summary before using publicly."
        capabilities_payload.append(
            {
                "id": capability_id,
                "name": str(existing.get("name") or capability_id.replace("_", " ").title()),
                "level": str(existing.get("level") or "working"),
                "confidence": _confidence(capability_rows),
                "evidence_type": str(existing.get("evidence_type") or "repo-evidenced"),
                "summary": summary,
                "skills": skills,
                "evidence_refs": sorted({str(row.get("repo", "")) for row in capability_rows if row.get("repo")}),
                "cv_phrases": list(existing.get("cv_phrases") or []),
            }
        )

    output = {
        "version": "generated.v1",
        "updated_at": date.today().isoformat(),
        "purpose": "Canonical technical profile generated from repo evidence.",
        "supporting_skill": "docs/technical-profile-evidence-skill.md",
        "sources": [str(evidence_path)],
        "capabilities": capabilities_payload,
        "job_matching_guidance": {"prioritize": [], "deprioritize": []},
        "update_rules": ["Review generated summaries manually before using for job matching."],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return TechnicalProfileGenerationResult(
        output_path=output_path,
        evidence_path=evidence_path,
        capabilities_count=len(capabilities_payload),
        generation_mode="deterministic",
    )


async def generate_technical_profile_with_skill(
    *,
    evidence_path: Path,
    output_path: Path,
    skill_path: Path | None = None,
    llm_service: Any | None = None,
) -> TechnicalProfileGenerationResult:
    """Generate the machine-readable profile using repo evidence plus the documented profile skill.

    Falls back to the deterministic generator when no LLM key is configured or the provider fails.
    """
    deterministic = _build_deterministic_profile(evidence_path=evidence_path, output_path=output_path)
    resolved_skill_path = skill_path or Path("docs/technical-profile-evidence-skill.md")
    skill_text = _read_optional_text(resolved_skill_path)
    service = llm_service or LlmGenerationService()
    prompt = _build_profile_skill_prompt(skill_text=skill_text, evidence_rows=_read_evidence_rows(evidence_path), existing_profile=_read_existing_profile(output_path), deterministic_profile=deterministic)
    logger.info(
        "technical profile llm generation requested",
        extra={"evidence_path": str(evidence_path), "output_path": str(output_path), "skill_path": str(resolved_skill_path), "evidence_rows": len(_read_evidence_rows(evidence_path))},
    )
    try:
        raw_result = await service.generate_text(
            system_prompt=_technical_profile_system_prompt(),
            prompt=prompt,
            temperature=0.1,
            max_tokens=3000,
        )
    except (MissingLlmApiKeyError, LlmGenerationProviderError) as exc:
        logger.warning(
            "technical profile llm generation unavailable; using deterministic fallback",
            extra={"error": str(exc), "generation_mode": "deterministic", "llm_fallback_reason": "llm_provider_unavailable"},
        )
        result = generate_technical_profile(evidence_path=evidence_path, output_path=output_path)
        return TechnicalProfileGenerationResult(
            output_path=result.output_path,
            evidence_path=result.evidence_path,
            capabilities_count=result.capabilities_count,
            generation_mode="deterministic",
            llm_fallback_reason="llm_provider_unavailable",
        )
    text = raw_result.text if isinstance(raw_result, LlmGenerationResult) else str(raw_result)
    try:
        output = _parse_profile_json(text)
        output = _normalize_profile_output(output, evidence_path=evidence_path)
    except ValueError as exc:
        logger.warning(
            "technical profile llm output invalid; using deterministic fallback",
            extra={"error": str(exc), "generation_mode": "deterministic", "llm_fallback_reason": "invalid_llm_output"},
        )
        result = generate_technical_profile(evidence_path=evidence_path, output_path=output_path)
        return TechnicalProfileGenerationResult(
            output_path=result.output_path,
            evidence_path=result.evidence_path,
            capabilities_count=result.capabilities_count,
            generation_mode="deterministic",
            llm_fallback_reason="invalid_llm_output",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "technical profile llm generation completed",
        extra={"generation_mode": "llm", "llm_provider": raw_result.provider, "llm_model": raw_result.model},
    )
    return TechnicalProfileGenerationResult(
        output_path=output_path,
        evidence_path=evidence_path,
        capabilities_count=len(output.get("capabilities") or []),
        generation_mode="llm",
        llm_provider=raw_result.provider,
        llm_model=raw_result.model,
    )


def _build_deterministic_profile(*, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    rows = _read_evidence_rows(evidence_path)
    existing_profile = _read_existing_profile(output_path)
    existing_capabilities = {str(cap.get("id") or ""): cap for cap in existing_profile.get("capabilities") or []}
    by_capability: dict[str, list[dict[str, Any]]] = {}
    skills_by_capability: dict[str, Counter[str]] = {}

    for row in rows:
        capabilities = row.get("capabilities", []) or [row.get("signal", "general_capability")]
        for capability in capabilities:
            capability_id = str(capability or "general_capability")
            by_capability.setdefault(capability_id, []).append(row)
            skills_by_capability.setdefault(capability_id, Counter()).update(str(skill) for skill in row.get("skills", []))

    capabilities_payload = []
    for capability_id, capability_rows in sorted(by_capability.items()):
        existing = existing_capabilities.get(capability_id, {})
        generated_skills = [name for name, _ in skills_by_capability[capability_id].most_common(12)]
        existing_skills = [str(skill) for skill in existing.get("skills") or [] if str(skill).strip()]
        skills = _unique(generated_skills + existing_skills)[:16]
        existing_summary = str(existing.get("summary") or "")
        summary = existing_summary if existing_summary and "Capability inferred from repo evidence" not in existing_summary else "Capability inferred from repo evidence. Edit this summary before using publicly."
        capabilities_payload.append(
            {
                "id": capability_id,
                "name": str(existing.get("name") or capability_id.replace("_", " ").title()),
                "level": str(existing.get("level") or "working"),
                "confidence": _confidence(capability_rows),
                "evidence_type": str(existing.get("evidence_type") or "repo-evidenced"),
                "summary": summary,
                "skills": skills,
                "evidence_refs": sorted({str(row.get("repo", "")) for row in capability_rows if row.get("repo")}),
                "cv_phrases": list(existing.get("cv_phrases") or []),
            }
        )

    return {
        "version": "generated.v1",
        "updated_at": date.today().isoformat(),
        "purpose": "Canonical technical profile generated from repo evidence.",
        "supporting_skill": "docs/technical-profile-evidence-skill.md",
        "sources": [str(evidence_path)],
        "capabilities": capabilities_payload,
        "job_matching_guidance": {"prioritize": [], "deprioritize": []},
        "update_rules": ["Review generated summaries manually before using for job matching."],
    }


def _technical_profile_system_prompt() -> str:
    return (
        "You update canonical technical profiles from evidence. "
        "Follow the provided skill document strictly. Return only valid JSON."
    )


def _build_profile_skill_prompt(
    *,
    skill_text: str,
    evidence_rows: list[dict[str, Any]],
    existing_profile: dict[str, Any],
    deterministic_profile: dict[str, Any],
) -> str:
    return (
        "Use the documented skill below to create/update technical_experience.json.\n\n"
        "Skill document:\n"
        "```markdown\n"
        f"{skill_text}\n"
        "```\n\n"
        "Rules for this response:\n"
        "- Return only JSON, no Markdown fences.\n"
        "- Preserve truthful existing curated summaries, skills, and cv_phrases when supported.\n"
        "- Translate repo evidence into general capabilities; do not document endpoints feature-by-feature.\n"
        "- Use evidence_type and confidence consistently with the skill.\n"
        "- Do not invent employers, dates, credentials, clients, metrics, or repo evidence.\n"
        "- Include supporting_skill as docs/technical-profile-evidence-skill.md.\n\n"
        "Existing profile JSON:\n"
        "```json\n"
        f"{json.dumps(existing_profile, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Granular repo evidence rows:\n"
        "```json\n"
        f"{json.dumps(evidence_rows, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Deterministic draft to improve, preserving the expected schema:\n"
        "```json\n"
        f"{json.dumps(deterministic_profile, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _parse_profile_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LLM profile output must be a JSON object")
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("LLM profile output must include capabilities list")
    return data


def _normalize_profile_output(output: dict[str, Any], *, evidence_path: Path) -> dict[str, Any]:
    output.setdefault("version", "generated.v1")
    output.setdefault("updated_at", date.today().isoformat())
    output["supporting_skill"] = "docs/technical-profile-evidence-skill.md"
    output.setdefault("purpose", "Canonical technical profile generated from repo evidence.")
    output.setdefault("sources", [str(evidence_path)])
    output.setdefault("job_matching_guidance", {"prioritize": [], "deprioritize": []})
    output.setdefault("update_rules", ["Review generated summaries manually before using for job matching."])
    return output


def _read_optional_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_evidence_rows(evidence_path: Path) -> list[dict[str, Any]]:
    if not evidence_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _read_existing_profile(output_path: Path) -> dict[str, Any]:
    if not output_path.exists():
        return {}
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _confidence(rows: list[dict[str, Any]]) -> str:
    values = {str(row.get("confidence", "")).lower() for row in rows}
    if "high" in values:
        return "high"
    if "medium_high" in values:
        return "medium_high"
    if "medium" in values:
        return "medium"
    return "low"
