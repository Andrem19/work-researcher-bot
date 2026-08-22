"""Adzuna — free aggregate API (needs app_id + app_key from adzuna.com)."""

from __future__ import annotations

from datetime import datetime

from ..domain import JobCard
from ..textutils import clean
from .base import ProviderError, SearchQuery, json_client

API = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    app_id, app_key = cfg.get("app_id"), cfg.get("app_key")
    if not (app_id and app_key):
        raise ProviderError("missing app_id/app_key — register free at adzuna.com (see SETUP.md)")
    params = {
        "app_id": app_id, "app_key": app_key,
        "what": query.query,
        "results_per_page": min(query.limit, 50),
        "sort_by": "date",
        "content-type": "application/json",
    }
    loc = query.location.strip()
    if loc and loc.upper() not in ("UK", "UNITED KINGDOM"):
        params["where"] = loc
        params["distance"] = min(query.radius_miles, 100)
    if query.max_days_old:
        params["max_days_old"] = query.max_days_old
    if query.work_from_home:
        params["work_from_home"] = "1"
    url = API.format(page=1)
    async with json_client() as client:
        data = await client.get(url, params=params)
        if data.status_code != 200:
            raise ProviderError(f"adzuna HTTP {data.status_code}: {data.text[:150]}")
        payload = data.json()
    cards = []
    for j in payload.get("results", []):
        created = None
        if j.get("created"):
            try:
                created = datetime.fromisoformat(j["created"].replace("Z", "+00:00"))
            except ValueError:
                created = None
        sal_min = j.get("salary_min")
        sal_max = j.get("salary_max")
        period = "day" if j.get("salary_is_daily") else "year"
        cards.append(JobCard(
            source="adzuna",
            source_job_id=str(j.get("id")),
            url=j.get("redirect_url"),
            apply_url=j.get("redirect_url"),
            title=j.get("title"),
            company=(j.get("company") or {}).get("display_name"),
            location_text=(j.get("location") or {}).get("display_name"),
            salary_raw=f"£{sal_min} - £{sal_max} per {period}" if sal_min else None,
            salary_min=float(sal_min) if sal_min else None,
            salary_max=float(sal_max) if sal_max else None,
            salary_period=period,
            contract_type=j.get("contract_time"),
            description=clean(j.get("description"))[:800],
            posted_at=created,
            extra={"category": (j.get("category") or {}).get("label")},
        ))
    if not cards:
        raise ProviderError("adzuna returned 0 results (check key/quota or broaden query)")
    return cards
