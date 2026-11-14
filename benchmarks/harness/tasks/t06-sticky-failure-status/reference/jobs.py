"""Track the outcome of multi-step jobs."""


class JobTracker:
    def __init__(self):
        self._reports = {}  # job_id -> list of (step, status)

    def report(self, job_id, step, status):
        """Record the outcome of one step. ``status`` is "ok" or "failed"."""
        if status not in ("ok", "failed"):
            raise ValueError(f"bad status: {status!r}")
        self._reports.setdefault(job_id, []).append((step, status))

    def retry(self, job_id):
        """Forget earlier reports so the job can start over."""
        self._reports.pop(job_id, None)

    def status(self, job_id):
        """Return "pending", "ok" or "failed" for the job."""
        reports = self._reports.get(job_id)
        if not reports:
            return "pending"
        if any(status == "failed" for _, status in reports):
            return "failed"
        return "ok"
