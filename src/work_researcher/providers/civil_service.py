"""Official Civil Service Careers Government Digital and Data vacancies."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlparse

from selectolax.parser import HTMLParser

from ..domain import JobCard
from ..textutils import clean, parse_salary, query_terms
from .base import ProviderError, SearchQuery, html_client

JOBS_URL = (
    "https://www.civil-service-careers.gov.uk/professions/"
    "working-in-digital-data-and-technology/"
)

_CACHE: list[JobCard] | None = None
_CACHE_LOCK = asyncio.Lock()


def parse_jobs(html: str) -> list[JobCard]:
    tree = HTMLParser(html)
    cards: list[JobCard] = []
    for node in tree.css("article.job"):
        anchor = node.css_first(".job__title a")
        if anchor is None:
            continue
        url = anchor.attributes.get("href") or ""
        title = clean(anchor.text())
        if not title or not url:
            continue
        company_node = node.css_first(".job__customer-name")
        location_node = node.css_first(".job__city-name")
        salary_node = node.css_first(".job__salary")
        closing_node = node.css_first(".job__closing-date")
        company = clean(company_node.text()) if company_node else None
        location = clean(location_node.text()) if location_node else None
        salary_raw = clean(salary_node.text()) if salary_node else None
        closing = clean(closing_node.text()) if closing_node else None
        tags = [clean(item.text()) for item in node.css(".job__roletype") if clean(item.text())]
        salary = parse_salary(salary_raw)
        vacancy_id = (parse_qs(urlparse(url).query).get("vxvac") or [None])[0]
        searchable = clean(" ".join([title, company or "", location or "", *tags]))
        cards.append(JobCard(
            source="civil_service",
            source_job_id=vacancy_id,
            url=url,
            apply_url=url,
            title=title,
            company=company,
            location_text=location,
            salary_raw=salary_raw,
            salary_min=salary[0], salary_max=salary[1], salary_period=salary[2],
            work_from_home=("remote" in searchable.lower() or "hybrid" in searchable.lower()),
            description=(
                "Official Civil Service Government Digital and Data vacancy. "
                f"Profession tags: {', '.join(tags) or 'not stated'}. "
                f"{closing or ''}"
            ).strip(),
            extra={
                "official_public_listing": True,
                "direct_employer": True,
                "closing_date": closing,
                "profession_tags": tags,
            },
        ))
    return cards


async def _all_jobs() -> list[JobCard]:
    global _CACHE
    if _CACHE is not None:
        return [card.model_copy(deep=True) for card in _CACHE]
    async with _CACHE_LOCK:
        if _CACHE is None:
            async with html_client() as client:
                response = await client.get(JOBS_URL)
                if response.status_code != 200:
                    raise ProviderError(f"Civil Service Careers HTTP {response.status_code}")
                response.encoding = "utf-8"
                parsed = parse_jobs(response.text)
                if not parsed:
                    raise ProviderError("Civil Service Careers returned no parseable vacancies")
                _CACHE = parsed
    return [card.model_copy(deep=True) for card in (_CACHE or [])]


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    cards = await _all_jobs()
    terms = query_terms(query.query)
    # Role-family terms are more useful than level words, which query_terms
    # already removes. Match title and official profession tags.
    relevant = []
    for card in cards:
        hay = f"{card.title} {' '.join(card.extra.get('profession_tags') or [])}".lower()
        if not terms or any(re.search(rf"\b{re.escape(term)}", hay) for term in terms):
            relevant.append(card)
    return relevant[:query.limit]
