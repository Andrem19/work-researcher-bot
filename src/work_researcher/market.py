"""Weekly UK technology-demand and salary market research."""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import seller, training
from .bot import _enrich_all
from .config import Settings, ensure_dirs
from .domain import JobCard, SearchParams
from .llm import classify_market_batch
from .providers import run_search
from .textutils import annualise

logger = logging.getLogger("work_researcher.market")

LEVEL_LABELS = {
    "entry": "Entry",
    "middle": "Middle",
    "high": "High-paying £80k+",
}

MARKET_PATHS = {
    "data_engineering": {
        "label": "Data Engineering",
        "queries": {
            "entry": [
                "Junior Data Engineer", "Graduate Data Engineer", "Trainee Data Engineer",
                "Data Engineering Apprentice", "Junior Analytics Engineer",
                "Junior ETL Developer", "Junior Data Platform Engineer",
            ],
            "middle": [
                "Data Engineer", "Analytics Engineer", "ETL Developer",
                "Data Warehouse Engineer", "Data Platform Engineer", "Cloud Data Engineer",
                "BI Engineer", "Database Developer",
            ],
            "high": [
                "Senior Data Engineer", "Lead Data Engineer", "Principal Data Engineer",
                "Data Architect", "Data Platform Architect", "Head of Data Engineering",
                "Senior Analytics Engineer",
            ],
        },
    },
    "geospatial_data": {
        "label": "Geospatial Data Engineering",
        "queries": {
            "entry": [
                "Junior GIS Analyst", "Graduate Geospatial Analyst", "Junior GIS Technician",
                "Graduate GIS", "Geospatial Apprentice", "Junior Remote Sensing Analyst",
            ],
            "middle": [
                "Geospatial Data Engineer", "GIS Developer", "GIS Analyst",
                "Geospatial Analyst", "Spatial Data Engineer", "GIS Consultant",
                "Remote Sensing Analyst", "Geospatial Data Scientist",
            ],
            "high": [
                "Senior Geospatial Engineer", "Lead GIS Architect", "Senior GIS Developer",
                "Senior GIS Consultant", "Principal Geospatial Consultant",
                "Geospatial Architect", "GIS Manager", "Head of Geospatial",
            ],
        },
    },
    "analytics": {
        "label": "Data Analytics",
        "queries": {
            "entry": [
                "Junior Data Analyst", "Graduate Data Analyst", "Trainee Data Analyst",
                "Data Analyst Apprentice", "Junior BI Analyst", "Graduate BI Analyst",
                "Junior Reporting Analyst",
            ],
            "middle": [
                "Data Analyst", "Business Intelligence Analyst", "BI Developer",
                "Reporting Analyst", "Insight Analyst", "Product Analyst",
                "Marketing Data Analyst", "Operations Data Analyst",
            ],
            "high": [
                "Senior Data Analyst", "Lead Data Analyst", "Principal Data Analyst",
                "Analytics Manager", "BI Manager", "Head of Analytics",
                "Director of Analytics", "Analytics Consultant",
            ],
        },
    },
    "software_data_platform": {
        "label": "Software Engineering",
        "queries": {
            "entry": [
                "Junior Software Engineer", "Graduate Software Engineer",
                "Software Engineering Apprentice", "Junior Python Developer",
                "Graduate Python Developer", "Junior Backend Developer",
                "Junior Platform Engineer",
            ],
            "middle": [
                "Software Engineer", "Python Software Engineer", "Backend Software Engineer",
                "Python Developer", "Backend Developer", "Platform Engineer",
                "API Developer", "Cloud Software Engineer",
            ],
            "high": [
                "Senior Software Engineer", "Lead Software Engineer",
                "Principal Software Engineer", "Staff Software Engineer",
                "Lead Platform Engineer", "Principal Platform Engineer",
                "Software Architect", "Head of Software Engineering",
            ],
        },
    },
}

