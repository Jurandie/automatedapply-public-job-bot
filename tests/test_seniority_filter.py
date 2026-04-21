import unittest

from app.classification.seniority_filter import detect_seniority


class SeniorityFilterTest(unittest.TestCase):
    def test_allows_junior_and_pleno(self):
        self.assertEqual(detect_seniority("Junior Python Developer")[0], "junior")
        self.assertEqual(detect_seniority("Pleno Backend Engineer")[0], "pleno")
        self.assertEqual(detect_seniority("Mid-level Automation Engineer")[0], "pleno")

    def test_rejects_senior_and_lead(self):
        self.assertEqual(detect_seniority("Senior Python Engineer")[0], "rejected_seniority")
        self.assertEqual(detect_seniority("Lead Backend Developer")[0], "rejected_seniority")
        self.assertEqual(detect_seniority("Principal Software Engineer")[0], "rejected_seniority")

    def test_unknown_seniority(self):
        self.assertIsNone(detect_seniority("Python Engineer")[0])


if __name__ == "__main__":
    unittest.main()
