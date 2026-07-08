#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.technical_profile_generation import generate_technical_profile, generate_technical_profile_with_skill


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a starter technical_experience.json from repo_evidence.jsonl.")
    parser.add_argument("--evidence", default="items/profile/repo_evidence.jsonl")
    parser.add_argument("--out", default="items/profile/technical_experience.json")
    parser.add_argument("--use-llm", action="store_true", help="Use the documented technical-profile-evidence skill plus the configured LLM provider.")
    parser.add_argument("--skill", default="docs/technical-profile-evidence-skill.md", help="Path to the technical profile skill markdown used with --use-llm.")
    args = parser.parse_args()

    if args.use_llm:
        result = asyncio.run(
            generate_technical_profile_with_skill(
                evidence_path=Path(args.evidence),
                output_path=Path(args.out),
                skill_path=Path(args.skill),
            )
        )
    else:
        result = generate_technical_profile(evidence_path=Path(args.evidence), output_path=Path(args.out))
    print(f"wrote {result.output_path}")


if __name__ == "__main__":
    main()
