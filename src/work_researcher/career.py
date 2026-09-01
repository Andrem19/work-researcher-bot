"""Career-path, entry-level and location policy used by the nightly bot."""

from __future__ import annotations

import re
from typing import Any

from . import requirements, seller, training
from .domain import JobCard

SENIOR_RE = re.compile(r"\b(senior|lead|principal|staff|manager|head of|director|architect)\b", re.I)
ENTRY_RE = re.compile(r"\b(junior|trainee|graduate|entry[ -]level|associate|level 1|data engineer i|apprentice)\b", re.I)
YEARS_RE = re.compile(r"\b([3-9]|\d{2,})\+?\s+years?\b", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|home[ -]based|anywhere in (?:the )?uk)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
ONSITE_ALLOWED = ("blackpool", "preston", "lytham", "fleetwood", "poulton", "kirkham")
HYBRID_ALLOWED = (*ONSITE_ALLOWED, "manchester", "salford", "bolton", "wigan", "lancaster", "liverpool", "chorley", "warrington", "burnley")


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
        "reject_reasons": hard_rejects,
    }
