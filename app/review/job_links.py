from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.extraction.link_extractor import canonical_job_url
from app.storage.db import Database


@dataclass(frozen=True)
class JobLinkExportResult:
    path: Path
    total_links: int


def export_job_links(db: Database, output_path: Path, status: str | None = None) -> JobLinkExportResult:
    rows = db.list_jobs(status=status)
    links = _collect_job_links(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_job_links_text(links, status=status), encoding="utf-8")
    return JobLinkExportResult(path=output_path, total_links=len(links))


def _collect_job_links(rows) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        for link in _links_from_job_row(row):
            key = canonical_job_url(link)
            if not key or key in seen:
                continue
            seen.add(key)
            collected.append(
                {
                    "title": row["title"] or "unknown",
                    "company": row["company"] or "unknown",
                    "status": row["eligibility_status"] or "unknown",
                    "url": link,
                }
            )
    return collected


def _links_from_job_row(row) -> list[str]:
    links: list[str] = []
    if row["application_url"]:
        links.append(str(row["application_url"]))
    raw_json = row["raw_json"] or "{}"
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        raw = {}
    if isinstance(raw, dict):
        for link in raw.get("application_links") or []:
            if link:
                links.append(str(link))
    return links


def _format_job_links_text(links: list[dict[str, str]], status: str | None = None) -> str:
    header = "Links de vagas"
    if status:
        header += f" - status: {status}"
    lines = [
        header,
        f"Total: {len(links)}",
        "",
    ]
    if not links:
        lines.append("Nenhum link de vaga encontrado.")
        return "\n".join(lines) + "\n"

    for index, item in enumerate(links, start=1):
        lines.extend(
            [
                f"{index}. {item['title']} | {item['company']} | {item['status']}",
                item["url"],
                "",
            ]
        )
    return "\n".join(lines)
