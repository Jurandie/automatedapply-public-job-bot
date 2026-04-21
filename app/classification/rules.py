from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.browser.form_detector import detect_ats_type
from app.classification.location_filter import detect_location
from app.classification.remote_filter import detect_remote_type
from app.classification.seniority_filter import detect_seniority
from app.extraction.link_extractor import select_application_links
from app.extraction.salary_parser import detect_currency, parse_salary_range
from app.storage.models import Job


POSITIVE_JOB_TERMS = (
    "hiring",
    "we are hiring",
    "job opening",
    "open role",
    "job title",
    "responsibilities",
    "requirements",
    "what you'll do",
    "vacancy",
    "apply",
    "software",
    "backend",
    "python",
    "engineer",
    "developer",
    "full-time",
    "full time",
    "contract",
)

NEGATIVE_TERMS = (
    "webinar",
    "newsletter",
    "course",
    "bootcamp",
    "looking for work",
    "layoff",
)

PAYMENT_REJECTION_TERMS = (
    "unpaid",
    "volunteer",
    "commission only",
    "equity only",
    "equity-only",
)


@dataclass(frozen=True)
class ClassificationResult:
    is_job_post: bool
    eligibility_status: str
    confidence: float
    reason: str
    role: str | None
    company: str | None
    location: str | None
    remote_type: str | None
    currency: str | None
    salary_min: int | None
    salary_max: int | None
    application_links: list[str] = field(default_factory=list)
    ats_type: str | None = None
    seniority: str | None = None
    raw_extra: dict[str, Any] = field(default_factory=dict)

    def to_job(self, source_post_id: str | None, post_text: str) -> Job:
        application_url = self.application_links[0] if self.application_links else None
        job_id = build_job_id(source_post_id, application_url, post_text)
        return Job(
            id=job_id,
            source_post_id=source_post_id,
            company=self.company,
            title=self.role,
            location=self.location,
            remote_type=self.remote_type,
            currency=self.currency,
            salary_min=self.salary_min,
            salary_max=self.salary_max,
            application_url=application_url,
            ats_type=self.ats_type,
            eligibility_status=self.eligibility_status,
            eligibility_reason=self.reason,
            confidence=self.confidence,
            raw={
                "is_job_post": self.is_job_post,
                "application_links": self.application_links,
                "seniority": self.seniority,
                **self.raw_extra,
            },
        )