# Canonical technology labels and deliberately conservative aliases. Boundaries
# avoid matching short names such as R, Go or FME inside ordinary words.
TECHNOLOGY_PATTERNS: dict[str, tuple[str, ...]] = {
    "SQL": (r"\bsql\b",),
    "Python": (r"\bpython\b",),
    "Scala": (r"\bscala\b",),
    "Java": (r"\bjava\b",),
    "C#": (r"\bc\s*#(?!\w)", r"\bcsharp\b"),
    "C++": (r"\bc\+\+(?!\w)",),
    "JavaScript": (r"\bjavascript\b", r"\bjs\b"),
    "TypeScript": (r"\btypescript\b",),
    "Go": (r"\bgolang\b", r"\bgo\s+(?:language|programming)\b"),
    "R": (r"\br\s+(?:language|programming)\b",),
    "AWS": (r"\baws\b", r"amazon web services"),
    "Azure": (r"\bazure\b",),
    "GCP": (r"\bgcp\b", r"google cloud(?: platform)?"),
    "Databricks": (r"\bdatabricks\b",),
    "Snowflake": (r"\bsnowflake\b",),
    "BigQuery": (r"\bbig\s*query\b",),
    "Redshift": (r"\bredshift\b",),
    "Microsoft Fabric": (r"\bmicrosoft fabric\b", r"\bfabric\b"),
    "Azure Data Factory": (r"\bazure data factory\b", r"\badf\b"),
    "Azure Synapse": (r"\b(?:azure\s+)?synapse\b",),
    "AWS Glue": (r"\b(?:aws\s+)?glue\b",),
    "AWS Lambda": (r"\b(?:aws\s+)?lambda\b",),
    "Amazon S3": (r"\b(?:amazon\s+)?s3\b",),
    "Spark": (r"\b(?:apache\s+)?spark\b", r"\bpyspark\b"),
    "Kafka": (r"\b(?:apache\s+)?kafka\b",),
    "Flink": (r"\b(?:apache\s+)?flink\b",),
    "Airflow": (r"\b(?:apache\s+)?airflow\b",),
    "dbt": (r"\bdbt\b", r"data build tool"),
    "Hadoop": (r"\bhadoop\b",),
    "Kubernetes": (r"\bkubernetes\b", r"\bk8s\b"),
    "Docker": (r"\bdocker\b", r"\bcontainers?\b"),
    "Terraform": (r"\bterraform\b",),
    "Git": (r"\bgit(?:hub|lab)?\b",),
    "CI/CD": (r"\bci\s*/?\s*cd\b", r"continuous integration"),
    "PostgreSQL": (r"\bpostgres(?:ql)?\b",),
    "SQL Server": (r"\bsql server\b", r"\bmssql\b"),
    "Oracle": (r"\boracle(?: db| database)?\b",),
    "MongoDB": (r"\bmongo(?:db)?\b",),
    "Elasticsearch": (r"\belastic\s*search\b",),
    "Redis": (r"\bredis\b",),
    "Neo4j": (r"\bneo4j\b",),
    "Power BI": (r"\bpower\s*bi\b",),
    "Tableau": (r"\btableau\b",),
    "Looker": (r"\blooker(?: studio)?\b",),
    "Excel": (r"\bexcel\b",),
    "DAX": (r"\bdax\b",),
    "Power Query": (r"\bpower query\b",),
    "SAS": (r"\bsas\b",),
    "Pandas": (r"\bpandas\b",),
    "NumPy": (r"\bnumpy\b",),
    "ArcGIS": (r"\barcgis(?: pro| online)?\b",),
    "QGIS": (r"\bqgis\b",),
    "PostGIS": (r"\bpostgis\b",),
    "FME": (r"\bfme\b",),
    "GeoPandas": (r"\bgeopandas\b",),
    "GDAL": (r"\bgdal\b",),
    "Mapbox": (r"\bmapbox\b",),
    "ArcPy": (r"\barcpy\b",),
    "GeoServer": (r"\bgeoserver\b",),
    "Leaflet": (r"\bleaflet(?:\.js)?\b",),
    "OpenLayers": (r"\bopenlayers\b",),
    "React": (r"\breact(?:\.js|js)?\b",),
    "Node.js": (r"\bnode(?:\.js|js)\b",),
    ".NET": (r"\.net\b", r"\bdotnet\b"),
    "FastAPI": (r"\bfastapi\b",),
    "Django": (r"\bdjango\b",),
    "Flask": (r"\bflask\b",),
    "Spring": (r"\bspring(?: boot)?\b",),
    "REST APIs": (r"\brest(?:ful)?\s+api", r"\brest apis?\b"),
    "GraphQL": (r"\bgraphql\b",),
    "Microservices": (r"\bmicroservices?\b",),
    "Linux": (r"\blinux\b",),
    "ETL/ELT": (r"\betl\b", r"\belt\b", r"extract[, ]+transform[, ]+(?:and )?load"),
}

