from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".cache"}
TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".js",
    ".ts",
    ".tsx",
    ".html",
    ".css",
}


@dataclass(frozen=True)
class RepoEvidenceRow:
    repo: str
    signal: str
    paths: list[str]
    capabilities: list[str]
    skills: list[str]
    confidence: str
    notes: str

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    def dedupe_key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.repo, self.signal, tuple(sorted(self.paths)))


@dataclass(frozen=True)
class ResolvedRepoSource:
    source: str
    source_type: str
    repo_path: Path | None
    warning: str | None = None


def analyze_repo_for_evidence(*, repo_path: Path, repo_label: str) -> list[RepoEvidenceRow]:
    repo_path = repo_path.expanduser().resolve()
    files = _repo_files(repo_path)
    text_index = _text_index(repo_path, files)
    lower_paths = {path.lower() for path in files}
    text_blob = "\n".join(text_index.values()).lower()
    rows: list[RepoEvidenceRow] = []

    if _has_any(lower_paths, {"pyproject.toml", "requirements.txt"}) and ("fastapi" in text_blob or "from fastapi" in text_blob):
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="fastapi_project",
                paths=_matching_paths(files, ["pyproject.toml", "requirements.txt", "app/main.py", "main.py", "app/routes"]),
                capabilities=["backend_python_api_design"],
                skills=["Python", "FastAPI", "REST APIs"],
                confidence="high",
                notes="FastAPI backend structure detected from project files and imports.",
            )
        )
    elif any(path.endswith(".py") for path in files):
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="python_project",
                paths=_matching_paths(files, ["pyproject.toml", "requirements.txt", "setup.py"]),
                capabilities=["python_software_development"],
                skills=["Python"],
                confidence="medium",
                notes="Python project files detected.",
            )
        )

    test_paths = [path for path in files if path.startswith("tests/") or Path(path).name.startswith("test_")]
    if test_paths or "pytest" in text_blob:
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="automated_testing",
                paths=sorted(test_paths[:12]) or _matching_paths(files, ["pyproject.toml", "pytest.ini"]),
                capabilities=["automated_testing"],
                skills=["pytest" if "pytest" in text_blob else "Automated testing"],
                confidence="high" if test_paths else "medium",
                notes="Automated test files or pytest configuration detected.",
            )
        )

    if any("sqlite" in value.lower() or "sqlalchemy" in value.lower() for value in text_index.values()):
        skills = ["SQLite"]
        if "sqlalchemy" in text_blob:
            skills.append("SQLAlchemy")
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="local_persistence",
                paths=_paths_containing(text_index, ["sqlite", "sqlalchemy"]),
                capabilities=["local_persistence_and_data_modeling"],
                skills=skills,
                confidence="medium_high",
                notes="Persistence-related code or configuration detected.",
            )
        )

    llm_terms = ["openai", "anthropic", "llm", "agent", "prompt"]
    if any(term in text_blob for term in llm_terms):
        skills = ["LLM APIs"]
        if "openai" in text_blob:
            skills.append("OpenAI-compatible APIs")
        if "anthropic" in text_blob:
            skills.append("Anthropic")
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="llm_or_agent_integration",
                paths=_paths_containing(text_index, llm_terms),
                capabilities=["llm_and_agent_workflow_integration"],
                skills=skills,
                confidence="medium_high",
                notes="LLM, agent, or prompt integration signals detected.",
            )
        )

    if any(path.startswith("scripts/") for path in files):
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="automation_scripts",
                paths=sorted([path for path in files if path.startswith("scripts/")][:12]),
                capabilities=["automation_workflow_orchestration"],
                skills=["Python", "CLI automation"],
                confidence="medium",
                notes="Automation scripts detected.",
            )
        )

    frontend_skills = []
    if "htmx" in text_blob:
        frontend_skills.append("HTMX")
    if "jinja2" in text_blob or any(path.startswith("app/templates/") for path in files):
        frontend_skills.append("Jinja2")
    if any(path.endswith(('.js', '.ts', '.tsx', '.html', '.css')) for path in files):
        frontend_skills.extend(["HTML", "CSS", "JavaScript"])
    if frontend_skills:
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="frontend_ui",
                paths=_matching_paths(files, ["app/templates", "app/static", "src", "package.json"]),
                capabilities=["frontend_ui_development"],
                skills=sorted(set(frontend_skills)),
                confidence="medium",
                notes="Frontend/UI templates, static assets, or client-side code detected.",
            )
        )

    if any(Path(path).name == "manifest.json" for path in files) and any("manifest_version" in value for value in text_index.values()):
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="browser_extension",
                paths=_matching_paths(files, ["manifest.json", "content", "popup"]),
                capabilities=["browser_extension_development"],
                skills=["JavaScript", "Browser Extensions"],
                confidence="high",
                notes="Browser extension manifest detected.",
            )
        )

    devops_paths = _matching_paths(files, ["Dockerfile", "docker-compose", ".github/workflows", "terraform", ".service"])
    if devops_paths:
        skills = []
        if any("docker" in path.lower() or Path(path).name == "Dockerfile" for path in devops_paths):
            skills.append("Docker")
        if any(".github/workflows" in path for path in devops_paths):
            skills.append("GitHub Actions")
        if any(path.endswith(".service") for path in devops_paths):
            skills.append("systemd")
        if any("terraform" in path.lower() for path in devops_paths):
            skills.append("Terraform")
        rows.append(
            RepoEvidenceRow(
                repo=repo_label,
                signal="deployment_operations",
                paths=devops_paths,
                capabilities=["deployment_and_operations"],
                skills=skills or ["DevOps"],
                confidence="medium",
                notes="Deployment, CI/CD, or operations files detected.",
            )
        )

    return rows


