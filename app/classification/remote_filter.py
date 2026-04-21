from __future__ import annotations


REMOTE_POSITIVE = (
    "remote",
    "remotely",
    "work from home",
    "wfh",
    "distributed",
)

REMOTE_RESTRICTED = (
    "remote us only",
    "remote usa only",
    "remote canada only",
    "us remote only",
    "must be based in us",
    "must be based in the us",
    "must be located in us",
    "u.s. only",
    "usa only",
    "canada only",
)

ONSITE_MARKERS = (
    "onsite",
    "on-site",
    "office-based",
    "office based",
    "in office",
)

HYBRID_MARKERS = ("hybrid", "2 days in office", "3 days in office")


def detect_remote_type(text: str) -> tuple[str | None, str | None]:
    lowered = text.lower()

    if any(marker in lowered for marker in REMOTE_RESTRICTED):
        return "rejected_remote_region", "remote restricted outside target region"

    if any(marker in lowered for marker in REMOTE_POSITIVE):
        if any(marker in lowered for marker in HYBRID_MARKERS):
            return "hybrid", "hybrid role with remote mention"
        return "remote", "remote role"

    if any(marker in lowered for marker in HYBRID_MARKERS):
        return "hybrid", "hybrid role"

    if any(marker in lowered for marker in ONSITE_MARKERS):
        return "onsite", "onsite role"

    return None, "remote type not explicit"

