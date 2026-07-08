from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def normalize_url(url: str) -> str:
    return str(url or "").strip().rstrip("/").lower()


def normalize_company_name(name: str) -> str:
    text = _compact(name).lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(
        r"(?:incorporated|inc|llc|ltd|limited|corp|corporation|co|s\.?a\.?|s\.?a\.??\s*de\s*c\.?v\.?)",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class JobPosting:
    company: str
    title: str
    description: str = ""
    location: str = ""
    source_url: str = ""
    source_job_id: str = ""
    posted_text: str = ""
    capture_method: str = ""
    source: str = "linkedin_jobs"
    raw: dict[str, Any] = field(default_factory=dict)

    def matching_text(self) -> str:
        parts = [
            self.title,
            self.company,
            self.location,
            self.description,
            self.posted_text,
            str(self.raw.get("detail_text") or ""),
            str(self.raw.get("card_text") or ""),
        ]
        return "\n".join(part for part in parts if part).strip()

    def dedupe_key(self) -> str:
        if self.source_job_id:
            return f"job_id:{self.source_job_id}"
        if self.source_url:
            return f"url:{normalize_url(self.source_url)}"
        fingerprint = "|".join([
            _compact(self.company).lower(),
            _compact(self.title).lower(),
            _compact(self.location).lower(),
            _compact(self.description)[:300].lower(),
        ])
        return "hash:" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]


@dataclass
class JobMatchResult:
    job: JobPosting
    fit_score: float
    fit_level: str
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]
    score_breakdown: dict[str, float]
    rank: int | None = None
    item_path: str = ""
    job_id: str = ""
    risk_flags: list[str] = field(default_factory=list)

    def to_response_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "rank": self.rank,
            "fit_score": round(self.fit_score, 3),
            "fit_level": self.fit_level,
            "company": self.job.company,
            "title": self.job.title,
            "location": self.job.location,
            "source_url": self.job.source_url,
            "source_job_id": self.job.source_job_id,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "reasons": self.reasons,
            "risk_flags": self.risk_flags,
            "item_path": self.item_path,
        }


@dataclass(frozen=True)
class SavedJob:
    job_id: str
    item_dir: Path
    json_path: Path
    md_path: Path
    match_path: Path
    inserted: bool


@dataclass(frozen=True)
class JobBatchResult:
    batch_id: str
    processed: int
    inserted: int
    updated_duplicates: int
    skipped_invalid: int
    saved_jobs: list[SavedJob]
    summary_path: Path
    matches_path: Path
    report_path: Path
    batch_dir: Path
    summary: dict[str, Any]


@dataclass(frozen=True)
class CompanySignal:
    company_key: str
    company_display: str
    first_seen_date: str
    last_seen_date: str
    days_seen: int
    best_score_ever: float
    last_score: float
    postings_seen_total: int
    last_batch_id: str | None = None
    updated_at: str | None = None


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
