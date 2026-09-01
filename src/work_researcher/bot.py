"""Nightly end-to-end job-search run."""

from __future__ import annotations

import asyncio
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
from .career import deterministic_assessment
from .config import Settings, ensure_dirs
from .cvmanager import extract_text
from .domain import JobCard, SearchParams
from .drive import sync_cvs_from_drive
from .llm import assess_batch
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

    async def one(path_id: str, query_text: str):
        async with semaphore:
            params = SearchParams(
                query=query_text, location="UK", max_days_old=settings.default_max_days_old,
                limit_per_source=settings.default_limit_per_source, exclude_training=True,
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
    for key, record in by_hash.items():
        card = record["card"]
        best = None
        for path_id in record["paths"]:
            assessment = deterministic_assessment(card, path_id, cvs[path_id]["text"])
            if best is None or assessment["base_score"] > best["base_score"]:
                best = assessment
        if best and best["eligible"]:
            candidates.append((key, card, best))
    logger.info("Deterministic screening completed: %d eligible cards", len(candidates))

    pool_cards = [record["card"] for record in by_hash.values()]
    async with db.connect(settings.db_path) as conn:
        pool = await dedup.load_pool(conn)
        resolution, merged = dedup.resolution_map(pool_cards, pool)
        await db.upsert_jobs(conn, pool_cards, resolution)
        already_delivered = await db.delivered_hashes(conn)
        await conn.commit()

    allow_seen = settings.report.get("include_seen", False) if include_seen is None else include_seen
    candidates.sort(
        key=lambda item: (
            -item[2]["base_score"],
            -len(item[1].description or ""),
            item[1].title or "",
        )
    )
    pre_llm_per_path = int(settings.report.get("pre_llm_max_per_path", 15))
    pre_llm_counts = defaultdict(int)
    shortlist = []
    for item in candidates:
        path_id = item[2]["path_id"]
        if pre_llm_counts[path_id] >= pre_llm_per_path:
            continue
        pre_llm_counts[path_id] += 1
        shortlist.append(item)

    llm_items = []
    candidate_map = {}
    for key, card, base in shortlist:
        if not (allow_seen or key not in already_delivered):
            continue
        cv = cvs[base["path_id"]]
        llm_items.append({
            "job_key": key, "career_path": settings.career_paths[base["path_id"]]["label"],
            "title": card.title, "company": card.company, "location": card.location_text,
            "salary": card.salary_raw, "source": card.source, "url": card.url,
            "description": (card.description or "")[:6000], "deterministic": base,
            "cv_filename": cv["filename"], "cv_excerpt": cv["text"][:4500],
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
    per_path = defaultdict(int)
    selected = []
    for job in jobs:
        if per_path[job["path_id"]] >= int(settings.report.get("max_per_path", 12)):
            continue
        per_path[job["path_id"]] += 1
        selected.append(job)
        if len(selected) >= int(settings.report.get("max_jobs", 40)):
            break

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
