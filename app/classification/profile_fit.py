from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.classification.rules import ClassificationResult
from app.resume.inventory import has_real_experience
from app.resume.tailoring import inventory_keywords, select_evidence


ROLE_KEYWORDS = {
    "python developer": ("python", "django", "fastapi", "flask"),
    "backend engineer": ("backend", "api", "rest", "node.js", "nestjs", "server", "database"),
    "automation engineer": ("automation", "script", "playwright", "selenium", "api integration"),
    "data engineer": ("data engineer", "pipeline", "etl", "sql", "database", "postgresql"),
    "full-stack developer": ("full-stack", "full stack", "frontend", "backend", "next.js", "node.js"),
    "mobile developer": ("mobile", "android", "flutter", "kotlin", "dart"),
    "android developer": ("android", "kotlin", "android studio", "jetpack"),
    "flutter developer": ("flutter", "dart", "mobile"),
    "web developer": ("web developer", "html", "css", "javascript", "php", "frontend"),
}


def allowed_seniority_from_profile(profile: dict[str, Any]) -> set[str]:
    preferences = profile.get("preferences") or {}
    values = preferences.get("seniority") or []
    if isinstance(values, str):
        values = [values]
    normalized = {_normalize_seniority(str(value)) for value in values if str(value).strip()}
    return {value for value in normalized if value} or {"junior", "pleno"}


def apply_profile_fit(
    result: ClassificationResult,
    text: str,
    profile: dict[str, Any],
    inventory: dict[str, Any] | None = None,
) -> ClassificationResult:
    if not result.is_job_post or result.eligibility_status != "ready_to_apply":
        return result

    role_ok, role_reason, matched_roles = _matches_profile_roles(text, profile, inventory)
    if not role_ok:
        return _needs_review(
            result,
            f"profile/CV role fit not proven: {role_reason}",
            {"profile_fit": {"role_fit": False, "matched_roles": matched_roles}},
        )

    if inventory and has_real_experience(inventory):
        selected = _matched_inventory_keywords(inventory, text)
        if not selected:
            return _needs_review(
                result,
                "CV evidence below minimum (0/{})".format(_minimum_evidence(profile)),
                {
                    "profile_fit": {
                        "role_fit": True,
                        "matched_roles": matched_roles,
                        "selected_keywords": [],
                        "evidence_count": 0,
                        "minimum_evidence": _minimum_evidence(profile),
                    }
                },
            )
        evidence = select_evidence(inventory, selected, text)
        minimum = _minimum_evidence(profile)
        if len(evidence) < minimum:
            return _needs_review(
                result,
                f"CV evidence below minimum ({len(evidence)}/{minimum})",
                {
                    "profile_fit": {
                        "role_fit": True,
                        "matched_roles": matched_roles,
                        "selected_keywords": selected,
                        "evidence_count": len(evidence),
                        "minimum_evidence": minimum,
                    }
                },
            )

        return replace(
            result,
            reason=f"{result.reason}; profile/CV fit confirmed",
            raw_extra={
                "profile_fit": {
                    "role_fit": True,
                    "matched_roles": matched_roles,
                    "selected_keywords": selected,
                    "evidence_count": len(evidence),
                    "minimum_evidence": minimum,
                }
            },
        )

    return replace(
        result,
        reason=f"{result.reason}; profile role fit confirmed; CV inventory not populated",
        raw_extra={
            "profile_fit": {
                "role_fit": True,
                "matched_roles": matched_roles,
                "evidence_count": None,
                "minimum_evidence": _minimum_evidence(profile),
                "warning": "experience inventory has no real experiences/projects",
            }
        },
    )


def merge_raw_extra(result: ClassificationResult) -> dict[str, Any]:
    extra = getattr(result, "raw_extra", None)
    return extra if isinstance(extra, dict) else {}


def _needs_review(result: ClassificationResult, reason: str, raw_extra: dict[str, Any]) -> ClassificationResult:
    return replace(
        result,
        eligibility_status="needs_review",
        confidence=min(result.confidence, 0.64),
        reason=reason,
        raw_extra=raw_extra,
    )


def _matches_profile_roles(
    text: str,
    profile: dict[str, Any],
    inventory: dict[str, Any] | None,
) -> tuple[bool, str, list[str]]:
    preferences = profile.get("preferences") or {}
    configured_roles = preferences.get("roles") or []
    if isinstance(configured_roles, str):
        configured_roles = [configured_roles]

    normalized_text = _normalize(text)
    matched_roles: list[str] = []
    for role in configured_roles:
        role_text = str(role).strip()
        if not role_text:
            continue
        role_key = role_text.lower()
        role_terms = ROLE_KEYWORDS.get(role_key, ())
        if role_key in normalized_text or any(term in normalized_text for term in role_terms):
            matched_roles.append(role_text)

    if matched_roles:
        return True, "matched configured role keywords", matched_roles

    if inventory and has_real_experience(inventory):
        keywords = inventory_keywords(inventory)
        matched_keywords = [
            keyword
            for keyword in keywords
            if len(keyword) >= 3 and re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized_text)
        ]
        if matched_keywords:
            return True, "matched CV inventory keywords", matched_keywords[:8]

    return False, "no configured role or CV keyword matched", []


def _matched_inventory_keywords(inventory: dict[str, Any], text: str, limit: int = 16) -> list[str]:
    normalized_text = _normalize(text)
    matches = [
        keyword
        for keyword in inventory_keywords(inventory)
        if len(keyword) >= 3 and re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized_text)
    ]
    return list(dict.fromkeys(matches))[:limit]


def _minimum_evidence(profile: dict[str, Any]) -> int:
    settings = profile.get("resume_tailoring") or {}
    return max(1, int(settings.get("minimum_matched_evidence") or 2))


def _normalize_seniority(value: str) -> str | None:
    lowered = value.lower().strip()
    if lowered in {"junior", "jr", "entry", "entry-level", "entry level", "associate"}:
        return "junior"
    if lowered in {"pleno", "mid", "mid-level", "mid level", "intermediate"}:
        return "pleno"
    if lowered in {"senior", "sr"}:
        return "senior"
    return lowered or None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())
