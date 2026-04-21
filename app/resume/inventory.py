from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import DEFAULT_EXPERIENCE_INVENTORY_PATH, load_yaml


class ExperienceInventoryError(ValueError):
    """Raised when the experience inventory cannot safely ground a resume."""


def load_experience_inventory(path: Path = DEFAULT_EXPERIENCE_INVENTORY_PATH) -> dict[str, Any]:
    inventory = load_yaml(path)
    validate_experience_inventory(inventory)
    return inventory


def validate_experience_inventory(inventory: dict[str, Any]) -> None:
    experiences = inventory.get("experiences") or []
    projects = inventory.get("projects") or []
    if not isinstance(experiences, list):
        raise ExperienceInventoryError("experiences precisa ser uma lista.")
    if not isinstance(projects, list):
        raise ExperienceInventoryError("projects precisa ser uma lista.")

    for section_name, records in (("experiences", experiences), ("projects", projects)):
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ExperienceInventoryError(f"{section_name}[{index}] precisa ser objeto.")
            bullets = record.get("bullets") or []
            if not isinstance(bullets, list):
                raise ExperienceInventoryError(f"{section_name}[{index}].bullets precisa ser lista.")
            for bullet_index, bullet in enumerate(bullets):
                if isinstance(bullet, str):
                    continue
                if not isinstance(bullet, dict) or not bullet.get("text"):
                    raise ExperienceInventoryError(
                        f"{section_name}[{index}].bullets[{bullet_index}] precisa ter text."
                    )


def has_real_experience(inventory: dict[str, Any]) -> bool:
    return bool((inventory.get("experiences") or []) or (inventory.get("projects") or []))

