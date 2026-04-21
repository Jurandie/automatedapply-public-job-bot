from __future__ import annotations

from app.browser.session import persistent_chromium_context


def open_linkedin_login_window(
    browser: str = "chrome",
    cdp_url: str = "http://127.0.0.1:9222",
) -> None:
    print("Abrindo LinkedIn em janela persistente.")
    print("Faca login manualmente. Quando terminar, feche a janela do navegador para continuar.")
    with persistent_chromium_context(headless=False, browser=browser, cdp_url=cdp_url) as context:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60_000)
        while True:
            try:
                if not context.pages:
                    break
                page.wait_for_timeout(1_000)
            except Exception:
                break
    print("Janela de login fechada. Sessao persistente salva.")
