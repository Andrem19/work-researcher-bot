import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from work_researcher import persistence as db
from work_researcher import seller, training
from work_researcher.bot import (
    _apply_global_ranking,
    _assign_cvs,
    _build_ranked_jobs,
    _report_signature,
    _select_report_jobs,
    _write_run_audit,
)
from work_researcher.career import (
    classify_career_path,
    deterministic_assessment,
    entry_allowed,
    location_allowed,
    vacancy_status,
)
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


def test_negated_remote_wording_does_not_bypass_onsite_policy() -> None:
    card = JobCard(
        source="test", title="Junior Support Analyst", company="Acme",
        location_text="Paisley", contract_type="On-site Permanent Full time",
        description="This is fully onsite. There is no remote or work-from-home element.",
    )
    assert location_allowed(card) == (False, "on_site: outside allowed area")


def test_agency_and_senior_roles_are_rejected() -> None:
    agency = JobCard(source="test", title="Junior Data Engineer", company="Hays", location_text="Remote", description="Remote UK")
    senior = JobCard(source="test", title="Senior Data Engineer", company="Acme", location_text="Blackpool")
    assert deterministic_assessment(agency, "data_engineering", "Python SQL")["eligible"] is False
    assert deterministic_assessment(senior, "data_engineering", "Python SQL")["eligible"] is False


def test_known_agencies_from_live_results_are_rejected() -> None:
    for company in ("Allstaff", "The Huntsmith Limited", "Avanti", "Vermelo RPO", "Southern Lights Ltd"):
        card = JobCard(
            source="test", title="Junior Data Analyst", company=company,
            location_text="Remote", description="Remote UK",
        )
        result = deterministic_assessment(card, "analytics", "SQL Power BI")
        assert result["eligible"] is False
        assert result["posted_by"] == "agency"


def test_agency_client_wording_and_unrelated_brand_are_distinguished() -> None:
    assert seller.classify("Akkodis", "My client are hiring a Data Analyst.")[0] == "agency"
    assert seller.classify("Avanti West Coast", "Join our own analytics team.")[0] == "employer"
    assert seller.classify("Breedon Group plc", "Join our data team.")[0] == "employer"
    assert seller.classify("Environment Agency", "Join our GIS team.")[0] == "employer"
    assert seller.classify("eFinancialCareers", "A data job listing.")[0] == "unknown"


def test_normal_employee_benefits_are_not_paid_training() -> None:
    job = JobCard(
        source="test", title="Junior Data Engineer", company="Acme",
        salary_min=30000, salary_max=35000,
        description="Salary sacrifice pension and cycle scheme; loan repayment through payroll.",
    )
    assert training.classify(job) == (False, None)
    course = job.model_copy(update={"description": "You must pay for your training. Course fees apply."})
    assert training.classify(course)[0] is True


def test_mentoring_juniors_is_not_positive_entry_evidence() -> None:
    job = JobCard(
        source="test", title="Data Engineer",
        description="Provide guidance and mentoring to junior team members.",
    )
    assert entry_allowed(job)[0] is False
    junior = job.model_copy(update={
        "title": "Junior Data Engineer",
        "description": "You will receive mentoring from experienced colleagues.",
    })
    assert entry_allowed(junior)[0] is True


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
    assert "Обязательно" in messages[5]
    assert "Обязательно" not in messages[6]
    assert "Суть" not in messages[6]
    assert "Почему" in messages[6]
    assert "Нюанс" in messages[6]
    assert "CV:" in messages[6]
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


def test_report_signature_collapses_regional_copies_of_one_advert() -> None:
    blackpool = {
        "title": "Data Engineer Level I", "company": "DWP Digital",
        "salary_raw": "£38,772", "location_text": "Blackpool",
    }
    manchester = {**blackpool, "location_text": "Manchester"}
    different_role = {**blackpool, "title": "Data Engineer"}
    assert _report_signature(blackpool) == _report_signature(manchester)
    assert _report_signature(blackpool) != _report_signature(different_role)


