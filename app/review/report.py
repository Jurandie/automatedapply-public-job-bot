from __future__ import annotations

from collections import Counter

from app.storage.db import Database


def build_job_summary(db: Database) -> dict:
    jobs = db.list_jobs()
    by_status = Counter(row["eligibility_status"] for row in jobs)
    by_ats = Counter(row["ats_type"] or "unknown" for row in jobs)
    return {
        "total_jobs": len(jobs),
        "by_status": dict(by_status),
        "by_ats": dict(by_ats),
    }


def format_review_table(db: Database, status: str | None = None) -> str:
    rows = db.list_jobs(status=status)
    if not rows:
        return "Nenhuma vaga encontrada."

    lines = [
        "status | confidence | ats | title | company | url",
        "--- | ---: | --- | --- | --- | ---",
    ]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    row["eligibility_status"],
                    f"{row['confidence']:.2f}",
                    row["ats_type"] or "unknown",
                    row["title"] or "unknown",
                    row["company"] or "unknown",
                    row["application_url"] or "no link",
                ]
            )
        )
    return "\n".join(lines)

