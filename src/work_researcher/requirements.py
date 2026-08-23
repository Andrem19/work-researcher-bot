"""Hard-requirements matching: parse job descriptions for mandatory
qualifications/experience and check them against the candidate's CVs.

The problem from the real run: the agent proposed a job requiring "AAT Level 2"
when the user does not have it. This module extracts hard requirements
(qualifications, certifications, years of experience, licences) and checks
them against the CV text. Jobs with unmet HARD requirements are flagged
requirements_match=gap and should not be proposed to the user.
"""

from __future__ import annotations

import re

# --- requirement extraction ------------------------------------------------

# "Essential:" / "Required:" / "Must have:" / "You will need:" sections
REQ_SECTION_RE = re.compile(
    r"(?:essential|required|must have|you will (?:need|have)|key requirements"
    r"|person specification|minimum requirements)\s*:?\s*\n((?:.*\n){0,30})",
    re.I)

# "Desirable:" / "Preferred:" — softer, don't fail on these
DESIRABLE_SECTION_RE = re.compile(
    r"(?:desirable|preferred|nice to have|advantageous|beneficial)\s*:?\s*\n"
    r"((?:.*\n){0,15})", re.I)

# Qualification patterns
QUAL_PATTERNS = [
    # AAT Level 2/3/4, CIMA, ACCA, ACA, CFA
    (re.compile(r"\b(AAT\s*(?:Level\s*)?[1-4])\b", re.I), "qualification"),
    (re.compile(r"\b(CIMA|ACCA|ACA|CFA|ATT|CIOT)\b", re.I), "qualification"),
    # Degree: BSc, MSc, BA, MEng, PhD, "degree in X"
    (re.compile(r"\b(BSc|MSc|BA|MA|MEng|BEng|PhD)\b(?:\s*(?:Hons?|in\s+\w+))?",
                re.I), "qualification"),
    (re.compile(r"\b(bachelor'?s|master'?s|degree)\s+(?:degree\s+)?in\s+(\w+)",
                re.I), "qualification"),
    # Professional registrations
    (re.compile(r"\b(Geol\s*Sci|CGeol|FGS|MGS|P\.Eng|CEng|IEng|CITB)\b", re.I),
     "qualification"),
    # Driving licence
    (re.compile(r"\b(full\s+(?:UK\s+)?driving\s+licence|driving\s+license)\b",
                re.I), "licence"),
    # GCSE / A-Level / NVQ
    (re.compile(r"\b(GCSE|A[\s-]?Level|NVQ\s*(?:Level\s*)?[1-5])\b", re.I),
     "qualification"),
    # Security clearance
    (re.compile(r"\b(SC|DV|CTC|security\s+clearance|DBS\s+(?:check|certified))\b",
                re.I), "clearance"),
    # Experience: "X years of experience in Y"
    (re.compile(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience\s+(?:in|of|with)\s+"
                r"([a-zA-Z\s,]{3,40})", re.I), "experience"),
    # "Proven experience in X"
    (re.compile(r"proven\s+experience\s+(?:in|of|with)\s+([a-zA-Z\s,]{3,40})",
                re.I), "experience"),
]

# Negation: "without X", "no requirement for X"
NEG_RE = re.compile(r"\b(?:no(?:t)?\s+(?:require|need)|without|optional)\b", re.I)


def extract_requirements(description: str | None) -> dict:
    """Return {hard: [{type, value}], desirable: [...], experience_years: int}."""
    if not description:
        return {"hard": [], "desirable": [], "experience_years": None}

    text = description

    # isolate essential vs desirable sections
    essential_text = text
    desirable_text = ""
    m = REQ_SECTION_RE.search(text)
    if m:
        essential_text = m.group(1) or text
    m = DESIRABLE_SECTION_RE.search(text)
    if m:
        desirable_text = m.group(1) or ""
        # remove desirable from essential to avoid double-counting
        if desirable_text:
            essential_text = essential_text.replace(desirable_text, "")

    hard: list[dict] = []
    desirable: list[dict] = []
    exp_years: int | None = None

    for pattern, rtype in QUAL_PATTERNS:
        for m in pattern.finditer(essential_text):
            # skip if negated nearby
            ctx = essential_text[max(0, m.start() - 30):m.end() + 30]
            if NEG_RE.search(ctx):
                continue
            value = m.group(0).strip()
            if rtype == "experience":
                years = int(m.group(1)) if m.lastindex and m.group(1) else None
                if years and (exp_years is None or years > exp_years):
                    exp_years = years
                value = m.group(0).strip()
            hard.append({"type": rtype, "value": value})
        if desirable_text:
            for m in pattern.finditer(desirable_text):
                value = m.group(0).strip()
                desirable.append({"type": rtype, "value": value})

    return {"hard": hard, "desirable": desirable, "experience_years": exp_years}


# --- CV matching -----------------------------------------------------------

def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9+#. ]", " ", (text or "").lower()).strip()


def match_requirements(reqs: dict, cv_text: str | None) -> dict:
    """Check hard requirements against CV text.

    Returns {status: match|gap|unknown, unmet: [...], met: [...],
             experience_gap: int|None}.
    status='gap' → the job has a hard requirement the CV does not satisfy;
    the agent should NOT propose it without a clear user override.
    """
    if not cv_text:
        return {"status": "unknown", "unmet": [], "met": [],
                "experience_gap": None}
    cv = _norm(cv_text)
    if not cv:
        return {"status": "unknown", "unmet": [], "met": [],
                "experience_gap": None}

    unmet: list[dict] = []
    met: list[dict] = []
    for req in reqs.get("hard", []):
        value = _norm(req["value"])
        rtype = req["type"]
        # fuzzy-ish check: the requirement value (or its key tokens) in CV
        key = value.replace("level", "").strip()
        if rtype == "experience":
            # "X years experience in Y" → check if Y appears in CV
            # (can't verify years, only domain)
            domain = re.sub(r"\d+\+?\s*years?\s*(?:of\s+)?experience\s*"
                            r"(?:in|of|with)\s*", "", value).strip()
            if domain and domain not in cv:
                unmet.append(req)
            else:
                met.append(req)
        elif rtype == "licence":
            if "driving licence" in value or "driving license" in value:
                if "driving licence" in cv or "driving license" in cv \
                        or "full uk driving" in cv or "clean driving" in cv:
                    met.append(req)
                else:
                    unmet.append(req)
            else:
                met.append(req)  # unknown licence type
        elif rtype == "clearance":
            # DBS/security clearance — often obtainable, flag but soft
            if value.lower().split()[0] in cv:
                met.append(req)
            else:
                met.append(req)  # clearances are obtainable, not a hard fail
        elif rtype == "qualification":
            # check the qualification appears in the CV (AAT, BSc, etc.)
            qual_token = key.split()[0] if key else value
            if qual_token and len(qual_token) >= 2:
                if qual_token in cv or value in cv:
                    met.append(req)
                else:
                    unmet.append(req)
            else:
                met.append(req)
        else:
            met.append(req)

    return {
        "status": "gap" if unmet else "match",
        "unmet": unmet,
        "met": met,
        "experience_gap": reqs.get("experience_years"),
    }
