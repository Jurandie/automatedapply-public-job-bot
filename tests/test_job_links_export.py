import tempfile
import unittest
from pathlib import Path

from app.classification.rules import classify_post
from app.review.job_links import export_job_links
from app.storage.db import Database
from app.storage.models import LinkedInPost


class JobLinksExportTest(unittest.TestCase):
    def test_export_job_links_writes_unique_links_to_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()
            post = LinkedInPost(
                id="p1",
                source_url="manual",
                post_text="Hiring Junior Python Engineer remote Ireland apply https://jobs.lever.co/acme/1",
            )
            result = classify_post(
                post.post_text,
                [
                    "https://jobs.lever.co/acme/1?utm_source=search",
                    "https://jobs.lever.co/acme/1#apply",
                    "https://jobs.ashbyhq.com/acme/2",
                ],
            )
            db.upsert_post(post)
            db.upsert_job(result.to_job(source_post_id=post.id, post_text=post.post_text))

            output = Path(tmp) / "vagas_links.txt"
            exported = export_job_links(db, output)

            text = output.read_text(encoding="utf-8")
            self.assertEqual(exported.total_links, 2)
            self.assertIn("Links de vagas", text)
            self.assertIn("https://jobs.lever.co/acme/1?utm_source=search", text)
            self.assertIn("https://jobs.ashbyhq.com/acme/2", text)

    def test_export_job_links_can_filter_by_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()
            post = LinkedInPost(
                id="p1",
                source_url="manual",
                post_text="Hiring Junior Python Engineer remote Ireland apply https://jobs.lever.co/acme/1",
            )
            result = classify_post(post.post_text, ["https://jobs.lever.co/acme/1"])
            db.upsert_post(post)
            db.upsert_job(result.to_job(source_post_id=post.id, post_text=post.post_text))

            output = Path(tmp) / "rejected_links.txt"
            exported = export_job_links(db, output, status="rejected")

            self.assertEqual(exported.total_links, 0)
            self.assertIn("Nenhum link de vaga encontrado.", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
