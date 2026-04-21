from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.application.autofill import select_adapter
from app.application.profile import load_candidate_profile
from app.application.submit_policy import evaluate_submit_policy
from app.browser.session import persistent_chromium_context
from app.config import DATA_DIR
from app.extraction.link_extractor import is_placeholder_url
from app.resume.tailoring import maybe_tailor_resume_for_job
from app.runtime_control import RunInterrupted, checkpoint
from app.storage.db import Database
from app.storage.models import Application, ApplicationEvent


@dataclass(frozen=True)
class ApplyRunOptions:
    mode: str
    headless: bool = False
    limit: int | None = None
    profile_path: Path | None = None
    snapshot_dir: Path = DATA_DIR / "runtime" / "snapshots"
    browser: str = "chrome"
    cdp_url: str = "http://127.0.0.1:9222"


def run_apply(db: Database, options: ApplyRunOptions) -> list[dict[str, Any]]:
    ready_jobs = db.list_jobs(status="ready_to_apply")
    if options.limit is not None:
        ready_jobs = ready_jobs[: options.limit]

    if not ready_jobs:
        return []

    results: list[dict[str, Any]] = []
    if options.mode == "dry_run":
        for row in ready_jobs:
            checkpoint()
            if is_placeholder_url(row["application_url"]):
                results.append(_placeholder_result(row))
                continue
            decision = evaluate_submit_policy(
                mode=options.mode,
                eligibility_status=row["eligibility_status"],
                confidence=float(row["confidence"]),
                ats_type=row["ats_type"],
            )
            results.append(_result_from_decision(row, decision, status="dry_run"))
        return results

    profile = load_candidate_profile(options.profile_path) if options.profile_path else load_candidate_profile()
    options.snapshot_dir.mkdir(parents=True, exist_ok=True)

    with persistent_chromium_context(
        headless=options.headless,
        browser=options.browser,
        cdp_url=options.cdp_url,
    ) as context:
        page = context.new_page()
        for row in ready_jobs:
            checkpoint()
            results.append(_apply_single_job(db, page, row, profile, options))
    return results


def _apply_single_job(db: Database, page, row, profile: dict[str, Any], options: ApplyRunOptions) -> dict[str, Any]:
    checkpoint()
    url = row["application_url"]
    if not url:
        return _record_blocked(db, row, options.mode, "missing application_url")
    if is_placeholder_url(url):
        return _record_blocked(db, row, options.mode, "demo/placeholder application URL blocked")

    initial_decision = evaluate_submit_policy(
        mode=options.mode,
        eligibility_status=row["eligibility_status"],
        confidence=float(row["confidence"]),
        ats_type=row["ats_type"],
    )
    if not initial_decision.can_fill:
        return _record_blocked(db, row, options.mode, initial_decision.reason)

    try:
        checkpoint()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        html = page.content()
        adapter = select_adapter(url, html)
        if not adapter:
            return _record_blocked(db, row, options.mode, "no matching adapter")

        checkpoint()
        job_description = _read_body_text(page)
        tailor_result = maybe_tailor_resume_for_job(
            profile=profile,
            job=row,
            job_description=job_description,
        )
        profile_for_fill = dict(profile)
        if tailor_result.upload_path:
            profile_for_fill["cv_path"] = tailor_result.upload_path

        checkpoint()
        fill_result = adapter.fill_form(page, profile_for_fill)
        validation = adapter.validate_before_submit(page)
        snapshot_path = _write_snapshot(options.snapshot_dir, row["id"], page.content())

        final_decision = evaluate_submit_policy(
            mode=options.mode,
            eligibility_status=row["eligibility_status"],
            confidence=float(row["confidence"]),
            ats_type=adapter.name,
            unknown_required_fields=int(validation.get("blocking_required_fields") or 0),
        )

        status = "filled" if fill_result.get("filled") and validation.get("valid") else "needs_review"
        if not final_decision.can_submit:
            submit_result = {
                "submitted": False,
                "reason": final_decision.reason,
            }
        else:
            submit_result = {
                "submitted": False,
                "reason": "submit intentionally disabled in this implementation step",
            }

        payload = {
            "url": url,
            "adapter": adapter.name,
            "tailored_resume": tailor_result.to_dict(),
            "fill_result": fill_result,
            "validation": validation,
            "submit_decision": {
                "can_fill": final_decision.can_fill,
                "can_submit": final_decision.can_submit,
                "reason": final_decision.reason,
            },
            "submit_result": submit_result,
            "snapshot_path": str(snapshot_path),
        }
        _record_application(db, row["id"], options.mode, status, str(snapshot_path), None)
        _record_event(db, row["id"], "apply_fill_attempt", payload)
        return {
            "job_id": row["id"],
            "title": row["title"],
            "status": status,
            "adapter": adapter.name,
            "filled": bool(fill_result.get("filled")),
            "valid": bool(validation.get("valid")),
            "can_submit": False,
            "reason": submit_result["reason"],
            "snapshot_path": str(snapshot_path),
            "tailored_resume_path": tailor_result.markdown_path,
        }
    except RunInterrupted:
        raise
    except Exception as exc:
        return _record_blocked(db, row, options.mode, str(exc), status="failed")


def _write_snapshot(snapshot_dir: Path, job_id: str, html: str) -> Path:
    path = snapshot_dir / f"{job_id}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _record_blocked(
    db: Database,
    row,
    mode: str,
    reason: str,
    status: str = "blocked",
) -> dict[str, Any]:
    _record_application(db, row["id"], mode, status, None, reason)
    _record_event(db, row["id"], "apply_blocked", {"reason": reason, "mode": mode})
    return {
        "job_id": row["id"],
        "title": row["title"],
        "status": status,
        "adapter": row["ats_type"],
        "filled": False,
        "valid": False,
        "can_submit": False,
        "reason": reason,
        "snapshot_path": None,
        "tailored_resume_path": None,
    }


def _record_application(
    db: Database,
    job_id: str,
    mode: str,
    status: str,
    snapshot_path: str | None,
    error: str | None,
) -> None:
    db.insert_application(
        Application(
            id=uuid.uuid4().hex,
            job_id=job_id,
            status=status,
            mode=mode,
            form_snapshot_path=snapshot_path,
            error=error,
        )
    )


def _record_event(db: Database, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    db.insert_event(
        ApplicationEvent(
            id=uuid.uuid4().hex,
            job_id=job_id,
            event_type=event_type,
            payload=payload,
        )
    )


def _result_from_decision(row, decision, status: str) -> dict[str, Any]:
    return {
        "job_id": row["id"],
        "title": row["title"],
        "status": status,
        "adapter": row["ats_type"],
        "filled": decision.can_fill,
        "valid": False,
        "can_submit": decision.can_submit,
        "reason": decision.reason,
        "snapshot_path": None,
        "tailored_resume_path": None,
    }


def _placeholder_result(row) -> dict[str, Any]:
    return {
        "job_id": row["id"],
        "title": row["title"],
        "status": "blocked",
        "adapter": row["ats_type"],
        "filled": False,
        "valid": False,
        "can_submit": False,
        "reason": "demo/placeholder application URL blocked",
        "snapshot_path": None,
        "tailored_resume_path": None,
    }


def _read_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return ""
