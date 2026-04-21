from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse


URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,);]}\"'"
PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "example.invalid",
}
PLACEHOLDER_ATS_COMPANY_SLUGS = {"example", "sample", "demo", "test"}
TRACKING_QUERY_KEYS = {
    "_ga",
    "_gl",
    "fbclid",
    "gclid",
    "gh_src",
    "msclkid",
    "ref",
    "ref_src",
    "referer",
    "referrer",
    "referral",
    "source",
    "src",
    "trk",
}


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.links.append(html.unescape(href))


def normalize_url(url: str) -> str:
    cleaned = html.unescape(url).strip().rstrip(TRAILING_PUNCTUATION)
    if "linkedin.com/safety/go" in cleaned or "linkedin.com/redir/redirect" in cleaned:
        parsed = urlparse(cleaned)
        match = re.search(r"(?:url|target)=([^&]+)", parsed.query)
        if match:
            return unquote(match.group(1))
    return cleaned


def canonical_job_url(url: str | None) -> str:
    if not url:
        return ""

    cleaned = normalize_url(url)
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned.strip().rstrip("/#").lower()

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else parsed.netloc.lower()
    if parsed.port and not (
        (scheme == "http" and parsed.port == 80)
        or (scheme == "https" and parsed.port == 443)
    ):
        host = f"{host}:{parsed.port}"

    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered_key = key.lower()
        if lowered_key.startswith("utm_") or lowered_key in TRACKING_QUERY_KEYS:
            continue
        params.append((key, value))
    query = urlencode(sorted(params))

    return urlunparse((scheme, host, path, "", query, ""))


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.findall(text):
        normalized = normalize_url(match)
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def extract_html_links(html_text: str | None) -> list[str]:
    if not html_text:
        return []
    parser = _AnchorParser()
    parser.feed(html_text)
    links = [normalize_url(link) for link in parser.links]
    links.extend(extract_urls(html_text))

    seen: set[str] = set()
    unique: list[str] = []
    for link in links:
        if link.startswith("http") and link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def is_application_link(url: str) -> bool:
    if is_placeholder_url(url):
        return False

    lowered = url.lower()
    markers = (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workdayjobs.com",
        "smartrecruiters.com",
        "breezy.hr",
        "teamtailor.com",
        "workable.com",
        "personio.com",
        "recruitee.com",
        "comeet.com",
        "/careers",
        "/career",
        "/jobs",
        "/job/",
        "/positions",
        "/position/",
        "/openings",
        "/vacancies",
        "/vacancy/",
        "linkedin.com/jobs",
    )
    return any(marker in lowered for marker in markers)


def select_application_links(urls: list[str]) -> list[str]:
    return [url for url in urls if is_application_link(url)]


def is_placeholder_url(url: str | None) -> bool:
    if not url:
        return False

    parsed = urlparse(normalize_url(url).lower())
    host = parsed.netloc.removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in PLACEHOLDER_DOMAINS or host.endswith(".invalid"):
        return True

    known_ats_host = any(
        marker in host
        for marker in (
            "ashbyhq.com",
            "greenhouse.io",
            "lever.co",
            "workable.com",
            "personio.com",
            "recruitee.com",
            "comeet.com",
        )
    )
    return bool(known_ats_host and path_parts and path_parts[0] in PLACEHOLDER_ATS_COMPANY_SLUGS)
