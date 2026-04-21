import tempfile
import unittest
from pathlib import Path

from app.main import _no_ready_jobs_message
from app.storage.db import Database


class ApplyMessagesTest(unittest.TestCase):
    def test_no_ready_message_explains_empty_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.sqlite3")
            db.init()

            message = _no_ready_jobs_message(db)

        self.assertIn("Banco atual tem 0 paginas coletadas e 0 vagas registradas", message)
        self.assertIn("Buscar e preencher elegiveis", message)


if __name__ == "__main__":
    unittest.main()
