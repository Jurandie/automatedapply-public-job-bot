from __future__ import annotations

from app.application.form_utils import (
    fill_known_text_fields,
    merge_selector_maps,
    upload_resume,
    validate_required_controls,
)


class SafeAdapterBase:
    name = "base"
    field_selectors: dict[str, tuple[str, ...]] = {}
    field_aliases: dict[str, tuple[str, ...]] = {}

    def extract_job_details(self, html: str) -> dict:
        return {}

    def fill_form(self, page, candidate_profile: dict) -> dict:
        text_result = fill_known_text_fields(
            page,
            candidate_profile,
            selector_map=self.field_selectors,
            alias_map=self.field_aliases,
        )
        upload_result = upload_resume(page, candidate_profile)
        return {
            "filled": bool(text_result["filled_count"] or upload_result.get("uploaded")),
            "adapter": self.name,
            "text_fields": text_result,
            "resume_upload": upload_result,
        }

    def validate_before_submit(self, page) -> dict:
        validation = validate_required_controls(page)
        validation["adapter"] = self.name
        return validation

    def submit(self, page) -> dict:
        return {
            "submitted": False,
            "reason": "automatic submit is intentionally disabled in MVP",
        }

    def selector_map(self, *maps: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        return merge_selector_maps(self.field_selectors, *maps)
