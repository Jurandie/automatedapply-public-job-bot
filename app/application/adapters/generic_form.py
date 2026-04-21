from __future__ import annotations

from app.application.adapters.base import SafeAdapterBase


class GenericFormAdapter(SafeAdapterBase):
    name = "generic_form"
    field_selectors = {
        "full_name": (
            "input[name*='name' i]",
            "input[id*='name' i]",
        ),
        "email": (
            "input[type='email']",
            "input[name*='email' i]",
        ),
        "phone": (
            "input[type='tel']",
            "input[name*='phone' i]",
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
        return "<form" in html.lower()
