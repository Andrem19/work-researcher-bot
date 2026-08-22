"""Totaljobs.com — HTTP HTML search (no key needed).

Search: https://www.totaljobs.com/jobs/{slug} or /jobs/{slug}-in-{location-slug}
Cards expose stable data-at / data-testid attributes even though classes are
hashed by the CSS-in-JS build.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from ..domain import JobCard
from ..textutils import clean, parse_salary, slugify
from .base import SearchQuery, html_client

BASE = "https://www.totaljobs.com"
FIELD_ATTRS = {
    "company": ("job-item-company-name",),
    "location": ("job-item-location",),
    "salary": ("job-item-salary-info",),
    "contract": ("job-item-type", "job-item-contract"),
    "timeago": ("job-item-timeago",),
    "description": ("job-item-description", "job-item-teaser", "text-snippet"),
}
RELATIVE_DAYS = re.compile(r"(\d+)\+?\s*(day|hour|minute|week)s?\s+ago", re.I)


def _strip_noise(node) -> None:
    """Emotion CSS injects <style> tags inside cards — drop them before .text()."""
    for junk in node.css("style, script, noscript"):
        junk.decompose(recursive=True)


def _posted_at(text: str):
    m = RELATIVE_DAYS.search(text)
    if not m:
        return None
    from datetime import UTC, datetime, timedelta

    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {
        "minute": timedelta(minutes=n), "hour": timedelta(hours=n),
        "day": timedelta(days=n), "week": timedelta(weeks=n),
    }[unit]
    return datetime.now(tz=UTC) - delta


def parse_jobs(html: str, query: SearchQuery) -> list[JobCard]:
    tree = HTMLParser(html)
    cards: list[JobCard] = []
    seen: set[str] = set()
    for anchor in tree.css('a[data-at="job-item-title"], a[data-testid="job-item-title"]'):
        href = anchor.attributes.get("href") or ""
        if not href.startswith("/job/"):
            continue
        url = urljoin(BASE, href.split("?")[0])
        if url in seen:
            continue
        seen.add(url)
        # climb to the enclosing card element
        node = anchor
        card_node = None
        for _ in range(10):
            node = node.parent
            if node is None:
                break
            attrs = node.attributes
            da = attrs.get("data-at") or attrs.get("data-testid") or ""
            tag = getattr(node, "tag", None)
            if da in ("job-item", "job-card") or tag == "article":
                card_node = node
                break
        _strip_noise(anchor)
        title = clean(anchor.text())
        company = location = salary_raw = contract = teaser = timeago = None
        if card_node is not None:
            _strip_noise(card_node)
            for field, aliases in FIELD_ATTRS.items():
                for alias in aliases:
                    found = card_node.css(f'[data-at="{alias}"], [data-testid="{alias}"]')
                    if found:
                        text = clean(found[0].text())
                        if text:
                            if field == "company":
                                company = text
                            elif field == "location":
                                location = text
                            elif field == "salary":
                                salary_raw = text
                            elif field == "contract":
                                contract = text
                            elif field == "timeago":
                                timeago = text
                            else:
                                teaser = text[:600]
                        break
            if company is None:  # logo alt fallback
                img = card_node.css_first("img[alt]")
                if img and img.attributes.get("alt"):
                    alt = clean(img.attributes["alt"])
                    if alt and len(alt) < 60 and "logo" not in alt.lower():
                        company = alt
        m = re.search(r"/job/[^/]+/([^/]+?)-job(\d+)$", url)
        job_id = m.group(2) if m else None
        sal = parse_salary(salary_raw)
        posted = _posted_at(timeago or (card_node.text() if card_node is not None else ""))
        cards.append(JobCard(
            source="totaljobs",
            source_job_id=job_id,
            url=url,
            title=title,
            company=company,
            location_text=location,
            salary_raw=salary_raw,
            salary_min=sal[0], salary_max=sal[1], salary_period=sal[2],
            contract_type=contract,
            description=teaser,
            posted_at=posted,
            extra={"fetched_via": "html", "timeago": timeago},
        ))
        if len(cards) >= query.limit:
            break
    return cards


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    slug = slugify(query.query)
    loc = query.location.strip()
    if loc and loc.upper() not in ("UK", "UNITED KINGDOM", "ENGLAND", "GREAT BRITAIN", ""):
        url = f"{BASE}/jobs/{slug}-in-{slugify(loc)}"
    else:
        url = f"{BASE}/jobs/{slug}"
    cards: list[JobCard] = []
    async with html_client() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            from .base import ProviderError

            raise ProviderError(f"HTTP {resp.status_code} for {url}")
        cards = parse_jobs(resp.text, query)
        for alt in query.alt_queries:
            if len(cards) >= 5:
                break
            resp2 = await client.get(f"{BASE}/jobs/{slugify(alt)}")
            if resp2.status_code == 200:
                seen = {c.url for c in cards}
                cards.extend(c for c in parse_jobs(resp2.text, query) if c.url not in seen)
    # 0 cards is a legitimate empty result (narrow query) — not an error
    return cards
