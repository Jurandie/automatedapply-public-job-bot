from __future__ import annotations

from app.application.adapters.base import SafeAdapterBase


class GreenhouseAdapter(SafeAdapterBase):
    name = "greenhouse"
    field_selectors = {
        "first_name": (
            "#first_name",
            "input[name='job_application[first_name]']",
        ),
        "last_name": (
            "#last_name",
            "input[name='job_application[last_name]']",
        ),
        "email": (
            "#email",
            "input[name='job_application[email]']",
        ),
        "phone": (
            "#phone",
            "input[name='job_application[phone]']",
        ),
        "linkedin": (
            "input[id*='linkedin' i]",
            "input[name*='linkedin' i]",
            "input[aria-label*='LinkedIn' i]",
        ),
        "github": (
            "input[id*='github' i]",
            "input[name*='github' i]",
            "input[aria-label*='GitHub' i]",
        ),
        "portfolio": (
            "input[id*='portfolio' i]",
            "input[name*='portfolio' i]",
            "input[id*='website' i]",
            "input[name*='website' i]",
        ),
    }

    def matches(self, url: str, html: str) -> bool:
        haystack = f"{url}\n{html}".lower()
        return "greenhouse.io" in haystack or "boards.greenhouse.io" in haystack
