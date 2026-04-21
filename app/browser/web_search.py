from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from app.browser.company_sites import (
    CompanyCareerSource,
    CompanyJobCollector,
    _looks_like_job_url_or_text,
    _looks_like_listing_url,
    safe_page_evaluate,
)
from app.browser.session import persistent_chromium_context
from app.config import DATA_DIR
from app.extraction.link_extractor import canonical_job_url
from app.extraction.post_parser import ParsedPost
from app.runtime_control import checkpoint


DEFAULT_WEB_ATS_DOMAINS = (
    "jobs.lever.co",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "apply.workable.com",
    "jobs.smartrecruiters.com",
    "jobs.personio.com",
    "recruitee.com",
    "comeet.com",
)

SEARCH_ENGINE_HOST_MARKERS = (
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "yahoo.com",
)

IGNORED_SEARCH_RESULT_HOST_MARKERS = (
    "glassdoor.",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)


@dataclass(frozen=True)
class WebSearchQuery:
    text: str
    country: str
    provider: str = "duckduckgo"
    url: str | None = None
    company: str | None = None

    @property
    def search_url(self) -> str:
        if self.url:
            return self.url
        return f"https://duckduckgo.com/html/?q={quote_plus(self.text)}"


class WebJobSearchCollector:
    """Discovers public job pages through web search, then collects job details."""

    def __init__(
        self,
        headless: bool = False,
        max_jobs: int = 50,
        results_per_query: int = 10,
        diagnostic_dir: Path = DATA_DIR / "runtime" / "diagnostics",
        browser: str = "chrome",
        cdp_url: str = "http://127.0.0.1:9222",
        known_job_urls: set[str] | None = None,
    ):
        self.headless = headless
        self.max_jobs = max_jobs
        self.results_per_query = results_per_query
        self.diagnostic_dir = diagnostic_dir
        self.browser = browser
        self.cdp_url = cdp_url
        self.known_job_urls: set[str] = set()
        for url in known_job_urls or set():
            url_key = canonical_job_url(url)
            if url_key:
                self.known_job_urls.add(url_key)

    def collect(self, queries: list[WebSearchQuery]) -> list[ParsedPost]:
        jobs: list[ParsedPost] = []
        seen_urls: set[str] = set()
        detail_collector = CompanyJobCollector(
            headless=self.headless,
            max_jobs_per_source=self.max_jobs,
            diagnostic_dir=self.diagnostic_dir,
            scroll_rounds=2,
            browser=self.browser,
            cdp_url=self.cdp_url,
            rating_gate=None,
            known_job_urls=self.known_job_urls,
        )

        if not queries:
            print("Nenhuma query de busca web configurada.")
            return jobs

        with persistent_chromium_context(
            headless=self.headless,
            browser=self.browser,
            cdp_url=self.cdp_url,
        ) as context:
            page = context.new_page()
            for query in queries:
                checkpoint()
                if len(jobs) >= self.max_jobs:
                    break
                print(f"Pesquisando vagas na web: {query.country} -> {query.text}")
                candidates = self._collect_search_results(page, query)
                print(f"Resultados candidatos encontrados: {len(candidates)}")

                queue = list(candidates)
                while queue and len(jobs) < self.max_jobs:
                    checkpoint()
                    candidate = queue.pop(0)
                    url = str(candidate.get("url") or "").strip()
                    url_key = canonical_job_url(url)
                    if not url or not url_key or url_key in seen_urls:
                        continue
                    seen_urls.add(url_key)

                    text = str(candidate.get("text") or "")
                    if not _looks_like_job_url_or_text(url, text):
                        continue

                    company = query.company or guess_company_from_url_or_text(url, text)
                    source = CompanyCareerSource(
                        name=company or f"Web search {query.country}",
                        careers_url=query.search_url,
                        country=query.country,
                        tags=("web-search",),
                    )
                    candidate["company"] = company or source.name
                    candidate["source_url"] = query.search_url

                    if _looks_like_listing_url(url, text) or _looks_like_career_listing_url(url, text):
                        nested = detail_collector._expand_listing_page(page, source, url)
                        for nested_candidate in nested:
                            nested_url = str(nested_candidate.get("url") or "")
                            nested_text = str(nested_candidate.get("text") or "")
                            nested_candidate["company"] = guess_company_from_url_or_text(
                                nested_url,
                                nested_text,
                            ) or source.name
                            nested_candidate["source_url"] = query.search_url
                        queue.extend(nested)
                        continue

                    if self._is_known_job_url(url):
                        print(f"Pulando vaga ja consultada: {url}")
                        continue

                    job = detail_collector._collect_job_page(page, source, candidate)
                    if job:
                        jobs.append(job)
                        self.known_job_urls.add(url_key)
                        detail_collector.known_job_urls.add(url_key)

        print(f"Vagas coletadas por busca web: {len(jobs)}")
        return jobs

    def _is_known_job_url(self, url: str) -> bool:
        url_key = canonical_job_url(url)
        return bool(url_key and url_key in self.known_job_urls)

    def _collect_search_results(self, page, query: WebSearchQuery) -> list[dict[str, str]]:
        try:
            page.goto(query.search_url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            if self._needs_human_validation(page):
                if self.headless:
                    print(
                        "O buscador solicitou validacao humana. "
                        "Rode sem --headless ou use --browser cdp com Chrome controlavel."
                    )
                    return []
                print("O buscador solicitou validacao humana. Resolva na janela aberta; aguardando ate 120s.")
                try:
                    page.wait_for_function(
                        """
                        () => {
                          const text = (document.body && document.body.innerText || '').toLowerCase();
                          const challenge = ['captcha', 'not a robot', 'desafio', 'challenge', 'select all squares']
                            .some((marker) => text.includes(marker));
                          return !challenge && document.querySelectorAll('a[href]').length > 5;
                        }
                        """,
                        timeout=120_000,
                    )
                except Exception:
                    print("Validacao humana nao foi concluida dentro do tempo limite.")
                    return []
        except Exception as exc:
            print(f"Falha ao pesquisar '{query.text}': {exc}")
            self._reset_page_after_failed_navigation(page)
            return []

        raw_results = safe_page_evaluate(
            page,
            """
            ({ limit }) => {
              const anchors = Array.from(document.querySelectorAll('a[href]'));
              const results = [];

              function nearestText(anchor) {
                const card = anchor.closest('.result, article, li, div');
                const text = ((card && card.innerText) || anchor.innerText || anchor.textContent || '').trim();
                return text.replace(/\\s+/g, ' ').slice(0, 1600);
              }

              for (const anchor of anchors) {
                const href = anchor.href || '';
                if (!href.startsWith('http')) continue;
                results.push({ url: href, text: nearestText(anchor) });
                if (results.length >= limit * 4) break;
              }
              return results;
            }
            """,
            {"limit": self.results_per_query},
            default=[],
            label=f"resultados da busca '{query.text}'",
        )

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_results:
            url = decode_search_result_url(str(item.get("url") or ""))
            text = str(item.get("text") or "").strip()
            if not url or url in seen:
                continue
            if query.provider == "career_page" and _same_document_url(query.search_url, url):
                continue
            if query.provider != "career_page" and _is_ignored_search_url(url):
                continue
            if query.provider == "workable" and not _is_workable_job_url(url):
                continue
            if query.provider == "career_page" and not _looks_like_career_page_candidate(url, text):
                continue
            if not _looks_like_job_url_or_text(url, text):
                continue
            seen.add(url)
            results.append({"url": url, "text": text})
            if len(results) >= self.results_per_query:
                break
        return results

    def _needs_human_validation(self, page) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=2_000).lower()
        except Exception:
            return False
        challenge_markers = (
            "captcha",
            "not a robot",
            "confirm you're not a robot",
            "resolva o desafio",
            "select all squares",
            "unfortunately, bots",
            "uma ultima etapa",
        )
        return any(marker in text for marker in challenge_markers)

    def _reset_page_after_failed_navigation(self, page) -> None:
        try:
            page.evaluate("window.stop()")
        except Exception:
            pass
        try:
            page.goto("about:blank", wait_until="domcontentloaded", timeout=5_000)
        except Exception:
            pass


