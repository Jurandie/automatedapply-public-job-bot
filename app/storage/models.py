from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LinkedInPost:
    id: str
    source_url: str
    post_text: str
    author: str | None = None
    company: str | None = None
    post_url: str | None = None
    posted_at: str | None = None
    collected_at: str = field(default_factory=utc_now_iso)
    raw_html: str | None = None
    status: str = "discovered"


@dataclass(frozen=True)
class Job:
    id: str
    source_post_id: str | None
    company: str | None
    title: str | None
    location: str | None
    remote_type: str | None
    currency: str | None
    salary_min: int | None
    salary_max: int | None
    application_url: str | None
    ats_type: str | None
    eligibility_status: str
    eligibility_reason: str
    confidence: float
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ApplicationEvent:
    id: str
    job_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class Application:
    id: str
    job_id: str
    status: str
    mode: str
    submitted_at: str | None = None
    form_snapshot_path: str | None = None
    confirmation_number: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
