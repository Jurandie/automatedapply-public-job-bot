import unittest

from app.classification.profile_fit import allowed_seniority_from_profile, apply_profile_fit
from app.classification.rules import classify_post


def inventory():
    return {
        "skills": [
            {"name": "Python", "aliases": ["python"]},
            {"name": "Flutter", "aliases": ["flutter"]},
            {"name": "Kotlin", "aliases": ["kotlin"]},
            {"name": "REST APIs", "aliases": ["rest api", "rest apis"]},
        ],
        "experiences": [
            {
                "id": "exp-python",
                "title": "Python Automation Developer",
                "skills": ["python", "automation", "rest apis"],
                "bullets": [
                    {
                        "id": "exp-python-1",
                        "text": "Developed modular scripts for process automation and integration with external APIs.",
                        "skills": ["python", "automation", "rest apis"],
                    },
                    {
                        "id": "exp-python-2",
                        "text": "Built REST API integrations for operational workflows.",
                        "skills": ["rest apis", "python"],
                    },
                ],
            }
        ],
        "projects": [],
    }


class ProfileFitTest(unittest.TestCase):
    def test_ready_job_stays_ready_when_profile_and_cv_match(self):
        profile = {
            "preferences": {"roles": ["Python Developer"], "seniority": ["junior"]},
            "resume_tailoring": {"minimum_matched_evidence": 2},
        }
        result = classify_post(
            "We are hiring a Junior Python Developer remote within Ireland. Build Python REST APIs.",
            ["https://jobs.ashbyhq.com/acme/123"],
            allowed_seniority=allowed_seniority_from_profile(profile),
        )

        adjusted = apply_profile_fit(result, "Junior Python Developer Python REST APIs", profile, inventory())

        self.assertEqual(adjusted.eligibility_status, "ready_to_apply")
        self.assertIn("profile/CV fit confirmed", adjusted.reason)

    def test_ready_job_moves_to_review_without_cv_evidence(self):
        profile = {
            "preferences": {"roles": ["Data Engineer"], "seniority": ["junior"]},
            "resume_tailoring": {"minimum_matched_evidence": 2},
        }
        result = classify_post(
            "We are hiring a Junior Data Engineer remote within Ireland. Hadoop Spark pipelines.",
            ["https://jobs.ashbyhq.com/acme/123"],
            allowed_seniority=allowed_seniority_from_profile(profile),
        )

        adjusted = apply_profile_fit(result, "Junior Data Engineer Hadoop Spark pipelines", profile, inventory())

        self.assertEqual(adjusted.eligibility_status, "needs_review")
        self.assertIn("CV evidence below minimum", adjusted.reason)

    def test_senior_only_allowed_when_profile_allows_it(self):
        blocked = classify_post(
            "We are hiring a Senior Python Engineer remote within Ireland.",
            ["https://jobs.ashbyhq.com/acme/123"],
            allowed_seniority={"junior"},
        )
        allowed = classify_post(
            "We are hiring a Senior Python Engineer remote within Ireland.",
            ["https://jobs.ashbyhq.com/acme/123"],
            allowed_seniority={"senior"},
        )

        self.assertEqual(blocked.eligibility_status, "rejected")
        self.assertEqual(allowed.seniority, "senior")


if __name__ == "__main__":
    unittest.main()
