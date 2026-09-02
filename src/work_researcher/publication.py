"""Evidence-backed publication dates and earliest known cross-board sources."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .domain import JobCard

UK = ZoneInfo("Europe/London")
DATE_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)(?:\s+(\d{4}))?\b", re.I)
MONTHS = {name: i for i, name in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def normalize_url(url: str | None) -> str:
    """Keep vacancy IDs in query strings; remove only known tracking fields."""
    parts = urlsplit((url or "").strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"source", "?source", "ref", "campaign"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), parts.fragment))


def source_for_url(url: str, fallback: str) -> str:
    host = urlsplit(url).hostname or ""
    for domain, source in {
        "reed.co.uk": "reed", "jobs.service.gov.uk": "findajob",
        "totaljobs.com": "totaljobs", "adzuna.co.uk": "adzuna",
        "jooble.org": "jooble", "earthworks-jobs.com": "earthworks",
    }.items():
        if host == domain or host.endswith("." + domain):
            return source
    return host or fallback


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").split("|", 1)[0].lower()).strip()


def match_key(card: JobCard) -> str:
    return hashlib.sha256(f"{_norm(card.title)}|{_norm(card.company)}".encode()).hexdigest()[:24]


def parse_posted(raw: str, *, now: datetime | None = None) -> dict | None:
    now = (now or datetime.now(UTC)).astimezone(UK)
    raw = (raw or "").strip()
    precision = "day"
    inferred = False
    value = None
    iso = re.match(r"^\d{4}-\d{2}-\d{2}(?:T[^\s]+)?", raw)
    if iso:
        try:
            value = datetime.fromisoformat(iso.group().replace("Z", "+00:00"))
            precision = "instant" if "T" in iso.group() else "day"
        except ValueError:
            return None
    if value is None:
        match = DATE_RE.search(raw)
        if match:
            day, month, year = match.groups()
            inferred = not bool(year)
            try:
                value = datetime(int(year or now.year), MONTHS[month[:3].lower()], int(day), tzinfo=UK)
                if inferred and value.date() > now.date():
                    value = value.replace(year=value.year - 1)
            except ValueError:
                return None
    if value is None:
        match = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", raw)
        if match:
            day, month, year = map(int, match.groups())
            try:
                value = datetime(year, month, day, tzinfo=UK)
            except ValueError:
                return None
    if value is None:
        match = re.search(r"\b(\d+)\s*(minute|min|hour|hr|day|week)s?\s+ago\b", raw, re.I)
        if match:
            n, unit = match.groups()
            seconds = {"minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400, "week": 604800}[unit.lower()]
            value = now - timedelta(seconds=int(n) * seconds)
            precision = "approximate"
        elif raw.lower() in {"today", "yesterday"}:
            value = now - timedelta(days=raw.lower() == "yesterday")
            precision = "approximate"
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UK)
    # Future timestamps are not credible publication evidence, even if the
    # source accidentally exposes an upcoming closing date in a posted field.
    if value.astimezone(UK).date() > now.date():
        return None
    return {"posted_at": value.isoformat(), "precision": precision,
            "year_inferred": inferred, "raw": raw}


def evidence(card: JobCard) -> list[dict]:
    items = list(card.extra.get("publication_evidence") or [])
    # Jooble's `updated` is not a publication date. Neither first_seen nor
    # fetched_at is allowed to enter this evidence set.
    if (card.posted_at or card.extra.get("publication_raw")) and card.source != "jooble" and not items:
        raw = card.extra.get("publication_raw") or card.posted_at.isoformat()
        parsed = parse_posted(raw)
        if parsed:
            items.append({**parsed, "source": card.source, "url": card.url, "kind": "provider"})
    return items


def combine_evidence(items: list[dict]) -> list[dict]:
    unique = {}
    for item in items:
        key = (item.get("url"), item.get("kind"), item.get("raw"), item.get("precision"))
        unique.setdefault(key, item)
    return list(unique.values())


def unique_cards(cards: list[JobCard]) -> list[JobCard]:
    """Retain every platform URL; richer text must not erase older date evidence."""
    unique = {}
    for card in cards:
        key = (card.source, normalize_url(card.url)) if card.url else (card.source, id(card))
        old = unique.get(key)
        if old is None:
            unique[key] = card
            card.extra["publication_evidence"] = evidence(card)
            continue
        items = combine_evidence(evidence(old) + evidence(card))
        if len(card.description or "") > len(old.description or ""):
            old.description = card.description
        unique[key].extra["publication_evidence"] = items
    return list(unique.values())


def add_evidence(card: JobCard, raw: str, url: str, *, kind: str, source: str | None = None) -> None:
    items = evidence(card)
    parsed = parse_posted(raw)
    if parsed:
        item = {**parsed, "url": url, "source": source or card.source, "kind": kind}
        if item not in items:
            items.append(item)
    card.extra["publication_evidence"] = combine_evidence(items)


def _application_identity(card: JobCard) -> str | None:
    pages = card.extra.get("verification_pages") or []
    if not pages:
        return None
    url = pages[-1].get("url") or ""
    parsed = urlsplit(url)
    # Generic login forms/home pages are not vacancy identifiers.
    if re.search(r"/jobs?/[^/]+|jcode=|vxvac=|[?&]jobid=|/applicant/\d+", url, re.I):
        return normalize_url(url)
    if parsed.fragment and re.search(r"applicant/\d+", parsed.fragment):
        return normalize_url(url)
    return None


def same_vacancy(left: JobCard, right: JobCard) -> bool:
    if left.url and normalize_url(left.url) == normalize_url(right.url):
        return True
    a, b = _application_identity(left), _application_identity(right)
    if a and b:
        if a == b:
            return True
        if urlsplit(a).netloc == urlsplit(b).netloc:
            return False
    if not left.title or not left.company or match_key(left) != match_key(right):
        return False
    if left.source == right.source:
        return False  # distinct IDs on one board need a common application ID
    if _norm(left.location_text) != _norm(right.location_text):
        return False
    # A shared generic title at a large employer is not enough to transfer dates.
    x = set(_norm(left.extra.get("publication_description") or left.description).split())
    y = set(_norm(right.extra.get("publication_description") or right.description).split())
    return min(len(x), len(y)) >= 30 and len(x & y) / max(1, len(x | y)) >= 0.65


def source_record(card: JobCard) -> dict:
    from .career import vacancy_status

    status = vacancy_status(card)
    return {
        "source": card.source, "url": card.url,
        "evidence": evidence(card),
        "application_check": card.extra.get("application_check"),
        "checked_at": card.extra.get("checked_at"),
        "closed": status["closed"],
        "reportable": status["reportable"],
    }


def attach_sources(card: JobCard, observations: list[JobCard]) -> None:
    card.extra["publication_sources"] = [source_record(other) for other in observations if same_vacancy(card, other)]


def report_fields(card: JobCard) -> dict:
    sources = card.extra.get("publication_sources") or [source_record(card)]
    rows = [item for source in sources for item in source.get("evidence", [])
            if item.get("posted_at") and item.get("url")]
    known = []
    for row in rows:
        parsed = parse_posted(str(row["posted_at"]))
        if parsed:
            known.append(row)
    # Exact dates take priority over estimates such as "3 days ago". Do not
    # invent an ordering within the same day when one source omits the time.
    precise = [r for r in known if r.get("precision") != "approximate" and not r.get("year_inferred")]
    pool = precise or known
    first = min(pool, key=lambda r: (datetime.fromisoformat(r["posted_at"]).astimezone(UK).date(),
                                    normalize_url(r["url"])), default=None)
    same_day = [r for r in pool if first and datetime.fromisoformat(r["posted_at"]).astimezone(UK).date()
                == datetime.fromisoformat(first["posted_at"]).astimezone(UK).date()]
    if same_day and all(r.get("precision") == "instant" for r in same_day):
        first = min(same_day, key=lambda r: datetime.fromisoformat(r["posted_at"]))
    result = {
        "publication_sources": sources,
        "publication_scope": "earliest_known" if first else "unknown",
        "publication_incomplete": any(not s.get("evidence") for s in sources),
        "posted_at": first["posted_at"] if first else None,
        "publication_url": first["url"] if first else None,
        "publication_source": first["source"] if first else None,
        "publication_precision": first.get("precision") if first else None,
        "publication_year_inferred": first.get("year_inferred", False) if first else False,
        "publication_date_conflict": len({r["posted_at"][:10] for r in known if first and normalize_url(r["url"]) == normalize_url(first["url"])}) > 1,
        "publication_tied": len({r["url"] for r in same_day}) > 1 and not all(r.get("precision") == "instant" for r in same_day),
        "publication_uncertain_dates": any(r.get("precision") == "approximate" or r.get("year_inferred") for r in known),
    }
    if first:
        origin = next((s for s in sources if first in s.get("evidence", [])), None)
        # Retain the oldest source as evidence even when archived. Never turn
        # its dead link into the active application link in the report.
        archived = bool(origin and (origin.get("closed") or not origin.get("reportable", True)))
        result["publication_archived"] = archived
        if not archived:
            result.update({"url": first["url"], "source": first["source"]})
    return result
