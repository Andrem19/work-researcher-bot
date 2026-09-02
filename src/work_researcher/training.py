"""Paid-training-offer detection.

'Trainee/Junior + training' searches on UK boards attract course ads where
the CANDIDATE PAYS for training (Netcom Online Learning, e-Careers, bootcamp
resellers). Those are not jobs and must never reach the user. A real paid
apprenticeship/traineeship (salary present) is a legitimate job and stays.

classify() returns (is_training_offer, reason).
"""

from __future__ import annotations

from .domain import JobCard

# Phrases that advertise a course, not a vacancy
COURSE_TITLE_MARKERS = (
    "training course", "skills bootcamp", "bootcamp", "certification course",
    "diploma course", "study course", "course +", "with certification",
    "guaranteed job interview", "career changer programme", "traineeship programme",
)

# You-pay-them language
PAY_MARKERS = (
    "course fee", "fees apply", "fee of £", "learner loan",
    "advanced learner", "self-fund", "self fund", "funded by you",
    "funding options available", "training investment",
    "cost of the course", "pay for your training",
)

# Known paid-course mills / resellers (name fragments)
PROVIDER_MARKERS = (
    "online learning", "e-learning", "e-careers", "learning people",
    "career switch", "it career switch", "justit", "just it training",
    "firebrand", "netcom", "training academy", "skills academy",
    "career institute", "career solutions", "it training",
    "nowskills", "back 2 work",
)

TRAINING_COMPANY_WORDS = ("learning", "training", "academy", "education",
                          "college", "institute")
JUNIOR_TITLE_WORDS = ("trainee", "apprentice", "no experience",
                      "placement", "graduate", "entry level", "starter",
                      "career start")
BAIT_TITLE_MARKERS = ("no experience needed", "no experience required",
                      "earn up to", "uncapped earnings", "guaranteed earnings")


def _bait_salary_range(card: JobCard) -> bool:
    """Trainee ads bait with inflated ranges: '£30,000 - £65,000' for a
    no-experience role. Real junior salaries are tight (£24-32k)."""
    if card.salary_min and card.salary_max and card.salary_min >= 25000:
        return card.salary_max / card.salary_min >= 1.55
    return False


def classify(card: JobCard) -> tuple[bool, str | None]:
    title = (card.title or "").lower()
    company = (card.company or "").lower()
    desc = (card.description or "").lower()
    text = f"{title} {company} {desc}"
    salary_raw = (card.salary_raw or "").lower()

    for m in COURSE_TITLE_MARKERS:
        if m in title:
            return True, f"title advertises a course ('{m}')"
    for m in PAY_MARKERS:
        if m in text:
            return True, f"pay-for-training language ('{m}')"
    for m in PROVIDER_MARKERS:
        if m in company:
            return True, f"known paid-course provider ('{m}')"
    for m in BAIT_TITLE_MARKERS:
        if m in title:
            return True, f"bait title ('{m}')"

    company_is_training_ish = any(w in company for w in TRAINING_COMPANY_WORDS)
    title_is_junior_ish = any(w in title for w in JUNIOR_TITLE_WORDS)
    if (
        title_is_junior_ish
        and (_bait_salary_range(card) or "up to" in salary_raw)
        and (company_is_training_ish or (card.salary_max or 0) >= 45000)
    ):
        return True, "trainee role with a bait salary range (course ad)"
    if company_is_training_ish and title_is_junior_ish and not card.salary_min:
        return True, "training company + junior/trainee role + no salary"
    # A stated salary keeps a real paid apprenticeship eligible.
    return False, None
