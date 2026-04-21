import tempfile
import unittest
from pathlib import Path

from app.application.runner import ApplyRunOptions, run_apply
from app.classification.rules import classify_post
from app.storage.db import Database
from app.storage.models import LinkedInPost


class RunnerTest(unittest.TestCase):
    def test_dry_run_does_not_require_playwright_or_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()
            post = LinkedInPost(
                id="p1",
                source_url="manual",
                post_text="Hiring Junior Python Engineer remote Italy apply https://jobs.ashbyhq.com/acme/1",
            )
            result = classify_post(post.post_text, ["https://jobs.ashbyhq.com/acme/1"])
            db.upsert_post(post)
            db.upsert_job(result.to_job(source_post_id=post.id, post_text=post.post_text))

            results = run_apply(db, ApplyRunOptions(mode="dry_run"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "dry_run")
        self.assertFalse(results[0]["filled"])

    def test_dry_run_blocks_stale_placeholder_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()
            post = LinkedInPost(
                id="p1",
                source_url="manual",
                post_text="Hiring Junior Python Engineer remote Italy apply https://jobs.ashbyhq.com/acme/1",
            )
            result = classify_post(post.post_text, ["https://jobs.ashbyhq.com/acme/1"])
            stale_job = result.to_job(source_post_id=post.id, post_text=post.post_text)
            stale_job = stale_job.__class__(
                **{
                    **stale_job.__dict__,
                    "application_url": "https://jobs.ashbyhq.com/example/123",
                }
            )
            db.upsert_post(post)
            db.upsert_job(stale_job)

            results = run_apply(db, ApplyRunOptions(mode="dry_run"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("placeholder", results[0]["reason"])


if __name__ == "__main__":
    unittest.main()
