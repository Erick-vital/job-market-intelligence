from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.job_matching import JobBatchResult, JobMatchResult, JobPosting
from app.services.cv_generation import GeneratedCv, generate_targeted_cv
from app.services.job_file_parser import parse_job_file
from app.services.job_store import JobStore
from app.services.profile_matcher import load_profile, rank_matches, score_job
from app.services.settings import JobMatchingSettings, get_job_matching_settings

logger = logging.getLogger(__name__)


@dataclass
class JobMatchingResponseData:
    batch: JobBatchResult
    matches: list[JobMatchResult]


@dataclass
class JobMatchingService:
    settings: JobMatchingSettings

    async def process_file(
        self,
        *,
        raw: bytes,
        filename: str,
        max_matches: int = 8,
        min_score: float | None = None,
    ) -> JobMatchingResponseData:
        jobs, skipped_invalid = parse_job_file(raw, filename)
        profile = load_profile(self.settings.profile_json_path, self.settings.skill_taxonomy_path)
        scored = [score_job(job, profile) for job in jobs]
        threshold = self.settings.min_score if min_score is None else min_score
        selected = rank_matches(scored, min_score=threshold, max_matches=max_matches)
        store = JobStore(data_dir=self.settings.data_dir, items_dir=self.settings.jobs_items_dir)
        batch = store.save_batch(
            source_filename=filename,
            matches=scored,
            skipped_invalid=skipped_invalid,
            selected_matches=selected,
        )
        logger.info("job matching batch completed", extra={"batch_id": batch.batch_id, "processed": batch.processed})
        return JobMatchingResponseData(batch=batch, matches=selected)

    async def match_manual_job(self, *, job: JobPosting) -> JobMatchResult:
        profile = load_profile(self.settings.profile_json_path, self.settings.skill_taxonomy_path)
        match = score_job(job, profile)
        match.rank = 1
        logger.info(
            "manual job match completed",
            extra={"company": job.company, "title": job.title, "fit_score": match.fit_score, "fit_level": match.fit_level},
        )
        return match

    async def generate_cv(self, *, job: JobPosting, language: str = "en") -> GeneratedCv:
        output_dir = self.settings.jobs_items_dir.parent / "cvs"
        cv = generate_targeted_cv(
            profile_json_path=self.settings.profile_json_path,
            output_dir=output_dir,
            job=job,
            language=language,
        )
        logger.info(
            "targeted cv generated",
            extra={"company": job.company, "title": job.title, "path": str(cv.path)},
        )
        return cv


def build_job_matching_service_from_env() -> JobMatchingService:
    return JobMatchingService(settings=get_job_matching_settings())
