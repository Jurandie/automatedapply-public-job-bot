from __future__ import annotations

import re


def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    if any(token in lowered for token in ("eur", "euro")) or "€" in text:
        return "EUR"
    if any(token in lowered for token in ("usd", "us$", "dollar")) or "$" in text:
        return "USD"
    if any(token in lowered for token in ("gbp", "pound")) or "£" in text:
        return "GBP"
    return None


def parse_salary_range(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None

    numbers = []
    for raw in re.findall(r"(?<!\w)(\d{2,3})(?:[,.]?000|k)?(?!\w)", text.lower()):
        value = int(raw)
        if value < 1000:
            value *= 1000
        numbers.append(value)

    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], None
    return min(numbers[:2]), max(numbers[:2])

