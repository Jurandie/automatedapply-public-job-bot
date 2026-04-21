import tempfile
import unittest
from pathlib import Path

from app.resume.tailoring import maybe_tailor_resume_for_job, tailor_resume_for_job


def inventory():
    return {
        "basics": {
            "headline": "Backend Engineer",
            "summary": "Engenheiro com experiencia em automacao e backend Python.",
        },
        "skills": [
            {"name": "Python", "aliases": ["python"]},
            {"name": "FastAPI", "aliases": ["fastapi"]},
            {"name": "Playwright", "aliases": ["playwright"]},
            {"name": "PostgreSQL", "aliases": ["postgresql"]},
        ],
        "experiences": [
            {
                "id": "exp-automation",
                "company": "Minha Empresa",
                "title": "Python Automation Engineer",
                "start": "2022",
                "end": "2025",
                "skills": ["python", "playwright", "fastapi"],
                "bullets": [
                    {
                        "id": "exp-automation-1",
                        "text": "Criei automacoes em Python com Playwright para reduzir tarefas manuais de operacao.",
                        "skills": ["python", "playwright"],
                    },
                    {
                        "id": "exp-automation-2",
                        "text": "Implementei APIs internas com FastAPI para integrar fluxos operacionais.",
                        "skills": ["python", "fastapi"],
                    },
                ],
            }
        ],
        "projects": [
            {
                "id": "proj-data",
                "name": "Data Pipeline",
                "skills": ["python", "postgresql"],
                "bullets": [
                    {
                        "id": "proj-data-1",
                        "text": "Modelei rotinas de carga em PostgreSQL para relatorios internos.",
                        "skills": ["python", "postgresql"],
                    }
                ],
            }
        ],
    }


class ResumeTailoringTest(unittest.TestCase):
    def test_generates_grounded_tailored_resume_from_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = tailor_resume_for_job(
                profile={
                    "name": "Ada Lovelace",
                    "email": "ada@example.com",
                    "location": "Ireland",
                    "linkedin": "https://linkedin.com/in/ada",
                },
                inventory=inventory(),
                job={
                    "id": "job-1",
                    "title": "Senior Python Backend Engineer",
                    "company": "Acme",
                    "location": "Remote Europe",
                },
                job_description="We need Python, FastAPI, Playwright and PostgreSQL experience.",
                output_dir=Path(tmp),
                minimum_evidence=2,
            )

            self.assertTrue(result.grounded)
            self.assertEqual(result.evidence_count, 3)
            markdown = Path(result.markdown_path).read_text(encoding="utf-8")
            self.assertIn("Criei automacoes em Python com Playwright", markdown)
            self.assertIn("Implementei APIs internas com FastAPI", markdown)
            self.assertNotIn("Kubernetes", markdown)
            self.assertTrue(Path(result.evidence_path).exists())

    def test_blocks_when_there_is_not_enough_matched_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = tailor_resume_for_job(
                profile={"name": "Ada Lovelace", "email": "ada@example.com"},
                inventory=inventory(),
                job={"id": "job-2", "title": "Kubernetes Platform Engineer"},
                job_description="Kubernetes, Terraform, AWS EKS.",
                output_dir=Path(tmp),
                minimum_evidence=2,
            )

            self.assertFalse(result.grounded)
            self.assertIsNone(result.markdown_path)
            self.assertIn("not enough matched evidence", result.warnings[0])

    def test_maybe_tailor_respects_disabled_setting(self):
        result = maybe_tailor_resume_for_job(
            profile={"resume_tailoring": {"enabled": False}},
            job={"id": "job-3", "title": "Python Engineer"},
        )

        self.assertFalse(result.enabled)
        self.assertFalse(result.grounded)


if __name__ == "__main__":
    unittest.main()
