import tempfile
import unittest
from pathlib import Path

from app.reputation.glassdoor import GlassdoorRatingGate


class GlassdoorRatingGateTest(unittest.TestCase):
    def test_missing_rating_is_blocked_when_required(self):
        gate = GlassdoorRatingGate(require_verified_rating=True)

        result = gate.check("Acme")

        self.assertFalse(result.allowed)
        self.assertIn("missing", result.reason.lower())
        self.assertIn("glassdoor", result.search_url.lower())

    def test_glassdoor_rating_above_minimum_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ratings.yaml"
            path.write_text(
                """
settings:
  minimum_rating: 3.5
  require_verified_rating: true
  max_age_days:
ratings:
  - company: Acme
    source: glassdoor
    rating: 4.0
    review_count: 100
    glassdoor_url: https://ratings.example/acme-reviews
    checked_at: "2026-04-21"
""",
                encoding="utf-8",
            )

            result = GlassdoorRatingGate.from_yaml(path).check("Acme")

        self.assertTrue(result.allowed)
        self.assertEqual(result.rating, 4.0)

    def test_rating_below_minimum_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ratings.yaml"
            path.write_text(
                """
settings:
  minimum_rating: 3.5
  require_verified_rating: true
  max_age_days:
ratings:
  - company: Acme
    source: glassdoor
    rating: 3.1
    checked_at: "2026-04-21"
""",
                encoding="utf-8",
            )

            result = GlassdoorRatingGate.from_yaml(path).check("Acme")

        self.assertFalse(result.allowed)
        self.assertIn("below", result.reason)


if __name__ == "__main__":
    unittest.main()
