from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.extraction.link_extractor import extract_html_links, extract_urls
from app.storage.models import LinkedInPost


@dataclass(frozen=True)
class ParsedPost:
    id: str
    source_url: str
    text: str
    links: list[str]
    author: str | None = None
    company: str | None = None
    post_url: str | None = None
    posted_at: str | None = None
    raw_html: str | None = None

    def to_storage(self, status: str = "discovered") -> LinkedInPost:
        return LinkedInPost(
            id=self.id,
            source_url=self.source_url,
            author=self.author,
            company=self.company,
            post_text=self.text,
            post_url=self.post_url,
            posted_at=self.posted_at,
            raw_html=self.raw_html,
            status=status,
        )


def build_post_id(source_url: str, text: str, post_url: str | None = None) -> str:
    stable_value = post_url or f"{source_url}\n{text[:500]}"
    return hashlib.sha256(stable_value.encode("utf-8")).hexdigest()[:24]


def parse_post_payload(payload: dict[str, Any]) -> ParsedPost:
    text = str(payload.get("post_text") or payload.get("text") or "").strip()
    source_url = str(payload.get("source_url") or "manual").strip()
    raw_html = payload.get("raw_html")
    post_url = payload.get("post_url")
    links = []
    links.extend(extract_urls(text))
    links.extend(extract_html_links(raw_html))
    links.extend(str(link) for link in payload.get("links", []) if link)

    seen: set[str] = set()
    unique_links: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    return ParsedPost(
        id=str(payload.get("id") or build_post_id(source_url, text, post_url)),
        source_url=source_url,
        text=text,
        links=unique_links,
        author=payload.get("author"),
        company=payload.get("company"),
        post_url=post_url,
        posted_at=payload.get("posted_at"),
        raw_html=raw_html,
    )


def load_posts_json(path) -> list[ParsedPost]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        data = data.get("posts", [])
    if not isinstance(data, list):
        raise ValueError("Arquivo de posts precisa conter uma lista ou {'posts': [...]}.")
    return [parse_post_payload(item) for item in data]

