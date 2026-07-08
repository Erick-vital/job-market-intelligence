from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.company_signals import CompanySignalStore
from app.services.market_report import build_market_report, report_to_markdown

from app.models.job_matching import (
    JobBatchResult,
    JobMatchResult,
    SavedJob,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ResolvedJob:
    job_id: str
    item_dir: Path
    inserted: bool


class JobStore:
    def __init__(self, *, data_dir: Path, items_dir: Path) -> None:
        self.data_dir = data_dir
        self.items_dir = items_dir
        self.db_path = data_dir / "job_market_intelligence.sqlite"
        self.company_signals = CompanySignalStore()

    def init_db(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'linkedin_jobs',
                    source_job_id TEXT,
                    source_url TEXT,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT,
                    description_preview TEXT,
                    fit_score REAL NOT NULL DEFAULT 0,
                    fit_level TEXT NOT NULL DEFAULT 'none',
                    matched_skills_json TEXT NOT NULL DEFAULT '[]',
                    missing_skills_json TEXT NOT NULL DEFAULT '[]',
                    item_dir TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    md_path TEXT NOT NULL,
                    match_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_match_batches (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source_filename TEXT,
                    processed INTEGER NOT NULL,
                    inserted INTEGER NOT NULL,
                    updated_duplicates INTEGER NOT NULL,
                    skipped_invalid INTEGER NOT NULL,
                    summary_path TEXT NOT NULL
                )
                """
            )
            self.company_signals.init_schema(conn)
            conn.commit()

    def save_batch(
        self,
        *,
        source_filename: str,
        matches: list[JobMatchResult],
        skipped_invalid: int,
        selected_matches: list[JobMatchResult],
    ) -> JobBatchResult:
        self.init_db()
        batch_id = _new_id("jobbatch")
        batch_dir = self.items_dir / "batches" / batch_id
        batch_dir.mkdir(parents=True, exist_ok=False)
        now = _iso_now()

        # Phase 1: resolve identities with a read-only pass.
        with self._connect() as conn:
            resolved: list[_ResolvedJob] = []
            seen: dict[str, _ResolvedJob] = {}
            for match in matches:
                dedupe_key = match.job.dedupe_key()
                if dedupe_key in seen:
                    prior = seen[dedupe_key]
                    resolved.append(_ResolvedJob(job_id=prior.job_id, item_dir=prior.item_dir, inserted=False))
                    continue
                resolution = self._resolve_job(conn, dedupe_key)
                seen[dedupe_key] = resolution
                resolved.append(resolution)

        # Phase 2: write filesystem artifacts outside any DB transaction.
        saved_jobs: list[SavedJob] = []
        for match, resolution in zip(matches, resolved):
            saved_jobs.append(self._write_job_files(batch_id=batch_id, match=match, resolution=resolution))
        inserted = sum(1 for item in resolved if item.inserted)
        updated = len(resolved) - inserted

        report = build_market_report(matches, selected_matches)
        summary = {
            "batch_id": batch_id,
            "created_at": now,
            "source_filename": source_filename,
            "processed": len(matches),
            "inserted": inserted,
            "updated_duplicates": updated,
            "skipped_invalid": skipped_invalid,
            "matches_count": len(selected_matches),
        }
        summary_path = batch_dir / "summary.json"
        matches_path = batch_dir / "matches.json"
        report_path = batch_dir / "report.md"
        _write_json(summary_path, {**summary, "report": report})
        _write_json(matches_path, {"matches": [match.to_response_dict() for match in selected_matches]})
        report_path.write_text(report_to_markdown(report), encoding="utf-8")

        # Phase 3: persist all rows in a single transaction.
        with self._connect() as conn:
            for match, resolution in zip(matches, resolved):
                self._upsert_job_row(conn, batch_id=batch_id, now=now, match=match, resolution=resolution)
            self.company_signals.upsert_from_matches(
                conn,
                batch_id=batch_id,
                now=now,
                observed_date=_current_local_date().isoformat(),
                matches=matches,
            )
            conn.execute(
                """
                INSERT INTO job_match_batches
                (id, created_at, source_filename, processed, inserted, updated_duplicates, skipped_invalid, summary_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, now, source_filename, len(matches), inserted, updated, skipped_invalid, str(summary_path)),
            )
            conn.commit()
        logger.info(
            "job matching batch saved",
            extra={
                "batch_id": batch_id,
                "source_filename": source_filename,
                "processed": len(matches),
                "inserted": inserted,
                "updated_duplicates": updated,
                "skipped_invalid": skipped_invalid,
                "batch_dir": str(batch_dir),
            },
        )
        return JobBatchResult(
            batch_id=batch_id,
            processed=len(matches),
            inserted=inserted,
            updated_duplicates=updated,
            skipped_invalid=skipped_invalid,
            saved_jobs=saved_jobs,
            summary_path=summary_path,
            matches_path=matches_path,
            report_path=report_path,
            batch_dir=batch_dir,
            summary={**summary, "report": report},
        )

    def _resolve_job(self, conn: sqlite3.Connection, dedupe_key: str) -> _ResolvedJob:
        existing = conn.execute("SELECT id, item_dir FROM job_postings WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        if existing is None:
            job_id = _new_id("job")
            return _ResolvedJob(job_id=job_id, item_dir=self.items_dir / job_id, inserted=True)
        return _ResolvedJob(job_id=existing["id"], item_dir=Path(existing["item_dir"]), inserted=False)

    def _write_job_files(self, *, batch_id: str, match: JobMatchResult, resolution: _ResolvedJob) -> SavedJob:
        item_dir = resolution.item_dir
        item_dir.mkdir(parents=True, exist_ok=True)
        json_path = item_dir / "job.json"
        md_path = item_dir / "job.md"
        match_path = item_dir / "match.json"
        match.job_id = resolution.job_id
        match.item_path = str(json_path)

        _write_json(json_path, _job_json(resolution.job_id, batch_id, match.job))
        md_path.write_text(_job_markdown(resolution.job_id, match.job), encoding="utf-8")
        _write_json(match_path, _match_json(match))
        return SavedJob(
            job_id=resolution.job_id,
            item_dir=item_dir,
            json_path=json_path,
            md_path=md_path,
            match_path=match_path,
            inserted=resolution.inserted,
        )

    def _upsert_job_row(
        self,
        conn: sqlite3.Connection,
        *,
        batch_id: str,
        now: str,
        match: JobMatchResult,
        resolution: _ResolvedJob,
    ) -> None:
        job = match.job
        item_dir = resolution.item_dir
        params = (
            batch_id,
            now,
            job.source,
            job.source_job_id,
            job.source_url,
            job.company,
            job.title,
            job.location,
            _preview(job.description),
            match.fit_score,
            match.fit_level,
            json.dumps(match.matched_skills, ensure_ascii=False),
            json.dumps(match.missing_skills, ensure_ascii=False),
            str(item_dir),
            str(item_dir / "job.json"),
            str(item_dir / "job.md"),
            str(item_dir / "match.json"),
            resolution.job_id,
        )
        if resolution.inserted:
            conn.execute(
                """
                INSERT INTO job_postings
                (batch_id, updated_at, source, source_job_id, source_url, company, title, location,
                 description_preview, fit_score, fit_level, matched_skills_json, missing_skills_json,
                 item_dir, json_path, md_path, match_path, id, dedupe_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*params[:-1], resolution.job_id, job.dedupe_key(), now),
            )
        else:
            conn.execute(
                """
                UPDATE job_postings
                SET batch_id=?, updated_at=?, source=?, source_job_id=?, source_url=?, company=?, title=?, location=?,
                    description_preview=?, fit_score=?, fit_level=?, matched_skills_json=?, missing_skills_json=?,
                    item_dir=?, json_path=?, md_path=?, match_path=?
                WHERE id=?
                """,
                params,
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _job_json(job_id: str, batch_id: str, job) -> dict[str, Any]:
    return {
        "id": job_id,
        "schema_version": "job_posting.v1",
        "batch_id": batch_id,
        "source": job.source,
        "source_job_id": job.source_job_id,
        "source_url": job.source_url,
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "description": job.description,
        "posted_text": job.posted_text,
        "capture_method": job.capture_method,
        "raw": job.raw,
    }


def _match_json(match: JobMatchResult) -> dict[str, Any]:
    return {
        "job_id": match.job_id,
        "fit_score": match.fit_score,
        "fit_level": match.fit_level,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "reasons": match.reasons,
        "risk_flags": match.risk_flags,
        "score_breakdown": match.score_breakdown,
    }


def _job_markdown(job_id: str, job) -> str:
    return f"# {job.title} — {job.company}\n\n- ID: {job_id}\n- Location: {job.location}\n- URL: {job.source_url}\n\n## Description\n\n{job.description}\n"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _preview(text: str, max_chars: int = 200) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized if len(normalized) <= max_chars else normalized[: max_chars - 1].rstrip() + "…"


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _current_local_date() -> date:
    return datetime.now(ZoneInfo("America/Mexico_City")).date()


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
