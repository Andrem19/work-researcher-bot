"""Provider registry and parallel search orchestration."""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import Any

from ..config import Settings
from ..domain import JobCard, ProviderReport
from .base import ProviderError, ProviderSkip, SearchQuery

REGISTRY: dict[str, str] = {
    "totaljobs": "work_researcher.providers.totaljobs",
    "reed": "work_researcher.providers.reed",
    "adzuna": "work_researcher.providers.adzuna",
    "jooble": "work_researcher.providers.jooble",
    "earthworks": "work_researcher.providers.earthworks",
    "findajob": "work_researcher.providers.findajob",
}

BROWSER_ONLY_NOTES = {
    "indeed": "Indeed blocks non-browser clients. Use the harness browser "
              "(or work-researcher browser tools) and submit_job_observations.",
    "cv-library": "CV-Library blocks non-browser clients. Same as Indeed.",
    "linkedin": "LinkedIn aggressively blocks automation and its ToS forbid it. "
                "Manual or careful browser use only.",
    "glassdoor": "Glassdoor blocks non-browser clients. Browser only.",
}


def provider_modules(settings: Settings) -> dict[str, Any]:
    out = {}
    for name, modpath in REGISTRY.items():
        if not settings.provider_enabled(name):
            continue
        try:
            out[name] = importlib.import_module(modpath)
        except Exception:
            continue
    return out


async def run_search(settings: Settings, params_dict: dict[str, Any]) -> tuple[dict[str, list[JobCard]], list[ProviderReport]]:
    """Run all enabled providers in parallel with per-provider timeout."""
    query = SearchQuery(params_dict)
    modules = provider_modules(settings)
    requested = params_dict.get("sources")
    if requested:
        requested_l = {s.lower() for s in requested}
        modules = {k: v for k, v in modules.items() if k in requested_l}

    async def _run_one(name: str, mod) -> tuple[str, list[JobCard], ProviderReport]:
        start = time.monotonic()
        try:
            cfg = dict(settings.provider_cfg(name))
            for secret_key in ("api_key", "app_id", "app_key"):
                val = settings.secret(name, secret_key)
                if val:
                    cfg[secret_key] = val
            jobs = await asyncio.wait_for(
                mod.fetch(query, cfg), timeout=settings.provider_timeout_s
            )
            dur = int((time.monotonic() - start) * 1000)
            return name, jobs, ProviderReport(
                provider=name, ok=True, jobs=len(jobs), duration_ms=dur
            )
        except ProviderSkip as exc:
            dur = int((time.monotonic() - start) * 1000)
            return name, [], ProviderReport(
                provider=name, ok=True, jobs=0, duration_ms=dur,
                error=f"skipped: {exc}",
            )
        except (ProviderError, asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            dur = int((time.monotonic() - start) * 1000)
            msg = f"{type(exc).__name__}: {exc}"
            return name, [], ProviderReport(
                provider=name, ok=False, error=msg[:300], duration_ms=dur
            )

    results = await asyncio.gather(*[_run_one(n, m) for n, m in modules.items()])
    cards_by_provider = {name: jobs for name, jobs, _ in results}
    reports = [rep for _, _, rep in results]
    return cards_by_provider, reports
