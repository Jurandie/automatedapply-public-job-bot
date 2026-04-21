from __future__ import annotations

from app.application.adapters.base import SafeAdapterBase


class LeverAdapter(SafeAdapterBase):
    name = "lever"
    field_selectors = {
        "full_name": (
            "input[name='name']",
            "input[id='name']",
        ),
        "email": (
            "input[name='email']",
            "input[type='email']",
        ),
        "phone": (
            "input[name='phone']",
            "input[type='tel']",
        ),
        "linkedin": (
            "input[name='urls[LinkedIn]']",
            "input[name*='linkedin' i]",
            "input[id*='linkedin' i]",
        ),
        "github": (
            "input[name='urls[GitHub]']",
            "input[name*='github' i]",
            "input[id*='github' i]",
        ),
        "portfolio": (
            "input[name='urls[Portfolio]']",
            "input[name='urls[Other]']",
            "input[name*='portfolio' i]",
            "input[name*='website' i]",
        ),
    }

    def matches(self, url: str, html: str) -> bool:
        haystack = f"{url}\n{html}".lower()
        return "lever.co" in haystack or "jobs.lever.co" in haystack
