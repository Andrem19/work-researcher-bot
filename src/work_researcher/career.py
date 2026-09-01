"""Career-path, entry-level and location policy used by the nightly bot."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from . import requirements, seller, training
from .domain import JobCard

SENIOR_RE = re.compile(r"\b(senior|lead|principal|staff|manager|head of|director|architect)\b", re.I)
ENTRY_RE = re.compile(r"\b(junior|trainee|graduate|entry[ -]level|associate|level 1|data engineer i|apprentice)\b", re.I)
YEARS_RE = re.compile(r"\b([3-9]|\d{2,})\+?\s+years?\b", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|home[ -]based|anywhere in (?:the )?uk)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
CLOSED_RE = re.compile(
    r"\b(?:this\s+)?(?:job|role|vacancy|position|advert(?:isement)?)\s+(?:has\s+)?"
    r"(?:expired|closed)|\bapplications?\s+(?:are\s+)?(?:now\s+)?closed\b|"
    r"\bno\s+longer\s+accepting\s+applications?\b",
    re.I,
)
DEADLINE_LABEL_RE = re.compile(
    r"\b(?:closing\s+date|application\s+deadline|applications?\s+close|closes)\s*:?[ \t]*"
    r"([^\n|;]{3,80})",
    re.I,
)
TEXT_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(\d{4})\b",
    re.I,
)
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
ONSITE_ALLOWED = ("blackpool", "preston", "lytham", "fleetwood", "poulton", "kirkham")
HYBRID_ALLOWED = (*ONSITE_ALLOWED, "manchester", "salford", "bolton", "wigan", "lancaster", "liverpool", "chorley", "warrington", "burnley")


def _parse_deadline(value: str) -> date | None:
    text_match = TEXT_DATE_RE.search(value)
    if text_match:
        day, month_text, year = text_match.groups()
        try:
            return date(int(year), MONTHS[month_text[:3].lower()], int(day))
        except ValueError:
            return None
    numeric_match = NUMERIC_DATE_RE.search(value)
    if numeric_match:
        day, month, year = (int(part) for part in numeric_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def vacancy_status(card: JobCard, *, today: date | None = None) -> dict[str, Any]:
    """Extract explicit closing evidence without guessing a missing deadline."""
    # The production run starts at 22:00 UK time, safely away from the UTC date
    # boundary, so the host-local calendar date is sufficient and portable on
    # Windows installations without the optional IANA tzdata package.
    current_date = today or datetime.now().date()
    description = card.description or ""
    extra_deadline = next((
        card.extra.get(key) for key in (
            "closing_date", "closingDate", "deadline", "application_deadline",
        ) if card.extra.get(key)
    ), None)
    deadline_text = str(extra_deadline) if extra_deadline else None
    if deadline_text is None:
        label_match = DEADLINE_LABEL_RE.search(description)
        deadline_text = label_match.group(1).strip() if label_match else None
    deadline = _parse_deadline(deadline_text or "")
    explicitly_closed = bool(CLOSED_RE.search(description))
    expired = explicitly_closed or (deadline is not None and deadline < current_date)
    days_left = (deadline - current_date).days if deadline is not None else None
    if expired:
        urgency = "expired"
    elif days_left is None:
        urgency = "unknown"
    elif days_left <= 2:
        urgency = "urgent"
    elif days_left <= 7:
        urgency = "soon"
    else:
        urgency = "none"
    return {
        "closed": expired,
        "deadline": deadline.isoformat() if deadline else None,
        "deadline_raw": deadline_text,
        "deadline_urgency": urgency,
        "vacancy_live_confidence": "low" if expired else ("high" if deadline else "medium"),
    }


def work_mode(card: JobCard) -> str:
    text = f"{card.title or ''} {card.description or ''}"
    if HYBRID_RE.search(text):
        return "hybrid"
    if REMOTE_RE.search(text) or card.work_from_home is True:
        return "remote"
    return "on_site"


def location_allowed(card: JobCard) -> tuple[bool, str]:
    mode = work_mode(card)
    location = (card.location_text or "").lower()
    if mode == "remote":
        return True, "UK-wide remote"
    allowed = HYBRID_ALLOWED if mode == "hybrid" else ONSITE_ALLOWED
    if any(place in location for place in allowed):
        return True, f"{mode}: allowed North West location"
    return False, f"{mode}: outside allowed area"


def entry_allowed(card: JobCard) -> tuple[bool, str]:
    text = f"{card.title or ''} {card.description or ''}"
    if ENTRY_RE.search(card.title or ""):
        if YEARS_RE.search(text):
            return False, "entry-labelled role still requires at least 3 years of experience"
        return True, "explicit entry-level signal"
    if SENIOR_RE.search(card.title or ""):
        return False, "senior title"
    if YEARS_RE.search(text):
        return False, "requires at least 3 years of experience"
    if ENTRY_RE.search(text):
        return True, "explicit entry-level signal"
    return True, "no senior/3+ years signal"


def deterministic_assessment(card: JobCard, path_id: str, cv_text: str) -> dict[str, Any]:
    posted_by, posted_reason = seller.classify(card.company, card.description, card.extra.get("recruiter"))
    is_training, training_reason = training.classify(card)
    entry_ok, entry_reason = entry_allowed(card)
    location_ok, location_reason = location_allowed(card)
    reqs = requirements.extract_requirements(card.description)
    req_match = requirements.match_requirements(reqs, cv_text)
    status = vacancy_status(card)
    hard_rejects = []
    if posted_by != "employer":
        hard_rejects.append(f"not verified direct employer ({posted_by})")
    if is_training:
        hard_rejects.append(training_reason or "paid training advert")
    if not entry_ok:
        hard_rejects.append(entry_reason)
    if not location_ok:
        hard_rejects.append(location_reason)
    if req_match["status"] == "gap":
        hard_rejects.append("unmet mandatory requirements")
    if status["closed"]:
        hard_rejects.append("vacancy is closed or its stated deadline has passed")
    score = 50
    score += 18 if ENTRY_RE.search(f"{card.title} {card.description}") else 5
    score += 12 if work_mode(card) == "remote" else 8
    score += 8 if card.salary_min else 0
    score += 8 if card.description and len(card.description) > 300 else 0
    score -= 50 if hard_rejects else 0
    return {
        "path_id": path_id, "eligible": not hard_rejects, "base_score": max(0, min(100, score)),
        "posted_by": posted_by, "posted_by_reason": posted_reason,
        "work_mode": work_mode(card), "location_reason": location_reason,
        "entry_reason": entry_reason, "mandatory": [x["value"] for x in reqs["hard"]],
        "desirable": [x["value"] for x in reqs["desirable"]],
        "requirements_status": req_match["status"],
        "requirements_unmet": [x["value"] for x in req_match["unmet"]],
        "deadline": status["deadline"], "deadline_raw": status["deadline_raw"],
        "deadline_urgency": status["deadline_urgency"],
        "vacancy_live_confidence": status["vacancy_live_confidence"],
        "reject_reasons": hard_rejects,
    }
