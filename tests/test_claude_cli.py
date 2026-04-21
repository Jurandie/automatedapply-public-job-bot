import os
import subprocess
import unittest
from unittest.mock import patch

from app.integrations.claude_cli import (
    build_classification_prompt,
    classify_post_with_script,
    parse_claude_json_response,
)


class ClaudeCliTest(unittest.TestCase):
    def test_classification_uses_hidden_direct_claude_call(self):
        response = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"is_job_post": false}',
            stderr="",
        )
        with patch("app.integrations.claude_cli.shutil.which", return_value=r"C:\Tools\claude.exe"):
            with patch("app.integrations.claude_cli.subprocess.run", return_value=response) as run:
                result = classify_post_with_script("Junior Python Developer - Remote Ireland")

        self.assertEqual(result["is_job_post"], False)
        command = run.call_args.args[0]
        lowered = " ".join(str(part).lower() for part in command)
        self.assertEqual(command[0], r"C:\Tools\claude.exe")
        self.assertNotIn("powershell", lowered)
        self.assertNotIn("cmd.exe", lowered)
        self.assertIn("-p", command)
        self.assertNotIn("--json-schema", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("Ireland", command[-1])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertIn("creationflags", run.call_args.kwargs)
            self.assertIn("startupinfo", run.call_args.kwargs)

    def test_classification_prompt_mentions_target_policy(self):
        prompt = build_classification_prompt("vaga")

        self.assertNotIn("Spain", prompt)
        self.assertIn("Italy ou Ireland", prompt)
        self.assertIn("Italia ou Irlanda", prompt)

    def test_parse_claude_json_response_accepts_fenced_json(self):
        parsed = parse_claude_json_response(
            '```json\n{"is_job_post": true, "reason": "ok"}\n```'
        )

        self.assertEqual(parsed["reason"], "ok")

    def test_parse_claude_json_response_extracts_first_object(self):
        parsed = parse_claude_json_response(
            'Segue o JSON:\n{"is_job_post": false, "reason": "ambigua"}\nFim.'
        )

        self.assertEqual(parsed["reason"], "ambigua")


if __name__ == "__main__":
    unittest.main()
