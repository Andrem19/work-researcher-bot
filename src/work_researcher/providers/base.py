"""Provider contract and shared HTTP helpers."""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..domain import JobCard

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class ProviderError(RuntimeError):
    pass


class ProviderSkip(Exception):
    """Provider deliberately not applicable to this query (not an error)."""


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
    )


def html_client() -> httpx.AsyncClient:
    return make_client()


def json_client() -> httpx.AsyncClient:
    client = make_client()
    client.headers["Accept"] = "application/json"
    return client


async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url)
    if resp.status_code in (403, 429):
        raise ProviderError(f"blocked (HTTP {resp.status_code}) — needs browser fallback")
    resp.raise_for_status()
    return resp.text


async def fetch_json(client: httpx.AsyncClient, url: str, **kw: Any) -> Any:
    resp = await client.get(url, **kw)
    if resp.status_code in (401, 403):
        raise ProviderError(f"auth failed (HTTP {resp.status_code}) — check API key")
    resp.raise_for_status()
    return resp.json()


class SearchQuery(dict):
    """Plain dict with attribute access: query, location, radius_miles,
    max_days_old, work_from_home, min_salary, limit, alt_queries."""

    @property
    def query(self) -> str:
        return self["query"]

    @property
    def location(self) -> str:
        return self.get("location") or "UK"

    @property
    def radius_miles(self) -> int:
        return int(self.get("radius_miles") or 40)

    @property
    def max_days_old(self) -> int:
        return int(self.get("max_days_old") or 14)

    @property
    def work_from_home(self) -> bool | None:
        return self.get("work_from_home")

    @property
    def min_salary(self) -> int | None:
        return self.get("min_salary")

    @property
    def limit(self) -> int:
        return int(self.get("limit") or 25)

    @property
    def alt_queries(self) -> list[str]:
        return list(self.get("alt_queries") or [])


def timed(fn):
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        jobs: list[JobCard] = await fn(*args, **kwargs)
        return jobs, int((time.monotonic() - start) * 1000)
    wrapper.__name__ = fn.__name__
    return wrapper
