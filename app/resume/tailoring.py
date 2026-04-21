from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, PROJECT_ROOT
from app.resume.inventory import ExperienceInventoryError, has_real_experience, load_experience_inventory


DEFAULT_TAILORED_RESUME_DIR = DATA_DIR / "runtime" / "resumes"
STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "based",
    "but",
    "for",
    "from",
    "has",
    "have",
    "hiring",
    "into",
    "job",
    "our",
    "role",
    "the",
    "this",
    "with",
    "within",
    "work",
    "you",
    "your",
}


@dataclass(frozen=True)
class EvidenceItem:
    source_type: str
    source_id: str
    title: str
    text: str
    matched_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TailoredResumeResult:
    enabled: bool
    grounded: bool
    markdown_path: str | None
    html_path: str | None
    evidence_path: str | None
    upload_path: str | None
    selected_keywords: list[str]
    evidence_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def maybe_tailor_resume_for_job(
    profile: dict[str, Any],
    job: Any,
    job_description: str = "",
    output_dir: Path = DEFAULT_TAILORED_RESUME_DIR,
) -> TailoredResumeResult:
    settings = profile.get("resume_tailoring") or {}
    if not settings.get("enabled", False):
        return TailoredResumeResult(
            enabled=False,
            grounded=False,
            markdown_path=None,
            html_path=None,
            evidence_path=None,
            upload_path=None,
            selected_keywords=[],
            evidence_count=0,
            warnings=["resume tailoring disabled"],
        )

    inventory_path = resolve_project_path(
        settings.get("experience_inventory_path") or "data/experience_inventory.yaml"
    )
    try:
        inventory = load_experience_inventory(inventory_path)
    except (ExperienceInventoryError, FileNotFoundError) as exc:
        return TailoredResumeResult(
            enabled=True,
            grounded=False,
            markdown_path=None,
            html_path=None,
            evidence_path=None,
            upload_path=None,
            selected_keywords=[],
            evidence_count=0,
            warnings=[f"experience inventory unavailable: {exc}"],
        )

    if not has_real_experience(inventory):
        return TailoredResumeResult(
            enabled=True,
            grounded=False,
            markdown_path=None,
            html_path=None,
            evidence_path=None,
            upload_path=None,
            selected_keywords=[],
            evidence_count=0,
            warnings=["experience inventory has no real experiences or projects"],
        )

    minimum_evidence = int(settings.get("minimum_matched_evidence") or 2)
    return tailor_resume_for_job(
        profile=profile,
        inventory=inventory,
        job=job,
        job_description=job_description,
        output_dir=resolve_project_path(settings.get("output_dir") or output_dir),
        minimum_evidence=minimum_evidence,
        use_tailored_resume_for_upload=bool(settings.get("use_tailored_resume_for_upload", False)),
    )


