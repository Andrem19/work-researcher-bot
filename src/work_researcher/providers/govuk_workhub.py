"""GOV.UK Find a job / Work Hub provider.

The official result page is attempted first. Some server networks receive an
Akamai 403, so the provider can fall back to Jina Reader's public read-through
of the same public GOV.UK result URL. No account, cookie or Google token is
used. Browser helpers remain below for interactive/local MCP use.

Search URL (GET, works in the browser):
  https://www.jobs.service.gov.uk/jobs?keywords=<query>&location=<place>&locationId=<id>

Card structure (from the page text, space-joined):
  "Data Analyst NHS Jobs - Manchester £32,073 to £39,043 a year HybridPermanentFull time
   <description excerpt> Added on <date> Save to favourites"

Filters: REMOTE, ONSITE, HYBRID, FIELD_BASED (checkboxes), Distance,
Posting date, Salary range, Contract type, Hours.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from urllib.parse import quote_plus

import httpx

from ..domain import JobCard
from ..textutils import clean, parse_salary, query_terms
from .base import ProviderError, SearchQuery, html_client

BASE = "https://www.jobs.service.gov.uk"
READER_BASE = "https://r.jina.ai/"
_READER_LOCK = asyncio.Lock()
_READER_LAST_REQUEST = 0.0
_READER_MIN_INTERVAL_S = 3.2  # public endpoint advertises 20 requests/minute

# The JS the agent runs via browser_eval to extract job cards as JSON.
# Run this AFTER navigating to a search results page.
SCRAPE_JS = r"""
() => {
  const text = (document.body.innerText || '').replace(/\s+/g, ' ').trim();
  // job entries are separated by "Save to favourites"
  const chunks = text.split(/Save to favourites/);
  const cards = [];
  for (let i = 0; i < chunks.length - 1 && cards.length < 50; i++) {
    const c = chunks[i].trim();
    if (!c || c.indexOf('jobs in') === -1 && c.indexOf('jobs per page') !== -1) continue;
    // skip the header chunk (before the first job)
    if (i === 0 && !/\d+\s+\w+.*\d+.*a year|£|Added on/.test(c)) continue;
    // title: text up to the company line; company is after " - "
    // Pattern: "Title Company - Location £salary Type ... Added on date"
    const m = c.match(/^(.+?)\s+(.+?)\s*-\s*(.+?)\s+(£[\d,.]+\s*(?:to\s*£[\d,.]+)?\s*\w+(?:\s*\w+)?)\s+((?:Remote|Onsite|Hybrid|Field[_ ]based)?\s*(?:Permanent|Temporary|Contract|Fixed term)?\s*(?:Full time|Part time)?)/i);
    let title = '', company = '', location = '', salary = '', workPattern = '';
    if (m) {
      title = m[1].trim();
      company = m[2].trim();
      location = m[3].trim();
      salary = m[4].trim();
      workPattern = m[5].trim();
    } else {
      // fallback: first line is title+company+location
      const firstBreak = c.indexOf('Added on');
      const head = firstBreak > 0 ? c.slice(0, firstBreak) : c.slice(0, 300);
      title = head.split(' - ')[0]?.trim() || '';
      company = head.split(' - ')[1]?.trim() || '';
      location = head.split(' - ')[2]?.trim() || '';
    }
    // extract "Added on DD Mon YYYY"
    const dateM = c.match(/Added on\s+(\d{1,2}\s+\w+\s+\d{4})/i);
    let postedAt = dateM ? dateM[1] : null;
    // extract job link
    const linkM = c.match(/\/job\/[^.\s]+/);
    const jobId = linkM ? linkM[0] : null;
    // description: between workPattern and "Added on"
    let desc = '';
    if (workPattern && dateM) {
      const di = c.indexOf(workPattern) + workPattern.length;
      const ai = c.indexOf('Added on');
      desc = c.slice(di, ai).trim().slice(0, 600);
    }
    if (title) {
      cards.push({title, company, location, salary, workPattern,
                  postedAt, jobId, description: desc});
    }
  }
  return {url: location.href, total: cards.length, cards};
}
"""

# Alternative: extract job links + their parent context (more robust).
# Work Hub job links use /jobs/{hex_id} (not /job/).
SCRAPE_LINKS_JS = r"""
() => {
  const links = Array.from(document.querySelectorAll('a'))
    .filter(a => a.href && a.href.match(/\/jobs\/[a-f0-9]{20,}/));
  const seen = new Set();
  const cards = [];
  for (const a of links) {
    if (seen.has(a.href)) continue;
    seen.add(a.href);
    const li = a.closest('li, div, article, [class*=result]');
    const text = (li ? li.innerText : a.innerText || '')
      .replace(/\s+/g, ' ').trim();
    cards.push({
      url: a.href,
      title: a.innerText.trim().slice(0, 120),
      context: text.slice(0, 500)
    });
    if (cards.length >= 25) break;
  }
  return {url: location.href, count: cards.length, cards};
}
"""


def search_url(query: str, location: str | None = None,
               work_pattern: str | None = None) -> str:
    """Build the current public Work Hub search URL."""
    params = {"keywords": query}
    if location and location.upper() not in ("UK", "UNITED KINGDOM"):
        params["location"] = location
    qs = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    url = f"{BASE}/jobs/search?{qs}&pageNumber=1"
    if work_pattern:
        url += f"&workingPattern={work_pattern}"
    return url


def _repair_reader_text(value: str) -> str:
    """Repair the occasional replacement character in reader output."""
    value = re.sub(r"�(?=\d)", "£", value or "")
    return value.replace("�", "'")


def parse_reader_markdown(markdown: str, limit: int = 50) -> list[JobCard]:
    """Parse the markdown representation of the official search result list."""
    markdown = _repair_reader_text(markdown)
    starts = list(re.finditer(
        r"^## \[(?P<title>.+?)\]\((?P<url>https://www\.jobs\.service\.gov\.uk/jobs/[a-f0-9]{20,}[^)]*)\)\s*$",
        markdown,
        re.M,
    ))
    cards: list[JobCard] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(markdown)
        body = markdown[match.end():end]
        body = body.split("\n* * *", 1)[0]
        parts = [clean(line) for line in body.splitlines() if clean(line) and clean(line) != "* * *"]
        if not parts:
            continue
        employer_location = parts[0]
        company, separator, location = employer_location.rpartition(" - ")
        if not separator:
            company, location = employer_location, None
        second = parts[1] if len(parts) > 1 else ""
        has_salary = bool(re.search(r"£|\b(?:salary|per (?:hour|day|week|year)|an hour|a year)\b", second, re.I))
        salary_raw = second if has_salary else None
        pattern_index = 2 if has_salary else 1
        pattern = parts[pattern_index] if len(parts) > pattern_index else ""
        description = clean(" ".join(parts[pattern_index + 1:]))[:6000] or None
        salary = parse_salary(salary_raw)
        url = match.group("url").split("?", 1)[0]
        work_low = f"{pattern} {description or ''}".lower()
        cards.append(JobCard(
            source="findajob",
            source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
            url=url,
            apply_url=url,
            title=clean(match.group("title")),
            company=clean(company) or None,
            location_text=clean(location) or None,
            salary_raw=salary_raw,
            salary_min=salary[0],
            salary_max=salary[1],
            salary_period=salary[2],
            contract_type=pattern or None,
            work_from_home=("remote" in work_low or "hybrid" in work_low),
            description=description,
            extra={"official_public_listing": True},
        ))
        if len(cards) >= limit:
            break
    return cards


async def fetch(query: SearchQuery, cfg: dict) -> list[JobCard]:
    """Fetch public GOV.UK listings, with a reader fallback for Akamai blocks."""
    url = search_url(query.query, query.location)
    markdown = ""
    fetched_via = "official"
    async with html_client() as client:
        response = await client.get(url)
        if response.status_code == 200 and "## [" in response.text:
            markdown = response.text
    if not markdown:
        if not cfg.get("reader_fallback", True):
            raise ProviderError(f"official GOV.UK result page unavailable: {response.status_code}")
        fetched_via = "public_reader_fallback"
        # Jina's Cloudflare rules may challenge a synthetic full Chrome UA;
        # use httpx's honest default identity for this read-through endpoint.
        global _READER_LAST_REQUEST
        async with _READER_LOCK:
            delay = _READER_MIN_INTERVAL_S - (time.monotonic() - _READER_LAST_REQUEST)
            if delay > 0:
                await asyncio.sleep(delay)
            async with httpx.AsyncClient(
                headers={"Accept": "application/json"}, follow_redirects=True, timeout=30
            ) as client:
                response = await client.get(f"{READER_BASE}{url}")
                _READER_LAST_REQUEST = time.monotonic()
                if response.status_code != 200:
                    raise ProviderError(f"GOV.UK reader fallback HTTP {response.status_code}")
                payload = response.json()
                markdown = str((payload.get("data") or {}).get("content") or "")
    cards = parse_reader_markdown(markdown, query.limit)
    terms = query_terms(query.query)
    relevant = [
        card for card in cards
        if not terms or any(term in f"{card.title} {card.description or ''}".lower() for term in terms)
    ]
    for card in relevant:
        card.extra["fetched_via"] = fetched_via
        card.extra["search_url"] = url
    return relevant[:query.limit]


def parse_card(context: str, url: str | None = None) -> dict:
    """Parse a single job card from its text context.

    Expected pattern (space-joined):
    "Data Analyst NHS Jobs - Manchester £32,073 to £39,043 a year HybridPermanentFull time <desc> Added on 17 Aug 2026 Save to favourites"
    """
    m = re.match(
        r"^(.+?)\s+(.+?)\s*-\s*(.+?)\s+"
        r"(£[\d,.]+(?:\s*to\s*£[\d,.]+)?\s*\w+(?:\s*\w+)?)\s*"
        r"((?:Remote|Onsite|Hybrid|Field[_\s]based)?\s*"
        r"(?:Permanent|Temporary|Contract|Fixed\s*term)?\s*"
        r"(?:Full\s*time|Part\s*time)?)",
        context, re.I,
    )
    if not m:
        return {}
    title = m.group(1).strip()
    company = m.group(2).strip()
    location = m.group(3).strip()
    salary_raw = m.group(4).strip()
    work_pattern = m.group(5).strip() if len(m.groups()) >= 5 else ""
    posted_m = re.search(r"Added on\s+(\d{1,2}\s+\w+\s+\d{4})", context, re.I)
    posted_at = _parse_date(posted_m.group(1)) if posted_m else None
    desc_start = m.end()
    desc_end = context.find("Added on", desc_start)
    desc = context[desc_start:desc_end if desc_end > 0 else desc_start + 600].strip()
    return {
        "title": title, "company": company, "location_text": location,
        "salary_raw": salary_raw, "work_pattern": work_pattern,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "url": url, "description": desc[:500] or None,
    }


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def normalize_work_pattern(wp: str) -> str | None:
    """Map Work Hub labels to our geo.py work_mode."""
    low = (wp or "").lower()
    if "remote" in low:
        return "remote"
    if "onsite" in low or "on_site" in low:
        return "on_site"
    if "hybrid" in low:
        return "hybrid"
    if "field" in low:
        return "field"
    return None
