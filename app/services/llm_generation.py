from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.settings import get_llm_api_key, get_llm_base_url, get_llm_default_model, get_llm_model, get_llm_provider

logger = logging.getLogger(__name__)


class LlmGenerationProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LlmGenerationResult:
    text: str
    provider: str
    model: str


@dataclass(frozen=True)
class LlmGenerationService:
    timeout_seconds: int = 90

    async def generate_text(
        self,
        *,
        system_prompt: str,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LlmGenerationResult:
        resolved_provider = get_llm_provider(provider)
        resolved_api_key = get_llm_api_key(api_key, provider=resolved_provider)
        requested_model = get_llm_model(model, provider=resolved_provider)
        default_model = get_llm_default_model(resolved_provider)
        resolved_base_url = get_llm_base_url(base_url, provider=resolved_provider)
        logger.info(
            "llm generation config resolved",
            extra={
                "provider": resolved_provider,
                "requested_model": requested_model,
                "default_model": default_model,
                "base_url": resolved_base_url,
                "prompt_chars": len(prompt),
                "system_prompt_chars": len(system_prompt),
            },
        )
        try:
            text = await self._generate_once(
                system_prompt=system_prompt,
                prompt=prompt,
                provider=resolved_provider,
                model=requested_model,
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LlmGenerationResult(text=text, provider=resolved_provider, model=requested_model)
        except LlmGenerationProviderError as exc:
            if requested_model != default_model and exc.status_code in {400, 404, 422}:
                logger.warning(
                    "llm generation falling back to default model",
                    extra={
                        "provider": resolved_provider,
                        "requested_model": requested_model,
                        "fallback_model": default_model,
                        "status_code": exc.status_code,
                        "error": str(exc),
                    },
                )
                text = await self._generate_once(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    provider=resolved_provider,
                    model=default_model,
                    base_url=resolved_base_url,
                    api_key=resolved_api_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return LlmGenerationResult(text=text, provider=resolved_provider, model=default_model)
            logger.warning(
                "llm generation provider failed without fallback",
                extra={
                    "provider": resolved_provider,
                    "model": requested_model,
                    "default_model": default_model,
                    "status_code": exc.status_code,
                    "error": str(exc),
                },
            )
            raise

    async def _generate_once(
        self,
        *,
        system_prompt: str,
        prompt: str,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        if provider == "anthropic":
            return await _post_anthropic_message(
                system_prompt=system_prompt,
                prompt=prompt,
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=self.timeout_seconds,
                max_tokens=max_tokens or 2000,
            )
        if provider in {"openai", "openai_compatible"}:
            return await _post_openai_chat_completion(
                system_prompt=system_prompt,
                prompt=prompt,
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=self.timeout_seconds,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        raise LlmGenerationProviderError(f"Unsupported LLM provider: {provider}")


async def _post_openai_chat_completion(
    *,
    system_prompt: str,
    prompt: str,
    api_key: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    temperature: float,
    max_tokens: int | None,
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = await _post_json(endpoint=endpoint, headers=headers, payload=payload, timeout_seconds=timeout_seconds, provider="openai_compatible", model=model)
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmGenerationProviderError("LLM provider returned an unexpected OpenAI-compatible response shape") from exc
    return _normalized_content(content)


async def _post_anthropic_message(
    *,
    system_prompt: str,
    prompt: str,
    api_key: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    max_tokens: int,
) -> str:
    endpoint = base_url.rstrip("/") + "/v1/messages"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    response = await _post_json(endpoint=endpoint, headers=headers, payload=payload, timeout_seconds=timeout_seconds, provider="anthropic", model=model)
    data = response.json()
    try:
        parts = data["content"]
    except (KeyError, TypeError) as exc:
        raise LlmGenerationProviderError("LLM provider returned an unexpected Anthropic response shape") from exc
    texts: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                texts.append(str(part["text"]))
    return _normalized_content("".join(texts))


async def _post_json(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
    provider: str,
    model: str,
) -> httpx.Response:
    logger.info(
        "llm provider request started",
        extra={"provider": provider, "model": model, "endpoint": endpoint, "timeout_seconds": timeout_seconds},
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(
                "llm provider request completed",
                extra={"provider": provider, "model": model, "endpoint": endpoint, "status_code": response.status_code},
            )
            return response
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        response_text = _safe_response_text(exc.response)
        logger.warning(
            "llm provider request returned error status",
            extra={"provider": provider, "model": model, "endpoint": endpoint, "status_code": status_code, "response_body": response_text},
        )
        raise LlmGenerationProviderError(f"LLM provider request failed: {exc}. Response body: {response_text}", status_code=status_code) from exc
    except httpx.HTTPError as exc:
        logger.warning("llm provider request failed", extra={"provider": provider, "model": model, "endpoint": endpoint, "error": str(exc)})
        raise LlmGenerationProviderError(f"LLM provider request failed: {exc}") from exc
    except RuntimeError as exc:
        logger.warning("llm provider request failed", extra={"provider": provider, "model": model, "endpoint": endpoint, "error": str(exc)})
        raise LlmGenerationProviderError(f"LLM provider request failed: {exc}") from exc


def _safe_response_text(response: httpx.Response | None, limit: int = 1000) -> str:
    if response is None:
        return ""
    text = response.text or ""
    return text[:limit]


def _normalized_content(content: object) -> str:
    text = str(content).strip()
    if not text:
        raise LlmGenerationProviderError("LLM provider returned empty content")
    return text + "\n"
