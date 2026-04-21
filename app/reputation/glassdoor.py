from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from app.config import DEFAULT_COMPANY_RATINGS_PATH, ConfigError, load_yaml


@dataclass(frozen=True)
class GlassdoorRatingResult:
    company: str
    allowed: bool
    reason: str
    rating: float | None = None
    review_count: int | None = None
    glassdoor_url: str | None = None
    search_url: str | None = None
    checked_at: str | None = None


class GlassdoorRatingGate:
    def __init__(
        self,
        path: Path = DEFAULT_COMPANY_RATINGS_PATH,
        minimum_rating: float = 3.5,
        require_verified_rating: bool = True,
        max_age_days: int | None = 120,
    ):
        self.path = path
        self.minimum_rating = minimum_rating
        self.require_verified_rating = require_verified_rating
        self.max_age_days = max_age_days
        self._ratings: dict[str, dict] = {}

    @classmethod
    def from_yaml(cls, path: Path = DEFAULT_COMPANY_RATINGS_PATH) -> "GlassdoorRatingGate":
        if not path.exists():
            return cls(path=path)

        data = load_yaml(path)
        settings = data.get("settings", {}) or {}
        gate = cls(
            path=path,
            minimum_rating=float(settings.get("minimum_rating", 3.5)),
            require_verified_rating=bool(settings.get("require_verified_rating", True)),
            max_age_days=_optional_int(settings.get("max_age_days", 120)),
        )
        ratings = data.get("ratings", []) or []
        if not isinstance(ratings, list):
            raise ConfigError(f"{path} precisa usar ratings como lista.")

        for item in ratings:
            if not isinstance(item, dict):
                continue
            company = str(item.get("company") or "").strip()
            if not company:
                continue
            gate._ratings[_normalize_company(company)] = item
        return gate

    def check(self, company: str) -> GlassdoorRatingResult:
        company = str(company or "").strip()
        search_url = build_glassdoor_search_url(company)
        item = self._ratings.get(_normalize_company(company))
        if not item:
            if self.require_verified_rating:
                return GlassdoorRatingResult(
                    company=company,
                    allowed=False,
                    reason="Glassdoor rating missing",
                    search_url=search_url,
                )
            return GlassdoorRatingResult(
                company=company,
                allowed=True,
                reason="Glassdoor rating missing but not required",
                search_url=search_url,
            )

        source = str(item.get("source") or "").strip().lower()
        rating = _optional_float(item.get("rating"))
        review_count = _optional_int(item.get("review_count"))
        checked_at = str(item.get("checked_at") or "").strip() or None
        glassdoor_url = str(item.get("glassdoor_url") or "").strip() or None

        if source != "glassdoor":
            return GlassdoorRatingResult(
                company=company,
                allowed=False,
                reason="rating source is not Glassdoor",
                rating=rating,
                review_count=review_count,
                glassdoor_url=glassdoor_url,
                search_url=search_url,
                checked_at=checked_at,
            )

        if rating is None:
            return GlassdoorRatingResult(
                company=company,
                allowed=False,
                reason="Glassdoor rating has no numeric value",
                glassdoor_url=glassdoor_url,
                search_url=search_url,
                checked_at=checked_at,
            )

        if self.max_age_days is not None and checked_at and _is_stale(checked_at, self.max_age_days):
            return GlassdoorRatingResult(
                company=company,
                allowed=False,
                reason=f"Glassdoor rating older than {self.max_age_days} days",
                rating=rating,
                review_count=review_count,
                glassdoor_url=glassdoor_url,
                search_url=search_url,
                checked_at=checked_at,
            )

        if rating < self.minimum_rating:
            return GlassdoorRatingResult(
                company=company,
                allowed=False,
                reason=f"Glassdoor rating below minimum {self.minimum_rating:g}",
                rating=rating,
                review_count=review_count,
                glassdoor_url=glassdoor_url,
                search_url=search_url,
                checked_at=checked_at,
            )

        return GlassdoorRatingResult(
            company=company,
            allowed=True,
            reason="Glassdoor rating accepted",
            rating=rating,
            review_count=review_count,
            glassdoor_url=glassdoor_url,
            search_url=search_url,
            checked_at=checked_at,
        )


def build_glassdoor_search_url(company: str) -> str:
    query = quote_plus(f"{company} Glassdoor reviews")
    return f"https://www.glassdoor.com/Search/results.htm?keyword={query}"


def _normalize_company(company: str) -> str:
    return " ".join(company.lower().replace(".", " ").split())


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_stale(raw_date: str, max_age_days: int) -> bool:
    try:
        checked = date.fromisoformat(raw_date[:10])
    except ValueError:
        return True
    today = datetime.now(timezone.utc).date()
    return (today - checked).days > max_age_days