def build_job_id(source_post_id: str | None, application_url: str | None, text: str) -> str:
    seed = application_url or f"{source_post_id or ''}\n{text[:500]}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def classify_post(
    text: str,
    links: list[str] | None = None,
    company: str | None = None,
    allowed_seniority: set[str] | None = None,
) -> ClassificationResult:
    links = links or []
    lowered = text.lower()
    application_links = select_application_links(links)
    currency = detect_currency(text)
    salary_min, salary_max = parse_salary_range(text)
    remote_type, remote_reason = detect_remote_type(text)
    location, location_reason = detect_location(text)
    seniority, seniority_reason = detect_seniority(text, allowed_levels=allowed_seniority)
    role = extract_role(text)
    ats_type = detect_ats_type(application_links[0] if application_links else "", "")

    if any(term in lowered for term in NEGATIVE_TERMS):
        return _result(
            False,
            "rejected",
            0.82,
            "post contains negative non-job marker",
            role,
            company,
            location,
            remote_type,
            currency,
            salary_min,
            salary_max,
            application_links,
            ats_type,
            seniority,
        )

    if any(term in lowered for term in PAYMENT_REJECTION_TERMS):
        return _result(
            True,
            "rejected",
            0.94,
            "payment terms are not acceptable",
            role,
            company,
            location,
            remote_type,
            currency,
            salary_min,
            salary_max,
            application_links,
            ats_type,
            seniority,
        )

    positive_hits = sum(1 for term in POSITIVE_JOB_TERMS if term in lowered)
    is_job = positive_hits >= 1 or bool(application_links)
    if not is_job:
        return _result(
            False,
            "rejected",
            0.72,
            "post does not look like a job opportunity",
            role,
            company,
            location,
            remote_type,
            currency,
            salary_min,
            salary_max,
            application_links,
            ats_type,
            seniority,
        )

    if seniority == "rejected_seniority":
        return _result(
            True,
            "rejected",
            0.93,
            seniority_reason,
            role,
            company,
            location,
            remote_type,
            currency,
            salary_min,
            salary_max,
            application_links,
            ats_type,
            seniority,
        )

    if remote_type == "rejected_remote_region" or location == "rejected_non_target":
        return _result(
            True,
            "rejected",
            0.91,
            f"{remote_reason}; {location_reason}",
            role,
            company,
            location,
            remote_type,
            currency,
            salary_min,
            salary_max,
            application_links,
            ats_type,
            seniority,
        )

    allowed_currency = currency in {"EUR", "USD"} or currency is None
    target_remote = remote_type == "remote" and location in {"Ireland", "Italy"}
    allowed_onsite = remote_type in {"onsite", "hybrid"} and location == "Ireland"

    if seniority is None:
        status = "needs_review"
        confidence = 0.61
        reason = "seniority not explicit; only junior/pleno allowed"
    elif currency and not allowed_currency:
        status = "needs_review"
        confidence = 0.62
        reason = f"currency {currency} is not EUR/USD"
    elif allowed_onsite or target_remote:
        status = "ready_to_apply" if application_links else "needs_review"
        confidence = 0.88 if application_links else 0.76
        reason = "eligible by deterministic rules"
    elif location in {"Ireland", "Italy"} and remote_type is None:
        status = "ready_to_apply" if application_links else "needs_review"
        confidence = 0.82 if application_links else 0.70
        reason = "eligible target country; remote type not explicit"
    elif remote_type == "remote" and location is None:
        status = "needs_review"
        confidence = 0.68
        reason = "remote role but Italy/Ireland is not explicit"
    elif remote_type in {"onsite", "hybrid"} and location != "Ireland":
        status = "rejected"
        confidence = 0.84
        reason = "onsite/hybrid role outside explicit Ireland eligibility"
    else:
        status = "needs_review"
        confidence = 0.58
        reason = "job-like post needs semantic review"

    return _result(
        True,
        status,
        confidence,
        reason,
        role,
        company,
        location,
        remote_type,
        currency,
        salary_min,
        salary_max,
        application_links,
        ats_type,
        seniority,
    )


def _result(
    is_job_post: bool,
    eligibility_status: str,
    confidence: float,
    reason: str,
    role: str | None,
    company: str | None,
    location: str | None,
    remote_type: str | None,
    currency: str | None,
    salary_min: int | None,
    salary_max: int | None,
    application_links: list[str],
    ats_type: str | None,
    seniority: str | None,
) -> ClassificationResult:
    return ClassificationResult(
        is_job_post=is_job_post,
        eligibility_status=eligibility_status,
        confidence=confidence,
        reason=reason,
        role=role,
        company=company,
        location=location,
        remote_type=remote_type,
        currency=currency,
        salary_min=salary_min,
        salary_max=salary_max,
        application_links=application_links,
        ats_type=ats_type,
        seniority=seniority,
    )


def extract_role(text: str) -> str | None:
    patterns = (
        r"((?:junior|jr\.?|pleno|mid[-\s]?level|mid|intermediate)\s+[\w\s]{0,40}?(?:data engineer|automation engineer|backend engineer|software engineer|engineer|developer))",
        r"(senior\s+[\w\s]{0,40}?(?:data engineer|automation engineer|backend engineer|software engineer|engineer|developer))",
        r"((?:python|backend|automation|data)\s+[\w\s]{0,35}?(?:engineer|developer))",
        r"(software\s+engineer)",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return " ".join(match.group(1).title().split())
    return None
