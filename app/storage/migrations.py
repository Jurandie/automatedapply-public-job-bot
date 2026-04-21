from __future__ import annotations

from app.storage.db import Database


def migrate(db: Database | None = None) -> None:
    (db or Database()).init()

