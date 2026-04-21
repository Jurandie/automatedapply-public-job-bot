from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from app.browser.session import persistent_chromium_context
from app.config import DATA_DIR
from app.extraction.link_extractor import extract_html_links, extract_urls
from app.extraction.post_parser import ParsedPost, build_post_id
from app.runtime_control import checkpoint


@dataclass(frozen=True)
class LinkedInSource:
    url: str
    label: str = "linkedin"
    kind: str = "url"
    query: str | None = None


class LinkedInCollectionError(RuntimeError):
    """Raised when LinkedIn cannot be collected safely."""


def build_linkedin_search_url(query: str) -> str:
    encoded = quote_plus(query)
    return (
        "https://www.linkedin.com/search/results/content/"
        f"?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER"
        "&sortBy=%22date_posted%22"
        "&datePosted=%22past-week%22"
    )


class LinkedInPostCollector:
    """Collects visible LinkedIn posts using the user's authenticated browser session."""

    def __init__(
        self,
        headless: bool = False,
        max_posts_per_source: int = 50,
        diagnostic_dir: Path = DATA_DIR / "runtime" / "diagnostics",
        scroll_rounds: int = 4,
        browser: str = "chrome",
        cdp_url: str = "http://127.0.0.1:9222",
    ):
        self.headless = headless
        self.max_posts_per_source = max_posts_per_source
        self.diagnostic_dir = diagnostic_dir
        self.scroll_rounds = scroll_rounds
        self.browser = browser
        self.cdp_url = cdp_url

    def collect(self, sources: list[LinkedInSource]) -> list[ParsedPost]:
        posts: list[ParsedPost] = []
        with persistent_chromium_context(
            headless=self.headless,
            browser=self.browser,
            cdp_url=self.cdp_url,
        ) as context:
            page = context.new_page()
            for source in sources:
                checkpoint()
                print(f"Coletando LinkedIn: {source.label} -> {source.url}")
                posts.extend(self._collect_source(page, source))
        return posts

    def _collect_source(self, page, source: LinkedInSource) -> list[ParsedPost]:
        checkpoint()
        page.goto(source.url, wait_until="domcontentloaded", timeout=60_000)
        self._wait_for_linkedin_content(page)
        if self._looks_logged_out(page):
            self._save_diagnostic(page, source, reason="login-required")
            raise LinkedInCollectionError(
                "LinkedIn parece estar deslogado ou bloqueou a sessao. "
                "Rode o scan sem headless, faca login manualmente na janela do Chromium "
                "e execute o scan novamente."
            )

        self._try_expand_visible_posts(page)
        self._scroll_results(page)

        candidates = self._extract_candidate_posts(page)
        parsed: list[ParsedPost] = []
        for candidate in candidates[: self.max_posts_per_source]:
            checkpoint()
            text = candidate["text"].strip()
            if not text:
                continue
            raw_html = candidate.get("html") or ""
            post_url = self._extract_post_url(raw_html)
            links = extract_urls(text)
            links.extend(extract_html_links(raw_html))
            parsed.append(
                ParsedPost(
                    id=build_post_id(source.url, text, post_url),
                    source_url=source.url,
                    text=text,
                    links=list(dict.fromkeys(links)),
                    post_url=post_url,
                    raw_html=raw_html,
                )
            )

        if not parsed:
            diagnostic = self._save_diagnostic(page, source, reason="no-posts-found")
            print(
                "Nenhum post encontrado nessa fonte. "
                f"Diagnostico salvo em: {diagnostic}"
            )
        else:
            print(f"Posts coletados nessa fonte: {len(parsed)}")
        return parsed

    def _wait_for_linkedin_content(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(2_000)
        except Exception:
            pass

    def _looks_logged_out(self, page) -> bool:
        current_url = page.url.lower()
        if "/login" in current_url or "checkpoint" in current_url:
            return True
        try:
            body_text = page.locator("body").inner_text(timeout=2_000).lower()
        except Exception:
            return False
        markers = (
            "sign in",
            "join linkedin",
            "email or phone",
            "forgot password",
            "authwall",
            "security verification",
        )
        return any(marker in body_text for marker in markers)

    def _try_expand_visible_posts(self, page) -> None:
        selectors = (
            "button:has-text('see more')",
            "button:has-text('See more')",
            "button:has-text('ver mais')",
            "button:has-text('Ver mais')",
        )
        for selector in selectors:
            buttons = page.locator(selector)
            try:
                count = min(buttons.count(), self.max_posts_per_source)
            except Exception:
                continue
            for index in range(count):
                checkpoint()
                try:
                    buttons.nth(index).click(timeout=800)
                except Exception:
                    continue

    def _scroll_results(self, page) -> None:
        for _ in range(self.scroll_rounds):
            checkpoint()
            try:
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(1_200)
                self._try_expand_visible_posts(page)
            except Exception:
                continue

    def _extract_candidate_posts(self, page) -> list[dict[str, str]]:
        return page.evaluate(
            """
            () => {
              const selectors = [
                'div.feed-shared-update-v2',
                'div[data-urn^="urn:li:activity"]',
                'li.reusable-search__result-container',
                'div.search-results-container li',
                'article'
              ];
              const nodes = [];
              for (const selector of selectors) {
                for (const node of document.querySelectorAll(selector)) {
                  if (!nodes.includes(node)) nodes.push(node);
                }
              }
              return nodes
                .map((node) => ({
                  text: (node.innerText || '').trim(),
                  html: node.innerHTML || ''
                }))
                .filter((item) => item.text.length > 80);
            }
            """
        )

    def _save_diagnostic(self, page, source: LinkedInSource, reason: str) -> Path:
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

    def _extract_post_url(self, raw_html: str) -> str | None:
        marker = "https://www.linkedin.com/feed/update/"
        start = raw_html.find(marker)
        if start < 0:
            return None
        end_candidates = [
            idx for idx in (raw_html.find('"', start), raw_html.find("'", start)) if idx > start
        ]
        end = min(end_candidates) if end_candidates else start + 200
        return raw_html[start:end]
