import tempfile
import unittest
from pathlib import Path

from app.classification.rules import classify_post
from app.storage.db import Database
from app.storage.models import LinkedInPost


class DatabaseTest(unittest.TestCase):
    def test_init_and_store_post_job(self):
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

            self.assertEqual(db.count("linkedin_posts"), 1)
            self.assertEqual(db.count("jobs"), 1)

    def test_list_known_job_urls_normalizes_posts_jobs_and_raw_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()
            post = LinkedInPost(
                id="p1",
                source_url="manual",
                post_text="Hiring Junior Python Engineer remote Italy apply https://jobs.ashbyhq.com/acme/1",
                post_url="https://Jobs.AshbyHQ.com/acme/1?utm_source=search#apply",
            )
            result = classify_post(
                post.post_text,
                [
                    "https://jobs.ashbyhq.com/acme/1?utm_source=search#apply",
                    "https://jobs.lever.co/acme/2?gh_src=abc",
                ],
            )
            db.upsert_post(post)
            db.upsert_job(result.to_job(source_post_id=post.id, post_text=post.post_text))

            self.assertEqual(
                db.list_known_job_urls(),
                {
                    "https://jobs.ashbyhq.com/acme/1",
                    "https://jobs.lever.co/acme/2",
                },
            )


if __name__ == "__main__":
    unittest.main()
