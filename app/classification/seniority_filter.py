from __future__ import annotations

import re


ALLOWED_SENIORITY_MARKERS = (
    r"\bjunior\b",
    r"\bjr\.?\b",
    r"\bentry[-\s]?level\b",
    r"\bentry\b",
    r"\bassociate\b",
    r"\bgraduate\b",
    r"\bpleno\b",
    r"\bmid[-\s]?level\b",
    r"\bmid\b",
    r"\bintermediate\b",
)

SENIOR_SENIORITY_MARKERS = (
    r"\bsenior\b",
    r"\bsr\.?\b",
)

REJECTED_SENIORITY_MARKERS = (
    r"\blead\b",
    r"\bstaff\b",
    r"\bprincipal\b",
    r"\barchitect\b",
    r"\bmanager\b",
    r"\bmanagement\b",
    r"\bhead\b",
    r"\bdirector\b",
    r"\bvp\b",
    r"\bchief\b",
    r"\btech lead\b",
    r"\bteam lead\b",
    r"\btrainee\b",
    r"\binternship\b",
    r"\bintern\b",
    r"\bestagio\b",
    r"\bestagiario\b",
)


def detect_seniority(text: str, allowed_levels: set[str] | None = None) -> tuple[str | None, str]:
    allowed_levels = allowed_levels or {"junior", "pleno"}
    lowered = text.lower()

    rejected = _matched_patterns(lowered, REJECTED_SENIORITY_MARKERS)
    allowed = _matched_patterns(lowered, ALLOWED_SENIORITY_MARKERS)
    senior = _matched_patterns(lowered, SENIOR_SENIORITY_MARKERS)

    if rejected:
        return "rejected_seniority", f"seniority outside junior/pleno detected: {', '.join(rejected)}"

    if senior:
        if "senior" in allowed_levels:
            return "senior", f"allowed seniority detected: {', '.join(senior)}"
        return "rejected_seniority", f"seniority outside configured levels detected: {', '.join(senior)}"

    if allowed:
        normalized = _normalize_allowed(allowed[0])
        if normalized not in allowed_levels:
            return "rejected_seniority", f"seniority outside configured levels detected: {', '.join(allowed)}"
        return normalized, f"allowed junior/pleno seniority detected: {', '.join(allowed)}"

    return None, "seniority not explicit"


def _matched_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    matches = []
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            matches.append(match.group(0).strip())
    return matches


def _normalize_allowed(marker: str) -> str:
    marker = marker.lower().strip(".")
    if marker in {"pleno", "mid", "mid-level", "mid level", "intermediate"}:
        return "pleno"
    return "junior"
