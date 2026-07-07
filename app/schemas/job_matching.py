from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

from app.models.job_matching import JobPosting
from app.services.settings import get_llm_provider


class JobRecordIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: str = ""
    location: str = ""
    source_url: str = ""
    source_job_id: str = ""
    posted_text: str = ""
    capture_method: str = ""
    source: str = "linkedin_jobs"

    def to_job(self, raw: dict[str, Any]) -> JobPosting:
        return JobPosting(
            company=self.company,
            title=self.title,
            description=self.description or "",
            location=self.location or "",
            source_url=self.source_url or "",
            source_job_id=str(self.source_job_id or ""),
            posted_text=self.posted_text or "",
            capture_method=self.capture_method or "",
            source=self.source or "linkedin_jobs",
            raw=raw,
        )


class JobMatchResponse(BaseModel):
    status: str
    batch_id: str
    processed: int
    inserted: int
    updated_duplicates: int
    skipped_invalid: int
    matches: list[dict]
    report: dict[str, Any]
    paths: dict[str, str]


class ManualJobMatchRequest(BaseModel):
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    location: str = ""
    source_url: str = ""

    def to_job(self) -> JobPosting:
        return JobPosting(
            company=self.company,
            title=self.title,
            description=self.description,
            location=self.location,
            source_url=self.source_url,
            capture_method="manual",
            source="manual",
            raw={"manual_entry": True},
        )


class ManualJobMatchResponse(BaseModel):
    status: str
    match: dict[str, Any]


class CvGenerateRequest(BaseModel):
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    api_key: str | None = None
    location: str = ""
    source_url: str = ""
    language: str = "en"
    provider: str = get_llm_provider()
    model: str | None = None
    base_url: str | None = None

    def to_job(self) -> JobPosting:
        return JobPosting(
            company=self.company,
            title=self.title,
            description=self.description,
            location=self.location,
            source_url=self.source_url,
            capture_method="manual_cv_generation",
            source="manual",
            raw={"manual_entry": True},
        )


class CvGenerateResponse(BaseModel):
    status: str
    markdown: str
    path: str
    matched_capabilities: list[str]
    provider: str
    model: str
