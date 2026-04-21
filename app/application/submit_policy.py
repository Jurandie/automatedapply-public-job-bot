from __future__ import annotations

from dataclasses import dataclass


ALLOWED_MODES = {"dry_run", "fill_only", "review_first", "auto_submit_safe"}


@dataclass(frozen=True)
class SubmitDecision:
    can_fill: bool
    can_submit: bool
    reason: str


def evaluate_submit_policy(
    mode: str,
    eligibility_status: str,
    confidence: float,
    ats_type: str | None,
    unknown_required_fields: int = 0,
) -> SubmitDecision:
    if mode not in ALLOWED_MODES:
        raise ValueError(f"Modo invalido: {mode}")

    if mode == "dry_run":
        return SubmitDecision(False, False, "dry_run never fills or submits")

    if eligibility_status != "ready_to_apply":
        return SubmitDecision(False, False, "job is not ready_to_apply")

    if unknown_required_fields:
        return SubmitDecision(False, False, "unfilled required fields block automation")

    if mode == "fill_only":
        return SubmitDecision(True, False, "fill_only blocks submit")

    if mode == "review_first":
        return SubmitDecision(True, False, "human review required before submit")

    safe_ats = {"greenhouse", "lever", "ashby"}
    if ats_type not in safe_ats:
        return SubmitDecision(True, False, "ATS is not in safe submit allowlist")
    if confidence < 0.9:
        return SubmitDecision(True, False, "confidence below auto_submit_safe threshold")

    return SubmitDecision(True, True, "safe auto-submit allowed")
