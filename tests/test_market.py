import importlib.util
from pathlib import Path

from work_researcher.cli import build_parser
from work_researcher.config import load_settings
from work_researcher.domain import JobCard
from work_researcher.market import (
    build_slice_statistics,
    deterministic_level,
    extract_technologies,
    percentile,
    salary_values,
)


def test_technology_aliases_are_normalized_without_short_word_false_positives() -> None:
    technologies = extract_technologies(
        "Build PySpark and C++ pipelines in Azure Databricks with dbt, PostgreSQL and Power BI. "
        "The team will go to production after review."
    )
    assert technologies == [
        "Azure", "C++", "Databricks", "PostgreSQL", "Power BI", "Spark", "dbt",
    ]
    assert "Go" not in technologies


def test_salary_range_is_annualised_to_midpoint() -> None:
    annual = JobCard(
        source="test", salary_min=60000, salary_max=80000, salary_period="year"
    )
    daily = JobCard(source="test", salary_min=400, salary_max=500, salary_period="day")
    assert salary_values(annual) == (60000.0, 80000.0, 70000.0)
    assert salary_values(daily) == (100000.0, 125000.0, 112500.0)


def test_percentile_uses_linear_interpolation() -> None:
    values = [40000, 60000, 80000, 100000]
    assert percentile(values, 0.25) == 55000
    assert percentile(values, 0.50) == 70000
    assert percentile(values, 0.75) == 85000


def test_market_statistics_include_demand_salary_quartiles_and_stacks() -> None:
    records = [
        {
            "salary": 40000, "technologies": ["Python", "SQL"],
            "mandatory_technologies": ["SQL"],
        },
        {
            "salary": 60000, "technologies": ["Python", "SQL"],
            "mandatory_technologies": ["Python", "SQL"],
        },
        {
            "salary": 80000, "technologies": ["AWS", "Snowflake"],
            "mandatory_technologies": ["AWS"],
        },
        {
            "salary": 100000, "technologies": ["AWS", "Snowflake"],
            "mandatory_technologies": ["AWS", "Snowflake"],
        },
        {"salary": None, "technologies": ["SQL"], "mandatory_technologies": []},
    ]
    stats = build_slice_statistics(records, minimum_combination_count=2)
    assert stats["job_count"] == 5
    assert stats["salary_count"] == 4
    assert stats["salary_coverage_pct"] == 80
    assert stats["salary"]["p50"] == 70000

    by_name = {row["name"]: row for row in stats["technologies"]}
    assert by_name["SQL"]["count"] == 3
    assert by_name["SQL"]["prevalence_pct"] == 60
    assert by_name["SQL"]["salary"]["p50"] == 50000
    assert by_name["SQL"]["salary_quartiles"] == {"q1": 1, "q2": 1, "q3": 0, "q4": 0}
    assert by_name["Snowflake"]["salary"]["p50"] == 90000
    assert by_name["Snowflake"]["median_premium"] == 20000

    combinations = {row["name"]: row for row in stats["combinations"]}
    assert combinations["Python + SQL"]["count"] == 2
    assert combinations["AWS + Snowflake"]["salary"]["p50"] == 90000


def test_market_levels_and_configuration_contract() -> None:
    assert deterministic_level(JobCard(source="test", title="Graduate GIS Analyst")) == "entry"
    assert deterministic_level(JobCard(source="test", title="Data Engineer")) == "middle"
    assert deterministic_level(JobCard(source="test", title="Principal Engineer")) == "senior"
    settings = load_settings(Path("missing-market-config.toml"))
    assert settings.market["high_salary_threshold"] == 80000
    assert settings.market["window_days"] == 30


def test_weekly_market_cli_and_dashboard_contract() -> None:
    args = build_parser().parse_args(["weekly-market"])
    assert args.command == "weekly-market"
    dashboard = Path("dashboard/index.html").read_text(encoding="utf-8")
    assert "data-level" in dashboard
    assert "High-paying £80k+" in dashboard
    assert "data.json" in dashboard
    assert "Demand" in dashboard and "salary" in dashboard


def test_nginx_location_installer_is_idempotent(tmp_path: Path) -> None:
    script = Path("deploy/install-nginx-location.py")
    spec = importlib.util.spec_from_file_location("install_nginx_location", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    site = tmp_path / "devbot.remart.ovh"
    site.write_text(
        "server {\n    listen 443 ssl;\n    location / {\n        return 404;\n    }\n}\n",
        encoding="utf-8",
    )
    module.install(site)
    first = site.read_text(encoding="utf-8")
    module.install(site)
    assert site.read_text(encoding="utf-8") == first
    assert first.count("work-researcher-jobs.conf") == 1
    assert site.with_suffix(".ovh.before-work-researcher").exists()
