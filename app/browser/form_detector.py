from __future__ import annotations


ATS_MARKERS = {
    "greenhouse": ("greenhouse.io", "boards.greenhouse.io", "greenhouse"),
    "lever": ("lever.co", "jobs.lever.co"),
    "ashby": ("ashbyhq.com", "jobs.ashbyhq.com", "ashby"),
    "workday": ("workdayjobs.com", "myworkdayjobs.com", "workday"),
    "smartrecruiters": ("smartrecruiters.com", "jobs.smartrecruiters.com"),
    "breezy": ("breezy.hr",),
    "teamtailor": ("teamtailor.com",),
    "workable": ("workable.com", "apply.workable.com"),
    "personio": ("personio.com", "jobs.personio.com"),
    "recruitee": ("recruitee.com",),
    "comeet": ("comeet.com",),
    "linkedin_jobs": ("linkedin.com/jobs",),
}


def detect_ats_type(url: str | None, html: str | None = None) -> str | None:
    haystack = f"{url or ''}\n{html or ''}".lower()
    for ats_type, markers in ATS_MARKERS.items():
        if any(marker in haystack for marker in markers):
            return ats_type
    if "<form" in haystack:
        return "generic_form"
    return None
