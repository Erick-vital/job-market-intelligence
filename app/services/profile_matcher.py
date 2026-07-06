from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.models.job_matching import JobMatchResult, JobPosting

EXTRA_ALIASES = {
    "REST APIs": ["rest", "restful"],
    "JSONL artifacts": ["ndjson"],
    "LLM integration": ["large language model", "ai agent", "agentic"],
    "Python": ["python3"],
    "S3": ["amazon s3"],
}

NEGATIVE_TERMS = ["frontend-only", "frontend only", "mobile ui", "react css", "android", "ios"]
TITLE_TERMS = ["backend", "python", "api", "automation", "data", "cloud", "serverless", "platform", "sre"]
GAP_SKILLS = ["Kubernetes", "React", "Terraform", "Java", ".NET", "Go", "GraphQL"]


@dataclass(frozen=True)
class SkillEntry:
    name: str
    category: str
    aliases: list[str]
    weight: float


@dataclass(frozen=True)
class ProfileIndex:
    skills: list[SkillEntry]
    capability_terms: set[str]
    summary: str


def load_profile(profile_json_path: Path, taxonomy_yaml_path: Path) -> ProfileIndex:
    profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
    taxonomy = yaml.safe_load(taxonomy_yaml_path.read_text(encoding="utf-8")) or {}
    capability_weights = _capability_skill_weights(profile)
    skills: list[SkillEntry] = []
    for category, data in (taxonomy.get("categories") or {}).items():
        category_weight = 0.45 if str(category).startswith("declared_") else 1.0
        for name in data.get("skills") or []:
            name = str(name)
            weight = capability_weights.get(_norm(name), 0.75) * category_weight
            skills.append(SkillEntry(name=name, category=category, aliases=_aliases_for(name), weight=weight))

    terms: set[str] = set()
    summaries: list[str] = []
    for cap in profile.get("capabilities") or []:
        summary = str(cap.get("summary") or "")
        summaries.append(f"{cap.get('name')}: {summary}")
        for token in _meaningful_tokens(" ".join([str(cap.get("name") or ""), summary])):
            terms.add(token)
    return ProfileIndex(skills=skills, capability_terms=terms, summary="\n".join(summaries[:10]))


def score_job(job: JobPosting, profile: ProfileIndex) -> JobMatchResult:
    raw_text = job.matching_text()
    text = _searchable(raw_text)
    title = _searchable(job.title)

    matched: list[SkillEntry] = []
    for skill in profile.skills:
        if any(_contains_alias(text, alias) for alias in skill.aliases):
            matched.append(skill)

    total_possible = sum(skill.weight for skill in profile.skills if skill.weight >= 0.7) or 1.0
    matched_weight = sum(skill.weight for skill in matched)
    skill_overlap = min(1.0, matched_weight / min(total_possible, 12.0))

    job_terms = set(_meaningful_tokens(raw_text))
    capability_alignment = min(1.0, len(job_terms & profile.capability_terms) / 12.0)
    title_alignment = min(1.0, sum(1 for term in TITLE_TERMS if term in title) / 3.0)
    location_bonus = 1.0 if any(term in _searchable(job.location) for term in ["remote", "remoto", "mexico", "méxico", "cdmx"]) else 0.0
    negative_penalty = 0.0
    if any(term in text for term in NEGATIVE_TERMS):
        negative_penalty = 0.25
    if "frontend" in title and not any(term in text for term in ["python", "backend", "api"]):
        negative_penalty = max(negative_penalty, 0.30)

    score = (skill_overlap * 0.55) + (capability_alignment * 0.25) + (title_alignment * 0.10) + (location_bonus * 0.05) - negative_penalty
    score = max(0.0, min(1.0, score))
    matched_names = _unique([skill.name for skill in sorted(matched, key=lambda item: item.weight, reverse=True)])[:12]
    missing = [skill for skill in GAP_SKILLS if _contains_alias(text, _searchable(skill)) and skill not in matched_names][:6]
    reasons = _reasons(job, matched_names, title_alignment, missing)
    return JobMatchResult(
        job=job,
        fit_score=round(score, 3),
        fit_level=_fit_level(score),
        matched_skills=matched_names,
        missing_skills=missing,
        reasons=reasons,
        score_breakdown={
            "skill_overlap": round(skill_overlap, 3),
            "capability_alignment": round(capability_alignment, 3),
            "role_title_alignment": round(title_alignment, 3),
            "location_bonus": round(location_bonus * 0.05, 3),
            "negative_penalty": round(negative_penalty, 3),
        },
    )


def rank_matches(results: list[JobMatchResult], min_score: float, max_matches: int = 4) -> list[JobMatchResult]:
    ranked = sorted((item for item in results if item.fit_score >= min_score), key=lambda item: item.fit_score, reverse=True)[:max(0, max_matches)]
    for index, item in enumerate(ranked, start=1):
        item.rank = index
    return ranked


def _capability_skill_weights(profile: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for cap in profile.get("capabilities") or []:
        level = str(cap.get("level") or "").lower()
        confidence = str(cap.get("confidence") or "").lower()
        base = 1.0
        if "strong" in level:
            base += 0.25
        if "high" in confidence:
            base += 0.15
        if "declared" in str(cap.get("evidence_type") or "").lower():
            base *= 0.55
        for skill in cap.get("skills") or []:
            weights[_norm(str(skill))] = max(weights.get(_norm(str(skill)), 0.0), base)
    return weights


def _aliases_for(name: str) -> list[str]:
    aliases = {_searchable(name)}
    aliases.add(_searchable(name.replace("-", " ")))
    if name.endswith("s"):
        aliases.add(_searchable(name[:-1]))
    compact = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    aliases.add(_searchable(compact))
    aliases.update(_searchable(alias) for alias in EXTRA_ALIASES.get(name, []))
    return sorted(alias for alias in aliases if alias)


def _contains_alias(text: str, alias: str) -> bool:
    if not alias:
        return False
    if len(alias) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text) is not None
    return alias in text


def _reasons(job: JobPosting, matched: list[str], title_alignment: float, missing: list[str]) -> list[str]:
    reasons: list[str] = []
    if matched:
        reasons.append("Mentions profile-aligned skills: " + ", ".join(matched[:5]) + ".")
    if title_alignment > 0:
        reasons.append("The title or responsibilities appear aligned with backend, APIs, automation, data, or cloud work.")
    if missing:
        reasons.append("Potential gap or caution: " + ", ".join(missing[:4]) + ".")
    if not reasons:
        reasons.append("Not enough clear technical signals matched the canonical profile.")
    return reasons


def _fit_level(score: float) -> str:
    if score >= 0.70:
        return "strong"
    if score >= 0.50:
        return "good"
    if score >= 0.42:
        return "possible"
    return "none"


def _searchable(value: str) -> str:
    value = str(value or "").lower()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    value = re.sub(r"[^a-z0-9+#.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _norm(value: str) -> str:
    return _searchable(value)


def _meaningful_tokens(value: str) -> list[str]:
    stop = {"with", "and", "the", "for", "de", "con", "para", "los", "las", "and", "or", "a", "to", "of", "in"}
    return [token for token in _searchable(value).split() if len(token) >= 4 and token not in stop]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
