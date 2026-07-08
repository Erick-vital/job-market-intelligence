from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TechnicalProfileGenerationResult:
    output_path: Path
    evidence_path: Path
    capabilities_count: int


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
    )


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
