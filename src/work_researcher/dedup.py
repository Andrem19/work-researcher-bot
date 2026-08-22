"""Cross-board duplicate detection.

The same vacancy is usually posted on several boards with slightly different
titles, company spellings and salaries. Ingest therefore resolves every
incoming card against recently stored jobs in three passes:

1. exact content hash (normalized title|company|location|salary_min)
2. same source + source_job_id (or same canonical URL)
3. fuzzy match: rapidfuzz token ratios on title/company/location, with company
   agreement mandatory when both sides are known

A duplicate never creates a second row: it attaches the extra source to the
canonical job (job_sources) and enriches missing fields. This is what keeps
the agent from applying to the same vacancy twice via different boards.
"""

from __future__ import annotations

import re

import aiosqlite
from rapidfuzz import fuzz

from .domain import JobCard
from .textutils import job_hash

TITLE_THRESHOLD = 85.0
COMPANY_THRESHOLD = 80.0
COMBINED_THRESHOLD = 88.0


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def _url_key(url: str | None) -> str | None:
    if not url:
        return None
    return re.sub(r"[?#].*$", "", url.strip().rstrip("/")).lower()


async def load_pool(conn: aiosqlite.Connection, window_days: int = 45,
                    limit: int = 3000) -> list[dict]:
    cur = await conn.execute(
        """SELECT id, content_hash, source, source_job_id, url, title, company,
                  location_text, salary_min
           FROM jobs WHERE last_seen >= datetime('now', ?) ORDER BY last_seen DESC LIMIT ?""",
        (f"-{window_days} days", limit),
    )
    return [dict(r) for r in await cur.fetchall()]


def _fuzzy_match(card: JobCard, row: dict) -> bool:
    t1, t2 = _norm(card.title), _norm(row["title"])
    c1, c2 = _norm(card.company), _norm(row["company"])
    l1, l2 = _norm(card.location_text), _norm(row["location_text"])
    if not t1 or not t2:
        return False
    title_r = fuzz.token_set_ratio(t1, t2)
    if title_r < TITLE_THRESHOLD:
        return False
    if c1 and c2:
        if fuzz.token_set_ratio(c1, c2) < COMPANY_THRESHOLD:
            return False
    else:
        # one side unknown company: require the location to agree
        if l1 and l2 and fuzz.token_set_ratio(l1, l2) < 80.0:
            return False
    combined = fuzz.token_set_ratio(f"{t1} {c1} {l1}", f"{t2} {c2} {l2}")
    return combined >= COMBINED_THRESHOLD


def resolve(card: JobCard, chash: str, pool: list[dict]) -> str | None:
    """Return the canonical content_hash if this card duplicates a pooled job."""
    for row in pool:
        if row["content_hash"] == chash:
            return row["content_hash"]
    for row in pool:
        if (card.source == row["source"] and card.source_job_id
                and card.source_job_id == row["source_job_id"]):
            return row["content_hash"]
    card_url = _url_key(card.url)
    if card_url:
        for row in pool:
            if card_url == _url_key(row["url"]):
                return row["content_hash"]
    for row in pool:
        if _fuzzy_match(card, row):
            return row["content_hash"]
    return None


def resolution_map(conn_cards: list[JobCard], pool: list[dict]) -> tuple[dict[str, str], int]:
    """For each card: content_hash -> canonical content_hash (itself if new).

    Intra-batch duplicates (the same vacancy arriving from two providers in
    one search) collapse onto the first card's hash via a union-find style
    pass, so they share one job row. Returns the map and the number of
    duplicates merged (cross-batch + intra-batch).
    """
    out: dict[str, str] = {}
    by_hash: dict[str, dict] = {row["content_hash"]: row for row in pool}
    merged = 0
    for card in conn_cards:
        chash = job_hash(card.title, card.company, card.location_text, card.salary_min)
        canonical = resolve(card, chash, list(by_hash.values()))
        if canonical is None:
            canonical = chash
            by_hash[chash] = {
                "content_hash": chash, "source": card.source,
                "source_job_id": card.source_job_id, "url": card.url,
                "title": card.title, "company": card.company,
                "location_text": card.location_text, "salary_min": card.salary_min,
            }
        elif canonical != chash:
            merged += 1
        out[chash] = canonical
    return out, merged
