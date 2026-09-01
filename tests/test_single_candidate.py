import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from work_researcher import persistence as db
from work_researcher.bot import _apply_global_ranking, _build_ranked_jobs
from work_researcher.career import deterministic_assessment, location_allowed, vacancy_status
from work_researcher.config import load_settings
from work_researcher.domain import JobCard
from work_researcher.drive import _select
from work_researcher.requirements import extract_requirements
from work_researcher.server import create_server
from work_researcher.telegram import render_report


def test_configuration_is_single_candidate() -> None:
    with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
        config = Path(directory) / "config.toml"
        config.write_text('[general]\ncandidate_name="Andrey Remnev"\n', encoding="utf-8")
        settings = load_settings(config)
        assert settings.candidate_name == "Andrey Remnev"
        assert not hasattr(settings, "available_profiles")


def test_mcp_has_no_profile_switch_tool() -> None:
    settings = load_settings(Path("missing-test-config.toml"))
    mcp, _ = create_server(settings)
    import asyncio
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert "manage_profiles" not in names
    assert "start_application" in names


def test_location_policy() -> None:
    remote = JobCard(source="test", title="Junior Data Engineer remote", location_text="London")
    onsite = JobCard(source="test", title="Junior Data Engineer", location_text="London")
    hybrid = JobCard(source="test", title="Junior Data Analyst hybrid", location_text="Manchester")
    assert location_allowed(remote)[0] is True
    assert location_allowed(onsite)[0] is False
    assert location_allowed(hybrid)[0] is True


def test_agency_and_senior_roles_are_rejected() -> None:
    agency = JobCard(source="test", title="Junior Data Engineer", company="Hays", location_text="Remote", description="Remote UK")
    senior = JobCard(source="test", title="Senior Data Engineer", company="Acme", location_text="Blackpool")
    assert deterministic_assessment(agency, "data_engineering", "Python SQL")["eligible"] is False
    assert deterministic_assessment(senior, "data_engineering", "Python SQL")["eligible"] is False


def test_apprentice_role_with_manager_in_occupation_name_is_entry_level() -> None:
    apprentice = JobCard(
        source="civil_service", title="Apprentice IT Asset Manager",
        company="Department for Work and Pensions", location_text="Blackpool",
    )
    assert deterministic_assessment(apprentice, "software_data_platform", "Python SQL")["eligible"] is True


def test_telegram_report_escapes_untrusted_text() -> None:
    messages = render_report([{
        "title": "A < B", "url": "https://example.test/?a=1&b=2", "company": "Acme & Co",
        "direct_employer_reason": "verified", "path_label": "Data", "overall_score": 91,
        "location_text": "Remote", "work_mode": "remote", "summary_ru": "Safe",
        "cv_filename": "cv.docx", "source": "test",
    }], [{"provider": "test", "ok": True}], {"files": [{}, {}, {}, {}]}, __import__("datetime").datetime.now())
    assert "A &lt; B" in messages[1]
    assert "Acme &amp; Co" in messages[1]


def test_telegram_uses_five_detailed_then_compact_cards() -> None:
    job = {
        "title": "Junior Data Analyst", "url": "https://example.test/job",
        "company": "Acme", "direct_employer_reason": "verified",
        "path_label": "Analytics", "overall_score": 75,
        "location_text": "Manchester", "work_mode": "hybrid",
        "salary_raw": "£30,000", "summary_ru": "Краткое описание.",
        "mandatory_requirements": ["SQL"], "desirable_requirements": ["Python"],
        "special_conditions": [], "cv_strengths": ["SQL"], "cv_gaps": [],
        "rejection_reasons": [], "cv_filename": "analytics.docx", "source": "test",
        "rank_reason_ru": "Лучшее сочетание entry-сигналов и географии.",
        "entry_evidence": ["Training provided"],
        "main_tradeoff_ru": "Зарплата не указана.",
    }
    messages = render_report(
        [{**job, "title": f"Junior Data Analyst {index}"} for index in range(1, 7)],
        [{"provider": "test", "ok": True}],
        {"files": [{}, {}, {}, {}]},
        __import__("datetime").datetime.now(),
        detailed_jobs=5,
    )
    assert len(messages) == 7
    assert "Обязательные требования" in messages[5]
    assert "Обязательные требования" not in messages[6]
    assert "Суть" not in messages[6]
    assert "Почему в топе" in messages[6]
    assert "Главный нюанс" in messages[6]
    assert "Подробности доступны по ссылке" in messages[6]
    assert "первые <b>5</b> подробно" in messages[0]


