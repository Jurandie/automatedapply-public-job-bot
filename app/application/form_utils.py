from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT


DEFAULT_FIELD_ALIASES = {
    "first_name": ("First name", "Given name"),
    "last_name": ("Last name", "Family name", "Surname"),
    "full_name": ("Full name", "Legal name", "Your name", "Name"),
    "email": ("Email", "Email address"),
    "phone": ("Phone", "Phone number", "Mobile phone"),
    "location": ("Location", "Current location", "City"),
    "linkedin": ("LinkedIn", "LinkedIn profile", "LinkedIn URL"),
    "github": ("GitHub", "GitHub profile", "GitHub URL"),
    "portfolio": ("Portfolio", "Website", "Personal website"),
}

DEFAULT_FIELD_SELECTORS = {
    "first_name": (
        "input[name='first_name']",
        "input[name='job_application[first_name]']",
        "input[id='first_name']",
        "input[autocomplete='given-name']",
    ),
    "last_name": (
        "input[name='last_name']",
        "input[name='job_application[last_name]']",
        "input[id='last_name']",
        "input[autocomplete='family-name']",
    ),
    "full_name": (
        "input[name='name']",
        "input[name='job_application[name]']",
        "input[name='_systemfield_name']",
        "input[id='name']",
        "input[autocomplete='name']",
    ),
    "email": (
        "input[type='email']",
        "input[name='email']",
        "input[name='job_application[email]']",
        "input[name='_systemfield_email']",
        "input[id='email']",
        "input[autocomplete='email']",
    ),
    "phone": (
        "input[type='tel']",
        "input[name='phone']",
        "input[name='job_application[phone]']",
        "input[name='_systemfield_phone']",
        "input[id='phone']",
        "input[autocomplete='tel']",
    ),
    "location": (
        "input[name='location']",
        "input[name='job_application[location]']",
        "input[id='location']",
    ),
    "linkedin": (
        "input[name='linkedin']",
        "input[name='urls[LinkedIn]']",
        "input[name='job_application[answers_attributes][linkedin]']",
        "input[id*='linkedin' i]",
    ),
    "github": (
        "input[name='github']",
        "input[name='urls[GitHub]']",
        "input[id*='github' i]",
    ),
    "portfolio": (
        "input[name='portfolio']",
        "input[name='website']",
        "input[name='urls[Portfolio]']",
        "input[id*='portfolio' i]",
        "input[id*='website' i]",
    ),
}

KNOWN_CONTROL_MARKERS = (
    "first",
    "given",
    "last",
    "family",
    "surname",
    "full name",
    "legal name",
    "name",
    "email",
    "phone",
    "mobile",
    "location",
    "city",
    "country",
    "linkedin",
    "github",
    "portfolio",
    "website",
    "resume",
    "cv",
    "curriculum",
    "upload",
)

SENSITIVE_CONTROL_MARKERS = (
    "salary",
    "compensation",
    "work authorization",
    "visa",
    "sponsorship",
    "race",
    "ethnicity",
    "gender",
    "disability",
    "veteran",
    "privacy",
    "terms",
    "consent",
)


def build_candidate_field_values(profile: dict[str, Any]) -> dict[str, str]:
    full_name = str(profile.get("name") or "").strip()
    parts = full_name.split()
    first_name = str(profile.get("first_name") or (parts[0] if parts else "")).strip()
    last_name = str(profile.get("last_name") or (" ".join(parts[1:]) if len(parts) > 1 else "")).strip()

    values = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": str(profile.get("email") or "").strip(),
        "phone": str(profile.get("phone") or "").strip(),
        "location": str(profile.get("location") or "").strip(),
        "linkedin": str(profile.get("linkedin") or "").strip(),
        "github": str(profile.get("github") or "").strip(),
        "portfolio": str(profile.get("portfolio") or "").strip(),
    }
    return {key: value for key, value in values.items() if value}


