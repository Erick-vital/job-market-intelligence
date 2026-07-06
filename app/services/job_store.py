from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.market_report import build_market_report, report_to_markdown

from app.models.job_matching import (
    CompanySignal,
    JobBatchResult,
    JobMatchResult,
    SavedJob,
    normalize_company_name,
)

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self, *, data_dir: Path, items_dir: Path) -> None:
        self.data_dir = data_dir
        self.items_dir = items_dir
        self.db_path = data_dir / "job_market_intelligence.sqlite"

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS company_signals (
                    company_key TEXT PRIMARY KEY,
                    company_display TEXT NOT NULL,
                    first_seen_date TEXT NOT NULL,
                    last_seen_date TEXT NOT NULL,
                    days_seen INTEGER NOT NULL DEFAULT 1,
                    best_score_ever REAL NOT NULL DEFAULT 0,
                    last_score REAL NOT NULL DEFAULT 0,
                    postings_seen_total INTEGER NOT NULL DEFAULT 0,
                    last_batch_id TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
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
        saved_jobs: list[SavedJob] = []
        inserted = 0
        updated = 0

        with self._connect() as conn:
            for match in matches:
                saved = self._save_job(conn, batch_id=batch_id, now=now, match=match)
                saved_jobs.append(saved)
                if saved.inserted:
                    inserted += 1
                else:
                    updated += 1
            self._upsert_company_signals(conn, batch_id=batch_id, now=now, matches=matches)
            summary_path = batch_dir / "summary.json"
            matches_path = batch_dir / "matches.json"
            report_path = batch_dir / "report.md"
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
            _write_json(summary_path, {**summary, "report": report})
            _write_json(matches_path, {"matches": [match.to_response_dict() for match in selected_matches]})
            report_path.write_text(report_to_markdown(report), encoding="utf-8")
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

    def _upsert_company_signals(
        self,
        conn: sqlite3.Connection,
        *,
        batch_id: str,
        now: str,
        matches: list[JobMatchResult],
    ) -> list[CompanySignal]:
        observed_date = _current_local_date().isoformat()
        grouped = _group_company_matches(matches)
        updated_signals: list[CompanySignal] = []

        for company_key, payload in grouped.items():
            existing = conn.execute(
                "SELECT * FROM company_signals WHERE company_key = ?",
                (company_key,),
            ).fetchone()
            if existing is None:
                signal = CompanySignal(
                    company_key=company_key,
                    company_display=payload["company_display"],
                    first_seen_date=observed_date,
                    last_seen_date=observed_date,
                    days_seen=1,
                    best_score_ever=payload["best_score"],
                    last_score=payload["last_score"],
                    postings_seen_total=payload["postings_seen_total"],
                    last_batch_id=batch_id,
                    updated_at=now,
                )
                conn.execute(
                    """
                    INSERT INTO company_signals
                    (company_key, company_display, first_seen_date, last_seen_date, days_seen,
                     best_score_ever, last_score, postings_seen_total, last_batch_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.company_key,
                        signal.company_display,
                        signal.first_seen_date,
                        signal.last_seen_date,
                        signal.days_seen,
                        signal.best_score_ever,
                        signal.last_score,
                        signal.postings_seen_total,
                        signal.last_batch_id,
                        signal.updated_at,
                    ),
                )
            else:
                same_day = existing["last_seen_date"] == observed_date
                signal = CompanySignal(
                    company_key=company_key,
                    company_display=payload["company_display"] or existing["company_display"],
                    first_seen_date=existing["first_seen_date"],
                    last_seen_date=existing["last_seen_date"] if same_day else observed_date,
                    days_seen=existing["days_seen"] if same_day else existing["days_seen"] + 1,
                    best_score_ever=max(float(existing["best_score_ever"]), payload["best_score"]),
                    last_score=payload["last_score"],
                    postings_seen_total=int(existing["postings_seen_total"]) + payload["postings_seen_total"],
                    last_batch_id=batch_id,
                    updated_at=now,
                )
                conn.execute(
                    """
                    UPDATE company_signals
                    SET company_display = ?,
                        last_seen_date = ?,
                        days_seen = ?,
                        best_score_ever = ?,
                        last_score = ?,
                        postings_seen_total = ?,
                        last_batch_id = ?,
                        updated_at = ?
                    WHERE company_key = ?
                    """,
                    (
                        signal.company_display,
                        signal.last_seen_date,
                        signal.days_seen,
                        signal.best_score_ever,
                        signal.last_score,
                        signal.postings_seen_total,
                        signal.last_batch_id,
                        signal.updated_at,
                        signal.company_key,
                    ),
                )
            updated_signals.append(signal)

        return updated_signals

    def _save_job(self, conn: sqlite3.Connection, *, batch_id: str, now: str, match: JobMatchResult) -> SavedJob:
        job = match.job
        dedupe_key = job.dedupe_key()
        existing = conn.execute("SELECT id, item_dir FROM job_postings WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        inserted = existing is None
        job_id = _new_id("job") if inserted else existing["id"]
        item_dir = self.items_dir / job_id if inserted else Path(existing["item_dir"])
        item_dir.mkdir(parents=True, exist_ok=True)
        json_path = item_dir / "job.json"
        md_path = item_dir / "job.md"
        match_path = item_dir / "match.json"
        match.job_id = job_id
        match.item_path = str(json_path)

        _write_json(json_path, _job_json(job_id, batch_id, job))
        md_path.write_text(_job_markdown(job_id, job), encoding="utf-8")
        _write_json(match_path, _match_json(match))

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
            str(json_path),
            str(md_path),
            str(match_path),
            job_id,
        )
        if inserted:
            conn.execute(
                """
                INSERT INTO job_postings
                (batch_id, updated_at, source, source_job_id, source_url, company, title, location,
                 description_preview, fit_score, fit_level, matched_skills_json, missing_skills_json,
                 item_dir, json_path, md_path, match_path, id, dedupe_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*params[:-1], job_id, dedupe_key, now),
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
        return SavedJob(job_id=job_id, item_dir=item_dir, json_path=json_path, md_path=md_path, match_path=match_path, inserted=inserted)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _group_company_matches(matches: list[JobMatchResult]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for match in matches:
        company_key = normalize_company_name(match.job.company)
        if not company_key:
            continue
        payload = grouped.setdefault(
            company_key,
            {
                "company_display": match.job.company,
                "best_score": 0.0,
                "last_score": 0.0,
                "postings_seen_total": 0,
            },
        )
        payload["postings_seen_total"] += 1
        payload["best_score"] = max(payload["best_score"], match.fit_score)
        payload["last_score"] = match.fit_score
        if not payload["company_display"]:
            payload["company_display"] = match.job.company
    for payload in grouped.values():
        payload["last_score"] = payload["best_score"]
    return grouped


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
