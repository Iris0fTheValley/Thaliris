`JobTracker` in `jobs.py` reports a job as "ok" when the last reported step succeeded, so a job that failed in the middle and then ran a successful cleanup step shows up green. Fix the status logic.

Failure is sticky: once any step of a job has reported `"failed"`, `status(job_id)` stays `"failed"`, even if that same step or any other step later reports `"ok"`. A job with reports and no failure is `"ok"`; a job with no reports is `"pending"`. Add `retry(job_id)`, which forgets all earlier reports of that job so it starts over (status `"pending"`); other jobs are not affected.
