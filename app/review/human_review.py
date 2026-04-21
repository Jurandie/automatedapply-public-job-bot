from __future__ import annotations

from app.review.report import format_review_table
from app.storage.db import Database


def print_review(db: Database, status: str | None = None) -> None:
    print(format_review_table(db, status=status))