ENTRY_RE = re.compile(
    r"\b(junior|graduate|trainee|entry[ -]level|apprentice|level\s*(?:i|1))\b",
    re.I,
)
SENIOR_RE = re.compile(
    r"\b(senior|lead|principal|staff|architect|manager|head of|director)\b",
    re.I,
)


def extract_technologies(text: str | None) -> list[str]:
    haystack = text or ""
    return sorted(
        name
        for name, patterns in TECHNOLOGY_PATTERNS.items()
        if any(re.search(pattern, haystack, re.I) for pattern in patterns)
    )


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear-interpolated percentile compatible with common P25/P50/P75 definitions."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def salary_values(card: JobCard) -> tuple[float | None, float | None, float | None]:
    low = annualise(card.salary_min, card.salary_period)
    high = annualise(card.salary_max, card.salary_period)
    if low is None and high is None:
        return None, None, None
    low = low if low is not None else high
    high = high if high is not None else low
    if low is None or high is None or low <= 0 or high <= 0:
        return None, None, None
    if low > high:
        low, high = high, low
    midpoint = round((low + high) / 2)
    if midpoint < 10000 or midpoint > 300000:
        return None, None, None
    return float(low), float(high), float(midpoint)


def deterministic_level(card: JobCard) -> str:
    title = card.title or ""
    if ENTRY_RE.search(title):
        return "entry"
    if SENIOR_RE.search(title):
        return "senior"
    return "middle"


def _quartile_bucket(value: float, quartiles: dict[str, float | None]) -> str:
    if quartiles["p25"] is not None and value <= quartiles["p25"]:
        return "q1"
    if quartiles["p50"] is not None and value <= quartiles["p50"]:
        return "q2"
    if quartiles["p75"] is not None and value <= quartiles["p75"]:
        return "q3"
    return "q4"


def _salary_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "max": round(max(values), 2) if values else None,
    }


def _metric_row(
    name: str,
    observations: list[dict],
    total: int,
    slice_median: float | None,
) -> dict[str, Any]:
    salaries = [item["salary"] for item in observations if item.get("salary") is not None]
    salary = _salary_summary(salaries)
    premium = (
        round(salary["p50"] - slice_median, 2)
        if salary["p50"] is not None and slice_median is not None else None
    )
    parts = name.split(" + ")
    required_count = sum(
        all(part in item.get("mandatory_technologies", []) for part in parts)
        for item in observations
    )
    return {
        "name": name,
        "count": len(observations),
        "prevalence_pct": round(100 * len(observations) / total, 1) if total else 0,
        "required_count": required_count,
        "required_pct": round(100 * required_count / total, 1) if total else 0,
        "salary_count": len(salaries),
        "salary": salary,
        "median_premium": premium,
    }


