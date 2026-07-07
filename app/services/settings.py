from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_ITEMS_DIR = ROOT_DIR / "items" / "jobs"
DEFAULT_PROFILE_JSON_PATH = ROOT_DIR / "items" / "profile" / "technical_experience.json"
DEFAULT_TAXONOMY_PATH = ROOT_DIR / "items" / "profile" / "skill_taxonomy.yaml"
DEFAULT_ENV_PATH = ROOT_DIR / ".env"
LLM_API_KEY_ENV_VAR = "JMI_LLM_API_KEY"
LLM_PROVIDER_ENV_VAR = "JMI_LLM_PROVIDER"
LLM_MODEL_ENV_VAR = "JMI_LLM_MODEL"
LLM_BASE_URL_ENV_VAR = "JMI_LLM_BASE_URL"
LEGACY_LLM_API_KEY_ENV_VAR = "JMI_OPENAI_API_KEY"
ANTHROPIC_LLM_API_KEY_ENV_VAR = "JMI_ANTHROPIC_API_KEY"
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


def _load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


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


def get_llm_api_key(request_api_key: str | None = None, provider: str | None = None) -> str:
    if request_api_key and request_api_key.strip():
        return request_api_key.strip()
    resolved_provider = get_llm_provider(provider)
    env_candidates = _llm_api_key_env_candidates(resolved_provider)
    for env_var in env_candidates:
        env_api_key = os.getenv(env_var, "").strip()
        if env_api_key:
            return env_api_key
    raise MissingLlmApiKeyError(
        f"Missing LLM API key. Set {env_candidates[0]} (or {', '.join(env_candidates[1:])}) in your .env file or pass api_key in the request."
    )


def get_llm_provider(request_provider: str | None = None) -> str:
    if request_provider and request_provider.strip():
        return _normalize_provider_name(request_provider)
    env_provider = os.getenv(LLM_PROVIDER_ENV_VAR, "").strip()
    if env_provider:
        return _normalize_provider_name(env_provider)
    detected_provider = _detect_provider_from_env()
    if detected_provider:
        return detected_provider
    return DEFAULT_LLM_PROVIDER


def get_llm_model(request_model: str | None = None, provider: str | None = None) -> str:
    resolved_provider = get_llm_provider(provider)
    if request_model and request_model.strip():
        return normalize_llm_model(request_model.strip(), provider=resolved_provider)
    env_model = os.getenv(LLM_MODEL_ENV_VAR, "").strip()
    if env_model:
        return normalize_llm_model(env_model, provider=resolved_provider)
    return get_llm_default_model(resolved_provider)


def get_llm_default_model(provider: str | None = None) -> str:
    resolved_provider = get_llm_provider(provider)
    return DEFAULT_LLM_MODEL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_MODEL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def get_llm_base_url(request_base_url: str | None = None, provider: str | None = None) -> str:
    if request_base_url and request_base_url.strip():
        return request_base_url.strip()
    env_base_url = os.getenv(LLM_BASE_URL_ENV_VAR, "").strip()
    if env_base_url:
        return env_base_url
    resolved_provider = get_llm_provider(provider)
    return DEFAULT_LLM_BASE_URL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_BASE_URL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def normalize_llm_model(model: str, provider: str | None = None) -> str:
    raw_model = str(model or "").strip()
    if not raw_model:
        return get_llm_default_model(provider)
    if get_llm_provider(provider) == "anthropic":
        alias_key = raw_model.lower().replace("·", " ").strip()
        return ANTHROPIC_MODEL_ALIASES.get(alias_key, raw_model)
    return raw_model


def _detect_provider_from_env() -> str | None:
    raw_provider_model = os.getenv(LLM_MODEL_ENV_VAR, "").strip().lower()
    api_key_candidates = [
        os.getenv(LLM_API_KEY_ENV_VAR, "").strip(),
        os.getenv(LEGACY_LLM_API_KEY_ENV_VAR, "").strip(),
        os.getenv(ANTHROPIC_LLM_API_KEY_ENV_VAR, "").strip(),
    ]
    if any(key.startswith("sk-ant") for key in api_key_candidates if key):
        return "anthropic"
    if any(token in raw_provider_model for token in ("claude", "sonnet", "haiku", "opus")):
        return "anthropic"
    return None


def _llm_api_key_env_candidates(provider: str) -> list[str]:
    normalized = _normalize_provider_name(provider)
    if normalized == "anthropic":
        return [ANTHROPIC_LLM_API_KEY_ENV_VAR, LLM_API_KEY_ENV_VAR, LEGACY_LLM_API_KEY_ENV_VAR]
    return [LLM_API_KEY_ENV_VAR, LEGACY_LLM_API_KEY_ENV_VAR, ANTHROPIC_LLM_API_KEY_ENV_VAR]


def _normalize_provider_name(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")
