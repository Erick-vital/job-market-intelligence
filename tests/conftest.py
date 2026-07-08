from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PROFILE_JSON = FIXTURES_DIR / "technical_experience.json"
FIXTURE_TAXONOMY_YAML = FIXTURES_DIR / "skill_taxonomy.yaml"


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch):
    """Keep tests hermetic: ignore the repo .env and the user's live profile files."""
    monkeypatch.setenv("JMI_ENV_FILE", "")
    monkeypatch.setenv("JMI_PROFILE_JSON_PATH", str(FIXTURE_PROFILE_JSON))
    monkeypatch.setenv("JMI_SKILL_TAXONOMY_PATH", str(FIXTURE_TAXONOMY_YAML))
