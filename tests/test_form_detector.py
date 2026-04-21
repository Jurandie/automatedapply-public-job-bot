import unittest

from app.browser.form_detector import detect_ats_type


class FormDetectorTest(unittest.TestCase):
    def test_detect_known_ats(self):
        self.assertEqual(detect_ats_type("https://jobs.ashbyhq.com/acme/123"), "ashby")
        self.assertEqual(detect_ats_type("https://jobs.lever.co/acme/123"), "lever")
        self.assertEqual(
            detect_ats_type("https://boards.greenhouse.io/acme/jobs/123"),
            "greenhouse",
        )
        self.assertEqual(detect_ats_type("https://apply.workable.com/acme/j/123"), "workable")

    def test_detect_generic_form(self):
        self.assertEqual(
            detect_ats_type("https://example.com/apply", "<form></form>"),
            "generic_form",
        )


if __name__ == "__main__":
    unittest.main()
