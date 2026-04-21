from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import DEFAULT_PROFILE_PATH, load_yaml


def load_candidate_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict[str, Any]:
    profile = load_yaml(path)
    required = ("name", "email", "cv_path")
    missing = [field for field in required if not profile.get(field)]
    if missing:
        raise ValueError(f"Campos obrigatorios ausentes no perfil: {', '.join(missing)}")
    return profile

