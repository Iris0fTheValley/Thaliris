import unittest

from jobs import JobTracker


class HiddenTests(unittest.TestCase):
    def test_same_step_success_after_failure_does_not_clear_it(self):
        jobs = JobTracker()
        jobs.report("j1", "build", "failed")
        jobs.report("j1", "build", "ok")
        self.assertEqual(jobs.status("j1"), "failed")

    def test_repeated_successes_do_not_clear_failure(self):
        jobs = JobTracker()
        jobs.report("j1", "a", "failed")
        for _ in range(3):
            jobs.report("j1", "a", "ok")
            jobs.report("j1", "b", "ok")
        self.assertEqual(jobs.status("j1"), "failed")

    def test_retry_then_success_is_ok(self):
        jobs = JobTracker()
        jobs.report("j1", "build", "failed")
        jobs.retry("j1")
        jobs.report("j1", "build", "ok")
        self.assertEqual(jobs.status("j1"), "ok")

    def test_retry_does_not_touch_other_jobs(self):
        jobs = JobTracker()
        jobs.report("j1", "build", "failed")
        jobs.report("j2", "build", "failed")
        jobs.retry("j1")
        self.assertEqual(jobs.status("j2"), "failed")

    def test_bad_status_still_rejected(self):
        jobs = JobTracker()
        with self.assertRaises(ValueError):
            jobs.report("j1", "build", "maybe")
