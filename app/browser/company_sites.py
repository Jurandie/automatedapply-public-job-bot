from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.browser.session import persistent_chromium_context
from app.config import DATA_DIR
from app.extraction.link_extractor import canonical_job_url, extract_html_links
from app.extraction.post_parser import ParsedPost, build_post_id
from app.reputation.glassdoor import GlassdoorRatingGate
from app.runtime_control import checkpoint


_MISSING = object()

TRANSIENT_PAGE_ERROR_MARKERS = (
    "execution context was destroyed",
    "most likely because of a navigation",
    "cannot find context with specified id",
    "target page, context or browser has been closed",
    "page.evaluate: execution context was destroyed",
)

TARGET_COUNTRY_TERMS = (
    "italy",
    "italia",
    "italian",
    "milan",
    "milano",
    "rome",
    "roma",
    "turin",
    "torino",
    "bologna",
    "ireland",
    "irish",
    "dublin",
    "cork",
    "galway",
    "limerick",
    "waterford",
)

JOB_TEXT_MARKERS = (
    "apply",
    "job",
    "career",
    "position",
    "opening",
    "vacancy",
    "engineer",
    "developer",
    "software",
    "backend",
    "python",
    "automation",
    "data",
)

JOB_URL_MARKERS = (
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
    "/careers/",
    "/career/",
    "/jobs/",
    "/job/",
    "/positions/",
    "/openings/",
    "/vacancies/",
)

IGNORED_URL_MARKERS = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com/",
    "youtube.com",
    "tiktok.com",
    "privacy",
    "terms",
    "cookie",
    "developers.",
    "/developers",
    "developer.",
    "docs.",
    "/docs",
    "api.",
    "/api/",
    "help.",
    "support.",
)

LISTING_PATH_SUFFIXES = (
    "/career",
    "/career/",
    "/careers",
    "/careers/",
    "/careers/listings",
    "/careers/listings/",
    "/jobs",
    "/jobs/",
    "/open-positions",
    "/open-positions/",
    "/positions",
    "/positions/",
    "/vacancies",
    "/vacancies/",
)


@dataclass(frozen=True)
class CompanyCareerSource:
    name: str
    careers_url: str
    country: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        country = f":{self.country}" if self.country else ""
        return f"company:{self.name}{country}"


class CompanySiteCollectionError(RuntimeError):
    """Raised when company career pages cannot be collected safely."""


