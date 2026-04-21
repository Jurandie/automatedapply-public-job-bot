from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from app.browser.company_sites import (
    CompanyCareerSource,
    CompanyJobCollector,
    CompanySiteCollectionError,
)
from app.browser.linkedin_posts import (
    LinkedInCollectionError,
    LinkedInPostCollector,
    LinkedInSource,
    build_linkedin_search_url,
)
from app.browser.session import BrowserDependencyError
from app.browser.web_search import WebJobSearchCollector, build_job_search_queries
from app.classification.claude_classifier import classify_ambiguous_post
from app.classification.profile_fit import allowed_seniority_from_profile, apply_profile_fit
from app.classification.rules import classify_post
from app.config import (
    DEFAULT_COMPANY_RATINGS_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PROFILE_PATH,
    DEFAULT_SOURCES_PATH,
    ConfigError,
    RuntimeConfig,
    ensure_runtime_dirs,
    load_yaml,
)
from app.extraction.post_parser import ParsedPost, load_posts_json
from app.extraction.link_extractor import canonical_job_url
from app.resume.inventory import ExperienceInventoryError, load_experience_inventory
from app.resume.tailoring import resolve_project_path
from app.review.human_review import print_review
from app.review.job_links import export_job_links
from app.review.report import build_job_summary
from app.reputation.glassdoor import GlassdoorRatingGate
from app.runtime_control import RunInterrupted, checkpoint
from app.storage.db import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automatedapply")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Caminho do SQLite.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Cria ou atualiza o banco SQLite.")
    login = subparsers.add_parser("open-linkedin-login", help="Abre LinkedIn para login manual persistente.")
    _add_browser_args(login)

    controlled = subparsers.add_parser(
        "open-controlled-chrome",
        help="Abre Google Chrome com remote debugging para o modo cdp.",
    )
    controlled.add_argument("--port", type=int, default=9222, help="Porta CDP.")

    company_scan = subparsers.add_parser("scan-company-sites", help="Coleta/classifica vagas em sites de empresas.")
    company_scan.add_argument("--use-claude", action="store_true", help="Usa Claude para vagas needs_review.")
    company_scan.add_argument("--headless", action="store_true", help="Roda Playwright em modo headless.")
    company_scan.add_argument("--max-jobs", type=int, default=50, help="Maximo de vagas coletadas.")
    company_scan.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Caminho do candidate_profile.yaml usado para montar buscas web.",
    )
    _add_discovery_args(company_scan)
    _add_rating_args(company_scan)
    _add_browser_args(company_scan)

    scan_apply = subparsers.add_parser(
        "scan-and-apply",
        help="Busca vagas em sites de empresas e depois prepara aplicacoes elegiveis.",
    )
    scan_apply.add_argument("--use-claude", action="store_true", help="Usa Claude para vagas needs_review.")
    scan_apply.add_argument("--headless", action="store_true", help="Roda Playwright em modo headless.")
    scan_apply.add_argument("--max-jobs", type=int, default=50, help="Maximo de vagas coletadas durante o scan.")
    _add_discovery_args(scan_apply)
    _add_rating_args(scan_apply)
    scan_apply.add_argument(
        "--mode",
        default="fill_only",
        choices=["dry_run", "fill_only", "review_first", "auto_submit_safe"],
    )
    scan_apply.add_argument("--limit", type=int, help="Limita a quantidade de vagas processadas no apply.")
    scan_apply.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Caminho do candidate_profile.yaml.",
    )
    _add_browser_args(scan_apply)

    ratings = subparsers.add_parser("check-company-ratings", help="Lista status das notas Glassdoor configuradas.")
    ratings.add_argument(
        "--ratings-file",
        type=Path,
        default=DEFAULT_COMPANY_RATINGS_PATH,
        help="Caminho do company_ratings.yaml.",
    )

    scan_json = subparsers.add_parser("scan-json", help="Ingere/classifica vagas de um arquivo JSON local.")
    scan_json.add_argument("--from-file", type=Path, required=True, help="Arquivo JSON com vagas para ingestao offline.")
    scan_json.add_argument("--use-claude", action="store_true", help="Usa Claude para vagas needs_review.")

    scan = subparsers.add_parser("scan-linkedin-posts", help="Coleta/classifica posts legados do LinkedIn.")
    scan.add_argument("--from-file", type=Path, help="Arquivo JSON com posts para ingestao offline.")
    scan.add_argument("--use-claude", action="store_true", help="Usa Claude para posts needs_review.")
    scan.add_argument("--headless", action="store_true", help="Roda Playwright em modo headless.")
    scan.add_argument("--max-posts", type=int, default=50, help="Posts por fonte.")
    _add_browser_args(scan)

    review = subparsers.add_parser("review-jobs", help="Lista vagas registradas.")
    review.add_argument("--status", help="Filtra por status.")

    export_links = subparsers.add_parser("export-job-links", help="Salva links das vagas em arquivo .txt.")
    export_links.add_argument("--status", help="Filtra por status antes de exportar.")
    export_links.add_argument(
        "--output",
        type=Path,
        help="Arquivo .txt de saida. Padrao: pasta runtime do banco.",
    )
    export_links.add_argument(
        "--open-notepad",
        action="store_true",
        help="Abre o arquivo exportado no Bloco de Notas.",
    )

    apply_cmd = subparsers.add_parser("apply", help="Prepara aplicacoes com politica segura.")
    apply_cmd.add_argument(
        "--mode",
        default="fill_only",
        choices=["dry_run", "fill_only", "review_first", "auto_submit_safe"],
    )
    apply_cmd.add_argument("--headless", action="store_true", help="Roda Playwright em modo headless.")
    apply_cmd.add_argument("--limit", type=int, help="Limita a quantidade de vagas processadas.")
    _add_browser_args(apply_cmd)
    apply_cmd.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Caminho do candidate_profile.yaml.",
    )

    tailor_cmd = subparsers.add_parser("tailor-resumes", help="Gera curriculos adaptados sem abrir browser.")
    tailor_cmd.add_argument("--status", default="ready_to_apply", help="Status das vagas usadas.")
    tailor_cmd.add_argument("--limit", type=int, help="Limita a quantidade de vagas processadas.")
    tailor_cmd.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Caminho do candidate_profile.yaml.",
    )

    subparsers.add_parser("report", help="Resumo agregado do banco.")
    return parser


def _add_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--browser",
        default="chrome",
        choices=["chrome", "cdp", "chromium"],
        help="chrome usa Google Chrome instalado; cdp conecta a Chrome aberto; chromium usa Chromium Playwright.",
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="URL CDP para conectar a um Chrome aberto com remote debugging.",
    )


def _add_rating_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ratings-file",
        type=Path,
        default=DEFAULT_COMPANY_RATINGS_PATH,
        help="Caminho do company_ratings.yaml.",
    )
    parser.add_argument(
        "--skip-glassdoor-gate",
        action="store_true",
        help="Compatibilidade: nao bloqueia empresas sem nota Glassdoor configurada.",
    )
    parser.add_argument(
        "--require-glassdoor-gate",
        action="store_true",
        help="Bloqueia empresas configuradas sem nota Glassdoor verificada.",
    )


def _add_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-mode",
        choices=["web", "configured", "both"],
        default="web",
        help="web pesquisa vagas na internet; configured usa data/target_sources.yaml; both combina os dois.",
    )
    parser.add_argument(
        "--max-search-queries",
        type=int,
        default=160,
        help="Maximo de consultas ao buscador para descoberta web.",
    )
    parser.add_argument(
        "--search-results-per-query",
        type=int,
        default=10,
        help="Maximo de resultados abertos por consulta de busca web.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db = Database(Path(args.db))

    try:
        ensure_runtime_dirs(RuntimeConfig(db_path=Path(args.db)))
        if args.command == "init-db":
            checkpoint()
            db.init()
            print(f"Banco inicializado em {Path(args.db)}")
            return 0

        if args.command == "open-linkedin-login":
            from app.browser.linkedin_login import open_linkedin_login_window

            open_linkedin_login_window(browser=args.browser, cdp_url=args.cdp_url)
            return 0

        if args.command == "open-controlled-chrome":
            from app.browser.session import start_controlled_chrome

            start_controlled_chrome(cdp_port=args.port)
            print(f"Google Chrome aberto com remote debugging na porta {args.port}.")
            print("Selecione browser=cdp para usar essa janela.")
            return 0

        if args.command == "scan-company-sites":
            checkpoint()
            db.init()
            posts = _load_or_collect_company_jobs(args)
            created = _classify_and_store_posts(
                db,
                posts,
                use_claude=args.use_claude,
                profile_path=args.profile,
            )
            print(f"Paginas de vaga processadas: {len(posts)}")
            print(f"Vagas registradas/atualizadas: {created}")
            return 0

        if args.command == "scan-and-apply":
            checkpoint()
            db.init()
            posts = _load_or_collect_company_jobs(args)
            created = _classify_and_store_posts(
                db,
                posts,
                use_claude=args.use_claude,
                profile_path=args.profile,
            )
            print(f"Paginas de vaga processadas: {len(posts)}")
            print(f"Vagas registradas/atualizadas: {created}")
            return _apply_jobs(db, args)

        if args.command == "scan-json":
            checkpoint()
            db.init()
            posts = load_posts_json(args.from_file)
            created = _classify_and_store_posts(db, posts, use_claude=args.use_claude)
            print(f"Registros JSON processados: {len(posts)}")
            print(f"Vagas registradas/atualizadas: {created}")
            return 0

        if args.command == "scan-linkedin-posts":
            checkpoint()
            db.init()
            posts = _load_or_collect_posts(args)
            created = _classify_and_store_posts(db, posts, use_claude=args.use_claude)
            print(f"Posts processados: {len(posts)}")
            print(f"Vagas registradas/atualizadas: {created}")
            return 0

        if args.command == "review-jobs":
            checkpoint()
            print_review(db, status=args.status)
            return 0

        if args.command == "export-job-links":
            checkpoint()
            db.init()
            output_path = args.output or (Path(args.db).resolve().parent / "vagas_links.txt")
            result = export_job_links(db, output_path=output_path, status=args.status)
            print(f"Links exportados: {result.total_links}")
            print(f"Arquivo: {result.path}")
            if args.open_notepad:
                _open_text_file(result.path)
            return 0

        if args.command == "apply":
            checkpoint()
            return _apply_jobs(db, args)

        if args.command == "tailor-resumes":
            checkpoint()
            return _tailor_resumes(db, args)

        if args.command == "report":
            checkpoint()
            print(json.dumps(build_job_summary(db), indent=2, ensure_ascii=False))
            return 0

        if args.command == "check-company-ratings":
            checkpoint()
            config = load_yaml(DEFAULT_SOURCES_PATH)
            sources = _build_company_sources(config)
            gate = GlassdoorRatingGate.from_yaml(args.ratings_file)
            for source in sources:
                rating = gate.check(source.name)
                value = rating.rating if rating.rating is not None else "missing"
                print(
                    f"{source.name} | allowed={rating.allowed} | rating={value} | "
                    f"{rating.reason} | {rating.glassdoor_url or rating.search_url}"
                )
            return 0
    except RunInterrupted as exc:
        print(str(exc))
        return 130
    except (
        BrowserDependencyError,
        ConfigError,
        LinkedInCollectionError,
        CompanySiteCollectionError,
        ValueError,
    ) as exc:
        parser.error(str(exc))
    return 1


def _open_text_file(path: Path) -> None:
    if os.name == "nt":
        subprocess.Popen(["notepad.exe", str(path)])
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])


