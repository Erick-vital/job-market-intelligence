from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class ProfileGenerateRequest(BaseModel):
    public_repo_urls: list[str] = Field(default_factory=list)
    local_repo_paths: list[str] = Field(default_factory=list)
    append_evidence: bool = True

    @field_validator("public_repo_urls", "local_repo_paths", mode="before")
    @classmethod
    def split_textarea_lines(cls, value):
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return value or []

    @model_validator(mode="after")
    def require_at_least_one_source(self):
        if not self.public_repo_urls and not self.local_repo_paths:
            raise ValueError("Provide at least one public repo URL or local repo path.")
        return self


class ProfileGenerateRepoSummary(BaseModel):
    source: str
    source_type: str
    status: str
    signals: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    warning: str | None = None


class ProfileGenerateResponse(BaseModel):
    status: str
    repos_analyzed: int
    evidence_rows_written: int
    technical_profile_path: str
    evidence_path: str
    repos: list[ProfileGenerateRepoSummary]