def build_slice_statistics(records: list[dict], minimum_combination_count: int = 2) -> dict:
    total = len(records)
    companies = {
        _normal(item.get("company"))
        for item in records
        if _normal(item.get("company"))
    }
    source_counts = Counter(
        str(item.get("source") or "unknown")
        for item in records
    )
    known_salaries = [item["salary"] for item in records if item.get("salary") is not None]
    salary = _salary_summary(known_salaries)
    technology_jobs: dict[str, list[dict]] = defaultdict(list)
    for item in records:
        for technology in item.get("technologies", []):
            technology_jobs[technology].append(item)

    technologies = [
        _metric_row(name, observations, total, salary["p50"])
        for name, observations in technology_jobs.items()
    ]
    technologies.sort(key=lambda row: (-row["count"], row["name"]))

    quartile_counts = {
        technology: {"q1": 0, "q2": 0, "q3": 0, "q4": 0}
        for technology in technology_jobs
    }
    for item in records:
        if item.get("salary") is None:
            continue
        bucket = _quartile_bucket(item["salary"], salary)
        for technology in item.get("technologies", []):
            quartile_counts[technology][bucket] += 1
    for row in technologies:
        row["salary_quartiles"] = quartile_counts[row["name"]]

    combination_jobs: dict[str, list[dict]] = defaultdict(list)
    for item in records:
        names = sorted(set(item.get("technologies", [])))
        for size in (2, 3):
            for combination in itertools.combinations(names, size):
                combination_jobs[" + ".join(combination)].append(item)
    combinations = [
        _metric_row(name, observations, total, salary["p50"])
        for name, observations in combination_jobs.items()
        if len(observations) >= minimum_combination_count
    ]
    combinations.sort(key=lambda row: (-row["count"], row["name"]))
    # Retain both common and high-paying stacks without letting a long tail make
    # the public JSON unbounded.
    by_salary = sorted(
        combinations,
        key=lambda row: (-(row["salary"]["p50"] or 0), -row["salary_count"]),
    )
    retained = {row["name"]: row for row in combinations[:100]}
    retained.update({row["name"]: row for row in by_salary[:100]})

    salary_bands = {"under_40": 0, "40_59": 0, "60_79": 0, "80_99": 0, "100_plus": 0}
    for value in known_salaries:
        if value < 40000:
            salary_bands["under_40"] += 1
        elif value < 60000:
            salary_bands["40_59"] += 1
        elif value < 80000:
            salary_bands["60_79"] += 1
        elif value < 100000:
            salary_bands["80_99"] += 1
        else:
            salary_bands["100_plus"] += 1

    return {
        "job_count": total,
        "company_count": len(companies),
        "source_count": len(source_counts),
        "sources": dict(sorted(source_counts.items())),
        "salary_count": len(known_salaries),
        "salary_coverage_pct": round(100 * len(known_salaries) / total, 1) if total else 0,
        "salary": salary,
        "salary_bands": salary_bands,
        "technologies": technologies,
        "combinations": sorted(retained.values(), key=lambda row: (-row["count"], row["name"])),
    }