def _load_or_collect_company_jobs(args) -> list[ParsedPost]:
    config = load_yaml(DEFAULT_SOURCES_PATH)
    source_mode = getattr(args, "source_mode", "web")
    posts: list[ParsedPost] = []
    db = Database(Path(args.db))
    known_job_urls = db.list_known_job_urls()
    if known_job_urls:
        print(f"Vagas ja conhecidas no banco: {len(known_job_urls)}. URLs repetidas serao puladas.")

    if source_mode in {"web", "both"}:
        profile_path = getattr(args, "profile", DEFAULT_PROFILE_PATH)
        profile = load_yaml(Path(profile_path))
        queries = build_job_search_queries(
            config,
            profile,
            max_queries=max(1, int(getattr(args, "max_search_queries", 20))),
        )
        collector = WebJobSearchCollector(
            headless=args.headless,
            max_jobs=args.max_jobs,
            results_per_query=max(1, int(getattr(args, "search_results_per_query", 10))),
            browser=args.browser,
            cdp_url=args.cdp_url,
            known_job_urls=known_job_urls,
        )
        web_posts = collector.collect(queries)
        posts.extend(web_posts)
        known_job_urls.update(_post_url_keys(web_posts))

    if source_mode in {"configured", "both"}:
        sources = _build_company_sources(config)
        rating_gate = None
        if getattr(args, "require_glassdoor_gate", False) and not getattr(args, "skip_glassdoor_gate", False):
            rating_gate = GlassdoorRatingGate.from_yaml(args.ratings_file)
        collector = CompanyJobCollector(
            headless=args.headless,
            max_jobs_per_source=args.max_jobs,
            browser=args.browser,
            cdp_url=args.cdp_url,
            rating_gate=rating_gate,
            known_job_urls=known_job_urls,
        )
        configured_posts = collector.collect(sources)
        posts.extend(configured_posts)
        known_job_urls.update(_post_url_keys(configured_posts))

    return _dedupe_posts(posts)


