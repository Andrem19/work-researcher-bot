"""Pydantic models shared between providers, persistence and MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCard(BaseModel):
    """A job listing as reported by one provider or an observation."""

    source: str
    source_job_id: str | None = None
    url: str | None = None
    apply_url: str | None = None
    title: str | None = None
    company: str | None = None
    location_text: str | None = None
    salary_raw: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str | None = None
    contract_type: str | None = None
    work_from_home: bool | None = None
    description: str | None = None
    posted_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderReport(BaseModel):
    provider: str
    ok: bool
    jobs: int = 0
    error: str | None = None
    fetched_url: str | None = None
    duration_ms: int = 0


class SearchParams(BaseModel):
    query: str
    alt_queries: list[str] = Field(default_factory=list)
    location: str = "UK"
    radius_miles: int = 40
    max_days_old: int = 14
    work_from_home: bool | None = None
    min_salary: int | None = None
    sources: list[str] | None = None
    limit_per_source: int = 25
    profile: str | None = None
    location_policy: str = "auto"  # auto | uk_wide | commute_only
    exclude_training: bool = True  # drop paid-course ads (training offers)
    drop_mismatch: bool = True  # drop on_site+mismatch from results (auto)


class JobBrief(BaseModel):
    """Compact row shown in search results."""

    job_id: str
    rank: int = 0
    score: float = 0.0
    is_new: bool = False
    title: str | None = None
    company: str | None = None
    location_text: str | None = None
    salary_raw: str | None = None
    salary_annum: int | None = None
    work_from_home: bool | None = None
    posted_at: datetime | None = None
    sources: list[str] = Field(default_factory=list)
    url: str | None = None
    apply_method: str | None = None
    already_applied: bool = False


class SearchResult(BaseModel):
    search_id: str
    params: SearchParams
    reports: list[ProviderReport]
    total_found: int
    new_jobs: int
    stored: int
    top: list[JobBrief]
    next_cursor: str | None = None


class ObservationIn(BaseModel):
    """A job seen by an external browser (Indeed, CV-Library, LinkedIn...)."""

    source: str
    url: str | None = None
    title: str | None = None
    company: str | None = None
    location_text: str | None = None
    salary_raw: str | None = None
    description: str | None = None
    posted_at: datetime | None = None
    contract_type: str | None = None
    work_from_home: bool | None = None
    source_job_id: str | None = None


class ApplyPlan(BaseModel):
    application_id: str
    job: dict[str, Any]
    cv: dict[str, Any] | None = None
    cv_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    apply_url: str | None = None
    apply_method: str
    applicant: dict[str, Any] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class ApplicationStatus(BaseModel):
    application_id: str
    job_id: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    submitted_at: str | None = None
    job_title: str | None = None
    company: str | None = None
    cv_id: str | None = None
    notes: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
