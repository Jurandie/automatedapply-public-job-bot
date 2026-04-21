import unittest

from app.browser.company_sites import _looks_like_job_url_or_text, _looks_like_listing_url, safe_page_evaluate
from app.browser.company_sites import CompanyCareerSource, CompanyJobCollector
from app.main import _build_company_sources


class FlakyEvaluatePage:
    def __init__(self):
        self.calls = 0
        self.waits = 0

    def evaluate(self, script, arg=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        return [{"url": "https://example.com/jobs/1"}]

    def wait_for_load_state(self, *_args, **_kwargs):
        self.waits += 1

    def wait_for_timeout(self, *_args, **_kwargs):
        self.waits += 1


class PageThatMustNotNavigate:
    def __init__(self):
        self.goto_calls = 0

    def goto(self, *_args, **_kwargs):
        self.goto_calls += 1
        raise AssertionError("duplicate job page should not be opened")


class CompanySourcesTest(unittest.TestCase):
    def test_build_company_sources_filters_to_target_countries(self):
        sources = _build_company_sources(
            {
                "company_sources": {
                    "target_countries": ["Italy", "Ireland"],
                    "companies": [
                        {
                            "name": "Milano Tech",
                            "country": "Italy",
                            "careers_url": "https://example.com/careers/",
                        },
                        {
                            "name": "Berlin Tech",
                            "country": "Germany",
                            "careers_url": "https://example.org/careers/",
                        },
                    ],
                }
            }
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "Milano Tech")
        self.assertEqual(sources[0].country, "Italy")

    def test_company_job_link_detection_accepts_common_ats(self):
        self.assertTrue(
            _looks_like_job_url_or_text(
                "https://apply.workable.com/acme/j/123/",
                "Junior Python Developer - Dublin, Ireland",
            )
        )

    def test_company_job_link_detection_rejects_social_links(self):
        self.assertFalse(
            _looks_like_job_url_or_text(
                "https://www.linkedin.com/company/acme",
                "Follow Acme",
            )
        )

    def test_listing_pages_are_not_treated_as_single_jobs(self):
        self.assertTrue(
            _looks_like_listing_url(
                "https://www.intercom.com/careers/listings",
                "See open roles",
            )
        )
        self.assertFalse(
            _looks_like_listing_url(
                "https://jobs.ashbyhq.com/acme/abc123",
                "Junior Python Engineer - Dublin, Ireland",
            )
        )

    def test_safe_page_evaluate_retries_transient_navigation_error(self):
        page = FlakyEvaluatePage()

        result = safe_page_evaluate(page, "() => []", default=[])

        self.assertEqual(result, [{"url": "https://example.com/jobs/1"}])
        self.assertEqual(page.calls, 2)
        self.assertGreater(page.waits, 0)

    def test_collect_job_page_skips_known_job_url_before_navigation(self):
        page = PageThatMustNotNavigate()
        collector = CompanyJobCollector(
            known_job_urls={"https://jobs.lever.co/acme/123?utm_source=old#apply"}
        )
        source = CompanyCareerSource(name="Acme", careers_url="https://acme.test/careers")

        job = collector._collect_job_page(
            page,
            source,
            {"url": "https://jobs.lever.co/acme/123?gh_src=new", "text": "Junior Python Engineer"},
        )

        self.assertIsNone(job)
        self.assertEqual(page.goto_calls, 0)


if __name__ == "__main__":
    unittest.main()