def _dedupe_posts(posts: list[ParsedPost]) -> list[ParsedPost]:
    unique: list[ParsedPost] = []
    seen: set[str] = set()
    for post in posts:
        key = canonical_job_url(post.post_url) or post.id
        if key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def _post_url_keys(posts: list[ParsedPost]) -> set[str]:
    keys: set[str] = set()
    for post in posts:
        url_key = canonical_job_url(post.post_url)
        if url_key:
            keys.add(url_key)
    return keys


def _load_or_collect_posts(args) -> list[ParsedPost]:
    if args.from_file:
        return load_posts_json(args.from_file)

    config = load_yaml(DEFAULT_SOURCES_PATH)
    sources = _build_sources(config)
    collector = LinkedInPostCollector(
        headless=args.headless,
        max_posts_per_source=args.max_posts,
        browser=args.browser,
        cdp_url=args.cdp_url,
    )
    return collector.collect(sources)


def _build_company_sources(config: dict) -> list[CompanyCareerSource]:
    company_sources = config.get("company_sources", {})
    target_countries = {
        str(country).strip().lower()
        for country in company_sources.get("target_countries", ["Italy", "Ireland"])
        if str(country).strip()
    }
    sources: list[CompanyCareerSource] = []
    for item in company_sources.get("companies", []) or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("careers_url") or item.get("url") or "").strip()
        name = str(item.get("name") or url).strip()
        country = str(item.get("country") or "").strip() or None
        if not url:
            continue
        if country and target_countries and country.lower() not in target_countries:
            continue
        sources.append(
            CompanyCareerSource(
                name=name,
                careers_url=url,
                country=country,
                tags=tuple(str(tag) for tag in item.get("tags", []) or []),
            )
        )

    if not sources:
        raise ConfigError("Nenhuma fonte company_sources.companies configurada para Italy/Ireland.")
    return sources


def _build_sources(config: dict) -> list[LinkedInSource]:
    linkedin = config.get("linkedin_sources", {})
    sources: list[LinkedInSource] = []
    for key in ("companies", "people"):
        for url in linkedin.get(key, []) or []:
            if url:
                sources.append(LinkedInSource(url=str(url), label=f"{key}:{url}", kind=key))

    for query in linkedin.get("search_terms", []) or []:
        if query:
            query_text = str(query)
            sources.append(
                LinkedInSource(
                    url=build_linkedin_search_url(query_text),
                    label=f"search:{query_text}",
                    kind="search",
                    query=query_text,
                )
            )

    if not sources:
        raise ConfigError("Nenhuma fonte configurada em data/target_sources.yaml.")
    return sources


