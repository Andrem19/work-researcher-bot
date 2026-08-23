"""Application tracker: plans, guards against double applications, history."""

from __future__ import annotations

import aiosqlite

from . import persistence as db
from .config import Settings
from .domain import ApplyPlan

PLAYBOOKS: dict[str, str] = {
    "indeed": (
        "Indeed UK: log in once via browser_open('https://uk.indeed.com') + manual "
        "sign-in (profile persists). 'Easy Apply' = in-page modal (CV upload once, "
        "screening questions); other jobs redirect to the employer site — follow "
        "the redirect. Cap ~10 applications/day; pause and ask the user on "
        "captchas/verification."
    ),
    "reed": (
        "Reed: browser_open(job url) → 'Apply now' → upload CV file → short form "
        "(right to work, notice) → 'Submit application'. 'Easy Apply' badge jobs "
        "skip most questions."
    ),
    "totaljobs": (
        "Totaljobs (and Jobsite): job page → 'Apply now' → CV upload + cover "
        "letter field + screening questions → 'Submit application'. "
        "SUPPORTING FILES must be LARGER than 8KB — generate cover letters "
        "with make_cover_letter (DOCX, auto-padded). Uploads go through "
        "browser_upload directly on the hidden input[type=file] element "
        "(no native chooser needed)."
    ),
    "cv-library": (
        "CV-Library: job page → 'Apply for job' → account CV or upload → quick "
        "questions → 'Submit application'."
    ),
    "linkedin": (
        "LinkedIn: ToS restrict automated applying. Use the logged-in session, "
        "slow pace, 'Easy Apply' modal (CV + questions). Prefer surfacing jobs "
        "to the user over bulk applying."
    ),
    "earthworks": (
        "Earthworks jobpost pages link to the employer/agency instructions — "
        "usually an email address or external portal; follow the page text."
    ),
    "findajob": (
        "GOV.UK Work Hub (jobs.service.gov.uk): the 'Apply for this job' "
        "button opens a 'Before you apply' page → click 'Continue to the "
        "employer's website' — Work Hub does NOT host its own application "
        "form; it redirects to the employer's external site (NHS Jobs, "
        "council portals, etc.). Sign in via GOV.UK One Login (email + "
        "confirmation code, NOT Google SSO) — needed to reach the apply "
        "button. On the employer site: upload CV, fill form, submit."
    ),
    "website_form": (
        "Employer career sites (Workday/SmartRecruiters/Greenhouse/iCIMS): "
        "browser_open(url) → browser_form() → browser_set per field → upload CV → "
        "next/submit → confirm → browser_screenshot. Workday flows are multi-page: "
        "expect 2-4 form pages."
    ),
}


def _apply_method(job: dict) -> tuple[str, str | None, list[str]]:
    """Guess how to apply from the job's source/URL."""
    url = (job.get("apply_url") or job.get("url") or "").lower()
    source = (job.get("source") or "").lower()
    if "indeed." in url or source == "indeed":
        return ("indeed_easy_apply", job.get("apply_url") or job.get("url"),
                ["Indeed blocks bots aggressively; prefer a logged-in browser profile",
                 "Easy Apply jobs complete in-page; others redirect to the employer site"])
    if "linkedin." in url or source == "linkedin":
        return ("linkedin_easy_apply", job.get("apply_url") or job.get("url"),
                ["LinkedIn ToS restrict automation — keep applications slow and manual-ish"])
    if source in ("reed", "totaljobs", "cv-library", "cvlibrary"):
        return ("board_account_apply", job.get("apply_url") or job.get("url"),
                ["Log into the board account in the browser profile first",
                 "Upload the chosen CV file, answer screening questions"])
    if source == "earthworks":
        return ("employer_site_or_email", job.get("apply_url") or job.get("url"),
                ["Earthworks posts link to the employer/agency instructions — read the page"])
    if source == "findajob":
        return ("employer_site_or_email", job.get("apply_url") or job.get("url"),
                ["GOV.UK Work Hub redirects to the employer's website — "
                 "click 'Continue to the employer's website' on the 'Before "
                 "you apply' page",
                 "GOV.UK One Login (email + code, NOT Google SSO) required "
                 "to reach the Apply button; the profile now has a session",
                 "On the employer site: upload CV, fill form, submit"])
    return ("website_form", job.get("apply_url") or job.get("url"), [])


