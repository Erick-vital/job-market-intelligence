from __future__ import annotations

import sqlite3
from typing import Any

from app.models.job_matching import CompanySignal, JobMatchResult, normalize_company_name


class CompanySignalStore:
    """Aggregates per-company observation signals inside the job store's SQLite database."""

    def init_schema(self, conn: sqlite3.Connection) -> None:
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

    def upsert_from_matches(
        self,
        conn: sqlite3.Connection,
        *,
        batch_id: str,
        now: str,
        observed_date: str,
        matches: list[JobMatchResult],
    ) -> list[CompanySignal]:
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
