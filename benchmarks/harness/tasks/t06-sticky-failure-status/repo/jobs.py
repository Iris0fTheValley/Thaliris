"""Track the outcome of multi-step jobs."""


class JobTracker:
    def __init__(self):
        self._status = {}

    def report(self, job_id, step, status):
        """Record the outcome of one step. ``status`` is "ok" or "failed"."""
        if status not in ("ok", "failed"):
            raise ValueError(f"bad status: {status!r}")
        self._status[job_id] = status

    def status(self, job_id):
        """Return "pending", "ok" or "failed" for the job."""
        return self._status.get(job_id, "pending")