async def start_application(conn: aiosqlite.Connection, settings: Settings,
                            job_id: str, cv_id: str | None = None,
                            notes: str | None = None) -> dict:
    """Create (or return the existing) application with a full apply plan.

    Never creates a second application for a job that already has one in a
    non-withdrawn state — this is the memory that prevents re-applying to a
    vacancy submitted days or weeks ago, even when it is re-found on another
    board (dedup keeps one canonical job row).
    """
    job = await db.get_job(conn, job_id)
    if job is None:
        return {"ok": False, "error": f"unknown job_id {job_id}"}
    existing = await db.application_for_job(conn, job_id)
    cautions: list[str] = []
    if existing and existing.get("status") not in ("withdrawn", "failed"):
        job_brief = {k: job.get(k) for k in
                     ("id", "title", "company", "location_text", "url", "apply_url",
                      "salary_raw", "posted_at", "source")}
        return {
            "ok": True, "already_exists": True, "application_id": existing["id"],
            "existing_status": existing["status"],
            "cautions": [
                f"An application for this job already exists "
                f"(status={existing['status']}, updated {existing['updated_at']}). "
                "Do NOT submit again; ask the user if they want to withdraw/re-apply."
            ],
            "application": existing,
        }
    from .cvmanager import recommend_cv

    import json as _json

    extra = {}
    try:
        extra = _json.loads(job.get("extra") or "{}")
    except (TypeError, ValueError):
        pass
    await db.ensure_seed_blocklist(conn, settings)
    companies, keywords = await db.load_blocked_norms(conn)
    hit = db.is_blocked(job.get("company"),
                        f"{job.get('title')} {job.get('description') or ''}",
                        companies, keywords)
    if hit:
        return {"ok": False, "blocked": True,
                "error": f"{job.get('company')} is on the blocklist ({hit}) — "
                         "remove it via manage_blocklist if the user changed "
                         "their mind"}
    if extra.get("training_offer"):
        return {"ok": False, "training_offer": True,
                "error": "this listing is a paid training/course ad "
                         f"({extra.get('training_reason')}) — not a real job; "
                         "do not apply"}
    loc_status = extra.get("location_status")
    if loc_status == "mismatch":
        cautions.append(
            f"LOCATION MISMATCH: {extra.get('location_reason')} — only proceed if "
            "the user explicitly confirmed they want to apply to this far-away "
            "non-remote job"
        )
    elif loc_status == "caution":
        cautions.append(f"Location caution: {extra.get('location_reason')}")
    recs = await recommend_cv(conn, job, limit=3)
    chosen = None
    if cv_id:
        chosen = await db.get_cv(conn, cv_id)
    elif recs and recs[0]["score"] > 0:
        chosen = await db.get_cv(conn, recs[0]["cv_id"])
    app_id = await db.create_application(conn, job_id,
                                         (chosen or {}).get("id") if chosen else cv_id,
                                         notes)
    method, apply_url, method_cautions = _apply_method(job)
    steps = [
        f"Open {apply_url} with browser_open (headed mode keeps logins)",
        "Sign in / create the account if the board requires it (persist in the profile)",
        f"Upload CV: {(chosen or {}).get('path') or 'pick via list_cvs'}",
        "Fill the form with the applicant profile values (see applicant block)",
        "Write a short tailored cover letter referencing the job's key requirements",
        "Screenshot the confirmation page (browser_screenshot)",
        "Call record_application with status='submitted' and the screenshot as evidence",
    ]
    plan = ApplyPlan(
        application_id=app_id,
        job={k: job.get(k) for k in
             ("id", "title", "company", "location_text", "url", "apply_url",
              "salary_raw", "posted_at", "source", "contract_type", "description")},
        cv={"id": chosen["id"], "filename": chosen["filename"],
            "path": chosen["path"], "tags": chosen.get("tags")}
        if chosen else None,
        cv_alternatives=[r for r in recs if not chosen or r["cv_id"] != chosen.get("id")],
        apply_url=apply_url,
        apply_method=method,
        applicant={k: v for k, v in settings.applicant.items() if v},
        steps=steps,
        cautions=cautions + method_cautions,
    )
    result = {"ok": True, "already_exists": False,
              "plan": plan.model_dump(mode="json")}
    result["plan"]["playbook"] = PLAYBOOKS.get(method, PLAYBOOKS["website_form"])
    result["plan"]["location"] = {
        k: extra.get(k) for k in ("work_mode", "distance_miles",
                                  "location_status", "location_reason")
    }
    return result
