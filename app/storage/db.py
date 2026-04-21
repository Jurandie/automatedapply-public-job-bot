from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.config import DEFAULT_DB_PATH, ensure_runtime_dirs
from app.extraction.link_extractor import canonical_job_url
from app.storage.models import Application, ApplicationEvent, Job, LinkedInPost, utc_now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS linkedin_posts (
    id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    author TEXT,
    company TEXT,
    post_text TEXT NOT NULL,
    post_url TEXT,
    posted_at TEXT,
    collected_at TEXT NOT NULL,
    raw_html TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source_post_id TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    remote_type TEXT,
    currency TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    application_url TEXT,
    ats_type TEXT,
    eligibility_status TEXT NOT NULL,
    eligibility_reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_post_id, application_url)
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT,
    mode TEXT NOT NULL,
    form_snapshot_path TEXT,
    confirmation_number TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blacklist (
    id TEXT PRIMARY KEY,
    value TEXT NOT NULL UNIQUE,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claude_decisions (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    prompt_path TEXT,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        ensure_runtime_dirs()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.session() as conn:
            conn.executescript(SCHEMA)

    def upsert_post(self, post: LinkedInPost) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO linkedin_posts (
                    id, source_url, author, company, post_text, post_url,
                    posted_at, collected_at, raw_html, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_url = excluded.source_url,
                    author = excluded.author,
                    company = excluded.company,
                    post_text = excluded.post_text,
                    post_url = excluded.post_url,
                    posted_at = excluded.posted_at,
                    raw_html = excluded.raw_html,
                    status = excluded.status
                """,
                (
                    post.id,
                    post.source_url,
                    post.author,
                    post.company,
                    post.post_text,
                    post.post_url,
                    post.posted_at,
                    post.collected_at,
                    post.raw_html,
                    post.status,
                ),
            )

    def upsert_posts(self, posts: Iterable[LinkedInPost]) -> None:
        for post in posts:
            self.upsert_post(post)

    def upsert_job(self, job: Job) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, source_post_id, company, title, location, remote_type,
                    currency, salary_min, salary_max, application_url, ats_type,
                    eligibility_status, eligibility_reason, confidence, raw_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    company = excluded.company,
                    title = excluded.title,
                    location = excluded.location,
                    remote_type = excluded.remote_type,
                    currency = excluded.currency,
                    salary_min = excluded.salary_min,
                    salary_max = excluded.salary_max,
                    application_url = excluded.application_url,
                    ats_type = excluded.ats_type,
                    eligibility_status = excluded.eligibility_status,
                    eligibility_reason = excluded.eligibility_reason,
                    confidence = excluded.confidence,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    job.id,
                    job.source_post_id,
                    job.company,
                    job.title,
                    job.location,
                    job.remote_type,
                    job.currency,
                    job.salary_min,
                    job.salary_max,
                    job.application_url,
                    job.ats_type,
                    job.eligibility_status,
                    job.eligibility_reason,
                    job.confidence,
                    json.dumps(job.raw, ensure_ascii=True),
                    job.created_at,
                    utc_now_iso(),
                ),
            )

    def insert_event(self, event: ApplicationEvent) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO application_events (id, job_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.job_id,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=True),
                    event.created_at,
                ),
            )

    def insert_application(self, application: Application) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO applications (
                    id, job_id, status, submitted_at, mode, form_snapshot_path,
                    confirmation_number, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.id,
                    application.job_id,
                    application.status,
                    application.submitted_at,
                    application.mode,
                    application.form_snapshot_path,
                    application.confirmation_number,
                    application.error,
                    application.created_at,
                    application.updated_at,
                ),
            )

    def list_posts(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM linkedin_posts"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY collected_at DESC"
        with self.session() as conn:
            return list(conn.execute(sql, params))

    def list_jobs(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE eligibility_status = ?"
            params = (status,)
        sql += " ORDER BY created_at DESC"
        with self.session() as conn:
            return list(conn.execute(sql, params))

    def list_known_job_urls(self) -> set[str]:
        urls: set[str] = set()
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT post_url AS url FROM linkedin_posts WHERE post_url IS NOT NULL AND post_url != ''
                UNION
                SELECT application_url AS url FROM jobs WHERE application_url IS NOT NULL AND application_url != ''
                """
            )
            for row in rows:
                normalized = canonical_job_url(row["url"])
                if normalized:
                    urls.add(normalized)

            for row in conn.execute("SELECT raw_json FROM jobs WHERE raw_json IS NOT NULL AND raw_json != ''"):
                try:
                    raw = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict):
                    continue
                for link in raw.get("application_links") or []:
                    normalized = canonical_job_url(str(link))
                    if normalized:
                        urls.add(normalized)
        return urls

    def count(self, table: str) -> int:
        allowed = {
            "linkedin_posts",
            "jobs",
            "applications",
            "application_events",
            "companies",
            "blacklist",
            "claude_decisions",
        }
        if table not in allowed:
            raise ValueError(f"Tabela nao permitida: {table}")
        with self.session() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
            return int(row["total"])
