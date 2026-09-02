import json
from datetime import UTC, date, datetime

import httpx
import pytest

from work_researcher.bot import _apply_global_ranking, _build_ranked_jobs
from work_researcher.career import vacancy_status
from work_researcher.config import load_settings
from work_researcher.domain import JobCard
from work_researcher.freshness import VacancyVerifier, parse_page
from work_researcher.telegram import render_report


def card(**kwargs):
    return JobCard(source="test", title="Data Engineer Level I", company="DWP Digital",
                   url="https://jobs.example.org/1", **kwargs)


@pytest.mark.parametrize("raw", ["1 Sept 2026", "2026-09-01", "01/09/2026", "Tuesday 1 September", "2026-09-01T22:55:00Z"])
def test_yesterday_is_expired(raw):
    status = vacancy_status(card(extra={"closing_date": raw}), today=date(2026, 9, 2))
    assert status["closed"]
    assert not status["reportable"]
    assert status["deadline"] == "2026-09-01"


@pytest.mark.parametrize("raw", ["2 September 2026 at 5:00 pm", "2026-09-02T16:00:00Z", "2 September 2026 at 5.00 pm"])
def test_cutoff_time_is_uk_dst_aware(raw):
    job = card(extra={"closing_date": raw})
    assert not vacancy_status(job, now=datetime(2026, 9, 2, 15, 59, tzinfo=UTC))["closed"]
    assert vacancy_status(job, now=datetime(2026, 9, 2, 16, 0, tzinfo=UTC))["closed"]


def test_date_only_is_not_misread_as_time_and_midnight_uses_uk_day():
    job = card(extra={"closing_date": "02.09.2026"})
    status = vacancy_status(job, now=datetime(2026, 9, 2, 22, 59, tzinfo=UTC))
    assert not status["closed"]
    assert status["deadline_at"] is None
    assert vacancy_status(job, now=datetime(2026, 9, 2, 23, 1, tzinfo=UTC))["closed"]


def test_iso_utc_cutoff_on_following_uk_day_is_not_rejected_early():
    job = card(extra={"validThrough": "2026-09-02T23:30:00Z"})
    status = vacancy_status(job, now=datetime(2026, 9, 2, 23, 1, tzinfo=UTC))
    assert status["deadline"] == "2026-09-03"
    assert not status["closed"]
    assert vacancy_status(job, now=datetime(2026, 9, 2, 23, 30, tzinfo=UTC))["closed"]


def test_earliest_deadline_and_primary_overrides_board():
    job = card(extra={"deadline_evidence": [
        {"raw": "11 Sept 2026", "kind": "listing"},
        {"raw": "13 Sept 2026", "kind": "employer", "source_url": "https://employer.example.org/1"},
    ]})
    result = vacancy_status(job, today=date(2026, 9, 2))
    assert result["deadline"] == "2026-09-13"
    assert result["deadline_conflict"]
    assert result["deadline_source_url"] == "https://employer.example.org/1"


def test_yearless_multiline_body_deadline_is_not_lost():
    job = card(description="Closing date for applications\nFriday, 18 September.\nHow to apply",
               extra={"closing_date": "1 Oct 2026"})
    status = vacancy_status(job, today=date(2026, 9, 2))
    assert status["deadline"] == "2026-09-18"
    assert status["deadline_year_inferred"]


def test_same_day_unknown_application_is_withheld_but_not_claimed_closed():
    result = vacancy_status(card(extra={"closing_date": "2 Sept 2026", "application_check": "unverified"}), today=date(2026, 9, 2))
    assert not result["closed"]
    assert not result["reportable"]


def test_jsonld_graph_and_related_jobs_do_not_pollute_status():
    content = '<script type="application/ld+json">' + json.dumps({"@graph": [
        {"@type": "JobPosting", "title": "Data Engineer Level I", "validThrough": "2026-09-18T23:00:00Z"},
        {"@type": "JobPosting", "title": "Other job", "validThrough": "2020-01-01"},
    ]}) + '</script><main>Data Engineer Level I<button>Apply now</button><h2>Similar Jobs</h2>This job has expired. Closing date: 1 Jan 2020</main>'
    page = parse_page(content, "https://jobs.example.org/1", "Data Engineer Level I")
    assert page["deadlines"] == ["2026-09-18T23:00:00Z"]
    assert not page["closed"]


@pytest.mark.asyncio
async def test_long_description_does_not_skip_application_deadline():
    pages = {
        "/1": '<main>Data Engineer Level I Closing date: 2 Sept 2026<a href="/apply">Apply for this job</a></main>',
        "/apply": '<a href="https://employer.example.org/role">Continue to the employer\'s website</a>',
        "/role": '<meta http-equiv="refresh" content="0;url=\'https://employer.example.org/final\'">',
        "/final": '<main>Data Engineer Level I Closing date: 1 Sept 2026 at 11:55 pm<button>Apply now</button></main>',
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=pages[req.url.path]))) as client:
        job = card(description="Data pipelines and SQL. " * 100)
        result = await VacancyVerifier(client).verify(job)
    assert result["deadline"] == "2026-09-01"
    assert result["deadline_kind"] == "employer"
    assert len(job.extra["verification_pages"]) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("code,body,closed", [(404, "", True), (410, "", True), (403, "Access denied", False), (200, "Quick check needed", False), (200, "This job has expired", True), (200, "This role is now closed", True)])
async def test_missing_closed_and_challenge_pages(code, body, closed):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(code, text=body))) as client:
        result = await VacancyVerifier(client).verify(card())
    assert result["closed"] is closed
    assert result["application_check"] == ("closed" if closed else "unverified")


@pytest.mark.asyncio
async def test_dwp_catalogue_matches_exact_job_id_not_similar_title():
    def handler(req):
        if req.url.host == "careers.dwp.gov.uk":
            return httpx.Response(200, text='<a href=" https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=2011471 ">Data Engineer Closing date: 13 Sept 2026</a>')
        return httpx.Response(200, text="Quick check needed")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = VacancyVerifier(client)
        job = card()
        job.url = "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=2011471"
        assert (await verifier.verify(job))["application_check"] == "employer_listing"
        job.url = "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=2009916"
        assert (await verifier.verify(job))["application_check"] == "unverified"


def test_model_cannot_revive_expired_or_overwrite_deadline():
    settings = load_settings()
    job = card(extra={"closing_date": "1 Sept 2020"})
    base = {"base_score": 90, "work_mode": "hybrid", "path_id": "data_engineering"}
    assessment = {"job_key": "x", "recommended": True, "direct_employer": True, "deadline": "2099-01-01"}
    assert _build_ranked_jobs({"x": assessment}, {"x": (job, base, {"filename": "de.docx"})}, settings) == []
    ranked = _apply_global_ranking([{"job_key": "x", "overall_score": 80, "deadline_urgency": "expired"}], [{"job_key": "x", "rank": 1, "deadline_urgency": "none"}])
    assert ranked[0]["deadline_urgency"] == "expired"


def test_compact_card_also_shows_deadline_and_uncertainty():
    jobs = [{"title": "Example", "deadline": "2026-09-18", "application_check": "unverified"}]
    text = render_report(jobs, [], {}, datetime.now(UTC), detailed_jobs=0)[1]
    assert "18.09.2026" in text
    assert "не подтверждён" in text