class CompanyJobCollector:
    """Collects public job pages from configured company career sites."""

    def __init__(
        self,
        headless: bool = False,
        max_jobs_per_source: int = 50,
        diagnostic_dir: Path = DATA_DIR / "runtime" / "diagnostics",
        scroll_rounds: int = 4,
        browser: str = "chrome",
        cdp_url: str = "http://127.0.0.1:9222",
        rating_gate: GlassdoorRatingGate | None = None,
        known_job_urls: set[str] | None = None,
    ):
        self.headless = headless
        self.max_jobs_per_source = max_jobs_per_source
        self.diagnostic_dir = diagnostic_dir
        self.scroll_rounds = scroll_rounds
        self.browser = browser
        self.cdp_url = cdp_url
        self.rating_gate = rating_gate
        self.known_job_urls = _canonical_url_set(known_job_urls)

    def collect(self, sources: list[CompanyCareerSource]) -> list[ParsedPost]:
        jobs: list[ParsedPost] = []
        with persistent_chromium_context(
            headless=self.headless,
            browser=self.browser,
            cdp_url=self.cdp_url,
        ) as context:
            page = context.new_page()
            for source in sources:
                checkpoint()
                if self.rating_gate:
                    rating = self.rating_gate.check(source.name)
                    if not rating.allowed:
                        detail = rating.search_url or "sem link Glassdoor"
                        print(
                            f"Pulando {source.name}: {rating.reason}. "
                            f"Verifique no Glassdoor: {detail}"
                        )
                        continue
                    print(
                        f"Glassdoor OK: {source.name} rating={rating.rating} "
                        f"reviews={rating.review_count or 'unknown'}"
                    )
                print(f"Coletando site de empresa: {source.label} -> {source.careers_url}")
                jobs.extend(self._collect_source(page, source))
        return jobs

    def _collect_source(self, page, source: CompanyCareerSource) -> list[ParsedPost]:
        checkpoint()
        try:
            page.goto(source.careers_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            diagnostic = self._save_diagnostic(page, source, reason="source-load-failed")
            print(f"Falha ao abrir fonte {source.name}: {exc}. Diagnostico: {diagnostic}")
            return []

        self._wait_for_content(page)
        self._scroll_results(page)

        candidates = self._extract_candidate_links(page)
        if not candidates:
            diagnostic = self._save_diagnostic(page, source, reason="no-job-links-found")
            print(f"Nenhum link de vaga encontrado nessa fonte. Diagnostico salvo em: {diagnostic}")
            return []

        parsed: list[ParsedPost] = []
        queue = list(candidates)
        seen_urls: set[str] = set()
        expanded_listing_urls: set[str] = set()
        while queue and len(parsed) < self.max_jobs_per_source:
            checkpoint()
            candidate = queue.pop(0)
            if len(parsed) >= self.max_jobs_per_source:
                break
            url = str(candidate.get("url") or "").strip()
            url_key = canonical_job_url(url)
            if not url or not url_key or url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            if not _looks_like_job_url_or_text(url, str(candidate.get("text") or "")):
                continue

            if _looks_like_listing_url(url, str(candidate.get("text") or "")) and url_key not in expanded_listing_urls:
                expanded_listing_urls.add(url_key)
                nested = self._expand_listing_page(page, source, url)
                queue.extend(nested)
                continue

            if self._is_known_job_url(url):
                print(f"Pulando vaga ja consultada: {url}")
                continue

            job = self._collect_job_page(page, source, candidate)
            if job:
                parsed.append(job)

        print(f"Vagas coletadas nessa fonte: {len(parsed)}")
        return parsed

    def _expand_listing_page(self, page, source: CompanyCareerSource, url: str) -> list[dict[str, str]]:
        checkpoint()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            self._wait_for_content(page)
            self._scroll_results(page)
        except Exception as exc:
            print(f"Falha ao abrir listagem de vagas {url}: {exc}")
            return []

        nested = [
            candidate
            for candidate in self._extract_candidate_links(page)
            if not _looks_like_listing_url(
                str(candidate.get("url") or ""),
                str(candidate.get("text") or ""),
            )
        ]
        print(f"Listagem expandida para {source.name}: {len(nested)} links candidatos.")
        return nested

    def _collect_job_page(self, page, source: CompanyCareerSource, candidate: dict[str, Any]) -> ParsedPost | None:
        checkpoint()
        url = str(candidate.get("url") or "").strip()
        card_text = str(candidate.get("text") or "").strip()
        company = str(candidate.get("company") or source.name).strip() or source.name
        source_url = str(candidate.get("source_url") or source.careers_url).strip() or source.careers_url
        url_key = canonical_job_url(url)
        if self._is_known_job_url(url):
            print(f"Pulando vaga ja consultada: {url}")
            return None
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            self._wait_for_content(page)
        except Exception as exc:
            print(f"Falha ao abrir vaga candidata {url}: {exc}")
            return None

        detail = self._extract_page_detail(page)
        body_text = str(detail.get("body_text") or "").strip()
        title = str(detail.get("title") or "").strip()
        raw_html = str(detail.get("html") or "")
        page_links = [str(link) for link in detail.get("links", []) if link]
        links = [url]
        links.extend(page_links)
        links.extend(extract_html_links(raw_html))
        unique_links = list(dict.fromkeys(links))

        text = "\n".join(
            part
            for part in (
                "Fonte: site publico de carreiras de empresa de TI",
                f"Empresa: {company}",
                f"Titulo: {title}" if title else "",
                f"Card da vaga: {card_text}" if card_text else "",
                f"URL da vaga: {url}",
                body_text[:12_000],
            )
            if part
        )
        if not text.strip():
            return None

        post = ParsedPost(
            id=build_post_id(source_url, text, url),
            source_url=source_url,
            text=text,
            links=unique_links,
            author=company,
            company=company,
            post_url=url,
            raw_html=raw_html,
        )
        if url_key:
            self.known_job_urls.add(url_key)
        return post

    def _is_known_job_url(self, url: str) -> bool:
        url_key = canonical_job_url(url)
        return bool(url_key and url_key in self.known_job_urls)

    def _wait_for_content(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1_000)
        except Exception:
            pass

    def _scroll_results(self, page) -> None:
        for _ in range(self.scroll_rounds):
            checkpoint()
            try:
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(800)
            except Exception:
                continue

    def _extract_candidate_links(self, page) -> list[dict[str, str]]:
        limit = max(self.max_jobs_per_source * 4, 20)
        return safe_page_evaluate(
            page,
            """
            ({ limit, jobUrlMarkers, jobTextMarkers, ignoredUrlMarkers }) => {
              const anchors = Array.from(document.querySelectorAll('a[href]'));
              const seen = new Set();
              const results = [];

              function nearestText(anchor) {
                const card = anchor.closest(
                  'li, article, tr, section, [role="listitem"], [class*="job"], [class*="career"], [class*="position"], [data-testid*="job"]'
                );
                const text = ((card && card.innerText) || anchor.innerText || anchor.textContent || '').trim();
                return text.replace(/\\s+/g, ' ').slice(0, 1600);
              }

              for (const anchor of anchors) {
                const href = anchor.href || '';
                if (!href.startsWith('http') || seen.has(href)) continue;
                const text = nearestText(anchor);
                const haystack = `${href} ${text}`.toLowerCase();
                if (ignoredUrlMarkers.some((marker) => haystack.includes(marker))) continue;

                const looksLikeJob =
                  jobUrlMarkers.some((marker) => haystack.includes(marker)) ||
                  jobTextMarkers.some((marker) => haystack.includes(marker));

                if (!looksLikeJob) continue;
                seen.add(href);
                results.push({ url: href, text });
                if (results.length >= limit) break;
              }
              return results;
            }
            """,
            {
                "limit": limit,
                "jobUrlMarkers": JOB_URL_MARKERS,
                "jobTextMarkers": JOB_TEXT_MARKERS,
                "ignoredUrlMarkers": IGNORED_URL_MARKERS,
            },
            default=[],
            label="links candidatos",
        )

    def _extract_page_detail(self, page) -> dict[str, Any]:
        return safe_page_evaluate(
            page,
            """
            () => {
              const titleNode = document.querySelector(
                'h1, [data-testid*="title"], [class*="job-title"], [class*="position-title"]'
              );
              const metaTitle = document.querySelector('meta[property="og:title"], meta[name="title"]');
              const title = (
                (titleNode && titleNode.innerText) ||
                (metaTitle && metaTitle.getAttribute('content')) ||
                document.title ||
                ''
              ).trim();
              const bodyText = (document.body && document.body.innerText || '').replace(/\\s+\\n/g, '\\n').trim();
              const links = Array.from(document.querySelectorAll('a[href]'))
                .map((anchor) => anchor.href)
                .filter(Boolean);
              return {
                title,
                body_text: bodyText,
                html: document.documentElement.outerHTML || '',
                links
              };
            }
            """,
            default={},
            label="detalhes da vaga",
        )

    def _save_diagnostic(self, page, source: CompanyCareerSource, reason: str) -> Path:
        self.diagnostic_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_label = "".join(char if char.isalnum() else "-" for char in source.label)[:64]
        base = self.diagnostic_dir / f"{timestamp}-{reason}-{safe_label}"
        html_path = base.with_suffix(".html")
        txt_path = base.with_suffix(".txt")
        png_path = base.with_suffix(".png")
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        try:
            txt_path.write_text(page.locator("body").inner_text(timeout=2_000), encoding="utf-8")
        except Exception:
            pass
        try:
            page.screenshot(path=str(png_path), full_page=True, timeout=5_000)
        except Exception:
            pass
        return html_path


def _looks_like_job_url_or_text(url: str, text: str) -> bool:
    lowered = f"{url} {text}".lower()
    if any(marker in lowered for marker in IGNORED_URL_MARKERS):
        return False
    return any(marker in lowered for marker in JOB_URL_MARKERS) or any(
        marker in lowered for marker in JOB_TEXT_MARKERS
    )


def _looks_like_listing_url(url: str, text: str) -> bool:
    parsed = urlparse(url)
    lowered_url = parsed.path.lower().rstrip("/")
    lowered_text = text.lower()
    if any(lowered_url.endswith(suffix.rstrip("/")) for suffix in LISTING_PATH_SUFFIXES):
        return True
    listing_text_markers = (
        "view jobs",
        "view open roles",
        "see open roles",
        "open roles",
        "all jobs",
        "job openings",
        "current vacancies",
    )
    return any(marker in lowered_text for marker in listing_text_markers) and not any(
        role_marker in lowered_text
        for role_marker in ("engineer", "developer", "analyst", "designer", "manager", "specialist")
    )


def _canonical_url_set(urls: set[str] | None) -> set[str]:
    normalized: set[str] = set()
    for url in urls or set():
        url_key = canonical_job_url(url)
        if url_key:
            normalized.add(url_key)
    return normalized


def safe_page_evaluate(
    page,
    script: str,
    arg: Any = _MISSING,
    *,
    default: Any = None,
    label: str = "pagina",
    retries: int = 1,
) -> Any:
    for attempt in range(retries + 1):
        try:
            if arg is _MISSING:
                return page.evaluate(script)
            return page.evaluate(script, arg)
        except Exception as exc:
            if not _is_transient_page_error(exc):
                print(f"Falha ao extrair {label}: {exc}")
                return default
            if attempt < retries:
                _wait_after_transient_navigation(page)
                continue
            print(f"Navegacao interrompeu a extracao de {label}; pulando item atual.")
            return default
    return default


def _is_transient_page_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in TRANSIENT_PAGE_ERROR_MARKERS)


def _wait_after_transient_navigation(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5_000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(500)
    except Exception:
        pass
