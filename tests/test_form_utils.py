import unittest

from app.application.form_utils import (
    build_candidate_field_values,
    is_known_candidate_control,
    is_sensitive_control,
    summarize_required_controls,
)
from app.application.submit_policy import evaluate_submit_policy


class FormUtilsTest(unittest.TestCase):
    def test_build_candidate_field_values_splits_name(self):
        values = build_candidate_field_values(
            {
                "name": "Ada Lovelace",
                "email": "ada@example.com",
                "phone": "+353123",
                "linkedin": "https://linkedin.com/in/ada",
            }
        )

        self.assertEqual(values["first_name"], "Ada")
        self.assertEqual(values["last_name"], "Lovelace")
        self.assertEqual(values["full_name"], "Ada Lovelace")
        self.assertEqual(values["email"], "ada@example.com")

    def test_required_summary_blocks_sensitive_and_unknown_fields(self):
        summary = summarize_required_controls(
            [
                {
                    "required": True,
                    "visible": True,
                    "disabled": False,
                    "type": "text",
                    "label": "Expected salary",
                    "name": "salary",
                    "value": "",
                },
                {
                    "required": True,
                    "visible": True,
                    "disabled": False,
                    "type": "textarea",
                    "label": "Why do you want this role?",
                    "name": "question",
                    "value": "",
                },
            ]
        )

        self.assertFalse(summary["valid"])
        self.assertEqual(summary["blocking_required_fields"], 2)
        self.assertEqual(summary["unknown_required_fields"], 2)
        self.assertEqual(len(summary["sensitive_required_field_details"]), 1)

    def test_known_empty_resume_is_a_blocker(self):
        summary = summarize_required_controls(
            [
                {
                    "required": True,
                    "visible": True,
                    "disabled": False,
                    "type": "file",
                    "label": "Resume",
                    "name": "resume",
                    "files_count": 0,
                }
            ]
        )

        self.assertFalse(summary["valid"])
        self.assertEqual(summary["blocking_required_fields"], 1)
        self.assertEqual(summary["unknown_required_fields"], 0)
        self.assertEqual(len(summary["missing_known_fields"]), 1)

    def test_known_and_sensitive_control_detection(self):
        self.assertTrue(is_known_candidate_control({"label": "LinkedIn URL"}))
        self.assertTrue(is_sensitive_control({"label": "Work authorization"}))

    def test_submit_policy_blocks_unfilled_required_fields(self):
        decision = evaluate_submit_policy(
            mode="auto_submit_safe",
            eligibility_status="ready_to_apply",
            confidence=0.95,
            ats_type="ashby",
            unknown_required_fields=1,
        )

        self.assertFalse(decision.can_submit)
        self.assertEqual(decision.reason, "unfilled required fields block automation")


if __name__ == "__main__":
    unittest.main()