def tailor_resume_for_job(
    profile: dict[str, Any],
    inventory: dict[str, Any],
    job: Any,
    job_description: str,
    output_dir: Path,
    minimum_evidence: int = 2,
    use_tailored_resume_for_upload: bool = False,
) -> TailoredResumeResult:
    job_data = row_to_dict(job)
    job_text = build_job_text(job_data, job_description)
    selected_keywords = select_keywords(inventory, job_text)
    evidence = select_evidence(inventory, selected_keywords, job_text)

    if len(evidence) < minimum_evidence:
        return TailoredResumeResult(
            enabled=True,
            grounded=False,
            markdown_path=None,
            html_path=None,
            evidence_path=None,
            upload_path=None,
            selected_keywords=selected_keywords,
            evidence_count=len(evidence),
            warnings=[
                "not enough matched evidence to generate a grounded tailored resume",
            ],
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    basename = build_resume_basename(job_data)
    markdown_path = output_dir / f"{basename}.md"
    html_path = output_dir / f"{basename}.html"
    evidence_path = output_dir / f"{basename}.evidence.json"

    markdown = render_markdown_resume(profile, inventory, job_data, selected_keywords, evidence)
    html_text = render_html_resume(markdown)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    evidence_path.write_text(
        json.dumps(
            {
                "job": job_data,
                "selected_keywords": selected_keywords,
                "evidence": [asdict(item) for item in evidence],
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    upload_path = str(markdown_path) if use_tailored_resume_for_upload else None
    return TailoredResumeResult(
        enabled=True,
        grounded=True,
        markdown_path=str(markdown_path),
        html_path=str(html_path),
        evidence_path=str(evidence_path),
        upload_path=upload_path,
        selected_keywords=selected_keywords,
        evidence_count=len(evidence),
        warnings=[] if use_tailored_resume_for_upload else ["tailored resume generated but base cv upload remains active"],
    )


def build_job_text(job_data: dict[str, Any], job_description: str) -> str:
    raw = job_data.get("raw_json") or job_data.get("raw") or ""
    return "\n".join(
        str(value or "")
        for value in (
            job_data.get("title"),
            job_data.get("company"),
            job_data.get("location"),
            job_data.get("remote_type"),
            raw,
            job_description,
        )
    )


def select_keywords(inventory: dict[str, Any], job_text: str, limit: int = 16) -> list[str]:
    normalized_job = normalize_text(job_text)
    candidate_keywords = inventory_keywords(inventory)
    matched = []
    for keyword in candidate_keywords:
        if keyword and re.search(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)", normalized_job):
            matched.append(keyword)

    if matched:
        return matched[:limit]

    tokens = [
        token
        for token in re.findall(r"[a-z][a-z0-9+#.-]{2,}", normalized_job)
        if token not in STOPWORDS
    ]
    return list(dict.fromkeys(tokens))[:limit]


def inventory_keywords(inventory: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    for item in inventory.get("skills") or []:
        if isinstance(item, str):
            keywords.append(item)
        elif isinstance(item, dict):
            for value in (item.get("name"), item.get("label")):
                if value:
                    keywords.append(str(value))
            keywords.extend(str(alias) for alias in item.get("aliases") or [])

    for record in all_records(inventory):
        keywords.extend(str(skill) for skill in record.get("skills") or [])
        for bullet in normalized_bullets(record):
            keywords.extend(str(skill) for skill in bullet.get("skills") or [])

    return list(dict.fromkeys(keyword.strip().lower() for keyword in keywords if str(keyword).strip()))


def select_evidence(
    inventory: dict[str, Any],
    selected_keywords: list[str],
    job_text: str,
    max_items: int = 12,
) -> list[EvidenceItem]:
    scored: list[tuple[int, EvidenceItem]] = []
    normalized_job = normalize_text(job_text)
    for record in all_records(inventory):
        source_type = str(record.get("_source_type") or "experience")
        source_id = str(record.get("id") or record.get("company") or record.get("name") or source_type)
        title = record_title(record)
        record_skills = set(str(skill).lower() for skill in record.get("skills") or [])

        for index, bullet in enumerate(normalized_bullets(record)):
            text = str(bullet.get("text") or "").strip()
            if not text:
                continue
            bullet_skills = record_skills | set(str(skill).lower() for skill in bullet.get("skills") or [])
            matched = sorted(
                keyword
                for keyword in selected_keywords
                if keyword in normalize_text(text) or keyword in bullet_skills
            )
            lexical_score = sum(1 for token in tokenize(text) if token in normalized_job)
            score = len(matched) * 5 + min(lexical_score, 5)
            if score <= 0:
                continue
            evidence_id = str(bullet.get("id") or f"{source_id}:bullet:{index + 1}")
            scored.append(
                (
                    score,
                    EvidenceItem(
                        source_type=source_type,
                        source_id=evidence_id,
                        title=title,
                        text=text,
                        matched_keywords=matched,
                    ),
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    evidence = [item for _, item in scored[:max_items]]
    return dedupe_evidence(evidence)


def render_markdown_resume(
    profile: dict[str, Any],
    inventory: dict[str, Any],
    job_data: dict[str, Any],
    selected_keywords: list[str],
    evidence: list[EvidenceItem],
) -> str:
    basics = inventory.get("basics") or {}
    lines = [
        f"# {profile.get('name', '').strip()}",
        "",
        contact_line(profile),
        "",
    ]

    headline = str(basics.get("headline") or profile.get("headline") or "").strip()
    if headline:
        lines.extend([f"## {headline}", ""])

    summary = str(basics.get("summary") or "").strip()
    if summary:
        lines.extend(["## Summary", summary, ""])

    if selected_keywords:
        lines.extend(
            [
                "## Targeted Skills",
                ", ".join(keyword.upper() if len(keyword) <= 3 else keyword.title() for keyword in selected_keywords[:12]),
                "",
            ]
        )

    grouped = group_evidence_by_title(evidence)
    lines.append("## Relevant Experience")
    for title, items in grouped.items():
        lines.extend([f"### {title}", ""])
        for item in items[:5]:
            lines.append(f"- {item.text}")
        lines.append("")

    education = inventory.get("education") or []
    if education:
        lines.extend(["## Education", ""])
        for item in education:
            if isinstance(item, str):
                lines.append(f"- {item}")
            elif isinstance(item, dict):
                lines.append(f"- {' - '.join(str(value) for value in item.values() if value)}")
        lines.append("")

    certifications = inventory.get("certifications") or []
    if certifications:
        lines.extend(["## Certifications", ""])
        for item in certifications:
            lines.append(f"- {item if isinstance(item, str) else item.get('name', '')}")
        lines.append("")

    lines.extend(
        [
            "<!-- Tailored for local review. Claims are copied from experience_inventory.yaml. -->",
            f"<!-- Target job: {job_data.get('title') or 'unknown'} at {job_data.get('company') or 'unknown'} -->",
        ]
    )
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def render_html_resume(markdown: str) -> str:
    body_lines: list[str] = []
    in_list = False
    for line in markdown.splitlines():
        if line.startswith("<!--"):
            continue
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.strip():
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        body_lines.append("</ul>")

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Tailored Resume</title>
  <style>
    body { font-family: Arial, sans-serif; color: #111; line-height: 1.35; max-width: 860px; margin: 32px auto; }
    h1 { font-size: 28px; margin-bottom: 6px; }
    h2 { font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 24px; }
    h3 { font-size: 15px; margin-bottom: 4px; }
    p, li { font-size: 12px; }
  </style>
</head>
<body>
""" + "\n".join(body_lines) + "\n</body>\n</html>\n"


def all_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_type in ("experiences", "projects"):
        singular = "experience" if source_type == "experiences" else "project"
        for record in inventory.get(source_type) or []:
            if isinstance(record, dict):
                copy = dict(record)
                copy["_source_type"] = singular
                records.append(copy)
    return records


def normalized_bullets(record: dict[str, Any]) -> list[dict[str, Any]]:
    bullets = []
    for bullet in record.get("bullets") or []:
        if isinstance(bullet, str):
            bullets.append({"text": bullet})
        elif isinstance(bullet, dict):
            bullets.append(bullet)
    return bullets


def record_title(record: dict[str, Any]) -> str:
    company = record.get("company") or record.get("name")
    title = record.get("title") or record.get("role")
    start = record.get("start")
    end = record.get("end")
    date_range = " - ".join(str(value) for value in (start, end) if value)
    parts = [str(value) for value in (title, company, date_range) if value]
    return " | ".join(parts) if parts else "Experience"


def group_evidence_by_title(evidence: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        grouped.setdefault(item.title, []).append(item)
    return grouped


def contact_line(profile: dict[str, Any]) -> str:
    values = [
        profile.get("email"),
        profile.get("phone"),
        profile.get("location"),
        profile.get("linkedin"),
        profile.get("github"),
        profile.get("portfolio"),
    ]
    return " | ".join(str(value).strip() for value in values if value)


def build_resume_basename(job_data: dict[str, Any]) -> str:
    seed = "-".join(
        str(value or "")
        for value in (job_data.get("id"), job_data.get("company"), job_data.get("title"))
    )
    slug = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
    return slug[:96] or "tailored-resume"


def row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9+#.-]{2,}", normalize_text(text))
        if token not in STOPWORDS
    }


def normalize_text(text: str) -> str:
    return str(text or "").lower()


def dedupe_evidence(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[str] = set()
    unique: list[EvidenceItem] = []
    for item in evidence:
        key = item.text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolve_project_path(path: Any) -> Path:
    resolved = Path(str(path)).expanduser()
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved

