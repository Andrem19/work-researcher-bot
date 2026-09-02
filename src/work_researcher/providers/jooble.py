"""Jooble — free aggregate API (needs an api key from jooble.org/api)."""

from __future__ import annotations

from datetime import datetime

from ..domain import JobCard
from ..textutils import clean, parse_salary
from .base import ProviderError, SearchQuery, make_client

API = "https://jooble.org/api/{key}"


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    api_key = cfg.get("api_key")
    if not api_key:
        raise ProviderError("missing api_key — request a free key at jooble.org/api (see SETUP.md)")
    body = {"keywords": query.query, "page": 1}
    loc = query.location.strip()
    if loc and loc.upper() not in ("UK", "UNITED KINGDOM"):
        body["location"] = loc
    async with make_client() as client:
        client.headers["Accept"] = "application/json"
        resp = await client.post(API.format(key=api_key), json=body)
        if resp.status_code != 200:
            raise ProviderError(f"jooble HTTP {resp.status_code}: {resp.text[:150]}")
        payload = resp.json()
    cards = []
    for j in payload.get("jobs", []):
        sal = parse_salary(j.get("salary"))
        cards.append(JobCard(
            source="jooble",
            source_job_id=str(j.get("id")),
            url=j.get("link"),
            apply_url=j.get("link"),
            title=j.get("title"),
            company=j.get("company"),
            location_text=j.get("location"),
            salary_raw=clean(j.get("salary")) or None,
            salary_min=sal[0], salary_max=sal[1], salary_period=sal[2],
            description=clean(j.get("snippet"))[:600],
            extra={"origin": j.get("source"), "source_updated_at": j.get("updated")},
        ))
        if len(cards) >= query.limit:
            break
    if not cards:
        raise ProviderError("jooble returned 0 results")
    return cards
