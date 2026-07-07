from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.job_matching import JobMatchResult, JobPosting
from app.services.profile_matcher import _searchable, score_job


@dataclass(frozen=True)
class GeneratedCv:
    markdown: str
    path: Path
    matched_capabilities: list[str]


def generate_targeted_cv(
    *,
    profile_json_path: Path,
    output_dir: Path,
    job: JobPosting,
    language: str = "en",
) -> GeneratedCv:
    profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
    profile_index = _profile_index_from_raw(profile)
    match = score_job(job, profile_index)
    matched_capabilities = _matched_capabilities(profile, job, match)
    markdown = _build_markdown(profile=profile, job=job, match=match, matched_capabilities=matched_capabilities, language=language)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"cv_{_slug(job.company)}_{_slug(job.title)}_{uuid.uuid4().hex[:8]}.md"
    path.write_text(markdown, encoding="utf-8")
    return GeneratedCv(markdown=markdown, path=path, matched_capabilities=matched_capabilities)


def _profile_index_from_raw(profile: dict[str, Any]):
    # Avoid duplicating taxonomy loading here. Build a minimal profile index from capability skills
    # so CV generation can reuse the same deterministic scoring vocabulary.
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


def _build_markdown(
    *,
    profile: dict[str, Any],
    job: JobPosting,
    match: JobMatchResult,
    matched_capabilities: list[str],
    language: str,
) -> str:
    language = (language or "en").lower()
    spanish = language.startswith("es")
    title = "# CV dirigido" if spanish else "# Targeted CV"
    professional_summary = "## Resumen profesional" if spanish else "## Professional summary"
    evidence = "## Evidencia seleccionada" if spanish else "## Selected evidence"
    skills = "## Skills relevantes" if spanish else "## Relevant skills"
    gaps = "## Gaps o cautelas" if spanish else "## Gaps or cautions"
    target = "Objetivo" if spanish else "Target"
    generated = "Generado" if spanish else "Generated"

    phrases = _cv_phrases_for_match(profile, match)
    capability_lines = matched_capabilities or [str(cap.get("name") or cap.get("id")) for cap in (profile.get("capabilities") or [])[:3]]
    matched_skills = match.matched_skills[:12]

    if spanish:
        summary = (
            f"Perfil técnico orientado a {job.title} en {job.company}, con énfasis en "
            f"{', '.join(matched_skills[:5]) if matched_skills else 'backend, automatización y datos'}."
        )
    else:
        summary = (
            f"Technical profile targeted to {job.title} at {job.company}, emphasizing "
            f"{', '.join(matched_skills[:5]) if matched_skills else 'backend, automation, and data work'}."
        )

    lines = [
        title,
        "",
        f"- {target}: {job.title} — {job.company}",
        f"- Fit score: {match.fit_score:.3f} ({match.fit_level})",
        f"- {generated}: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        professional_summary,
        "",
        summary,
        "",
        evidence,
        "",
    ]
    if capability_lines:
        lines.extend(f"- {name}" for name in capability_lines)
    else:
        lines.append("- No profile capabilities matched this job strongly enough.")
    if phrases:
        lines.extend(["", "## CV-ready bullets" if not spanish else "## Bullets listos para CV", ""])
        lines.extend(f"- {phrase}" for phrase in phrases[:8])
    lines.extend(["", skills, ""])
    lines.append("- " + (", ".join(matched_skills) if matched_skills else "No clear matched skills detected."))
    lines.extend(["", gaps, ""])
    if match.missing_skills:
        lines.extend(f"- {skill}" for skill in match.missing_skills)
    else:
        lines.append("- No major deterministic gaps detected from the configured gap list.")
    lines.extend(["", "## Matching rationale" if not spanish else "## Razones del match", ""])
    lines.extend(f"- {reason}" for reason in match.reasons)
    return "\n".join(lines) + "\n"


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
