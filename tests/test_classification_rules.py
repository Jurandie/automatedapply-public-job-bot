import unittest

from app.classification.rules import classify_post


class ClassificationRulesTest(unittest.TestCase):
    def test_remote_italy_eur_job_is_ready(self):
        result = classify_post(
            "We are hiring a Junior Python Engineer remote within Italy. Salary EUR 50000.",
            ["https://jobs.ashbyhq.com/acme/123"],
            company="Acme",
        )
        self.assertTrue(result.is_job_post)
        self.assertEqual(result.eligibility_status, "ready_to_apply")
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.ats_type, "ashby")

    def test_us_only_remote_is_rejected(self):
        result = classify_post(
            "Hiring Backend Developer remote US only.",
            ["https://jobs.lever.co/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "rejected")

    def test_onsite_ireland_is_ready(self):
        result = classify_post(
            "Open role for Pleno Automation Engineer onsite in Dublin, Ireland.",
            ["https://boards.greenhouse.io/acme/jobs/123"],
        )
        self.assertEqual(result.eligibility_status, "ready_to_apply")

    def test_senior_job_is_rejected(self):
        result = classify_post(
            "We are hiring a Senior Python Engineer remote within Italy.",
            ["https://jobs.ashbyhq.com/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "rejected")
        self.assertEqual(result.seniority, "rejected_seniority")

    def test_unknown_seniority_needs_review(self):
        result = classify_post(
            "We are hiring a Python Engineer remote within Ireland.",
            ["https://jobs.ashbyhq.com/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "needs_review")
        self.assertIn("seniority not explicit", result.reason)

    def test_generic_europe_is_rejected(self):
        result = classify_post(
            "We are hiring a Junior Python Engineer remote within Europe.",
            ["https://jobs.ashbyhq.com/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "rejected")
        self.assertIn("target countries", result.reason)

    def test_remote_germany_is_rejected(self):
        result = classify_post(
            "We are hiring a Junior Python Engineer remote in Germany.",
            ["https://jobs.ashbyhq.com/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "rejected")

    def test_italy_onsite_is_rejected_by_current_policy(self):
        result = classify_post(
            "Open role for Pleno Automation Engineer onsite in Milan, Italy.",
            ["https://boards.greenhouse.io/acme/jobs/123"],
        )
        self.assertEqual(result.eligibility_status, "rejected")
        self.assertIn("Ireland", result.reason)

    def test_remote_ireland_is_ready(self):
        result = classify_post(
            "We are hiring a Junior Python Engineer remote Ireland. Salary EUR 50000.",
            ["https://jobs.ashbyhq.com/acme/123"],
            company="Acme",
        )
        self.assertEqual(result.eligibility_status, "ready_to_apply")
        self.assertEqual(result.location, "Ireland")

    def test_hybrid_ireland_is_ready(self):
        result = classify_post(
            "Open role for Pleno Flutter Developer hybrid in Dublin, Ireland.",
            ["https://jobs.lever.co/acme/123"],
        )
        self.assertEqual(result.eligibility_status, "ready_to_apply")
        self.assertEqual(result.location, "Ireland")

    def test_unpaid_is_rejected(self):
        result = classify_post(
            "We are hiring a Junior Python Developer remote Italy unpaid volunteer role.",
            ["https://example.com/careers/python"],
        )
        self.assertEqual(result.eligibility_status, "rejected")

    def test_placeholder_application_url_is_not_ready_to_apply(self):
        result = classify_post(
            "We are hiring a Junior Python Engineer remote within Italy. Apply here.",
            ["https://jobs.ashbyhq.com/example/123"],
        )
        self.assertEqual(result.eligibility_status, "needs_review")
        self.assertEqual(result.application_links, [])


if __name__ == "__main__":
    unittest.main()
