import unittest

from jobs import JobTracker


class VisibleTests(unittest.TestCase):
    def test_failure_is_not_hidden_by_later_success_of_other_step(self):
        jobs = JobTracker()
        jobs.report("j1", "build", "failed")
        jobs.report("j1", "cleanup", "ok")
        self.assertEqual(jobs.status("j1"), "failed")

    def test_ok_and_pending(self):
        jobs = JobTracker()
        self.assertEqual(jobs.status("j1"), "pending")
        jobs.report("j1", "build", "ok")
        jobs.report("j1", "test", "ok")
        self.assertEqual(jobs.status("j1"), "ok")

    def test_retry_resets(self):
        jobs = JobTracker()
        jobs.report("j1", "build", "failed")
        jobs.retry("j1")
        self.assertEqual(jobs.status("j1"), "pending")
