import json
from datetime import UTC, datetime

import httpx
import pytest

from work_researcher import bot, publication
from work_researcher import persistence as db
from work_researcher.config import load_settings
from work_researcher.domain import JobCard
from work_researcher.freshness import VacancyVerifier, parse_page
from work_researcher.telegram import render_report

NOW = datetime(2026, 9, 2, 20, tzinfo=UTC)
DESCRIPTION = "Junior Data Engineer hybrid SQL pipelines. " + " ".join(f"requirement{i}" for i in range(50))


def card(source="reed", url="https://www.reed.co.uk/jobs/example/123", raw=None):
    result = JobCard(source=source, url=url, title="Junior Data Engineer", company="Acme",
                     location_text="Blackpool", description=DESCRIPTION, salary_min=30000)
    if raw:
        publication.add_evidence(result, raw, url, kind="datePosted")
    return result


@pytest.mark.parametrize(("raw", "day", "precision"), [
    ("28 Aug 2026", "2026-08-28", "day"),
    ("2026-08-28T12:30:00Z", "2026-08-28", "instant"),
    ("28/08/2026", "2026-08-28", "day"),
    ("2 days ago", "2026-08-31", "approximate"),
    ("1 hr ago", "2026-09-02", "approximate"),
])
def test_publication_date_precision(raw, day, precision):
    value = publication.parse_posted(raw, now=NOW)
    assert value["posted_at"].startswith(day)
    assert value["precision"] == precision


def test_no_guessed_future_or_modified_dates():
    assert publication.parse_posted("2026-09-03", now=NOW) is None
    assert publication.parse_posted("unknown", now=NOW) is None
    missing = card()
    missing.extra.update({"first_seen": "2020-01-01", "fetched_at": "2020-01-01"})
    assert publication.report_fields(missing)["posted_at"] is None
    missing.source = "jooble"
    missing.posted_at = datetime(2020, 1, 1, tzinfo=UTC)
    assert publication.evidence(missing) == []


def test_yearless_publication_handles_new_year_without_future_guess():
    value = publication.parse_posted("31 December", now=datetime(2026, 1, 2, tzinfo=UTC))
    assert value["posted_at"].startswith("2025-12-31")
    assert value["year_inferred"]


def test_page_extracts_posting_metadata_not_modified_or_other_job():
    payload = {"@graph": [
        {"@type": "JobPosting", "title": "Junior Data Engineer", "datePosted": "2026-08-20", "dateModified": "2026-09-02"},
        {"@type": "JobPosting", "title": "Other role", "datePosted": "2020-01-01"},
    ]}
    page = parse_page('<script type="application/ld+json">' + json.dumps(payload) + '</script><main>Junior Data Engineer Posting date: 28 Aug 2026 Closing date: 18 Sep 2026</main>', card().url, card().title)
    dates = [publication.parse_posted(raw, now=NOW)["posted_at"][:10] for raw, _ in page["publications"]]
    assert dates == ["2026-08-28", "2026-08-20"]


def test_missing_posting_date_cannot_consume_adjacent_deadline():
    page = parse_page("<main>Junior Data Engineer Posting date: not stated Closing date: 18 Sep 2026</main>", card().url, card().title)
    assert all(publication.parse_posted(raw, now=NOW) is None for raw, _ in page["publications"])


def test_publication_source_is_actual_page_not_redirecting_board():
    assert publication.source_for_url("https://careers.example.org/jobs/1", "adzuna") == "careers.example.org"
    assert publication.source_for_url("https://www.reed.co.uk/jobs/123", "jooble") == "reed"


def test_selects_oldest_platform_and_retains_all_sources():
    newer = card(raw="2026-08-28")
    older = card("findajob", "https://www.jobs.service.gov.uk/jobs/abc", "2026-08-20")
    assert publication.same_vacancy(newer, older)
    publication.attach_sources(newer, [newer, older])
    result = publication.report_fields(newer)
    assert result["source"] == "findajob"
    assert result["url"] == older.url
    assert result["posted_at"].startswith("2026-08-20")
    assert len(result["publication_sources"]) == 2


def test_different_seniority_and_application_ids_never_share_dates():
    a, b = card(), card("findajob", "https://jobs.example.org/2", "2020-01-01")
    b.title = "Senior Data Engineer"
    assert not publication.same_vacancy(a, b)
    b.title = a.title
    a.extra["verification_pages"] = [{}, {"url": "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=111"}]
    b.extra["verification_pages"] = [{}, {"url": "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=222"}]
    assert not publication.same_vacancy(a, b)
    b.extra["verification_pages"][-1]["url"] = "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?jcode=111&source=board"
    assert publication.same_vacancy(a, b)


def test_identical_generic_titles_without_description_are_not_duplicates():
    a, b = card(), card("findajob", "https://jobs.example.org/2")
    a.description = b.description = "Data engineer required."
    assert not publication.same_vacancy(a, b)


def test_archived_original_keeps_active_link_and_labels_provenance():
    a, b = card(raw="2026-08-28"), card("findajob", "https://jobs.example.org/2", "2020-01-01")
    b.extra["vacancy_closed"] = True
    publication.attach_sources(a, [a, b])
    result = publication.report_fields(a)
    assert result["publication_archived"]
    assert result["publication_url"] == b.url
    assert "url" not in result  # caller's active link remains untouched


