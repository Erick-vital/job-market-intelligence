from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas.job_matching import CvGenerateRequest, ManualJobMatchRequest
from app.services.cv_generation import CvGenerationProviderError
from app.services.job_file_parser import JobFileParseError
from app.services.job_matching import JobMatchingService, build_job_matching_service_from_env
from app.services.settings import MissingLlmApiKeyError, get_llm_provider

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def get_job_matching_service() -> JobMatchingService:
    return build_job_matching_service_from_env()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={})


@router.post("/ui/jobs/import", response_class=HTMLResponse)
async def import_jobs_ui(
    request: Request,
    file: UploadFile = File(...),
    max_matches: int = Form(default=8),
    min_score: float | None = Form(default=None),
    service: JobMatchingService = Depends(get_job_matching_service),
) -> HTMLResponse:
    raw = await file.read()
    try:
        result = await service.process_file(
            raw=raw,
            filename=file.filename or "jobs.csv",
            max_matches=max_matches,
            min_score=min_score,
        )
    except JobFileParseError as exc:
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)
    return templates.TemplateResponse(
        request=request,
        name="partials/results.html",
        context={"batch": result.batch, "matches": result.matches, "report": result.batch.summary.get("report", {})},
    )


@router.post("/ui/jobs/match", response_class=HTMLResponse)
async def match_manual_job_ui(
    request: Request,
    company: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    location: str = Form(default=""),
    source_url: str = Form(default=""),
    service: JobMatchingService = Depends(get_job_matching_service),
) -> HTMLResponse:
    payload = ManualJobMatchRequest(company=company, title=title, description=description, location=location, source_url=source_url)
    match = await service.match_manual_job(job=payload.to_job())
    return templates.TemplateResponse(request=request, name="partials/manual_match.html", context={"match": match})


@router.post("/ui/cv/generate", response_class=HTMLResponse)
async def generate_cv_ui(
    request: Request,
    company: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    location: str = Form(default=""),
    source_url: str = Form(default=""),
    language: str = Form(default="en"),
    provider: str = Form(default=get_llm_provider()),
    model: str = Form(default=""),
    base_url: str = Form(default=""),
    service: JobMatchingService = Depends(get_job_matching_service),
) -> HTMLResponse:
    payload = CvGenerateRequest(
        company=company,
        title=title,
        description=description,
        location=location,
        source_url=source_url,
        language=language,
        provider=provider,
        model=model or None,
        base_url=base_url or None,
    )
    try:
        logger.info(
            "cv ui generate requested",
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
        logger.warning("cv ui generate missing api key", extra={"provider": payload.provider, "error": str(exc)})
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)
    except CvGenerationProviderError as exc:
        logger.warning(
            "cv ui generate provider error",
            extra={"provider": payload.provider, "model": payload.model, "status_code": exc.status_code, "error": str(exc)},
        )
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=502)
    logger.info(
        "cv ui generate completed",
        extra={"provider": generated.provider, "model": generated.model, "path": str(generated.path)},
    )
    return templates.TemplateResponse(request=request, name="partials/generated_cv.html", context={"generated": generated})
