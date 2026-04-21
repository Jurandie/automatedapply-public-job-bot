import unittest

from app.browser.linkedin_posts import build_linkedin_search_url
from app.main import _build_sources


class LinkedInSourcesTest(unittest.TestCase):
    def test_build_sources_includes_search_terms(self):
        sources = _build_sources(
            {
                "linkedin_sources": {
                    "companies": [],
                    "people": [],
                    "search_terms": ["python developer remote europe"],
                }
            }
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].kind, "search")
        self.assertIn("/search/results/content/", sources[0].url)
        self.assertIn("python+developer+remote+europe", sources[0].url)

    def test_search_url_uses_recent_posts_filters(self):
        url = build_linkedin_search_url("backend engineer remote eur")

        self.assertIn("sortBy=%22date_posted%22", url)
        self.assertIn("datePosted=%22past-week%22", url)


if __name__ == "__main__":
    unittest.main()