def test_ties_and_approximate_dates_do_not_claim_false_precision():
    a, b = card(raw="2026-08-28"), card("findajob", "https://jobs.example.org/2", "2026-08-28")
    publication.attach_sources(a, [a, b])
    assert publication.report_fields(a)["publication_tied"]
    a.extra["publication_evidence"][0]["posted_at"] = "2020-01-01T00:00:00+00:00"
    a.extra["publication_evidence"][0]["precision"] = "approximate"
    publication.attach_sources(a, [a, b])
    assert publication.report_fields(a)["source"] == "findajob"


def test_exact_same_day_instants_choose_earliest_time():
    a, b = card(raw="2026-08-28T15:00:00Z"), card("findajob", "https://jobs.example.org/2", "2026-08-28T08:00:00Z")
    publication.attach_sources(a, [a, b])
    assert publication.report_fields(a)["source"] == "findajob"


@pytest.mark.asyncio
async def test_publication_history_preserves_old_date_and_separate_urls(tmp_path):
    a, b = card(raw="2026-08-20"), card(url="https://www.reed.co.uk/jobs/example/456", raw="2026-08-25")
    async with db.connect(tmp_path / "history.db") as conn:
        await db.save_publications(conn, [a, b])
        refreshed = card(raw="2026-09-01")
        await db.save_publications(conn, [refreshed])
        history = await db.publication_history(conn, [a])
    assert len(history) == 2
    stored = next(c for c in history if c.url == a.url)
    assert publication.report_fields(stored)["posted_at"].startswith("2026-08-20")
    assert publication.report_fields(stored)["publication_date_conflict"]


@pytest.mark.asyncio
async def test_verifier_captures_published_date_despite_long_description():
    content = '<main>Junior Data Engineer Posting date: 28 Aug 2026 Closing date: 18 Sep 2026<button>Apply now</button></main>'
    job = card()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=content))) as client:
        await VacancyVerifier(client).verify(job)
    assert publication.report_fields(job)["posted_at"].startswith("2026-08-28")


@pytest.mark.parametrize("detailed", [0, 5])
def test_both_card_formats_always_contain_publication_and_deadline(detailed):
    job = {"title": "Example", "posted_at": "2026-08-28", "deadline": "2026-09-18"}
    message = render_report([job], [], {}, NOW, detailed_jobs=detailed)[1]
    assert "<b>Опубликовано:</b> 28.08.2026" in message
    assert "<b>Дедлайн:</b> 18.09.2026" in message
    missing = render_report([{"title": "Example"}], [], {}, NOW, detailed_jobs=detailed)[1]
    assert "<b>Опубликовано:</b> не указано" in missing
    assert "<b>Дедлайн:</b> не указано" in missing


@pytest.mark.asyncio
async def test_nightly_pipeline_does_not_drop_older_platform_before_ranking(tmp_path, monkeypatch):
    settings = load_settings(tmp_path / "missing.toml")
    settings.data_dir, settings.db_path, settings.cv_dir = tmp_path, tmp_path / "jobs.db", tmp_path / "cvs"
    newer, older = card(raw="2026-08-28"), card("findajob", "https://jobs.example.org/2", "2026-08-20")
    newer.description += " More description."

    async def collect(_):
        return [("data_engineering", newer), ("data_engineering", older)], []

    async def sync(_):
        return {"files": ["cv"]}

    async def enrich(_):
        pass

    async def verify(cards):
        assert len(cards) == 2
        for job in cards:
            job.extra.update({"application_check": "application_page_checked", "closing_date": "18 Sep 2099"})

    async def assess(_, batch):
        return [{"job_key": row["job_key"], "overall_score": 80, "recommended": True, "direct_employer": True,
                 "posted_at": "2000-01-01", "source": "invented", "url": "https://invented.example.org"} for row in batch]

    monkeypatch.setattr(bot, "_collect", collect)
    monkeypatch.setattr(bot, "sync_cvs_from_drive", sync)
    monkeypatch.setattr(bot, "_enrich_all", enrich)
    monkeypatch.setattr(bot, "verify_cards", verify)
    monkeypatch.setattr(bot, "assess_batch", assess)
    monkeypatch.setattr(bot, "_assign_cvs", lambda _: {"data_engineering": {"filename": "de.docx", "text": "SQL"}})
    monkeypatch.setattr(bot, "deterministic_assessment", lambda *args: {"eligible": True, "base_score": 80, "path_id": "data_engineering", "work_mode": "hybrid"})
    result = await bot.run_once(settings, deliver=False)
    assert result["reported"] == 1
    report = result["jobs"][0]
    assert report["url"] == older.url
    assert report["source"] == "findajob"
    assert report["posted_at"].startswith("2026-08-20")
    assert len(report["publication_sources"]) == 2

    async def collect_only_newer(_):
        return [("data_engineering", newer)], []

    monkeypatch.setattr(bot, "_collect", collect_only_newer)
    second = await bot.run_once(settings, deliver=False)
    assert second["jobs"][0]["url"] == older.url
    assert second["jobs"][0]["posted_at"].startswith("2026-08-20")