def test_route_is_classified_from_vacancy_not_discovery_query() -> None:
    engineer = JobCard(
        source="test", title="Data Engineer", company="DWP Digital",
        description="Build and validate ETL data pipelines in Azure Data Factory.",
    )
    analyst = JobCard(
        source="test", title="Data Analyst", company="Acme",
        description="Create Power BI dashboards and analyse data with SQL.",
    )
    geospatial = JobCard(
        source="test", title="Graduate GIS Analyst", company="MapCo",
        description="Use ArcGIS, QGIS and spatial data.",
    )
    software = JobCard(
        source="test", title="Junior Python Developer", company="AppCo",
        description="Build backend REST APIs with FastAPI and unit tests.",
    )
    assert classify_career_path(engineer)[0] == "data_engineering"
    assert classify_career_path(analyst)[0] == "analytics"
    assert classify_career_path(geospatial)[0] == "geospatial_data"
    assert classify_career_path(software)[0] == "software_data_platform"


def test_off_route_jobs_do_not_receive_a_career_label() -> None:
    network = JobCard(
        source="test", title="Network Operations Engineer",
        description="Monitor routers, switches and telecoms incidents.",
    )
    administrator = JobCard(
        source="test", title="Data, Workflow and Secretarial Administrator",
        description="Diary management, typing and general office administration.",
    )
    assert classify_career_path(network)[0] is None
    assert classify_career_path(administrator)[0] is None


def test_report_selection_prefers_source_and_route_diversity_then_fills() -> None:
    jobs = [
        {
            "job_key": str(index), "title": f"Role {index}", "company": f"Co {index}",
            "salary_raw": str(30000 + index), "source": source, "path_id": path,
        }
        for index, (source, path) in enumerate([
            ("findajob", "analytics"),
            ("findajob", "analytics"),
            ("findajob", "analytics"),
            ("reed", "data_engineering"),
            ("civil_service", "software_data_platform"),
        ])
    ]
    selected = _select_report_jobs(
        jobs, max_jobs=4, diverse_max_per_path=2, diverse_max_per_source=2
    )
    assert [job["job_key"] for job in selected] == ["0", "1", "3", "4"]


def test_report_selection_collapses_board_and_employer_copy() -> None:
    common = {
        "salary_raw": "£25,760 to £27,476 a year", "source": "findajob",
        "path_id": "analytics", "location_text": "Preston",
    }
    jobs = [
        {
            **common, "job_key": "board", "title": "Compliance and Assurance Analyst",
            "company": "NHS Jobs",
        },
        {
            **common, "job_key": "employer",
            "title": "Compliance and Assurance Analyst | Lancashire Teaching Hospitals",
            "company": "Lancashire Teaching Hospitals NHS Foundation Trust",
            "salary_raw": "£25,760 - £27,476 Per Annum, Pro Rata",
        },
    ]
    selected = _select_report_jobs(
        jobs, max_jobs=10, diverse_max_per_path=4, diverse_max_per_source=5
    )
    assert [job["job_key"] for job in selected] == ["board"]


def test_exact_report_audit_is_saved_for_later_diagnosis(tmp_path: Path) -> None:
    settings = load_settings(Path("missing-test-config.toml"))
    settings.data_dir = tmp_path
    started = datetime(2026, 9, 2, 16, 0, tzinfo=UTC)
    payload = {"messages": ["Report"], "jobs": [{"title": "Data Engineer"}]}
    _write_run_audit(settings, started, payload)
    path = tmp_path / "nightly-runs" / "20260902T160000Z.json"
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_cv_assignment_uses_the_four_route_specific_filenames(tmp_path: Path) -> None:
    filenames = [
        "Andrew_CV_Data_Analytics.docx",
        "Andrew_CV_Data_Engineering.docx",
        "Andrew_CV_Geospatial_Data_Engineering.docx",
        "Andrew_CV_Software_Engineering.docx",
    ]
    for filename in filenames:
        (tmp_path / filename).write_bytes(b"placeholder")
    settings = load_settings(Path("missing-test-config.toml"))
    settings.cv_dir = tmp_path
    with patch("work_researcher.bot.extract_text", return_value=""):
        mapping = _assign_cvs(settings)
    assert mapping["analytics"]["filename"] == "Andrew_CV_Data_Analytics.docx"
    assert mapping["data_engineering"]["filename"] == "Andrew_CV_Data_Engineering.docx"
    assert mapping["geospatial_data"]["filename"] == (
        "Andrew_CV_Geospatial_Data_Engineering.docx"
    )
    assert mapping["software_data_platform"]["filename"] == (
        "Andrew_CV_Software_Engineering.docx"
    )


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
