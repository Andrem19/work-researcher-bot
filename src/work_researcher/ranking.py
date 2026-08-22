"""Relevance scoring: query match + freshness + salary + source weight."""

from __future__ import annotations

from datetime import UTC, datetime

from .domain import JobCard
from .textutils import annualise, query_terms, term_coverage

SOURCE_WEIGHT = {
    "reed": 1.00, "adzuna": 1.00, "totaljobs": 1.00, "findajob": 0.95,
    "earthworks": 0.95, "jooble": 0.90, "observation": 0.90,
}


def _days_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(tz=UTC) - dt).total_seconds() / 86400


LOCATION_PENALTY = {"mismatch": 40.0, "caution": 8.0, "unknown": 3.0}


def score_job(card: JobCard, query: str, min_salary: int | None = None,
              work_from_home: bool | None = None,
              location_status: str | None = None) -> tuple[float, list[str]]:
    """Return (score 0..100, reasons)."""
    reasons: list[str] = []
    terms = query_terms(query)
    title_cov = term_coverage(terms, card.title)
    desc_cov = term_coverage(terms, card.description or "")
    score = title_cov * 42 + desc_cov * 18
    if title_cov >= 0.99:
        reasons.append("all query terms in title")
    elif title_cov >= 0.5:
        reasons.append(f"title match {title_cov:.0%}")

    days = _days_since(card.posted_at)
    if days is not None:
        if days <= 3:
            score += 14
            reasons.append("posted <=3d ago")
        elif days <= 7:
            score += 10
            reasons.append("posted <=7d ago")
        elif days <= 14:
            score += 5
    else:
        score += 3  # unknown age: mild neutral bonus so it is not buried

    if card.salary_min:
        score += 8
        ann = annualise(card.salary_min, card.salary_period)
        if min_salary and ann and ann >= min_salary:
            score += 8
            reasons.append(f"salary >= £{min_salary:,}")
        elif min_salary and ann and ann < min_salary * 0.8:
            score -= 12
            reasons.append(f"salary £{ann:,} below £{min_salary:,}")
    if card.work_from_home:
        score += 4

    score *= SOURCE_WEIGHT.get(card.source, 0.9)
    if work_from_home and card.work_from_home is False:
        score -= 25
        reasons.append("not remote (remote requested)")
    if location_status in LOCATION_PENALTY:
        score -= LOCATION_PENALTY[location_status]
        if location_status == "mismatch":
            reasons.append("LOCATION MISMATCH — too far from home, not remote")
        elif location_status == "caution":
            reasons.append("relocation required — confirm with user")
    return round(max(0.0, min(100.0, score)), 1), reasons
