import threading
import time
import unittest

from app.runtime_control import (
    RunInterrupted,
    checkpoint,
    request_pause,
    request_stop,
    reset_run_control,
    resume_run,
)


class RuntimeControlTest(unittest.TestCase):
    def tearDown(self):
        reset_run_control()

    def test_checkpoint_raises_after_stop(self):
        reset_run_control()
        request_stop()

        with self.assertRaises(RunInterrupted):
            checkpoint()

    def test_checkpoint_waits_while_paused_and_resumes(self):
        reset_run_control()
        request_pause()
        finished = threading.Event()

        thread = threading.Thread(target=lambda: (checkpoint(), finished.set()))
        thread.start()
        time.sleep(0.25)

        self.assertFalse(finished.is_set())
        resume_run()
        thread.join(timeout=1.0)

        self.assertTrue(finished.is_set())


if __name__ == "__main__":
    unittest.main()
