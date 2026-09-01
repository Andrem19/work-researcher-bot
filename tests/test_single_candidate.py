import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from work_researcher import persistence as db
from work_researcher.career import deterministic_assessment, location_allowed
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


def test_telegram_report_escapes_untrusted_text() -> None:
    messages = render_report([{
        "title": "A < B", "url": "https://example.test/?a=1&b=2", "company": "Acme & Co",
        "direct_employer_reason": "verified", "path_label": "Data", "overall_score": 91,
        "location_text": "Remote", "work_mode": "remote", "summary_ru": "Safe",
        "cv_filename": "cv.docx", "source": "test",
    }], [{"provider": "test", "ok": True}], {"files": [{}, {}, {}, {}]}, __import__("datetime").datetime.now())
    assert "A &lt; B" in messages[1]
    assert "Acme &amp; Co" in messages[1]


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
