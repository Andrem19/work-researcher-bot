"""GOV.UK Work Hub (www.jobs.service.gov.uk/jobs) — browser-only provider.

The site renders results as a JS SPA; HTTP returns a bare shell. The agent
searches it with the browser_* tools and feeds findings back through
submit_job_observations. This module provides a scrape helper and the
parsing logic so the agent can call it from a single browser_eval.

Search URL (GET, works in the browser):
  https://www.jobs.service.gov.uk/jobs?keywords=<query>&location=<place>&locationId=<id>

Card structure (from the page text, space-joined):
  "Data Analyst NHS Jobs - Manchester £32,073 to £39,043 a year HybridPermanentFull time
   <description excerpt> Added on <date> Save to favourites"

Filters: REMOTE, ONSITE, HYBRID, FIELD_BASED (checkboxes), Distance,
Posting date, Salary range, Contract type, Hours.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

BASE = "https://www.jobs.service.gov.uk"

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
    """Build a Work Hub search URL (works as GET in the browser)."""
    params = {"keywords": query}
    if location and location.upper() not in ("UK", "UNITED KINGDOM"):
        params["location"] = location
    qs = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    url = f"{BASE}/jobs?{qs}"
    if work_pattern:
        url += f"&workingPattern={work_pattern}"
    return url


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