def build_job_search_queries(
    config: dict[str, Any],
    profile: dict[str, Any],
    max_queries: int = 20,
) -> list[WebSearchQuery]:
    preferences = profile.get("preferences", {}) if isinstance(profile, dict) else {}
    company_sources = config.get("company_sources", {}) if isinstance(config, dict) else {}
    web_search = config.get("web_search", {}) if isinstance(config, dict) else {}

    countries = _string_list(preferences.get("allowed_countries"))
    if not countries:
        countries = _string_list(company_sources.get("target_countries"))
    if not countries:
        countries = ["Italy", "Ireland"]

    roles = _string_list(preferences.get("roles"))
    if not roles:
        roles = ["Python Developer", "Backend Engineer", "Automation Engineer", "Data Engineer"]

    seniority_terms = _seniority_search_terms(_string_list(preferences.get("seniority")))
    if not seniority_terms:
        seniority_terms = ["junior", "mid"]

    ats_domains = _string_list(web_search.get("ats_domains")) or list(DEFAULT_WEB_ATS_DOMAINS)
    company_targets = _interleave_company_targets(_company_targets(config, countries), countries)

    queries: list[WebSearchQuery] = []
    for company in company_targets:
        if not company.careers_url:
            pass
        else:
            queries.append(
                WebSearchQuery(
                    text=f"{company.name} careers {company.country or 'target countries'}",
                    country=company.country or ",".join(countries),
                    provider="career_page",
                    url=company.careers_url,
                    company=company.name,
                )
            )
        for country in _company_countries(company, countries):
            queries.append(
                WebSearchQuery(
                    text=f'"{company.name}" "{country}" careers jobs software engineer visa sponsorship relocation',
                    country=country,
                    company=company.name,
                )
            )
            queries.append(
                WebSearchQuery(
                    text=f"Workable {company.name} software engineer {country}",
                    country=country,
                    provider="workable",
                    url=build_workable_search_url(f"{company.name} software engineer", country),
                    company=company.name,
                )
            )

    for seniority in seniority_terms:
        for role in roles:
            for country in countries:
                query_text = f"{seniority} {role}"
                queries.append(
                    WebSearchQuery(
                        text=f"Workable {query_text} {country}",
                        country=country,
                        provider="workable",
                        url=build_workable_search_url(query_text, country),
                    )
                )

    for seniority in seniority_terms:
        for role in roles:
            for country in countries:
                work_mode = "remote"
                if country.lower() == "ireland":
                    work_mode = "remote OR hybrid OR onsite"
                queries.append(
                    WebSearchQuery(
                        text=f'"{seniority} {role}" "{country}" {work_mode} apply job',
                        country=country,
                    )
                )

    for seniority in seniority_terms:
        for role in roles:
            for country in countries:
                for domain in ats_domains:
                    queries.append(
                        WebSearchQuery(
                            text=f'site:{domain} "{country}" "{seniority} {role}"',
                            country=country,
                        )
                    )

    unique: list[WebSearchQuery] = []
    seen_text: set[str] = set()
    for query in queries:
        key = query.text.lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        unique.append(query)
        if len(unique) >= max_queries:
            break
    return unique


