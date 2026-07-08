from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.models.job_matching import JobMatchResult


def build_market_report(matches: list[JobMatchResult], selected: list[JobMatchResult]) -> dict[str, Any]:
    skill_counter: Counter[str] = Counter()
    gap_counter: Counter[str] = Counter()
    company_best: dict[str, float] = defaultdict(float)
    levels: Counter[str] = Counter()

    for match in matches:
        levels[match.fit_level] += 1
        company_best[match.job.company] = max(company_best[match.job.company], match.fit_score)
        skill_counter.update(match.matched_skills)
        gap_counter.update(match.missing_skills)

    top_companies = sorted(
        ({"company": company, "best_score": round(score, 3)} for company, score in company_best.items()),
        key=lambda item: item["best_score"],
        reverse=True,
    )[:10]

    return {
        "jobs_analyzed": len(matches),
        "strong_matches": sum(1 for item in matches if item.fit_level == "strong"),
        "good_or_better_matches": sum(1 for item in matches if item.fit_level in {"good", "strong"}),
        "fit_level_counts": dict(levels),
        "top_matched_skills": _counter_items(skill_counter),
        "top_missing_skills": _counter_items(gap_counter),
        "top_companies": top_companies,
        "recommended_matches": [item.to_response_dict() for item in selected],
    }


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Job Market Intelligence Report",
        "",
        f"- Jobs analyzed: {report['jobs_analyzed']}",
        f"- Strong matches: {report['strong_matches']}",
        f"- Good or better matches: {report['good_or_better_matches']}",
        "",
        "## Top matched skills",
    ]
    lines.extend(_bullet_count(report.get("top_matched_skills", [])))
    lines.extend(["", "## Top missing skills"])
    lines.extend(_bullet_count(report.get("top_missing_skills", [])))
    lines.extend(["", "## Top companies by fit"])
    for item in report.get("top_companies", []):
        lines.append(f"- {item['company']}: {item['best_score']}")
    lines.extend(["", "## Recommended matches"])
    for item in report.get("recommended_matches", []):
        lines.append(f"- {item['fit_score']} · {item['title']} — {item['company']}")
    return "\n".join(lines) + "\n"


def _counter_items(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _bullet_count(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- No data yet."]
    return [f"- {item['name']}: {item['count']}" for item in items]
