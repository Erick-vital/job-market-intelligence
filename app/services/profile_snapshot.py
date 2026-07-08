from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProfileSnapshot:
    path: Path
    exists: bool
    version: str | None
    updated_at: str | None
    purpose: str | None
    sources: list[str]
    capabilities: list[dict[str, Any]]
    capability_count: int
    skill_count: int
    unique_skills: list[str]


def load_profile_snapshot(profile_json_path: Path) -> ProfileSnapshot:
    path = profile_json_path.expanduser().resolve()
    if not path.exists():
        return ProfileSnapshot(
            path=path,
            exists=False,
            version=None,
            updated_at=None,
            purpose=None,
            sources=[],
            capabilities=[],
            capability_count=0,
            skill_count=0,
            unique_skills=[],
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    capabilities = list(data.get("capabilities") or [])
    unique_skills = sorted({str(skill) for cap in capabilities for skill in (cap.get("skills") or []) if str(skill).strip()})
    return ProfileSnapshot(
        path=path,
        exists=True,
        version=str(data.get("version") or ""),
        updated_at=str(data.get("updated_at") or ""),
        purpose=str(data.get("purpose") or ""),
        sources=[str(item) for item in data.get("sources") or []],
        capabilities=capabilities,
        capability_count=len(capabilities),
        skill_count=sum(len(cap.get("skills") or []) for cap in capabilities),
        unique_skills=unique_skills,
    )