@dataclass(frozen=True)
class _CompanySearchTarget:
    name: str
    country: str | None = None
    careers_url: str | None = None


def _company_targets(config: dict[str, Any], countries: list[str]) -> list[_CompanySearchTarget]:
    company_sources = config.get("company_sources", {}) if isinstance(config, dict) else {}
    web_search = config.get("web_search", {}) if isinstance(config, dict) else {}
    raw_items: list[Any] = []
    raw_items.extend(company_sources.get("companies", []) or [])
    raw_items.extend(web_search.get("target_companies", []) or [])

    allowed = {country.lower() for country in countries}
    targets: list[_CompanySearchTarget] = []
    seen: set[tuple[str, str | None]] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        country = str(item.get("country") or "").strip() or None
        if country and allowed and country.lower() not in allowed:
            continue
        key = (name.lower(), country.lower() if country else None)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            _CompanySearchTarget(
                name=name,
                country=country,
                careers_url=str(item.get("careers_url") or item.get("url") or "").strip() or None,
            )
        )
    return targets


def _company_countries(company: _CompanySearchTarget, countries: list[str]) -> list[str]:
    if company.country:
        return [company.country]
    return countries


def _interleave_company_targets(
    targets: list[_CompanySearchTarget],
    countries: list[str],
) -> list[_CompanySearchTarget]:
    country_order = [country for country in countries if country]
    buckets: dict[str, list[_CompanySearchTarget]] = {country.lower(): [] for country in country_order}
    other: list[_CompanySearchTarget] = []
    for target in targets:
        if target.country and target.country.lower() in buckets:
            buckets[target.country.lower()].append(target)
        else:
            other.append(target)

    ordered: list[_CompanySearchTarget] = []
    index = 0
    while True:
        added = False
        for country in country_order:
            bucket = buckets.get(country.lower(), [])
            if index < len(bucket):
                ordered.append(bucket[index])
                added = True
        if not added:
            break
        index += 1
    ordered.extend(other)
    return ordered


def decode_search_result_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)

    if "duckduckgo.com" in host:
        for key in ("uddg", "u"):
            values = query.get(key)
            if values:
                return unquote(values[0])
        return ""

    return url


def build_workable_search_url(query: str, country: str) -> str:
    return (
        "https://jobs.workable.com/search?"
        f"query={quote_plus(query)}&location={quote_plus(country)}"
    )


