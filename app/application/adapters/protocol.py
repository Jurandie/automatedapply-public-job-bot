from __future__ import annotations

from typing import Protocol


class ApplicationAdapter(Protocol):
    name: str

    def matches(self, url: str, html: str) -> bool:
        ...

    def extract_job_details(self, html: str) -> dict:
        ...

    def fill_form(self, page, candidate_profile: dict) -> dict:
        ...

    def validate_before_submit(self, page) -> dict:
        ...

    def submit(self, page) -> dict:
        ...

