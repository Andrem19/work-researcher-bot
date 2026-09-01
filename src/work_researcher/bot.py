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


async def _enrich(card: JobCard) -> None:
    if len(card.description or "") >= 500 or not card.url:
        return
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
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
    cvs = _assign_cvs(settings)
    tagged_cards, provider_health = await _collect(settings)

    # Collapse duplicate listings while retaining every career-path match.
    by_hash: dict[str, dict] = {}
    for path_id, card in tagged_cards:
        key = job_hash(card.title, card.company, card.location_text, card.salary_min)
        record = by_hash.setdefault(key, {"card": card, "paths": set()})
        record["paths"].add(path_id)
        if len(card.description or "") > len(record["card"].description or ""):
            record["card"] = card
    await asyncio.gather(*[_enrich(record["card"]) for record in by_hash.values()])

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

    pool_cards = [record["card"] for record in by_hash.values()]
    async with db.connect(settings.db_path) as conn:
        pool = await dedup.load_pool(conn)
        resolution, merged = dedup.resolution_map(pool_cards, pool)
        await db.upsert_jobs(conn, pool_cards, resolution)
        already_delivered = await db.delivered_hashes(conn)
        await conn.commit()

    allow_seen = settings.report.get("include_seen", False) if include_seen is None else include_seen
    llm_items = []
    candidate_map = {}
    for key, card, base in candidates:
        if not (allow_seen or key not in already_delivered):
            continue
        cv = cvs[base["path_id"]]
        llm_items.append({
            "job_key": key, "career_path": settings.career_paths[base["path_id"]]["label"],
            "title": card.title, "company": card.company, "location": card.location_text,
            "salary": card.salary_raw, "source": card.source, "url": card.url,
            "description": (card.description or "")[:10000], "deterministic": base,
            "cv_filename": cv["filename"], "cv_excerpt": cv["text"][:10000],
        })
        candidate_map[key] = (card, base, cv)

    assessments = []
    batch_size = int(settings.llm.get("batch_size", 6))
    for offset in range(0, len(llm_items), batch_size):
        assessments.extend(await assess_batch(settings, llm_items[offset:offset + batch_size]))

    jobs = []
    for assessment in assessments:
        key = str(assessment.get("job_key", ""))
        if key not in candidate_map:
            continue
        card, base, cv = candidate_map[key]
        if not assessment.get("recommended") or not assessment.get("direct_employer"):
            continue
        overall = int(assessment.get("overall_score") or 0)
        job = {
            **assessment, "job_key": key, "overall_score": overall,
            "title": card.title, "company": card.company,
            "location_text": card.location_text, "salary_raw": card.salary_raw,
            "url": card.apply_url or card.url, "source": card.source,
            "work_mode": base["work_mode"], "path_id": base["path_id"],
            "path_label": settings.career_paths[base["path_id"]]["label"],
            "cv_filename": cv["filename"],
        }
        jobs.append(job)
    jobs.sort(key=lambda item: -item["overall_score"])
    per_path = defaultdict(int)
    selected = []
    for job in jobs:
        if per_path[job["path_id"]] >= int(settings.report.get("max_per_path", 12)):
            continue
        per_path[job["path_id"]] += 1
        selected.append(job)
        if len(selected) >= int(settings.report.get("max_jobs", 40)):
            break

    messages = render_report(selected, provider_health, cv_sync, started)
    message_ids = await send_messages(settings, messages) if deliver else []
    if deliver:
        async with db.connect(settings.db_path) as conn:
            await db.mark_report_delivered(
                conn,
                [str(job["job_key"]) for job in selected],
                message_ids,
            )
    return {
        "ok": True, "started_at": started.isoformat(), "cv_sync": cv_sync,
        "provider_health": provider_health, "raw_cards": len(tagged_cards),
        "deduplicated": len(by_hash), "duplicates_merged": merged,
        "eligible_before_glm": len(llm_items), "reported": len(selected),
        "message_ids": message_ids, "jobs": selected,
    }