def guess_company_from_url_or_text(url: str, text: str = "") -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    company_slug: str | None = None
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com"}:
        company_slug = path_parts[0] if path_parts else None
    elif host == "apply.workable.com":
        company_slug = path_parts[0] if path_parts else None
    elif host == "jobs.workable.com" and len(path_parts) >= 3 and path_parts[0] == "view":
        job_slug = path_parts[-1].lower()
        if "-at-" in job_slug:
            company_slug = job_slug.rsplit("-at-", 1)[1]
    elif host == "jobs.smartrecruiters.com":
        company_slug = path_parts[0] if path_parts else None
    elif host.endswith(".jobs.personio.com"):
        company_slug = host.split(".jobs.personio.com", 1)[0]
    elif host.endswith(".recruitee.com"):
        company_slug = host.split(".recruitee.com", 1)[0]
    elif "comeet.com" in host and len(path_parts) >= 2 and path_parts[0] == "jobs":
        company_slug = path_parts[1]

    if company_slug:
        return _humanize_slug(company_slug)

    text_company = _company_from_text(text)
    if text_company:
        return text_company

    domain_parts = host.split(".")
    if len(domain_parts) >= 2 and domain_parts[-2] not in {"greenhouse", "lever", "ashbyhq", "workable"}:
        return _humanize_slug(domain_parts[-2])
    return None


def _is_ignored_search_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(marker in host for marker in SEARCH_ENGINE_HOST_MARKERS + IGNORED_SEARCH_RESULT_HOST_MARKERS)


def _is_workable_job_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    return host == "jobs.workable.com" and parsed.path.startswith("/view/")


def _looks_like_career_page_candidate(url: str, text: str) -> bool:
    lowered = f"{url} {text}".lower()
    direct_markers = (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workdayjobs.com",
        "myworkdayjobs.com",
        "smartrecruiters.com",
        "successfactors",
        "oraclecloud.com",
        "icims.com",
        "jobvite.com",
        "breezy.hr",
        "teamtailor.com",
        "workable.com",
        "personio.com",
        "recruitee.com",
        "comeet.com",
        "/job/",
        "/jobs/",
        "/job-",
        "/jobs-",
        "/position/",
        "/positions/",
        "/opening/",
        "/openings/",
        "/vacanc",
        "jobid",
        "job_id",
        "requisition",
        "reqid",
    )
    role_markers = (
        "engineer",
        "developer",
        "software",
        "backend",
        "python",
        "automation",
        "data engineer",
        "cloud",
        "devops",
        "consultant",
        "analyst",
    )
    return any(marker in lowered for marker in direct_markers) or (
        any(marker in lowered for marker in role_markers)
        and any(marker in lowered for marker in ("apply", "posted", "full-time", "full time", "job"))
    )


def _looks_like_career_listing_url(url: str, text: str) -> bool:
    lowered = f"{url} {text}".lower()
    markers = (
        "/job-search",
        "/jobs/search",
        "/search-jobs",
        "/search-results",
        "/careers/jobs",
        "/careers/search",
        "jobsearch",
    )
    return any(marker in lowered for marker in markers)


def _same_document_url(source_url: str, candidate_url: str) -> bool:
    source = urlparse(source_url)
    candidate = urlparse(candidate_url)
    return (
        source.scheme.lower() == candidate.scheme.lower()
        and source.netloc.lower() == candidate.netloc.lower()
        and source.path.rstrip("/") == candidate.path.rstrip("/")
        and source.query == candidate.query
    )


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _seniority_search_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in {"junior", "jr", "entry", "entry-level", "entry level", "associate"}:
            terms.extend(["junior", "entry level"])
        elif lowered in {"pleno", "mid", "mid-level", "mid level", "intermediate"}:
            terms.extend(["mid", "mid-level"])
        else:
            terms.append(value)
    return list(dict.fromkeys(terms))


def _humanize_slug(slug: str) -> str | None:
    cleaned = unquote(slug).strip().strip("/")
    cleaned = re.sub(r"[-_]+", " ", cleaned)
    cleaned = re.sub(r"\b\d+\b", "", cleaned)
    cleaned = " ".join(part for part in cleaned.split() if part)
    if not cleaned:
        return None
    return cleaned.title()


def _company_from_text(text: str) -> str | None:
    patterns = (
        r"\bat\s+([A-Z][A-Za-z0-9&.,' -]{2,60})\b",
        r"\|\s*([A-Z][A-Za-z0-9&.,' -]{2,60})\s*$",
        r"-\s*([A-Z][A-Za-z0-9&.,' -]{2,60})\s+(?:careers|jobs)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            company = " ".join(match.group(1).split()).strip(" -|")
            if company and len(company) <= 60:
                return company
    return None