def _classify_and_store_posts(
    db: Database,
    posts: list[ParsedPost],
    use_claude: bool,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> int:
    profile = load_yaml(Path(profile_path))
    inventory = _load_inventory_for_profile(profile)
    allowed_seniority = allowed_seniority_from_profile(profile)
    created = 0
    for post in posts:
        checkpoint()
        result = classify_post(
            post.text,
            post.links,
            company=post.company,
            allowed_seniority=allowed_seniority,
        )
        result = apply_profile_fit(result, post.text, profile, inventory)
        if use_claude and result.eligibility_status == "needs_review":
            claude = classify_ambiguous_post(post.text, enabled=True)
            if claude.error:
                print(f"Claude falhou para post {post.id}: {claude.error}")
        db.upsert_post(post.to_storage(status=result.eligibility_status))
        if result.is_job_post:
            db.upsert_job(result.to_job(source_post_id=post.id, post_text=post.text))
            created += 1
    return created


def _load_inventory_for_profile(profile: dict) -> dict | None:
    settings = profile.get("resume_tailoring") or {}
    inventory_path = resolve_project_path(settings.get("experience_inventory_path") or "data/experience_inventory.yaml")
    try:
        return load_experience_inventory(inventory_path)
    except (ConfigError, ExperienceInventoryError, FileNotFoundError) as exc:
        print(f"Inventario de experiencias indisponivel para fit do CV: {exc}")
        return None


def _apply_jobs(db: Database, args) -> int:
    from app.application.runner import ApplyRunOptions, run_apply

    results = run_apply(
        db,
        ApplyRunOptions(
            mode=args.mode,
            headless=args.headless,
            limit=args.limit,
            profile_path=args.profile,
            browser=args.browser,
            cdp_url=args.cdp_url,
        ),
    )
    if not results:
        print(_no_ready_jobs_message(db))
        return 0
    for result in results:
        resume_suffix = ""
        if result.get("tailored_resume_path"):
            resume_suffix = f" resume={result['tailored_resume_path']}"
        print(
            f"{result['job_id']} | {result.get('title') or 'unknown'} | "
            f"status={result['status']} adapter={result.get('adapter') or 'unknown'} "
            f"filled={result['filled']} valid={result['valid']} "
            f"submit={result['can_submit']} | {result['reason']}{resume_suffix}"
        )
    return 0


def _no_ready_jobs_message(db: Database) -> str:
    total_jobs = db.count("jobs")
    total_sources = db.count("linkedin_posts")
    if total_jobs == 0:
        return (
            "Nenhuma vaga ready_to_apply encontrada.\n"
            f"Banco atual tem {total_sources} paginas coletadas e {total_jobs} vagas registradas.\n"
            "Use 'Buscar e preencher elegiveis' na interface, ou rode 'Buscar vagas sem preencher' antes."
        )

    summary = build_job_summary(db)
    by_status = summary.get("by_status", {})
    status_text = ", ".join(f"{status}={count}" for status, count in sorted(by_status.items())) or "sem status"
    recent_rows = db.list_jobs()[:5]
    reasons = []
    for row in recent_rows:
        reasons.append(
            f"- {row['title'] or 'unknown'} | {row['eligibility_status']} | "
            f"{row['eligibility_reason']} | {row['application_url'] or 'sem link'}"
        )
    recent_text = "\n".join(reasons)
    return (
        "Nenhuma vaga ready_to_apply encontrada.\n"
        f"Resumo do banco: total_jobs={total_jobs}; {status_text}.\n"
        "Ultimas vagas analisadas:\n"
        f"{recent_text}\n"
        "Use 'Revisar vagas' para confirmar os motivos ou rode novo scan."
    )


def _tailor_resumes(db: Database, args) -> int:
    from app.application.profile import load_candidate_profile
    from app.resume.tailoring import maybe_tailor_resume_for_job

    profile = load_candidate_profile(args.profile)
    jobs = db.list_jobs(status=args.status)
    if args.limit is not None:
        jobs = jobs[: args.limit]
    if not jobs:
        print("Nenhuma vaga encontrada para tailoring.")
        return 0

    for row in jobs:
        checkpoint()
        result = maybe_tailor_resume_for_job(profile=profile, job=row, job_description="")
        if result.grounded:
            print(f"{row['id']} | {row['title'] or 'unknown'} | resume={result.markdown_path}")
        else:
            print(
                f"{row['id']} | {row['title'] or 'unknown'} | resume=blocked | "
                f"{'; '.join(result.warnings)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
