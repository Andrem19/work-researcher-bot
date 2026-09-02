"""Nightly end-to-end job-search run."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime

import httpx
from selectolax.parser import HTMLParser

from . import dedup
from . import persistence as db
from .career import classify_career_path, deterministic_assessment
from .config import Settings, ensure_dirs
from .cvmanager import extract_text
from .domain import JobCard, SearchParams
from .drive import sync_cvs_from_drive
from .llm import assess_batch, rerank_shortlist
from .providers import run_search
from .telegram import render_report, send_messages
from .textutils import job_hash

logger = logging.getLogger("work_researcher.bot")

PATH_KEYWORDS = {
    "data_engineering": ("pipeline", "etl", "data engineer", "databricks", "spark", "azure data"),
    "geospatial_data": ("gis", "geospatial", "postgis", "geopandas", "spatial", "arcgis", "qgis"),
    "analytics": ("data analyst", "analytics", "power bi", "tableau", "dashboard", "reporting"),
    "software_data_platform": ("python developer", "software engineer", "backend", "api", "application developer"),
}

LOCAL_DISCOVERY_QUERIES = {
    "data_engineering": "data engineer",
    "geospatial_data": "GIS data analyst",
    "analytics": "data analyst",
    "software_data_platform": "junior python developer",
}


def _report_signature(job: dict) -> tuple[str, str, str]:
    """Identify regional copies of the same employer/title/salary advert."""
    normalized = []
    for field in ("title", "company", "salary_raw"):
        normalized.append(re.sub(r"[^a-z0-9]+", " ", str(job.get(field) or "").lower()).strip())
    return tuple(normalized)


def _report_base_title(value: str | None) -> str:
    """Remove board-added employer suffixes from a title for report dedup."""
    value = (value or "").split("|", 1)[0]
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_report_duplicate(job: dict, selected: list[dict]) -> bool:
    signature = _report_signature(job)
    if any(_report_signature(other) == signature for other in selected):
        return True
    title = _report_base_title(job.get("title"))
    salary = re.sub(r"[^a-z0-9]+", " ", str(job.get("salary_raw") or "").lower()).strip()
    location = re.sub(
        r"[^a-z0-9]+", " ", str(job.get("location_text") or "").lower()
    ).strip()
    generic_companies = {"nhs jobs", "find a job", "civil service jobs", "not specified"}
    company = re.sub(
        r"[^a-z0-9]+", " ", str(job.get("company") or "").lower()
    ).strip()
    for other in selected:
        other_company = re.sub(
            r"[^a-z0-9]+", " ", str(other.get("company") or "").lower()
        ).strip()
        if (
            title == _report_base_title(other.get("title"))
            and salary == re.sub(
                r"[^a-z0-9]+", " ", str(other.get("salary_raw") or "").lower()
            ).strip()
            and location == re.sub(
                r"[^a-z0-9]+", " ", str(other.get("location_text") or "").lower()
            ).strip()
            and (company in generic_companies or other_company in generic_companies)
        ):
            return True
    return False


def _preselect_candidates(
    candidates: list[tuple[str, JobCard, dict]],
    *,
    max_per_path: int,
    max_per_source_path: int,
) -> list[tuple[str, JobCard, dict]]:
    """Keep model input broad across paths and sources, with soft source caps."""
    selected = []
    deferred = []
    path_counts = defaultdict(int)
    source_path_counts = defaultdict(int)
    for item in candidates:
        path_id = item[2]["path_id"]
        source_path = (path_id, item[1].source)
        if path_counts[path_id] >= max_per_path:
            continue
        if source_path_counts[source_path] >= max_per_source_path:
            deferred.append(item)
            continue
        selected.append(item)
        path_counts[path_id] += 1
        source_path_counts[source_path] += 1
    for item in deferred:
        path_id = item[2]["path_id"]
        if path_counts[path_id] >= max_per_path:
            continue
        selected.append(item)
        path_counts[path_id] += 1
    return selected


def _select_report_jobs(
    jobs: list[dict],
    *,
    max_jobs: int,
    diverse_max_per_path: int,
    diverse_max_per_source: int,
) -> list[dict]:
    """Prefer a varied top list, then fill any gaps with the best remaining jobs."""
    unique = []
    for job in jobs:
        if not _is_report_duplicate(job, unique):
            unique.append(job)

    selected = []
    deferred = []
    path_counts = defaultdict(int)
    source_counts = defaultdict(int)
    for job in unique:
        if (
            path_counts[job["path_id"]] >= diverse_max_per_path
            or source_counts[job["source"]] >= diverse_max_per_source
        ):
            deferred.append(job)
            continue
        selected.append(job)
        path_counts[job["path_id"]] += 1
        source_counts[job["source"]] += 1
        if len(selected) >= max_jobs:
            return selected
    for job in deferred:
        selected.append(job)
        if len(selected) >= max_jobs:
            break
    order = {str(job.get("job_key")): index for index, job in enumerate(jobs)}
    selected.sort(key=lambda job: order.get(str(job.get("job_key")), len(jobs)))
    return selected


def _apply_global_ranking(jobs: list[dict], ranking: list[dict]) -> list[dict]:
    """Apply a possibly partial GLM ranking while preserving every eligible job."""
    def rank_value(item: dict) -> int:
        try:
            return int(item.get("rank") or 1_000_000)
        except (TypeError, ValueError):
            return 1_000_000

    by_key = {str(job.get("job_key")): job for job in jobs}
    original_order = {str(job.get("job_key")): index for index, job in enumerate(jobs)}
    valid = []
    seen = set()
    for item in sorted(
        ranking,
        key=rank_value,
    ):
        key = str(item.get("job_key", ""))
        if key not in by_key or key in seen:
            continue
        seen.add(key)
        valid.append((key, item))
    for key in sorted(by_key, key=lambda value: original_order[value]):
        if key not in seen:
            valid.append((key, {}))
    ordered = []
    for rank, (key, item) in enumerate(valid, 1):
        job = by_key[key]
        final_score = item.get("final_score")
        if final_score is not None:
            with contextlib.suppress(TypeError, ValueError):
                job["overall_score"] = max(0, min(100, int(final_score)))
        for field in (
            "rank_reason_ru", "entry_evidence", "main_tradeoff_ru",
            "deadline_urgency", "vacancy_live_confidence",
        ):
            if item.get(field) not in (None, "", []):
                job[field] = item[field]
        job["global_rank"] = rank
        ordered.append(job)
    return ordered


def _build_ranked_jobs(assessment_map: dict[str, dict], candidate_map: dict, settings: Settings) -> list[dict]:
    """Merge model opinions into the hard-filtered shortlist without a veto."""
    jobs = []
    for assessment in assessment_map.values():
        key = str(assessment.get("job_key", ""))
        if key not in candidate_map:
            continue
        card, base, cv = candidate_map[key]
        overall = int(assessment.get("overall_score") or base.get("base_score") or 0)
        glm_recommended = bool(assessment.get("recommended"))
        glm_direct = bool(assessment.get("direct_employer"))
        if glm_recommended and glm_direct:
            review_tier = "strong"
        elif overall >= 55:
            review_tier = "review"
        else:
            review_tier = "fallback"
        jobs.append({
            **assessment, "job_key": key, "overall_score": overall,
            "title": card.title, "company": card.company,
            "location_text": card.location_text, "salary_raw": card.salary_raw,
            "url": card.apply_url or card.url, "source": card.source,
            "work_mode": base["work_mode"], "path_id": base["path_id"],
            "path_label": settings.career_paths[base["path_id"]]["label"],
            "cv_filename": cv["filename"],
            "deterministic_score": base.get("base_score"),
            "entry_reason": base.get("entry_reason"),
            "location_reason": base.get("location_reason"),
            "requirements_status": base.get("requirements_status"),
            "deadline": assessment.get("deadline") or base.get("deadline"),
            "deadline_urgency": (
                assessment.get("deadline_urgency") or base.get("deadline_urgency")
            ),
            "vacancy_live_confidence": (
                assessment.get("vacancy_live_confidence")
                or base.get("vacancy_live_confidence")
            ),
            "contract_type": card.contract_type,
            "posted_at": card.posted_at.isoformat() if card.posted_at else None,
            "description_evidence": (card.description or "")[:1200],
            "glm_recommended": glm_recommended,
            "glm_direct_employer": glm_direct,
            "review_tier": review_tier,
            "hard_filters_passed": True,
            # Direct-employer status is established by the hard filter. Keep
            # GLM's lower-confidence opinion separately instead of re-vetoing.
            "direct_employer": True,
            "direct_employer_reason": (
                assessment.get("direct_employer_reason")
                if glm_direct else base.get("posted_by_reason")
            ),
        })
    jobs.sort(key=lambda item: -item["overall_score"])
    return jobs


def _assign_cvs(settings: Settings) -> dict[str, dict]:
    files = sorted(p for p in settings.cv_dir.iterdir() if p.suffix.lower() in {".docx", ".pdf", ".doc"})
    if len(files) != 4:
        raise RuntimeError(f"exactly four career CVs are required, found {len(files)}")
    records = []
    for path in files:
        text = extract_text(path)
        records.append({"path": path, "filename": path.name, "text": text})
    path_ids = list(settings.career_paths)
    best_score, best = -1, None
    for permutation in itertools.permutations(records, len(path_ids)):
        score = 0
        for path_id, cv in zip(path_ids, permutation, strict=True):
            hay = f"{cv['filename']} {cv['text'][:12000]}".lower()
            score += sum(1 for keyword in PATH_KEYWORDS.get(path_id, ()) if keyword in hay)
            score += sum(3 for hint in settings.career_paths[path_id].get("cv_name_contains", []) if hint in cv["filename"].lower())
        if score > best_score:
            best_score, best = score, permutation
    if best is None:
        raise RuntimeError("could not assign CVs to career paths")
    return {path_id: cv for path_id, cv in zip(path_ids, best, strict=True)}


async def _enrich(card: JobCard, client: httpx.AsyncClient) -> None:
    if len(card.description or "") >= 500 or not card.url:
        return
    try:
        response = await client.get(card.url)
        if response.status_code != 200:
            return
        tree = HTMLParser(response.text)
        for script in tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.text())
            except (ValueError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                    card.description = re.sub(r"<[^>]+>", " ", str(item["description"]))[:12000]
                    return
        body = tree.body.text(separator=" ") if tree.body else ""
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) > 500:
            card.description = body[:12000]
    except Exception as exc:
        logger.warning("description enrichment failed for %s: %s", card.url, exc)


async def _enrich_all(records: list[dict]) -> None:
    """Enrich cards with bounded sockets and memory, reusing one HTTP pool."""
    semaphore = asyncio.Semaphore(8)
    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0"},
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
    ) as client:
        async def one(record: dict) -> None:
            async with semaphore:
                await _enrich(record["card"], client)

        await asyncio.gather(*(one(record) for record in records))


async def _collect(settings: Settings) -> tuple[list[tuple[str, JobCard]], list[dict]]:
    collected: list[tuple[str, JobCard]] = []
    health: dict[str, dict] = defaultdict(lambda: {"ok": False, "jobs": 0, "errors": []})
    semaphore = asyncio.Semaphore(3)

    async def one(
        path_id: str,
        query_text: str,
        *,
        location: str = "UK",
        sources: list[str] | None = None,
        max_days_old: int | None = None,
    ):
        async with semaphore:
            params = SearchParams(
                query=query_text, location=location,
                max_days_old=max_days_old or settings.default_max_days_old,
                limit_per_source=settings.default_limit_per_source, exclude_training=True,
                sources=sources,
            )
            cards_by_provider, reports = await run_search(settings, params.model_dump())
            for report in reports:
                state = health[report.provider]
                state["ok"] = state["ok"] or report.ok
                state["jobs"] += report.jobs
                if report.error:
                    state["errors"].append(report.error)
            for cards in cards_by_provider.values():
                collected.extend((path_id, card) for card in cards)

    tasks = []
    for path_id, spec in settings.career_paths.items():
        for query in spec.get("queries", []):
            tasks.append(one(path_id, query))
    # The successful interactive search did not rely solely on national result
    # pages: it ran broad role-family searches in each allowed local geography.
    # This prevents a strong Blackpool/Preston vacancy from being buried below
    # the first page of national results.
    local_sources = ["totaljobs", "reed", "findajob", "civil_service"]
    if settings.secret("adzuna", "app_id") and settings.secret("adzuna", "app_key"):
        local_sources.append("adzuna")
    if settings.secret("jooble", "api_key"):
        local_sources.append("jooble")
    for path_id, query in LOCAL_DISCOVERY_QUERIES.items():
        if path_id not in settings.career_paths:
            continue
        for location in ("Blackpool", "Preston", "Lancashire", "Manchester"):
            tasks.append(one(
                path_id,
                query,
                location=location,
                sources=local_sources,
                max_days_old=30,
            ))
    await asyncio.gather(*tasks)
    reports = [
        {"provider": name, "ok": state["ok"], "jobs": state["jobs"],
         "error": "; ".join(dict.fromkeys(state["errors"]))[:300] or None}
        for name, state in sorted(health.items())
    ]
    return collected, reports


async def run_once(settings: Settings, *, deliver: bool = True, include_seen: bool | None = None) -> dict:
    ensure_dirs(settings)
    started = datetime.now(UTC)
    cv_sync = await sync_cvs_from_drive(settings)
    logger.info("CV sync completed: %d files", len(cv_sync.get("files", [])))
    cvs = _assign_cvs(settings)
    logger.info(
        "CV route mapping: %s",
        ", ".join(f"{path_id}={cv['filename']}" for path_id, cv in cvs.items()),
    )
    tagged_cards, provider_health = await _collect(settings)
    logger.info("Provider collection completed: %d tagged cards", len(tagged_cards))

    # Collapse duplicate listings while retaining every career-path match.
    by_hash: dict[str, dict] = {}
    for path_id, card in tagged_cards:
        key = job_hash(card.title, card.company, card.location_text, card.salary_min)
        record = by_hash.setdefault(key, {"card": card, "paths": set()})
        record["paths"].add(path_id)
        if len(card.description or "") > len(record["card"].description or ""):
            record["card"] = card
    await _enrich_all(list(by_hash.values()))
    logger.info("Description enrichment completed: %d unique cards", len(by_hash))

    candidates = []
    outside_routes = 0
    for key, record in by_hash.items():
        card = record["card"]
        path_id, path_score, path_evidence = classify_career_path(card)
        if path_id is None or path_id not in cvs:
            outside_routes += 1
            continue
        assessment = deterministic_assessment(card, path_id, cvs[path_id]["text"])
        assessment["path_score"] = path_score
        assessment["path_evidence"] = path_evidence
        if assessment["eligible"]:
            candidates.append((key, card, assessment))
    logger.info("Deterministic screening completed: %d eligible cards", len(candidates))
    logger.info("Career-path screening excluded %d off-route cards", outside_routes)

    pool_cards = [record["card"] for record in by_hash.values()]
    async with db.connect(settings.db_path) as conn:
        pool = await dedup.load_pool(conn)
        resolution, merged = dedup.resolution_map(pool_cards, pool)
        await db.upsert_jobs(conn, pool_cards, resolution)
        already_delivered = await db.delivered_hashes(conn)
        await conn.commit()

    allow_seen = settings.report.get("include_seen", False) if include_seen is None else include_seen
    candidates = [
        item for item in candidates
        if allow_seen or item[0] not in already_delivered
    ]
    candidates.sort(
        key=lambda item: (
            -item[2]["base_score"],
            -len(item[1].description or ""),
            item[1].title or "",
        )
    )
    shortlist = _preselect_candidates(
        candidates,
        max_per_path=int(settings.report.get("pre_llm_max_per_path", 15)),
        max_per_source_path=int(
            settings.report.get("pre_llm_max_per_source_path", 8)
        ),
    )

    llm_items = []
    candidate_map = {}
    for key, card, base in shortlist:
        cv = cvs[base["path_id"]]
        llm_items.append({
            "job_key": key, "career_path": settings.career_paths[base["path_id"]]["label"],
            "title": card.title, "company": card.company, "location": card.location_text,
            "salary": card.salary_raw, "source": card.source, "url": card.url,
            "description": (card.description or "")[:6000], "deterministic": base,
            "path_evidence": base.get("path_evidence", []),
            "cv_filename": cv["filename"], "cv_excerpt": cv["text"][:10000],
        })
        candidate_map[key] = (card, base, cv)

    assessments = []
    batch_size = int(settings.llm.get("batch_size", 6))
    for offset in range(0, len(llm_items), batch_size):
        batch = llm_items[offset:offset + batch_size]
        logger.info(
            "GLM batch %d/%d",
            offset // batch_size + 1,
            (len(llm_items) + batch_size - 1) // batch_size,
        )
        try:
            assessments.extend(await assess_batch(settings, batch))
        except Exception as exc:
            logger.warning("GLM batch failed; keeping deterministic shortlist: %s", exc)

    # GLM ranks and explains vacancies; it must never veto a vacancy which has
    # already passed the direct-employer, entry-level, location and requirement
    # filters. It may also omit items from malformed/partial JSON, so fill every
    # missing assessment with a transparent deterministic fallback.
    assessment_map = {
        str(item.get("job_key", "")): item
        for item in assessments
        if str(item.get("job_key", "")) in candidate_map
    }
    for item in llm_items:
        key = str(item["job_key"])
        if key not in assessment_map:
            base = item["deterministic"]
            assessment_map[key] = {
                "job_key": key,
                "direct_employer": True,
                "direct_employer_reason": base.get("posted_by_reason"),
                "entry_level_fit": base.get("base_score", 0),
                "career_path_fit": base.get("base_score", 0),
                "cv_fit": 0,
                "overall_score": base.get("base_score", 0),
                "recommended": False,
                "summary_ru": (
                    "Вакансия прошла все жёсткие фильтры, но модель не вернула "
                    "оценку. Она включена в отчёт для ручного решения."
                ),
                "mandatory_requirements": base.get("mandatory", []),
                "desirable_requirements": base.get("desirable", []),
                "special_conditions": [],
                "cv_strengths": [],
                "cv_gaps": ["Автоматическая оценка GLM недоступна или неполна"],
                "rejection_reasons": [],
            }

    jobs = _build_ranked_jobs(assessment_map, candidate_map, settings)
    if len(jobs) > 1:
        logger.info("GLM global comparative rerank: %d jobs", len(jobs))
        try:
            ranking = await rerank_shortlist(settings, jobs)
            jobs = _apply_global_ranking(jobs, ranking)
        except Exception as exc:
            logger.warning("GLM global rerank failed; keeping batch-score order: %s", exc)
    selected = _select_report_jobs(
        jobs,
        max_jobs=int(settings.report.get("max_jobs", 10)),
        diverse_max_per_path=int(settings.report.get("diverse_max_per_path", 4)),
        diverse_max_per_source=int(settings.report.get("diverse_max_per_source", 5)),
    )

    messages = render_report(
        selected,
        provider_health,
        cv_sync,
        started,
        detailed_jobs=int(settings.report.get("detailed_jobs", 5)),
    )
    message_ids = await send_messages(settings, messages) if deliver else []
    if deliver:
        async with db.connect(settings.db_path) as conn:
            await db.mark_report_delivered(
                conn,
                [str(job["job_key"]) for job in selected],
                message_ids,
            )
    logger.info("Run completed: %d jobs, %d Telegram messages", len(selected), len(message_ids))
    return {
        "ok": True, "started_at": started.isoformat(), "cv_sync": cv_sync,
        "provider_health": provider_health, "raw_cards": len(tagged_cards),
        "deduplicated": len(by_hash), "duplicates_merged": merged,
        "eligible_before_glm": len(llm_items), "reported": len(selected),
        "message_ids": message_ids, "jobs": selected,
    }