def resolve_local_repo_source(path_value: str) -> ResolvedRepoSource:
    path = Path(path_value).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        return ResolvedRepoSource(source=path_value, source_type="local", repo_path=None, warning=str(exc))
    if not resolved.exists() or not resolved.is_dir():
        return ResolvedRepoSource(source=path_value, source_type="local", repo_path=None, warning="Local repo path does not exist or is not a directory.")
    return ResolvedRepoSource(source=str(resolved), source_type="local", repo_path=resolved)


def clone_public_repo(url: str, destination: Path, *, timeout_seconds: int = 60) -> ResolvedRepoSource:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ResolvedRepoSource(source=url, source_type="public_url", repo_path=None, warning="Only HTTPS public repo URLs are supported.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(destination)],
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git clone failed").strip().splitlines()[-1]
        return ResolvedRepoSource(source=url, source_type="public_url", repo_path=None, warning=message)
    return ResolvedRepoSource(source=url, source_type="public_url", repo_path=destination)


def analyze_public_repos(public_repo_urls: list[str]) -> list[tuple[ResolvedRepoSource, list[RepoEvidenceRow]]]:
    analyzed: list[tuple[ResolvedRepoSource, list[RepoEvidenceRow]]] = []
    with tempfile.TemporaryDirectory(prefix="jmi-profile-repos-") as temp_root:
        root = Path(temp_root)
        for index, url in enumerate(public_repo_urls, start=1):
            source = clone_public_repo(url, root / f"repo-{index}")
            rows = analyze_repo_for_evidence(repo_path=source.repo_path, repo_label=source.source) if source.repo_path else []
            analyzed.append((source, rows))
    return analyzed


def _repo_files(repo_path: Path) -> list[str]:
    if (repo_path / ".git").exists():
        result = subprocess.run(["git", "-C", str(repo_path), "ls-files"], text=True, capture_output=True, check=False)
        if result.returncode == 0:
            return sorted(path for path in result.stdout.splitlines() if path and not _is_skipped(path))
    files: list[str] = []
    for path in repo_path.rglob("*"):
        rel = path.relative_to(repo_path).as_posix()
        if path.is_file() and not _is_skipped(rel):
            files.append(rel)
    return sorted(files)


def _text_index(repo_path: Path, files: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for rel in files:
        path = repo_path / rel
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            if path.stat().st_size > 120_000:
                continue
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            values[rel] = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
    return values


def _is_skipped(rel_path: str) -> bool:
    parts = set(Path(rel_path).parts)
    return bool(parts & SKIP_DIRS)


def _has_any(paths: set[str], names: set[str]) -> bool:
    return any(name.lower() in paths for name in names)


def _matching_paths(files: list[str], needles: list[str]) -> list[str]:
    matches: list[str] = []
    for path in files:
        lower = path.lower()
        if any(needle.lower() in lower for needle in needles):
            matches.append(path)
    return sorted(matches[:12])


def _paths_containing(text_index: dict[str, str], terms: list[str]) -> list[str]:
    matches = [path for path, text in text_index.items() if any(term.lower() in text.lower() for term in terms)]
    return sorted(matches[:12])
