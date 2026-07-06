from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_ITEMS_DIR = ROOT_DIR / "items" / "jobs"
DEFAULT_PROFILE_JSON_PATH = ROOT_DIR / "items" / "profile" / "technical_experience.json"
DEFAULT_TAXONOMY_PATH = ROOT_DIR / "items" / "profile" / "skill_taxonomy.yaml"


@dataclass(frozen=True)
class JobMatchingSettings:
    data_dir: Path = DEFAULT_DATA_DIR
    jobs_items_dir: Path = DEFAULT_ITEMS_DIR
    profile_json_path: Path = DEFAULT_PROFILE_JSON_PATH
    skill_taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    min_score: float = 0.42


def get_job_matching_settings() -> JobMatchingSettings:
    return JobMatchingSettings(
        data_dir=Path(os.getenv("JMI_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser(),
        jobs_items_dir=Path(os.getenv("JMI_JOBS_ITEMS_DIR", str(DEFAULT_ITEMS_DIR))).expanduser(),
        profile_json_path=Path(os.getenv("JMI_PROFILE_JSON_PATH", str(DEFAULT_PROFILE_JSON_PATH))).expanduser(),
        skill_taxonomy_path=Path(os.getenv("JMI_SKILL_TAXONOMY_PATH", str(DEFAULT_TAXONOMY_PATH))).expanduser(),
        min_score=float(os.getenv("JMI_MIN_SCORE", "0.42")),
    )
