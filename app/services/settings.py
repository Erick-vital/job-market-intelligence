from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_ITEMS_DIR = ROOT_DIR / "items" / "jobs"
DEFAULT_PROFILE_JSON_PATH = ROOT_DIR / "items" / "profile" / "technical_experience.json"
DEFAULT_TAXONOMY_PATH = ROOT_DIR / "items" / "profile" / "skill_taxonomy.yaml"
DEFAULT_ENV_PATH = ROOT_DIR / ".env"
DEFAULT_LLM_PROVIDER = "openai_compatible"
DEFAULT_LLM_MODEL_BY_PROVIDER = {
    "openai_compatible": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
}
ANTHROPIC_MODEL_ALIASES = {
    "default": "claude-sonnet-5",
    "recommended": "claude-sonnet-5",
    "sonnet": "claude-sonnet-5",
    "sonnet 5": "claude-sonnet-5",
    "sonnet-5": "claude-sonnet-5",
    "claude sonnet 5": "claude-sonnet-5",
    "fable": "claude-fable-5",
    "fable 5": "claude-fable-5",
    "fable-5": "claude-fable-5",
    "claude fable 5": "claude-fable-5",
    "opus": "claude-opus-4-8",
    "opus 4.8": "claude-opus-4-8",
    "opus-4.8": "claude-opus-4-8",
    "claude opus 4.8": "claude-opus-4-8",
    "haiku": "claude-haiku-4-5-20251001",
    "haiku 4.5": "claude-haiku-4-5-20251001",
    "haiku-4.5": "claude-haiku-4-5-20251001",
    "claude haiku 4.5": "claude-haiku-4-5-20251001",
}
DEFAULT_LLM_BASE_URL_BY_PROVIDER = {
    "openai_compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}


class MissingLlmApiKeyError(RuntimeError):
    pass


class AppSettings(BaseSettings):
    """All JMI_* configuration, sourced from the environment and the repo .env file."""

    model_config = SettingsConfigDict(env_prefix="JMI_", extra="ignore")

    data_dir: Path = DEFAULT_DATA_DIR
    jobs_items_dir: Path = DEFAULT_ITEMS_DIR
    profile_json_path: Path = DEFAULT_PROFILE_JSON_PATH
    skill_taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    min_score: float = 0.42

    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    openai_api_key: str = ""  # legacy JMI_OPENAI_API_KEY
    anthropic_api_key: str = ""


def _env_file() -> str | None:
    # JMI_ENV_FILE overrides the .env location; an empty value disables it (used by tests).
    override = os.getenv("JMI_ENV_FILE")
    if override is not None:
        return override or None
    return str(DEFAULT_ENV_PATH)


def get_app_settings() -> AppSettings:
    return AppSettings(_env_file=_env_file())


@dataclass(frozen=True)
class JobMatchingSettings:
    data_dir: Path = DEFAULT_DATA_DIR
    jobs_items_dir: Path = DEFAULT_ITEMS_DIR
    profile_json_path: Path = DEFAULT_PROFILE_JSON_PATH
    skill_taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    min_score: float = 0.42


def get_job_matching_settings() -> JobMatchingSettings:
    settings = get_app_settings()
    return JobMatchingSettings(
        data_dir=settings.data_dir.expanduser(),
        jobs_items_dir=settings.jobs_items_dir.expanduser(),
        profile_json_path=settings.profile_json_path.expanduser(),
        skill_taxonomy_path=settings.skill_taxonomy_path.expanduser(),
        min_score=settings.min_score,
    )


def get_llm_api_key(request_api_key: str | None = None, provider: str | None = None) -> str:
    if request_api_key and request_api_key.strip():
        return request_api_key.strip()
    settings = get_app_settings()
    resolved_provider = get_llm_provider(provider, settings=settings)
    candidates = _llm_api_key_candidates(settings, resolved_provider)
    for _, value in candidates:
        if value.strip():
            return value.strip()
    env_names = [name for name, _ in candidates]
    raise MissingLlmApiKeyError(
        f"Missing LLM API key. Set {env_names[0]} (or {', '.join(env_names[1:])}) in your .env file or pass api_key in the request."
    )


def get_llm_provider(request_provider: str | None = None, *, settings: AppSettings | None = None) -> str:
    if request_provider and request_provider.strip():
        return _normalize_provider_name(request_provider)
    settings = settings or get_app_settings()
    if settings.llm_provider.strip():
        return _normalize_provider_name(settings.llm_provider)
    detected_provider = _detect_provider(settings)
    if detected_provider:
        return detected_provider
    return DEFAULT_LLM_PROVIDER


def get_llm_model(request_model: str | None = None, provider: str | None = None) -> str:
    settings = get_app_settings()
    resolved_provider = get_llm_provider(provider, settings=settings)
    if request_model and request_model.strip():
        return normalize_llm_model(request_model.strip(), provider=resolved_provider)
    if settings.llm_model.strip():
        return normalize_llm_model(settings.llm_model.strip(), provider=resolved_provider)
    return get_llm_default_model(resolved_provider)


def get_llm_default_model(provider: str | None = None) -> str:
    resolved_provider = get_llm_provider(provider)
    return DEFAULT_LLM_MODEL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_MODEL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def get_llm_base_url(request_base_url: str | None = None, provider: str | None = None) -> str:
    if request_base_url and request_base_url.strip():
        return request_base_url.strip()
    settings = get_app_settings()
    if settings.llm_base_url.strip():
        return settings.llm_base_url.strip()
    resolved_provider = get_llm_provider(provider, settings=settings)
    return DEFAULT_LLM_BASE_URL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_BASE_URL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def normalize_llm_model(model: str, provider: str | None = None) -> str:
    raw_model = str(model or "").strip()
    if not raw_model:
        return get_llm_default_model(provider)
    if get_llm_provider(provider) == "anthropic":
        alias_key = raw_model.lower().replace("·", " ").strip()
        return ANTHROPIC_MODEL_ALIASES.get(alias_key, raw_model)
    return raw_model


def _detect_provider(settings: AppSettings) -> str | None:
    api_key_candidates = [settings.llm_api_key, settings.openai_api_key, settings.anthropic_api_key]
    if any(key.strip().startswith("sk-ant") for key in api_key_candidates if key.strip()):
        return "anthropic"
    raw_model = settings.llm_model.strip().lower()
    if any(token in raw_model for token in ("claude", "sonnet", "haiku", "opus")):
        return "anthropic"
    return None


def _llm_api_key_candidates(settings: AppSettings, provider: str) -> list[tuple[str, str]]:
    generic = [
        ("JMI_LLM_API_KEY", settings.llm_api_key),
        ("JMI_OPENAI_API_KEY", settings.openai_api_key),
    ]
    anthropic = ("JMI_ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if _normalize_provider_name(provider) == "anthropic":
        return [anthropic, *generic]
    return [*generic, anthropic]


def _normalize_provider_name(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")
