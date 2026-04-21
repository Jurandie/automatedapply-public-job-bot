from __future__ import annotations

from app.application.adapters.base import SafeAdapterBase


class AshbyAdapter(SafeAdapterBase):
    name = "ashby"
    field_selectors = {
        "full_name": (
            "input[name='_systemfield_name']",
            "input[id*='name' i]",
        ),
        "email": (
            "input[name='_systemfield_email']",
            "input[type='email']",
        ),
        "phone": (
            "input[name='_systemfield_phone']",
            "input[type='tel']",
        ),
        "linkedin": (
            "input[name*='linkedin' i]",
            "input[id*='linkedin' i]",
        ),
        "github": (
            "input[name*='github' i]",
            "input[id*='github' i]",
        ),
        "portfolio": (
            "input[name*='portfolio' i]",
            "input[id*='portfolio' i]",
            "input[name*='website' i]",
            "input[id*='website' i]",
        ),
    }

    def matches(self, url: str, html: str) -> bool:
        haystack = f"{url}\n{html}".lower()
        return "ashbyhq.com" in haystack or "jobs.ashbyhq.com" in haystack
