from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routes.helpers import CvGenerationHttpError, generate_cv_for_request
from app.schemas.job_matching import CvGenerateRequest, ManualJobMatchRequest
from app.schemas.profile_generation import ProfileGenerateRequest
from app.services.job_file_parser import JobFileParseError
from app.services.job_matching import JobMatchingService, build_job_matching_service_from_env
from app.services.profile_generation import ProfileGenerationService, build_profile_generation_service_from_env
from app.services.profile_snapshot import load_profile_snapshot
from app.services.settings import get_job_matching_settings, get_llm_provider

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def get_job_matching_service() -> JobMatchingService:
    return build_job_matching_service_from_env()


def get_profile_generation_service() -> ProfileGenerationService:
    return build_profile_generation_service_from_env()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    settings = get_job_matching_settings()
    profile = load_profile_snapshot(settings.profile_json_path)
    return templates.TemplateResponse(request=request, name="index.html", context={"profile": profile})


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


@router.post("/ui/profile/generate", response_class=HTMLResponse)
async def generate_profile_ui(
    request: Request,
    public_repo_urls: str = Form(default=""),
    local_repo_paths: str = Form(default=""),
    append_evidence: bool = Form(default=False),
    service: ProfileGenerationService = Depends(get_profile_generation_service),
) -> HTMLResponse:
    try:
        logger.info(
            "profile ui update requested",
            extra={
                "public_repo_url_chars": len(public_repo_urls),
                "local_repo_path_chars": len(local_repo_paths),
                "append_evidence": append_evidence,
            },
        )
        payload = ProfileGenerateRequest.model_validate(
            {
                "public_repo_urls": public_repo_urls,
                "local_repo_paths": local_repo_paths,
                "append_evidence": append_evidence,
            }
        )
        result = await service.generate_profile(payload)
    except ValueError as exc:
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)
    profile = load_profile_snapshot(service.settings.profile_json_path)
    logger.info(
        "profile ui update response rendered",
        extra={
            "status": result.status,
            "repos_analyzed": result.repos_analyzed,
            "profile_capability_count": profile.capability_count,
            "profile_path": str(profile.path),
        },
    )
    return templates.TemplateResponse(request=request, name="partials/profile_generation.html", context={"result": result, "profile": profile})


@router.post("/ui/cv/generate", response_class=HTMLResponse)
async def generate_cv_ui(
    request: Request,
    company: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    location: str = Form(default=""),
    source_url: str = Form(default=""),
    language: str = Form(default="en"),
    provider: str = Form(default=""),
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
        provider=provider.strip() or get_llm_provider(),
        model=model or None,
        base_url=base_url or None,
    )
    try:
        generated = await generate_cv_for_request(service, payload, source="ui")
    except CvGenerationHttpError as exc:
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request=request, name="partials/generated_cv.html", context={"generated": generated})
