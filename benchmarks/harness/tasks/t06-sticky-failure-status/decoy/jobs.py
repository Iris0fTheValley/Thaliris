"""Track the outcome of multi-step jobs."""


class JobTracker:
    def __init__(self):
        self._steps = {}  # job_id -> {step: latest status}

    def report(self, job_id, step, status):
        """Record the outcome of one step. ``status`` is "ok" or "failed"."""
        if status not in ("ok", "failed"):
            raise ValueError(f"bad status: {status!r}")
        self._steps.setdefault(job_id, {})[step] = status

    def retry(self, job_id):
        self._steps.pop(job_id, None)

    def status(self, job_id):
        """Return "pending", "ok" or "failed" for the job."""
        steps = self._steps.get(job_id)
        if not steps:
            return "pending"
        if "failed" in steps.values():
            return "failed"
        return "ok"