def _normal(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _market_key(path_id: str, card: JobCard) -> str:
    low, high, _ = salary_values(card)
    value = f"{path_id}|{_normal(card.title)}|{_normal(card.company)}|{low}|{high}"
    return hashlib.sha1(value.encode()).hexdigest()[:16]


async def _collect_market(settings: Settings) -> tuple[list[tuple[str, str, JobCard]], list[dict]]:
    tagged: list[tuple[str, str, JobCard]] = []
    health: dict[str, dict] = defaultdict(lambda: {"ok": False, "jobs": 0, "errors": []})
    semaphore = asyncio.Semaphore(3)
    window_days = int(settings.market.get("window_days", 30))
    limit = int(settings.market.get("limit_per_source", 40))
    high_threshold = int(settings.market.get("high_salary_threshold", 80000))

    async def one(path_id: str, level_hint: str, query: str) -> None:
        async with semaphore:
            params = SearchParams(
                query=query,
                location="UK",
                max_days_old=window_days,
                limit_per_source=limit,
                min_salary=high_threshold if level_hint == "high" else None,
                exclude_training=True,
            )
            cards_by_provider, reports = await run_search(settings, params.model_dump())
            for report in reports:
                state = health[report.provider]
                state["ok"] = state["ok"] or report.ok
                state["jobs"] += report.jobs
                if report.error:
                    state["errors"].append(report.error)
            for cards in cards_by_provider.values():
                tagged.extend((path_id, level_hint, card) for card in cards)

    tasks = [
        one(path_id, level, query)
        for path_id, path in MARKET_PATHS.items()
        for level, queries in path["queries"].items()
        for query in queries
    ]
    await asyncio.gather(*tasks)
    reports = [
        {
            "provider": name,
            "ok": state["ok"],
            "jobs": state["jobs"],
            "error": "; ".join(dict.fromkeys(state["errors"]))[:400] or None,
        }
        for name, state in sorted(health.items())
    ]
    return tagged, reports


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _history_summary(history_dir: Path, current: dict, weeks: int) -> list[dict]:
    snapshots = []
    for path in sorted(history_dir.glob("*.json"))[-max(0, weeks - 1):]:
        try:
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    if not any(item.get("generated_at") == current.get("generated_at") for item in snapshots):
        snapshots.append(current)
    # Manual verification runs can happen in the same week. A trend point is a
    # week, not a process invocation, so retain only that week's latest snapshot.
    weekly: dict[str, dict] = {}
    for snapshot in snapshots:
        generated_at = snapshot.get("generated_at")
        try:
            generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            iso_year, iso_week, _ = generated.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
        except (TypeError, ValueError):
            week_key = str(generated_at)
        weekly[week_key] = snapshot

    output = []
    for week_key, snapshot in list(weekly.items())[-weeks:]:
        points = {}
        for path_id, path_data in snapshot.get("paths", {}).items():
            points[path_id] = {
                level: {
                    "jobs": stats.get("job_count", 0),
                    "companies": stats.get("company_count", 0),
                    "salary_count": stats.get("salary_count", 0),
                    "median": stats.get("salary", {}).get("p50"),
                    "technologies": {
                        row.get("name"): {
                            "count": row.get("count", 0),
                            "demand": row.get("prevalence_pct", 0),
                            "salary_count": row.get("salary_count", 0),
                            "median": row.get("salary", {}).get("p50"),
                        }
                        for row in stats.get("technologies", [])
                        if row.get("name")
                    },
                    "combinations": {
                        row.get("name"): {
                            "count": row.get("count", 0),
                            "demand": row.get("prevalence_pct", 0),
                            "salary_count": row.get("salary_count", 0),
                            "median": row.get("salary", {}).get("p50"),
                        }
                        for row in stats.get("combinations", [])
                        if row.get("name")
                    },
                }
                for level, stats in path_data.get("levels", {}).items()
            }
        output.append({
            "week": week_key,
            "generated_at": snapshot.get("generated_at"),
            "paths": points,
        })
    return output


async def run_weekly_market(settings: Settings) -> dict:
    """Collect, classify, aggregate and atomically publish one weekly snapshot."""
    ensure_dirs(settings)
    started = datetime.now(UTC)
    tagged, provider_health = await _collect_market(settings)
    logger.info("Market provider collection completed: %d tagged cards", len(tagged))

    records: dict[tuple[str, str], dict] = {}
    for path_id, level_hint, card in tagged:
        key = _market_key(path_id, card)
        record = records.setdefault(
            (path_id, key),
            {"path_id": path_id, "job_key": key, "card": card, "hints": set()},
        )
        record["hints"].add(level_hint)
        if len(card.description or "") > len(record["card"].description or ""):
            record["card"].description = card.description

    await _enrich_all(list(records.values()))
    logger.info("Market description enrichment completed: %d unique path cards", len(records))

    now = datetime.now(UTC)
    window_start = now - timedelta(days=int(settings.market.get("window_days", 30)) + 2)
    filtered = Counter()
    candidates = []
    for record in records.values():
        card = record["card"]
        if card.posted_at and card.posted_at.astimezone(UTC) < window_start:
            filtered["outside_window"] += 1
            continue
        posted_by, _ = seller.classify(card.company, card.description, card.extra.get("recruiter"))
        if posted_by != "employer":
            filtered["agency_or_unknown"] += 1
            continue
        is_training, _ = training.classify(card)
        if is_training:
            filtered["training"] += 1
            continue
        low, high, midpoint = salary_values(card)
        record.update({
            "salary_low": low,
            "salary_high": high,
            "salary": midpoint,
            "deterministic_level": deterministic_level(card),
            "deterministic_technologies": extract_technologies(
                f"{card.title or ''}\n{card.description or ''}"
            ),
        })
        candidates.append(record)

    max_per_slice = int(settings.market.get("max_per_slice", 120))
    shortlisted: dict[tuple[str, str], dict] = {}
    for path_id in MARKET_PATHS:
        path_records = [record for record in candidates if record["path_id"] == path_id]
        for level in LEVEL_LABELS:
            matching = [record for record in path_records if level in record["hints"]]
            matching.sort(key=lambda record: (
                record["card"].posted_at or datetime.min.replace(tzinfo=UTC),
                len(record["card"].description or ""),
            ), reverse=True)
            for record in matching[:max_per_slice]:
                shortlisted[(path_id, record["job_key"])] = record
    candidates = list(shortlisted.values())
    logger.info("Market shortlist for GLM: %d cards", len(candidates))

    assessments: dict[str, dict] = {}
    batch_size = int(settings.market.get("llm_batch_size", 6))
    allowed = sorted(TECHNOLOGY_PATTERNS)
    for offset in range(0, len(candidates), batch_size):
        batch_records = candidates[offset:offset + batch_size]
        items = [{
            "job_key": record["job_key"],
            "career_path": MARKET_PATHS[record["path_id"]]["label"],
            "search_level_hints": sorted(record["hints"]),
            "title": record["card"].title,
            "company": record["card"].company,
            "salary": record["card"].salary_raw,
            "description": (record["card"].description or "")[:4500],
        } for record in batch_records]
        logger.info(
            "GLM market batch %d/%d",
            offset // batch_size + 1,
            (len(candidates) + batch_size - 1) // batch_size,
        )
        try:
            for assessment in await classify_market_batch(settings, items, allowed):
                key = str(assessment.get("job_key", ""))
                if key:
                    assessments[key] = assessment
        except Exception as exc:
            logger.warning("GLM market batch failed; deterministic fallback retained: %s", exc)

    high_threshold = float(settings.market.get("high_salary_threshold", 80000))
    slices: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in candidates:
        card = record["card"]
        assessment = assessments.get(record["job_key"], {})
        if assessment.get("relevant_to_path") is False:
            filtered["glm_path_mismatch"] += 1
            continue
        model_level = str(assessment.get("career_level") or "").lower()
        career_level = model_level if model_level in {"entry", "middle", "senior"} \
            else record["deterministic_level"]
        if record["salary"] is not None and record["salary"] >= high_threshold:
            cohort = "high"
        elif career_level == "entry":
            cohort = "entry"
        elif career_level == "middle":
            cohort = "middle"
        else:
            filtered["senior_below_high_threshold"] += 1
            continue

        canonical = set(record["deterministic_technologies"])
        mandatory = {
            name for name in assessment.get("mandatory_technologies", [])
            if isinstance(name, str) and name in TECHNOLOGY_PATTERNS
        }
        desirable = {
            name for name in assessment.get("desirable_technologies", [])
            if isinstance(name, str) and name in TECHNOLOGY_PATTERNS
        }
        technologies = sorted(canonical | mandatory | desirable)
        slices[(record["path_id"], cohort)].append({
            "job_key": record["job_key"],
            "title": card.title,
            "company": card.company,
            "source": card.source,
            "url": card.url,
            "salary": record["salary"],
            "salary_low": record["salary_low"],
            "salary_high": record["salary_high"],
            "technologies": technologies,
            "mandatory_technologies": sorted(mandatory),
            "desirable_technologies": sorted(desirable),
            "level_confidence": assessment.get("level_confidence", "deterministic"),
        })

    minimum_combo = int(settings.market.get("minimum_combination_count", 2))
    paths = {}
    for path_id, specification in MARKET_PATHS.items():
        levels = {
            level: build_slice_statistics(slices[(path_id, level)], minimum_combo)
            for level in LEVEL_LABELS
        }
        paths[path_id] = {"label": specification["label"], "levels": levels}

    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "started_at": started.isoformat(timespec="seconds"),
        "window_days": int(settings.market.get("window_days", 30)),
        "high_salary_threshold": int(high_threshold),
        "model": settings.llm.get("model", "glm-5.3-flash"),
        "raw_cards": len(tagged),
        "unique_path_cards": len(records),
        "analysed_cards": len(candidates),
        "filtered": dict(filtered),
        "provider_health": provider_health,
        "paths": paths,
        "methodology": {
            "entry": "GLM-confirmed junior, graduate, trainee, apprentice or Level I roles; salary optional.",
            "middle": "GLM-confirmed independent practitioner roles without senior ownership; salary optional.",
            "high": "Any relevant role with advertised annualised salary midpoint of at least £80,000.",
            "demand": "Share of deduplicated vacancies in the selected path and level mentioning a technology.",
            "salary": "P25, median and P75 of annualised advertised salary midpoints; no salary is imputed.",
            "combinations": "Technology pairs and triples appearing together in at least two vacancies.",
        },
    }

    history_dir = settings.data_dir / str(settings.market.get("history_dir", "market/history"))
    site_dir = settings.data_dir / str(settings.market.get("site_dir", "market/site"))
    history_dir.mkdir(parents=True, exist_ok=True)
    site_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"{started:%Y-%m-%dT%H%M%SZ}.json"
    _atomic_json(history_file, snapshot)
    published = dict(snapshot)
    published["history"] = _history_summary(
        history_dir,
        snapshot,
        int(settings.market.get("history_weeks", 104)),
    )
    _atomic_json(site_dir / "data.json", published)

    history_files = sorted(history_dir.glob("*.json"), reverse=True)
    for old in history_files[int(settings.market.get("history_weeks", 104)):]:
        old.unlink(missing_ok=True)
    logger.info("Weekly market snapshot published: %s", site_dir / "data.json")
    return published
