import unittest

from app.extraction.link_extractor import (
    canonical_job_url,
    extract_html_links,
    extract_urls,
    is_placeholder_url,
    select_application_links,
)


class LinkExtractorTest(unittest.TestCase):
    def test_extract_urls_strips_trailing_punctuation(self):
        text = "Apply: https://jobs.ashbyhq.com/example/123."
        self.assertEqual(extract_urls(text), ["https://jobs.ashbyhq.com/example/123"])

    def test_extract_html_links(self):
        html = '<a href="https://boards.greenhouse.io/acme/jobs/1">Apply</a>'
        self.assertEqual(extract_html_links(html), ["https://boards.greenhouse.io/acme/jobs/1"])

    def test_select_application_links(self):
        links = ["https://example.com", "https://jobs.lever.co/acme/123"]
        self.assertEqual(select_application_links(links), ["https://jobs.lever.co/acme/123"])

    def test_select_application_links_accepts_company_job_pages(self):
        links = ["https://company.test/about", "https://company.test/positions/backend-engineer"]
        self.assertEqual(select_application_links(links), ["https://company.test/positions/backend-engineer"])

    def test_placeholder_application_links_are_rejected(self):
        links = [
            "https://jobs.ashbyhq.com/example/123",
            "https://example.invalid/jobs/backend",
            "https://jobs.lever.co/acme/123",
        ]
        self.assertEqual(select_application_links(links), ["https://jobs.lever.co/acme/123"])
        self.assertTrue(is_placeholder_url("https://jobs.ashbyhq.com/example/123"))

    def test_canonical_job_url_ignores_tracking_and_fragment(self):
        self.assertEqual(
            canonical_job_url("https://Jobs.Lever.co/acme/123/?utm_source=ddg&gh_src=abc#apply"),
            "https://jobs.lever.co/acme/123",
        )

    def test_canonical_job_url_keeps_meaningful_query_params_sorted(self):
        self.assertEqual(
            canonical_job_url("https://company.test/jobs?b=2&utm_campaign=x&a=1"),
            "https://company.test/jobs?a=1&b=2",
        )


if __name__ == "__main__":
    unittest.main()
