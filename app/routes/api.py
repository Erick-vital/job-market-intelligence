from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.schemas.job_matching import (
    CvGenerateRequest,
    CvGenerateResponse,
    JobMatchResponse,
    ManualJobMatchRequest,
    ManualJobMatchResponse,
)
from app.services.job_file_parser import JobFileParseError
from app.services.cv_generation import CvGenerationProviderError
from app.services.job_matching import JobMatchingService, build_job_matching_service_from_env
from app.services.settings import MissingLlmApiKeyError

router = APIRouter(prefix="/api", tags=["job-intelligence"])
logger = logging.getLogger(__name__)


def get_job_matching_service() -> JobMatchingService:
    return build_job_matching_service_from_env()


@router.post("/jobs/import", response_model=JobMatchResponse)
async def import_jobs(
    file: UploadFile = File(...),
    max_matches: int = Form(default=8),
    min_score: float | None = Form(default=None),
    service: JobMatchingService = Depends(get_job_matching_service),
) -> JobMatchResponse:
    raw = await file.read()
    try:
        result = await service.process_file(
            raw=raw,
            filename=file.filename or "jobs.csv",
            max_matches=max_matches,
            min_score=min_score,
        )
    except JobFileParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    batch = result.batch
    return JobMatchResponse(
        status="completed",
        batch_id=batch.batch_id,
        processed=batch.processed,
        inserted=batch.inserted,
        updated_duplicates=batch.updated_duplicates,
        skipped_invalid=batch.skipped_invalid,
        matches=[match.to_response_dict() for match in result.matches],
        report=batch.summary.get("report", {}),
        paths={
            "summary_json": str(batch.summary_path),
            "matches_json": str(batch.matches_path),
            "report_markdown": str(batch.report_path),
            "batch_dir": str(batch.batch_dir),
        },
    )


@router.post("/jobs/match", response_model=ManualJobMatchResponse)
async def match_manual_job(
    payload: ManualJobMatchRequest,
    service: JobMatchingService = Depends(get_job_matching_service),
) -> ManualJobMatchResponse:
    match = await service.match_manual_job(job=payload.to_job())
    return ManualJobMatchResponse(status="completed", match=match.to_response_dict())


@router.post("/cv/generate", response_model=CvGenerateResponse)
async def generate_cv(
    payload: CvGenerateRequest,
    service: JobMatchingService = Depends(get_job_matching_service),
) -> CvGenerateResponse:
    try:
        logger.info(
            "cv api generate requested",
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
        generated = await service.generate_cv(
            job=payload.to_job(),
            api_key=payload.api_key,
            language=payload.language,
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
        )
    except MissingLlmApiKeyError as exc:
        logger.warning("cv api generate missing api key", extra={"provider": payload.provider, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CvGenerationProviderError as exc:
        logger.warning(
            "cv api generate provider error",
            extra={"provider": payload.provider, "model": payload.model, "status_code": exc.status_code, "error": str(exc)},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    logger.info(
        "cv api generate completed",
        extra={"provider": generated.provider, "model": generated.model, "path": str(generated.path)},
    )
    return CvGenerateResponse(
        status="completed",
        markdown=generated.markdown,
        path=str(generated.path),
        matched_capabilities=generated.matched_capabilities,
        provider=generated.provider,
        model=generated.model,
    )
