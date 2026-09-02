"""Read-only, bounded checks of shortlisted adverts and their application links.

No forms are submitted. Search snippets, HTTP 200 challenge pages and an
aggregator's advert expiry are never treated as proof of an open application.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from .career import CLOSED_RE, DEADLINE_LABEL_RE, vacancy_status
from .domain import JobCard
from .publication import add_evidence, source_for_url

CHALLENGE_RE = re.compile(r"quick check needed|verify you are human|access denied|captcha|just a moment", re.I)
APPLY_RE = re.compile(r"^(?:apply(?: now| for (?:this|the) (?:job|role))?|continue to (?:the )?employer['\u2019]s website)$", re.I)
DWP_JOBS = "https://careers.dwp.gov.uk/all-digital-jobs/"


def public_url(url: str) -> bool:
    """Reject literal private/local targets, credentials and non-web links."""
    import ipaddress

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or "." not in host or host.endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def _postings(data):
    if isinstance(data, list):
        for value in data:
            yield from _postings(value)
    elif isinstance(data, dict):
        kind = data.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            yield data
        yield from _postings(data.get("@graph"))


def parse_page(content: str, url: str, title: str | None = None) -> dict:
    """Extract job-scoped metadata, not dates/expired badges on related jobs."""
    tree = HTMLParser(content)
    postings = []
    for script in tree.css('script[type="application/ld+json"]'):
        with contextlib.suppress(ValueError, TypeError):
            postings.extend(_postings(json.loads(script.text())))
    for node in tree.css("script, style, nav, footer, header, aside"):
        node.decompose()
    main = tree.css_first("main") or tree.body or tree.root
    text = main.text(separator=" ", strip=True)
    text = re.split(r"\b(?:Related jobs|Similar Jobs|Featured roles|Recommended courses)\b", text, maxsplit=1, flags=re.I)[0]
    deadlines = [m.group(1).strip() for m in DEADLINE_LABEL_RE.finditer(text)]
    publications = [(re.split(r"\b(?:closing date|deadline|last updated|date modified|salary|hours|job type|apply|summary)\b", m.group(1), maxsplit=1, flags=re.I)[0].strip(), "visible_posting_date") for m in re.finditer(
        r"\b(?:posting date|date posted|posted on|published on|publication date)\s*[:|]?\s*([^|\n]{3,60})", text, re.I,
    )]
    matched = [p for p in postings if not title or str(p.get("title", "")).casefold() == title.casefold()]
    for posting in matched:
        if posting.get("validThrough"):
            deadlines.append(str(posting["validThrough"]))
        if posting.get("datePosted"):
            publications.append((str(posting["datePosted"]), "datePosted"))
    posted_by = main.css_first('[data-qa="job-posted-by"]')
    if posted_by:
        publications.append((posted_by.text(separator=" ", strip=True).split(" by ")[0], "visible_posting_date"))
    if urlparse(url).hostname in {"www.reed.co.uk", "reed.co.uk"}:
        heading = re.split(r"Full job description|Job Description", text, maxsplit=1, flags=re.I)[0]
        visible = re.search(r"\b(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)\s+by\b", heading)
        if visible:
            publications.append((visible.group(1), "visible_posting_date"))
    next_url = None
    for meta in tree.css("meta[http-equiv]"):
        if str(meta.attributes.get("http-equiv", "")).lower() == "refresh":
            match = re.search(r"url\s*=\s*['\"]?(.+?)['\"]?\s*$", meta.attributes.get("content", ""), re.I)
            if match:
                next_url = urljoin(url, match.group(1))
                break
    has_apply = False
    for node in main.css("a, button, input"):
        label = (node.attributes.get("value") or node.text()).strip()
        if APPLY_RE.fullmatch(label) and "disabled" not in node.attributes:
            has_apply = True
            href = node.attributes.get("href") or ""
            if not next_url and href and not href.startswith(("#", "javascript:", "mailto:")):
                next_url = urljoin(url, href)
    if next_url and not public_url(next_url):
        next_url = None
    return {
        "deadlines": list(dict.fromkeys(deadlines)), "closed": bool(CLOSED_RE.search(text)),
        "challenge": bool(CHALLENGE_RE.search(text)), "has_apply": has_apply,
        "next_url": next_url, "has_job": bool(matched) or bool(title and title.casefold() in text.casefold()),
        "publications": publications,
        "description": str(matched[0].get("description") or "") if matched else text,
    }


class VacancyVerifier:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: dict[str, tuple[int, str, str]] = {}
        self.lock = asyncio.Lock()

    async def fetch(self, url: str) -> tuple[int, str, str]:
        if not public_url(url):
            return 0, "", url
        if url in self.cache:
            return self.cache[url]
        current = url
        try:
            # Validate every ordinary redirect too; no unbounded HTTP chain.
            for _ in range(6):
                response = await self.client.get(current, follow_redirects=False)
                if response.is_redirect and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    if not public_url(current):
                        return 0, "", url
                    continue
                response.encoding = "utf-8"
                result = (response.status_code, response.text, current)
                self.cache[url] = result
                return result
        except httpx.HTTPError:
            pass
        return 0, "", current

    async def _dwp_deadline(self, url: str) -> dict | None:
        """The public DWP catalogue is authoritative even if CS Jobs challenges."""
        jcode = (parse_qs(urlparse(url).query).get("jcode") or [None])[0]
        if not jcode:
            return None
        async with self.lock:
            status, content, _ = await self.fetch(DWP_JOBS)
        if status != 200:
            return None
        for node in HTMLParser(content).css("a[href]"):
            href = node.attributes["href"].strip()
            if (parse_qs(urlparse(href).query).get("jcode") or [None])[0] != jcode:
                continue
            match = DEADLINE_LABEL_RE.search(node.text(separator=" "))
            if match:
                return {"raw": match.group(1), "source_url": DWP_JOBS, "kind": "employer"}
        return None

    async def verify(self, card: JobCard) -> dict:
        card.extra["checked_at"] = datetime.now(UTC).isoformat()
        card.extra["application_check"] = "unverified"
        card.extra["deadline_evidence"] = []
        card.extra["verification_pages"] = []
        card.extra.pop("vacancy_closed", None)
        current = card.url or card.apply_url or ""
        seen = set()
        for hop in range(5):
            if not current or current in seen:
                break
            seen.add(current)
            status, content, resolved = await self.fetch(current)
            card.extra["verification_pages"].append({"url": resolved, "http_status": status})
            if status in {404, 410}:
                card.extra["vacancy_closed"] = True
                card.extra["application_check"] = "closed"
                break
            if status != 200:
                break
            page = parse_page(content, resolved, card.title)
            if page["challenge"]:
                if urlparse(resolved).hostname == "www.civilservicejobs.service.gov.uk" and "dwp" in (card.company or "").lower():
                    primary = await self._dwp_deadline(resolved)
                    if primary:
                        card.extra["deadline_evidence"].append(primary)
                        card.extra["application_check"] = "employer_listing"
                break
            if page["has_job"]:
                for raw, kind in page["publications"]:
                    source = source_for_url(resolved, card.source)
                    add_evidence(card, raw, resolved, kind=kind, source=source)
                description = HTMLParser(page["description"]).text(separator=" ", strip=True)
                if len(description) >= 500:
                    card.extra["publication_description"] = description[:12000]
            kind = "listing" if hop == 0 else "employer"
            card.extra["deadline_evidence"].extend(
                {"raw": value, "source_url": resolved, "kind": kind} for value in page["deadlines"]
            )
            if page["closed"]:
                card.extra["vacancy_closed"] = True
                card.extra["application_check"] = "closed"
                break
            if page["next_url"]:
                current = page["next_url"]
                continue
            if page["has_job"] and page["has_apply"]:
                card.extra["application_check"] = "listing_checked" if hop == 0 else "application_page_checked"
            break
        return vacancy_status(card)


async def verify_cards(cards: list[JobCard]) -> list[dict]:
    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "WorkResearcherBot/0.1"}) as client:
        verifier = VacancyVerifier(client)

        async def one(card):
            async with semaphore:
                return await verifier.verify(card)

        return await asyncio.gather(*(one(card) for card in cards))
