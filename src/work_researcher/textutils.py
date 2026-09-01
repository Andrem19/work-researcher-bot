"""Text normalization, salary parsing, hashing, relevance helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

_WS = re.compile(r"\s+")
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "for", "to", "with", "at",
    "by", "on", "senior", "junior", "graduate", "lead", "uk", "ltd", "limited",
}

_SAL_PATTERNS = [
    # £45-50k
    (
        re.compile(r"£\s*([\d,.]+)\s*(?:-|–|to)\s*£?\s*([\d,.]+)\s*k\b", re.I),
        "range_k",
    ),
    # £30,000 - £40,000 per annum | £300 - £400 per day
    (
        re.compile(
            r"£?\s*([\d,]+(?:\.\d+)?)\s*(?:-|–|to)\s*£?\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s+|a\s+)?(annum|year|yearly|month|monthly|week|weekly|day|daily|hour|hr|hourly)",
            re.I,
        ),
        "range",
    ),
    # £45,000 per annum | 45000/year
    (
        re.compile(
            r"£?\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s+)?(annum|year|yearly|month|monthly|week|weekly|day|daily|hour|hr|hourly)\b",
            re.I,
        ),
        "single",
    ),
    # £31,000 (period omitted on compact official listings)
    (re.compile(r"£\s*([\d,]+(?:\.\d+)?)\b", re.I), "currency_single"),
]

_PERIOD_CANON = {
    "annum": "year", "year": "year", "yearly": "year",
    "month": "month", "monthly": "month",
    "week": "week", "weekly": "week",
    "day": "day", "daily": "day",
    "hour": "hour", "hr": "hour", "hourly": "hour",
}

_HOURLY_ANNUALISE = {"hour": 37.5 * 52, "day": 250, "week": 52, "month": 12}


def clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text).strip()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9\s-]", "", (text or "").lower())
    return re.sub(r"[\s-]+", "-", s).strip("-")


def query_terms(query: str) -> list[str]:
    """Meaningful lowercase terms from a query, stopwords removed."""
    words = re.findall(r"[a-zA-Z+#.]{2,}", (query or "").lower())
    return [w for w in words if w not in STOPWORDS]


def term_coverage(terms: list[str], text: str | None) -> float:
    """Fraction of query terms present anywhere in text (case-insensitive)."""
    if not terms:
        return 0.0
    hay = (text or "").lower()
    return sum(1 for t in terms if t in hay) / len(terms)


def parse_salary(raw: str | None) -> tuple[float | None, float | None, str | None]:
    """Return (min, max, period) parsed from a raw salary string."""
    if not raw:
        return None, None, None
    text = clean(raw)
    for pattern, kind in _SAL_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if kind in {"range", "range_k"}:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", ""))
            if kind == "range_k":
                lo, hi, period = lo * 1000, hi * 1000, "year"
            else:
                period = _PERIOD_CANON.get((m.group(3) or "").lower())
        else:
            lo = float(m.group(1).replace(",", ""))
            hi = None
            period = (
                _PERIOD_CANON.get((m.group(2) or "").lower())
                if kind == "single" else "year"
            )
        # "£300 per day" vs "£300,000" heuristics: tiny numbers imply hour/day rates
        if period == "year" and lo and lo < 3000:
            period = "week" if lo < 400 else "month"
        return lo, hi, period
    return None, None, None


def annualise(amount: float | None, period: str | None) -> float | None:
    if amount is None:
        return None
    if period in _HOURLY_ANNUALISE:
        return round(amount * _HOURLY_ANNUALISE[period])
    return round(amount)


def job_hash(title: str | None, company: str | None, location: str | None,
             salary_min: float | None) -> str:
    """Stable cross-source dedup key: normalized title|company|location|salary."""
    t = re.sub(r"[^a-z0-9]", "", (title or "").lower())[:60]
    c = re.sub(r"[^a-z0-9]", "", (company or "").lower())[:40]
    l = re.sub(r"[^a-z0-9]", "", (location or "").lower())[:30]
    s = f"{salary_min:.0f}" if salary_min else ""
    digest = hashlib.sha1(f"{t}|{c}|{l}|{s}".encode()).hexdigest()[:16]
    return digest


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
