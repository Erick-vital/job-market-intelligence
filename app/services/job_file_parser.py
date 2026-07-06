from __future__ import annotations

import csv
import io
import json
from typing import Any

from pydantic import ValidationError

from app.schemas.job_matching import JobRecordIn
from app.models.job_matching import JobPosting


class JobFileParseError(ValueError):
    pass


def parse_job_file(raw: bytes, filename: str) -> tuple[list[JobPosting], int]:
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise JobFileParseError("Uploaded file is empty")

    lower_filename = (filename or "").lower()
    if lower_filename.endswith((".jsonl", ".ndjson")) or (not lower_filename.endswith(".csv") and text.startswith("{")):
        records = _parse_jsonl(text)
    else:
        records = _parse_csv(text)

    jobs: list[JobPosting] = []
    skipped_invalid = 0
    for record in records:
        normalized = _normalize_record(record)
        try:
            parsed = JobRecordIn.model_validate(normalized)
        except ValidationError:
            skipped_invalid += 1
            continue
        jobs.append(parsed.to_job(raw=record))
    return jobs, skipped_invalid


def _parse_jsonl(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JobFileParseError(f"Invalid JSONL line: {line[:80]}") from exc
        if isinstance(item, dict):
            records.append(item)
    if not records:
        raise JobFileParseError("No records found in uploaded file")
    return records


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "company" not in reader.fieldnames or "title" not in reader.fieldnames:
        raise JobFileParseError("CSV must include company and title headers")
    return [dict(row) for row in reader]


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    if not normalized.get("description"):
        normalized["description"] = normalized.get("detail_text") or normalized.get("card_text") or ""
    if not normalized.get("source_url"):
        normalized["source_url"] = normalized.get("url") or ""
    if not normalized.get("source_job_id"):
        normalized["source_job_id"] = normalized.get("job_id") or ""
    return normalized
