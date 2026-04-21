from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import RuntimeConfig, ensure_runtime_dirs


class BrowserDependencyError(RuntimeError):
    """Raised when Playwright is not installed or browser binaries are missing."""


def find_google_chrome() -> Path | None:
    candidates: list[Path] = []
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def start_controlled_chrome(
    cdp_port: int = 9222,
    profile_dir: Path | None = None,
    url: str = "about:blank",
) -> subprocess.Popen:
    chrome = find_google_chrome()
    if not chrome:
        raise BrowserDependencyError("Google Chrome nao encontrado neste Windows.")
    config = RuntimeConfig()
    profile = profile_dir or (config.project_root / "google-chrome-control-profile")
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def configure_playwright_browsers_path() -> Path | None:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "ms-playwright",
                exe_dir / "_internal" / "ms-playwright",
            ]
        )

    existing_env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if existing_env:
        candidates.append(Path(existing_env))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "ms-playwright")

    candidates.append(Path.home() / "AppData" / "Local" / "ms-playwright")

    for candidate in candidates:
        if _has_chromium(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return candidate

    return None


@contextmanager
def persistent_chromium_context(
    profile_dir: Path | None = None,
    headless: bool = False,
    browser: str = "chrome",
    cdp_url: str = "http://127.0.0.1:9222",
) -> Iterator[object]:
    ensure_runtime_dirs()
    browser = (browser or "chrome").lower()
    browser_path = configure_playwright_browsers_path() if browser == "chromium" else None
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise BrowserDependencyError(
            "Playwright nao esta instalado. Rode: python -m pip install -e ."
        ) from exc

    config = RuntimeConfig()
    user_data_dir = profile_dir or config.playwright_profile_dir
    with sync_playwright() as playwright:
        if browser == "cdp":
            try:
                connected = playwright.chromium.connect_over_cdp(cdp_url)
                context = connected.contexts[0] if connected.contexts else connected.new_context()
            except Exception as exc:
                raise BrowserDependencyError(
                    "Nao foi possivel conectar ao Google Chrome aberto. "
                    "Abra o Chrome com depuracao pela interface do bot ou rode: "
                    "chrome.exe --remote-debugging-port=9222 --user-data-dir=\"D:\\automatedapply\\google-chrome-control-profile\". "
                    f"URL tentada: {cdp_url}. Erro original: {exc}"
                ) from exc
            try:
                yield context
            finally:
                # Nao fechar o Chrome do usuario ao desconectar do CDP.
                pass
            return

        launch_kwargs = {
            "user_data_dir": str(user_data_dir),
            "headless": headless,
            "viewport": {"width": 1366, "height": 900},
        }
        if browser == "chrome":
            launch_kwargs["channel"] = "chrome"
        elif browser != "chromium":
            raise BrowserDependencyError(f"Modo de navegador invalido: {browser}")

        try:
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            if browser == "chrome":
                hint = (
                    "Google Chrome instalado nao foi encontrado ou nao abriu. "
                    "Instale o Google Chrome ou selecione o modo Chromium Playwright."
                )
            else:
                hint = (
                    "Chromium do Playwright nao foi encontrado. "
                    "Rode: python -m playwright install chromium. "
                    "Se estiver usando o .exe, reconstrua com scripts/build_exe.ps1 "
                    "ou copie a pasta %LOCALAPPDATA%\\ms-playwright para dist\\AutomatedApply\\ms-playwright."
                )
                if browser_path:
                    hint += f" Caminho tentado: {browser_path}."
            raise BrowserDependencyError(f"{hint}\nErro original: {exc}") from exc
        try:
            yield context
        finally:
            context.close()


def _has_chromium(path: Path) -> bool:
    if not path.exists():
        return False
    return any(path.glob("chromium-*/chrome-win64/chrome.exe"))
