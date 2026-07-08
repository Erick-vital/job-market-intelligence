from __future__ import annotations

from typing import Any


def build_skill_taxonomy(profile: dict[str, Any]) -> dict[str, Any]:
    """Derive a matcher skill taxonomy from a canonical profile's capabilities."""
    core: list[str] = []
    declared_expansion: list[str] = []
    for cap in profile.get("capabilities") or []:
        skills = [str(skill).strip() for skill in cap.get("skills") or [] if str(skill).strip()]
        if not skills:
            continue
        evidence_type = str(cap.get("evidence_type") or "repo-evidenced").lower()
        confidence = str(cap.get("confidence") or "").lower()
        target = core if evidence_type == "repo-evidenced" and confidence in {"high", "medium_high"} else declared_expansion
        target.extend(skills)
    return {
        "categories": {
            "core": {"skills": unique(core)},
            "declared_expansion": {"skills": unique(declared_expansion)},
        }
    }


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
