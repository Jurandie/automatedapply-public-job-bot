from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.integrations.claude_cli import ClaudeCliError, classify_post_with_script


@dataclass(frozen=True)
class ClaudeClassification:
    data: dict[str, Any]
    used: bool
    error: str | None = None


def classify_ambiguous_post(post_text: str, enabled: bool = True) -> ClaudeClassification:
    if not enabled:
        return ClaudeClassification(data={}, used=False)
    try:
        return ClaudeClassification(data=classify_post_with_script(post_text), used=True)
    except ClaudeCliError as exc:
        return ClaudeClassification(data={}, used=True, error=str(exc))

