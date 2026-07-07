from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas.job_matching import CvGenerateRequest, ManualJobMatchRequest
from app.services.job_file_parser import JobFileParseError
from app.services.job_matching import JobMatchingService, build_job_matching_service_from_env

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


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
    service: JobMatchingService = Depends(get_job_matching_service),
) -> HTMLResponse:
    payload = CvGenerateRequest(
        company=company,
        title=title,
        description=description,
        location=location,
        source_url=source_url,
        language=language,
    )
    generated = await service.generate_cv(job=payload.to_job(), language=payload.language)
    return templates.TemplateResponse(request=request, name="partials/generated_cv.html", context={"generated": generated})