def test_glm_cannot_veto_a_hard_filtered_vacancy() -> None:
    settings = load_settings(Path("missing-test-config.toml"))
    card = JobCard(
        source="test", title="Junior Data Analyst", company="Acme",
        location_text="Blackpool", url="https://example.test/job",
    )
    base = {
        "path_id": "analytics", "base_score": 73, "work_mode": "on_site",
        "posted_by_reason": "no agency signals",
    }
    jobs = _build_ranked_jobs({"job-1": {
        "job_key": "job-1", "recommended": False, "direct_employer": False,
        "overall_score": 42, "rejection_reasons": ["low CV fit"],
    }}, {"job-1": (card, base, {"filename": "analytics.docx"})}, settings)
    assert len(jobs) == 1
    assert jobs[0]["hard_filters_passed"] is True
    assert jobs[0]["review_tier"] == "fallback"
    assert jobs[0]["direct_employer"] is True


def test_global_ranking_reorders_but_never_drops_jobs() -> None:
    jobs = [
        {"job_key": "a", "overall_score": 80},
        {"job_key": "b", "overall_score": 70},
        {"job_key": "c", "overall_score": 60},
    ]
    ranking = [
        {"job_key": "b", "rank": 1, "final_score": 93, "rank_reason_ru": "Лучший fit"},
        {"job_key": "a", "rank": "invalid", "final_score": 82},
        {"job_key": "b", "rank": 2, "final_score": 10},
    ]
    result = _apply_global_ranking(jobs, ranking)
    assert [job["job_key"] for job in result] == ["b", "a", "c"]
    assert result[0]["overall_score"] == 93
    assert result[0]["rank_reason_ru"] == "Лучший fit"
    assert [job["global_rank"] for job in result] == [1, 2, 3]


def test_explicitly_closed_and_expired_vacancies_are_rejected() -> None:
    closed = JobCard(
        source="test", title="Junior Data Analyst", company="Acme",
        location_text="Blackpool", description="Applications are now closed.",
    )
    expired = JobCard(
        source="test", title="Junior Data Analyst", company="Acme",
        location_text="Blackpool", description="Closing date: 31 August 2020",
    )
    assert vacancy_status(closed, today=__import__("datetime").date(2026, 9, 1))["closed"]
    status = vacancy_status(expired, today=__import__("datetime").date(2026, 9, 1))
    assert status["deadline"] == "2020-08-31"
    assert status["deadline_urgency"] == "expired"
    assert deterministic_assessment(expired, "analytics", "SQL Power BI")["eligible"] is False


def test_upcoming_deadline_is_retained_and_marked_urgent() -> None:
    card = JobCard(
        source="test", title="Junior Data Analyst", company="Acme",
        location_text="Blackpool", description="Applications close: 3 September 2026",
    )
    status = vacancy_status(card, today=__import__("datetime").date(2026, 9, 1))
    assert status["closed"] is False
    assert status["deadline"] == "2026-09-03"
    assert status["deadline_urgency"] == "urgent"


def test_drive_selection_excludes_geology(tmp_path: Path) -> None:
    names = [
        "Data_Engineering.docx",
        "Geospatial_Data_Engineering.docx",
        "Data_Analytics.docx",
        "Software_Engineering.docx",
        "Engineering_Geology.docx",
    ]
    files = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"test")
        files.append(path)
    settings = load_settings(Path("missing-test-config.toml"))
    settings.drive = {
        "exclude_name_patterns": ["geolog"],
        "include_names": [],
        "required_count": 4,
    }
    assert len(_select(settings, files)) == 4


async def test_report_delivery_state_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    async with db.connect(database) as conn:
        assert await db.delivered_hashes(conn) == set()
        await db.mark_report_delivered(conn, ["job-a", "job-b"], [11, 12, 13])
    async with db.connect(database) as conn:
        assert await db.delivered_hashes(conn) == {"job-a", "job-b"}


def test_proven_experience_without_years_does_not_parse_text_as_integer() -> None:
    requirements = extract_requirements(
        "Proven experience in data capture and analysis  Expert in the use of GIS"
    )
    assert requirements["experience_years"] is None
    assert requirements["hard"][0]["type"] == "experience"
