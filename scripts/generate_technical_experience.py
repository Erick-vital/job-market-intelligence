#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a starter technical_experience.json from repo_evidence.jsonl.")
    parser.add_argument("--evidence", default="items/profile/repo_evidence.jsonl")
    parser.add_argument("--out", default="items/profile/technical_experience.json")
    args = parser.parse_args()

    evidence_path = Path(args.evidence)
    rows = []
    if evidence_path.exists():
        for line in evidence_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    by_capability: dict[str, list[dict]] = {}
    skills_by_capability: dict[str, Counter[str]] = {}
    for row in rows:
        for capability in row.get("capabilities", []) or [row.get("signal", "general_capability")]:
            by_capability.setdefault(capability, []).append(row)
            skills_by_capability.setdefault(capability, Counter()).update(row.get("skills", []))

    capabilities = []
    for capability_id, capability_rows in sorted(by_capability.items()):
        skills = [name for name, _ in skills_by_capability[capability_id].most_common(12)]
        capabilities.append({
            "id": capability_id,
            "name": capability_id.replace("_", " ").title(),
            "level": "working",
            "confidence": _confidence(capability_rows),
            "evidence_type": "repo-evidenced",
            "summary": "Capability inferred from repo evidence. Edit this summary before using publicly.",
            "skills": skills,
            "evidence_refs": sorted({str(row.get("repo", "")) for row in capability_rows if row.get("repo")}),
            "cv_phrases": [],
        })

    output = {
        "version": "generated.v1",
        "updated_at": date.today().isoformat(),
        "purpose": "Canonical technical profile generated from repo evidence.",
        "supporting_skill": "docs/technical-profile-evidence-skill.md",
        "sources": [str(evidence_path)],
        "capabilities": capabilities,
        "job_matching_guidance": {"prioritize": [], "deprioritize": []},
        "update_rules": ["Review generated summaries manually before using for job matching."],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


def _confidence(rows: list[dict]) -> str:
    values = {str(row.get("confidence", "")).lower() for row in rows}
    if "high" in values:
        return "high"
    if "medium_high" in values:
        return "medium_high"
    if "medium" in values:
        return "medium"
    return "low"


if __name__ == "__main__":
    main()
