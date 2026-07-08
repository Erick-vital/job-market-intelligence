from __future__ import annotations

import logging

from app.schemas.job_matching import CvGenerateRequest
from app.services.cv_generation import CvGenerationProviderError, GeneratedCv
from app.services.job_matching import JobMatchingService
from app.services.settings import MissingLlmApiKeyError

logger = logging.getLogger(__name__)


class CvGenerationHttpError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def generate_cv_for_request(
    service: JobMatchingService, payload: CvGenerateRequest, *, source: str
) -> GeneratedCv:
    """Run CV generation with shared logging and error-to-HTTP-status mapping."""
    logger.info(
        f"cv {source} generate requested",
        extra={
            "provider": payload.provider,
            "model_supplied": bool(payload.model),
            "base_url_supplied": bool(payload.base_url),
            "language": payload.language,
            "company": payload.company,
            "title": payload.title,
            "description_chars": len(payload.description),
        },
    )
    try:
        generated = await service.generate_cv(
            job=payload.to_job(),
            api_key=payload.api_key,
            language=payload.language,
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
        )
    except MissingLlmApiKeyError as exc:
        logger.warning(f"cv {source} generate missing api key", extra={"provider": payload.provider, "error": str(exc)})
        raise CvGenerationHttpError(status_code=400, detail=str(exc)) from exc
    except CvGenerationProviderError as exc:
        logger.warning(
            f"cv {source} generate provider error",
            extra={"provider": payload.provider, "model": payload.model, "status_code": exc.status_code, "error": str(exc)},
        )
        raise CvGenerationHttpError(status_code=502, detail=str(exc)) from exc
    logger.info(
        f"cv {source} generate completed",
        extra={"provider": generated.provider, "model": generated.model, "path": str(generated.path)},
    )
    return generated
