"""Who posted this vacancy: recruitment agency or direct employer.

UK boards mix both; the user wants to see it per job. Signals, in order:
1. explicit recruiter field from APIs (Reed) when it differs from the employer
2. agency words in the poster/company name (recruitment, staffing, …)
3. well-known UK agency brands (Harnham, Experis, Hays, …)
4. agency phrasing in the description ("our client is seeking", …)

Returns (seller, reason): seller = 'agency' | 'employer' | 'unknown'.
'employer' without an explicit signal is an assumption — the note says so.
"""

from __future__ import annotations

AGENCY_NAME_WORDS = (
    "recruitment", "recruiter", "recruiting", "staffing",
    "personnel", "resourcing", "search & selection", "search and selection",
    "agency", "talent solutions", "employment agency", "staff solutions",
    "work solutions", "recruitment consultancy", "recruitment agency",
    # NB: bare "consultancy"/"associates" are NOT markers — engineering
    # consultancies (Atkins/RSK/Bridgewater) are employers in geoscience;
    # agencies with those words are caught by the phrases/brands below.
)

AGENCY_BRANDS = (
    "harnham", "experis", "hays", "adecco", "reed", "office angels",
    "staffline", "manpower", "randstad", "monarch", "matchtech",
    "computer futures", "progressive recruitment", "real it", "vanrath",
    "jonathan lee", "s_three", "sthree", "morgan law", "sanderson",
    "baxter clay", "acquity", "frank recruitment", "tenth revolution",
    "nicoll jackson", "penguin recruitment", "itol recruit", "itology",
    "nigel wright", "neo recruitment", "holt recruitment",
    "robert walters", "michael page", "page personnel", "badenoch",
    "outsource uk", "outsource", "carrington west", "hudson shribman",
    "calibre search", "zenith people",
)

AGENCY_DESCRIPTION_PHRASES = (
    "our client is seeking", "our client is looking", "on behalf of our client",
    "our client, a ", "we are recruiting for a", "our prestigious client",
    "our client based", "client of ours",
)


def classify(company: str | None, description: str | None,
             recruiter: str | None = None) -> tuple[str, str | None]:
    company_l = (company or "").lower().strip()
    desc_l = (description or "").lower()

    if recruiter and company:
        recruiter_l = recruiter.lower().strip()
        if recruiter_l and recruiter_l != company_l:
            return "agency", f"posted by recruiter '{recruiter}'"

    for w in AGENCY_NAME_WORDS:
        if w in company_l:
            return "agency", f"'{w}' in poster name"
    for b in AGENCY_BRANDS:
        if b in company_l:
            return "agency", f"known agency brand '{b}'"
    for p in AGENCY_DESCRIPTION_PHRASES:
        if p in desc_l:
            return "agency", f"description says '{p}'"

    if company_l:
        return "employer", "no agency signals (assumed direct employer)"
    return "unknown", "no company name on the card"
