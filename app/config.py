from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _project_root()
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "runtime" / "automatedapply.sqlite3"
DEFAULT_PROFILE_PATH = DATA_DIR / "candidate_profile.yaml"
DEFAULT_SOURCES_PATH = DATA_DIR / "target_sources.yaml"
DEFAULT_BLACKLIST_PATH = DATA_DIR / "blacklist.yaml"
DEFAULT_EXPERIENCE_INVENTORY_PATH = DATA_DIR / "experience_inventory.yaml"
DEFAULT_COMPANY_RATINGS_PATH = DATA_DIR / "company_ratings.yaml"


class ConfigError(RuntimeError):
    """Raised when local configuration is missing or invalid."""


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    db_path: Path = DEFAULT_DB_PATH
    profile_path: Path = DEFAULT_PROFILE_PATH
    sources_path: Path = DEFAULT_SOURCES_PATH
    blacklist_path: Path = DEFAULT_BLACKLIST_PATH
    playwright_profile_dir: Path = PROJECT_ROOT / "playwright-profile"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Arquivo de configuracao nao encontrado: {path}")

    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ConfigError(
            "PyYAML nao esta instalado. Rode: python -m pip install -e ."
        ) from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ConfigError(f"O arquivo {path} precisa conter um objeto YAML.")

    return data


def ensure_runtime_dirs(config: RuntimeConfig | None = None) -> None:
    config = config or RuntimeConfig()
    config.data_dir.mkdir(exist_ok=True)
    (config.data_dir / "runtime").mkdir(exist_ok=True)
    (config.data_dir / "tmp").mkdir(exist_ok=True)
    (config.data_dir / "screenshots").mkdir(exist_ok=True)
    config.playwright_profile_dir.mkdir(exist_ok=True)
