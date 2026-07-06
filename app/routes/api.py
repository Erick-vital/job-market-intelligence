from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.schemas.job_matching import JobMatchResponse
from app.services.job_file_parser import JobFileParseError
from app.services.job_matching import JobMatchingService, build_job_matching_service_from_env

router = APIRouter(prefix="/api", tags=["job-intelligence"])


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
