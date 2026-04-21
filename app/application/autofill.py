from __future__ import annotations

from app.application.adapters import ADAPTERS


def select_adapter(url: str, html: str = ""):
    for adapter in ADAPTERS:
        if adapter.matches(url, html):
            return adapter
    return None

