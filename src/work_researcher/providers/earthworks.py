"""Earthworks-jobs.com — geoscience/environment niche board, plain HTML.

Each listing row embeds a JSON-LD JobPosting (title, hiringOrganization,
jobLocation with country, datePosted) — parse that instead of scraping text.
The board is global; filter to the UK unless told otherwise.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin

from ..domain import JobCard
from ..textutils import clean, query_terms
from .base import ProviderError, ProviderSkip, SearchQuery, html_client

BASE = "https://www.earthworks-jobs.com/"

GEO_HINTS = (
    "geolog", "geoscience", "geophysic", "geotech", "hydrogeolog", "geochemist",
    "mining", "mineral", "exploration", "environment", "contaminated", "drilling",
    "borehole", "geomatics", "survey", "geohazard", "paleo", "seismolog",
    "stratigra", "sedimentolog", "petrolog", "volcan", "quarry", "aggregates",
    "wind farm", "renewab", "water resources", "field engineer", "fieldwork",
)

UK_MARKERS = (
    "uk", "united kingdom", "england", "scotland", "wales", "northern ireland",
    "london", "manchester", "birmingham", "leeds", "bristol", "edinburgh",
    "glasgow", "cardiff", "belfast", "aberdeen", "newcastle", "nottingham",
    "sheffield", "liverpool", "reading", "keyworth", "nottingham", "cambridge",
    "oxford", "york", "leicester", "coventry", "brighton", "southampton",
    "norwich", "hull", "swansea", "dundee", "inverness", "stoke", "preston",
    "blackpool", "surrey", "kent", "essex", "hampshire", "yorkshire", "cornwall",
    "devon", "lancashire", "cumbria", "east anglia", "midlands",
)


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_jsonld(html: str) -> list[dict]:
    out = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S,
    ):
        raw = m.group(1).strip()
        if not raw or "JobPosting" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            out.append(data)
    return out


def _posting_to_card(p: dict) -> JobCard:
    org = (p.get("hiringOrganization") or {})
    if isinstance(org, list):
        org = org[0] if org else {}
    loc = (p.get("jobLocation") or {})
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = (loc.get("address") or {})
    if isinstance(addr, list):
        addr = addr[0] if addr else {}
    locality = addr.get("addressLocality") or ""
    country = addr.get("addressCountry") or ""
    location = clean(", ".join(x for x in (locality, country) if x)) or None
    return JobCard(
        source="earthworks",
        source_job_id=str(p.get("identifier") or
                          (p.get("url") or "")[-40:] or None),
        url=p.get("url"), apply_url=p.get("url"),
        title=clean(p.get("title")),
        company=clean(org.get("name")),
        location_text=location,
        description=clean(p.get("description"))[:700] or None,
        posted_at=_dt(p.get("datePosted")),
        extra={
            "niche": "geoscience",
            "valid_through": p.get("validThrough"),
            "country": clean(country) or None,
        },
    )


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    uk_only = cfg.get("uk_only", True)
    all_query_text = " ".join([query.query] + query.alt_queries).lower()
    if not any(h in all_query_text for h in GEO_HINTS):
        raise ProviderSkip("earthworks skipped: query is not geoscience-flavoured")

    terms = query_terms(query.query) + [
        t for alt in query.alt_queries for t in query_terms(alt)
    ]
    collected: dict[str, JobCard] = {}
    pages = 7  # whole live feed (niche board, ~20 jobs/page)
    async with html_client() as client:
        for page in range(1, pages + 1):
            url = BASE if page == 1 else f"{BASE}?page-nr={page}"
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ProviderError(f"HTTP {resp.status_code} for {url}")
            postings = parse_jsonld(resp.text)
            if not postings:
                break
            for p in postings:
                card = _posting_to_card(p)
                if not card.title or not card.url:
                    continue
                low = f"{card.title} {card.description or ''}".lower()
                if terms and not any(t in low for t in terms):
                    continue
                if uk_only:
                    hay = f"{card.location_text or ''} {card.extra.get('country') or ''}".lower()
                    if not any(m in hay for m in UK_MARKERS):
                        continue
                collected[card.url] = card
                if len(collected) >= query.limit:
                    break
            if len(collected) >= query.limit:
                break
    cards = list(collected.values())
    if not cards:
        raise ProviderSkip(
            "0 earthworks listings matched the query + UK filter "
            f"(scanned {page} page(s)); try uk_only=false or broader terms"
        )
    return cards