def merge_selector_maps(*maps: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {}
    for selector_map in maps:
        for field, selectors in selector_map.items():
            merged.setdefault(field, [])
            merged[field].extend(selectors)
    return {field: tuple(dict.fromkeys(selectors)) for field, selectors in merged.items()}


def fill_known_text_fields(
    page,
    profile: dict[str, Any],
    selector_map: dict[str, tuple[str, ...]] | None = None,
    alias_map: dict[str, tuple[str, ...]] | None = None,
    timeout_ms: int = 1200,
) -> dict[str, Any]:
    values = build_candidate_field_values(profile)
    selectors = merge_selector_maps(DEFAULT_FIELD_SELECTORS, selector_map or {})
    aliases = merge_selector_maps(DEFAULT_FIELD_ALIASES, alias_map or {})
    filled: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for field, value in values.items():
        if _fill_by_selectors(page, selectors.get(field, ()), value, timeout_ms):
            filled.append({"field": field, "method": "selector"})
            continue
        if _fill_by_labels(page, aliases.get(field, ()), value, timeout_ms):
            filled.append({"field": field, "method": "label"})
            continue
        skipped.append({"field": field, "reason": "no matching visible field"})

    return {
        "filled_fields": filled,
        "skipped_fields": skipped,
        "filled_count": len(filled),
    }


def upload_resume(page, profile: dict[str, Any], timeout_ms: int = 1200) -> dict[str, Any]:
    cv_path = _resolve_cv_path(profile.get("cv_path"))
    if not cv_path:
        return {"uploaded": False, "reason": "cv_path is not configured"}
    if not cv_path.exists():
        return {"uploaded": False, "reason": f"cv_path does not exist: {cv_path}"}

    file_inputs = page.locator("input[type='file']")
    try:
        count = file_inputs.count()
    except Exception as exc:
        return {"uploaded": False, "reason": f"file input lookup failed: {exc}"}

    fallback_index: int | None = None
    for index in range(count):
        locator = file_inputs.nth(index)
        descriptor = _safe_locator_descriptor(locator, timeout_ms)
        if fallback_index is None:
            fallback_index = index
        if _descriptor_contains(descriptor, ("resume", "cv", "curriculum", "upload")):
            try:
                locator.set_input_files(str(cv_path), timeout=timeout_ms)
                return {"uploaded": True, "field": descriptor or f"file_input_{index}"}
            except Exception as exc:
                return {"uploaded": False, "reason": f"resume upload failed: {exc}"}

    if fallback_index is not None:
        try:
            file_inputs.nth(fallback_index).set_input_files(str(cv_path), timeout=timeout_ms)
            return {"uploaded": True, "field": f"file_input_{fallback_index}"}
        except Exception as exc:
            return {"uploaded": False, "reason": f"fallback resume upload failed: {exc}"}

    return {"uploaded": False, "reason": "no file input found"}


def collect_required_controls(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('input, textarea, select')).map((el) => {
            const id = el.getAttribute('id') || '';
            const name = el.getAttribute('name') || '';
            const type = (el.getAttribute('type') || el.tagName || '').toLowerCase();
            const labelNode = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const parentLabel = el.closest('label');
            const label = (labelNode?.innerText || parentLabel?.innerText || '').trim();
            const describedBy = el.getAttribute('aria-describedby') || '';
            const placeholder = el.getAttribute('placeholder') || '';
            const ariaLabel = el.getAttribute('aria-label') || '';
            const required = el.required || el.getAttribute('aria-required') === 'true';
            const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
            const value = type === 'file' ? '' : (el.value || '');
            const filesCount = type === 'file' ? (el.files ? el.files.length : 0) : 0;
            const checked = type === 'checkbox' || type === 'radio' ? el.checked : null;
            return {
                tag: el.tagName.toLowerCase(),
                id,
                name,
                type,
                label,
                described_by: describedBy,
                placeholder,
                aria_label: ariaLabel,
                required,
                visible,
                disabled,
                value,
                files_count: filesCount,
                checked
            };
        })
        """
    )


def summarize_required_controls(controls: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[dict[str, Any]] = []
    missing_known: list[dict[str, Any]] = []
    unknown_required: list[dict[str, Any]] = []
    sensitive_required: list[dict[str, Any]] = []

    for control in controls:
        if not control.get("required") or not control.get("visible") or control.get("disabled"):
            continue
        if not _control_is_empty(control):
            continue

        summary = _control_summary(control)
        missing.append(summary)
        if is_sensitive_control(control):
            sensitive_required.append(summary)
        elif is_known_candidate_control(control):
            missing_known.append(summary)
        else:
            unknown_required.append(summary)

    return {
        "valid": not unknown_required and not sensitive_required and not missing_known,
        "missing_required_fields": missing,
        "blocking_required_fields": len(missing),
        "missing_known_fields": missing_known,
        "unknown_required_fields": len(unknown_required) + len(sensitive_required),
        "unknown_required_field_details": unknown_required,
        "sensitive_required_field_details": sensitive_required,
    }


def validate_required_controls(page) -> dict[str, Any]:
    return summarize_required_controls(collect_required_controls(page))


def is_known_candidate_control(control: dict[str, Any]) -> bool:
    descriptor = control_descriptor(control)
    return _descriptor_contains(descriptor, KNOWN_CONTROL_MARKERS)


def is_sensitive_control(control: dict[str, Any]) -> bool:
    descriptor = control_descriptor(control)
    return _descriptor_contains(descriptor, SENSITIVE_CONTROL_MARKERS)


def control_descriptor(control: dict[str, Any]) -> str:
    return " ".join(
        str(control.get(key) or "")
        for key in ("label", "aria_label", "placeholder", "name", "id", "described_by", "type")
    ).strip().lower()


def _fill_by_selectors(page, selectors: tuple[str, ...], value: str, timeout_ms: int) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if _fill_locator(locator, value, timeout_ms):
                return True
        except Exception:
            continue
    return False


def _fill_by_labels(page, labels: tuple[str, ...], value: str, timeout_ms: int) -> bool:
    for label in labels:
        try:
            locator = page.get_by_label(label, exact=True)
            if _fill_locator(locator, value, timeout_ms):
                return True
        except Exception:
            continue
    return False


def _fill_locator(locator, value: str, timeout_ms: int) -> bool:
    try:
        if locator.count() < 1:
            return False
        target = locator.first
        if callable(target):
            target = locator.first()
        try:
            existing = target.input_value(timeout=timeout_ms)
            if str(existing).strip():
                return True
        except Exception:
            pass
        target.fill(value, timeout=timeout_ms)
        return True
    except Exception:
        return False


def _resolve_cv_path(raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _safe_locator_descriptor(locator, timeout_ms: int) -> str:
    try:
        return str(
            locator.evaluate(
                """
                (el) => [
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('name') || '',
                    el.getAttribute('id') || '',
                    el.getAttribute('accept') || ''
                ].join(' ')
                """,
                timeout=timeout_ms,
            )
        ).lower()
    except Exception:
        return ""


def _control_is_empty(control: dict[str, Any]) -> bool:
    control_type = str(control.get("type") or "").lower()
    if control_type == "file":
        return int(control.get("files_count") or 0) == 0
    if control_type in {"checkbox", "radio"}:
        return not bool(control.get("checked"))
    return not str(control.get("value") or "").strip()


def _control_summary(control: dict[str, Any]) -> dict[str, str]:
    return {
        "label": str(control.get("label") or control.get("aria_label") or ""),
        "name": str(control.get("name") or ""),
        "id": str(control.get("id") or ""),
        "type": str(control.get("type") or ""),
        "placeholder": str(control.get("placeholder") or ""),
    }


def _descriptor_contains(descriptor: str, markers: tuple[str, ...]) -> bool:
    lowered = descriptor.lower()
    return any(marker in lowered for marker in markers)
