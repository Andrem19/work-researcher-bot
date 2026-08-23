"""Reed.co.uk — free partner API when a key is configured, HTML fallback otherwise.

API: GET https://www.reed.co.uk/api/1.0/search (Basic auth, apiKey as user).
HTML: cards are <article data-qa="job-card"> with data-qa sub-fields.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus, urljoin

from selectolax.parser import HTMLParser

from ..domain import JobCard
from ..textutils import clean, parse_salary, slugify
from .base import ProviderError, SearchQuery, html_client, json_client

API = "https://www.reed.co.uk/api/1.0/search"
BASE = "https://www.reed.co.uk"
RELATIVE_DAYS = re.compile(r"(\d+)\s*(day|hour|minute|week)s?\s+ago", re.I)
ABS_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+("
                      r"Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|"
                      r"Oct\w*|Nov\w*|Dec\w*)(?:\s+(\d{4}))?\b", re.I)


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch_api(query: SearchQuery, api_key: str) -> list[JobCard]:
    params = {
        "keywords": query.query,
        "resultsToReturn": min(query.limit, 100),
    }
    loc = query.location.strip()
    if loc and loc.upper() not in ("UK", "UNITED KINGDOM"):
        params["locationName"] = loc
        params["distanceFromLocation"] = query.radius_miles
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    async with json_client() as client:
        client.headers["Authorization"] = f"Basic {token}"
        data = await client.get(API, params=params)
        if data.status_code != 200:
            raise ProviderError(f"reed API HTTP {data.status_code}")
        payload = data.json()
    cards = []
    for j in payload.get("jobs", []):
        cards.append(JobCard(
            source="reed",
            source_job_id=str(j.get("jobId")),
            url=j.get("jobUrl"),
            apply_url=j.get("jobUrl"),
            title=j.get("jobTitle"),
            company=j.get("employerName"),
            location_text=j.get("locationName"),
            salary_raw=(j.get("minimumSalary") or j.get("maximumSalary"))
            and f"£{j.get('minimumSalary') or '?'} - £{j.get('maximumSalary') or '?'} "
            f"per {j.get('salaryType', 'annum')}".replace("per ?", "per annum"),
            salary_min=float(j["minimumSalary"]) if j.get("minimumSalary") else None,
            salary_max=float(j["maximumSalary"]) if j.get("maximumSalary") else None,
            salary_period="year",
            contract_type=j.get("contractType"),
            description=clean(j.get("jobDescription"))[:800],
            posted_at=_dt(j.get("date")),
            extra={"api": True, "recruiter": j.get("recruiterName")},
        ))
        if len(cards) >= query.limit:
            break
    return cards


def _posted_from_card(text: str) -> datetime | None:
    m = RELATIVE_DAYS.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "minute": timedelta(minutes=n), "hour": timedelta(hours=n),
            "day": timedelta(days=n), "week": timedelta(weeks=n),
        }[unit]
        return datetime.now(tz=UTC) - delta
    m = ABS_DATE.search(text)
    if m:
        day, mon, year = int(m.group(1)), m.group(2), m.group(3)
        months = ["january", "february", "march", "april", "may", "june", "july",
                  "august", "september", "october", "november", "december"]
        ml = mon.lower()[:3]
        for i, name in enumerate(months, 1):
            if name.startswith(ml if len(ml) == 3 else ml[:3]):
                try:
                    return datetime(int(year or datetime.now(tz=UTC).year), i, day,
                                    tzinfo=UTC)
                except ValueError:
                    return None
    return None


def parse_html(html: str, query: SearchQuery) -> list[JobCard]:
    tree = HTMLParser(html)
    cards: list[JobCard] = []
    for art in tree.css('article[data-qa="job-card"]'):
        a = art.css_first('a[data-qa="job-card-title"]')
        if a is None:
            continue
        href = (a.attributes.get("href") or "").split("?")[0]
        if not href.startswith("/jobs/"):
            continue
        url = urljoin(BASE, href)
        title = clean(a.text()) or clean(a.attributes.get("title"))
        fields = {}
        for key in ("job-metadata-location", "job-metadata-salary", "job-posted-by"):
            el = art.css_first(f'[data-qa="{key}"]')
            if el is not None:
                fields[key] = clean(el.text())
        salary_raw = fields.get("job-metadata-salary")
        sal = parse_salary(salary_raw)
        posted_by = fields.get("job-posted-by") or ""
        company = posted_by.split(" by ")[-1].strip() if " by " in posted_by \
            else (posted_by or None)
        cards.append(JobCard(
            source="reed",
            source_job_id=(a.attributes.get("data-id") or "").removeprefix("job") or None,
            url=url, apply_url=url, title=title,
            company=company,
            location_text=fields.get("job-metadata-location"),
            salary_raw=salary_raw,
            salary_min=sal[0], salary_max=sal[1], salary_period=sal[2],
            posted_at=_posted_from_card(posted_by or clean(art.text())),
            extra={"easy_apply": bool(art.css_first(
                '[data-qa="badge-1-easyApply"], [data-qa*="easyApply"]'))},
        ))
        if len(cards) >= query.limit:
            break
    return cards


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    api_key = cfg.get("api_key") if isinstance(cfg, dict) else None
    if api_key:
        try:
            cards = await fetch_api(query, api_key)
            if cards:
                return cards
        except ProviderError:
            pass  # fall through to HTML
    slug = slugify(query.query)
    # hideTrainingJobs is Reed's own filter for paid-course ads
    url = f"{BASE}/jobs/{slug}-jobs?hideTrainingJobs=true"
    async with html_client() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise ProviderError(f"HTTP {resp.status_code} for {url}")
        cards = parse_html(resp.text, query)
    if not cards:
        raise ProviderError(f"0 cards parsed from {url} — selector drift?")
    return cards
