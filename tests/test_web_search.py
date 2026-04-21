import unittest

from app.browser.web_search import (
    WebJobSearchCollector,
    build_workable_search_url,
    build_job_search_queries,
    decode_search_result_url,
    guess_company_from_url_or_text,
    _same_document_url,
    _looks_like_career_page_candidate,
)
from app.main import build_parser


class WebSearchTest(unittest.TestCase):
    def test_scan_company_sites_uses_web_discovery_by_default(self):
        args = build_parser().parse_args(["scan-company-sites"])

        self.assertEqual(args.source_mode, "web")
        self.assertFalse(args.require_glassdoor_gate)

    def test_build_job_search_queries_uses_profile_targets(self):
        queries = build_job_search_queries(
            {
                "company_sources": {
                    "target_countries": ["Italy", "Ireland"],
                    "companies": [
                        {
                            "name": "Microsoft",
                            "country": "Ireland",
                            "careers_url": "https://company.example/ireland-careers",
                        }
                    ],
                }
            },
            {
                "preferences": {
                    "roles": ["Python Developer"],
                    "seniority": ["junior"],
                    "allowed_countries": ["Ireland"],
                }
            },
            max_queries=3,
        )

        self.assertTrue(queries)
        self.assertTrue(all(query.country == "Ireland" for query in queries))
        self.assertEqual(queries[0].company, "Microsoft")
        self.assertEqual(queries[0].provider, "career_page")

    def test_build_job_search_queries_interleaves_countries(self):
        queries = build_job_search_queries(
            {},
            {
                "preferences": {
                    "roles": ["Python Developer"],
                    "seniority": ["junior"],
                    "allowed_countries": ["Italy", "Ireland"],
                }
            },
            max_queries=2,
        )

        self.assertEqual([query.country for query in queries], ["Italy", "Ireland"])

    def test_build_job_search_queries_interleaves_company_countries(self):
        queries = build_job_search_queries(
            {
                "company_sources": {
                    "target_countries": ["Italy", "Ireland"],
                    "companies": [
                        {"name": "IrelandCo", "country": "Ireland", "careers_url": "https://ie.example/jobs"},
                        {"name": "ItalyCo", "country": "Italy", "careers_url": "https://it.example/jobs"},
                    ],
                }
            },
            {
                "preferences": {
                    "roles": ["Python Developer"],
                    "seniority": ["junior"],
                    "allowed_countries": ["Italy", "Ireland"],
                }
            },
            max_queries=6,
        )

        self.assertEqual([query.company for query in queries[0:6:3]], ["ItalyCo", "IrelandCo"])

    def test_build_job_search_queries_adds_company_specific_searches(self):
        queries = build_job_search_queries(
            {
                "web_search": {
                    "target_companies": [
                        {"name": "Google", "country": "Ireland"},
                    ]
                }
            },
            {
                "preferences": {
                    "roles": ["Backend Engineer"],
                    "seniority": ["mid"],
                    "allowed_countries": ["Ireland"],
                }
            },
            max_queries=2,
        )

        self.assertEqual(queries[0].company, "Google")
        self.assertIn("visa sponsorship", queries[0].text)

    def test_decode_duckduckgo_result_url(self):
        decoded = decode_search_result_url(
            "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fjobs.lever.co%2Facme%2Fabc"
        )

        self.assertEqual(decoded, "https://jobs.lever.co/acme/abc")

    def test_guess_company_from_common_ats_url(self):
        company = guess_company_from_url_or_text("https://jobs.lever.co/acme-tech/abc", "")

        self.assertEqual(company, "Acme Tech")

    def test_guess_company_from_workable_view_url(self):
        company = guess_company_from_url_or_text(
            "https://jobs.workable.com/view/abc/remote-python-developer-in-italy-at-acme-tech",
            "",
        )

        self.assertEqual(company, "Acme Tech")

    def test_build_workable_search_url_filters_by_country(self):
        url = build_workable_search_url("junior Python Developer", "Ireland")

        self.assertIn("jobs.workable.com/search", url)
        self.assertIn("location=Ireland", url)

    def test_same_document_url_ignores_fragments(self):
        self.assertTrue(
            _same_document_url(
                "https://company.example/careers",
                "https://company.example/careers#hero",
            )
        )
        self.assertFalse(
            _same_document_url(
                "https://company.example/careers",
                "https://company.example/jobs/software-engineer",
            )
        )

    def test_career_page_candidate_rejects_navigation_links(self):
        self.assertFalse(
            _looks_like_career_page_candidate(
                "https://company.example/media-centre",
                "Services Industries Media Centre Careers About Us",
            )
        )
        self.assertTrue(
            _looks_like_career_page_candidate(
                "https://example.com/jobs/software-engineer",
                "Software Engineer Apply Full-time",
            )
        )

    def test_web_collector_recognizes_known_job_url_variants(self):
        collector = WebJobSearchCollector(
            known_job_urls={"https://jobs.lever.co/acme/123?utm_source=old#apply"}
        )

        self.assertTrue(collector._is_known_job_url("https://jobs.lever.co/acme/123?gh_src=new"))


if __name__ == "__main__":
    unittest.main()
