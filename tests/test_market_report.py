from __future__ import annotations

from app.models.job_matching import JobPosting
from app.services.market_report import build_market_report, report_to_markdown


def test_report_markdown_uses_real_newlines():
    markdown = report_to_markdown(build_market_report([], []))
    assert "\\n" not in markdown
    assert markdown.startswith("# Job Market Intelligence Report\n")
    assert "\n## Top matched skills\n" in markdown


def test_matching_text_joins_parts_with_real_newlines():
    job = JobPosting(company="Acme", title="Backend Engineer", description="Python FastAPI")
    assert job.matching_text() == "Backend Engineer\nAcme\nPython FastAPI"
