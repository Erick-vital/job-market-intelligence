from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.schemas.profile_generation import ProfileGenerateRepoSummary, ProfileGenerateRequest, ProfileGenerateResponse
from app.services.profile_evidence import RepoEvidenceRow, analyze_public_repos, analyze_repo_for_evidence, resolve_local_repo_source
from app.services.settings import JobMatchingSettings, get_job_matching_settings
from app.services.technical_profile_generation import generate_technical_profile, generate_technical_profile_with_skill

logger = logging.getLogger(__name__)


@dataclass
class ProfileGenerationService:
    settings: JobMatchingSettings
    use_llm: bool = True

    async def generate_profile(self, request: ProfileGenerateRequest) -> ProfileGenerateResponse:
        logger.info(
            "profile generation requested",
            extra={"public_repo_url_count": len(request.public_repo_urls), "local_repo_path_count": len(request.local_repo_paths)},
        )
        repo_results: list[ProfileGenerateRepoSummary] = []
        evidence_rows: list[RepoEvidenceRow] = []

        for path_value in request.local_repo_paths:
            source = resolve_local_repo_source(path_value)
            if source.repo_path is None:
                repo_results.append(
                    ProfileGenerateRepoSummary(
                        source=source.source,
                        source_type=source.source_type,
                        status="failed",
                        warning=source.warning,
                    )
                )
                continue
            rows = analyze_repo_for_evidence(repo_path=source.repo_path, repo_label=source.source)
            evidence_rows.extend(rows)
            repo_results.append(
                ProfileGenerateRepoSummary(
                    source=source.source,
                    source_type=source.source_type,
                    status="completed",
                    signals=[row.signal for row in rows],
                    evidence_count=len(rows),
                )
            )

        for source, rows in analyze_public_repos(request.public_repo_urls):
            evidence_rows.extend(rows)
            repo_results.append(
                ProfileGenerateRepoSummary(
                    source=source.source,
                    source_type=source.source_type,
                    status="completed" if source.repo_path else "failed",
                    signals=[row.signal for row in rows],
                    evidence_count=len(rows),
                    warning=source.warning,
                )
            )

        evidence_path = self.settings.profile_json_path.parent / "repo_evidence.jsonl"
        written_count = _write_evidence_rows(evidence_path=evidence_path, rows=evidence_rows, append=request.append_evidence)
        if self.use_llm:
            profile_result = await generate_technical_profile_with_skill(evidence_path=evidence_path, output_path=self.settings.profile_json_path)
        else:
            profile_result = generate_technical_profile(evidence_path=evidence_path, output_path=self.settings.profile_json_path)
        repos_analyzed = sum(1 for item in repo_results if item.status == "completed")
        status = "completed" if repos_analyzed else "failed"
        logger.info(
            "profile generation completed",
            extra={
                "status": status,
                "repos_analyzed": repos_analyzed,
                "evidence_rows_written": written_count,
                "technical_profile_path": str(profile_result.output_path),
                "skill_taxonomy_path": str(profile_result.output_path.parent / "skill_taxonomy.yaml"),
                "evidence_path": str(evidence_path),
                "technical_profile_generation_mode": profile_result.generation_mode,
                "technical_profile_llm_provider": profile_result.llm_provider,
                "technical_profile_llm_model": profile_result.llm_model,
                "technical_profile_llm_fallback_reason": profile_result.llm_fallback_reason,
            },
        )
        return ProfileGenerateResponse(
            status=status,
            repos_analyzed=repos_analyzed,
            evidence_rows_written=written_count,
            technical_profile_path=str(profile_result.output_path),
            evidence_path=str(evidence_path),
            repos=repo_results,
        )


def _write_evidence_rows(*, evidence_path: Path, rows: list[RepoEvidenceRow], append: bool) -> int:
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines: list[str] = []
    existing_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    if append and evidence_path.exists():
        existing_lines = evidence_path.read_text(encoding="utf-8").splitlines()
        for line in existing_lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing_keys.add((str(payload.get("repo", "")), str(payload.get("signal", "")), tuple(sorted(payload.get("paths", [])))))

    new_lines: list[str] = []
    seen_new: set[tuple[str, str, tuple[str, ...]]] = set()
    for row in rows:
        key = row.dedupe_key()
        if key in existing_keys or key in seen_new:
            continue
        seen_new.add(key)
        new_lines.append(row.to_json_line())

    all_lines = [line for line in existing_lines if line.strip()] + new_lines if append else new_lines
    evidence_path.write_text(("\n".join(all_lines) + "\n") if all_lines else "", encoding="utf-8")
    return len(new_lines)


def build_profile_generation_service_from_env() -> ProfileGenerationService:
    return ProfileGenerationService(settings=get_job_matching_settings())
