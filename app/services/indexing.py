"""The queue's policy: how long to wait, and what a failure is allowed to say.

The mechanics live in `app/repositories/jobs.py` — the claim, the lease and the
conditional finishes. What lives here is everything that decides rather than
executes, starting with the two rules that are easiest to get quietly wrong.
"""

#: The delay before a failed attempt becomes due again: 2^attempts × 10s, as
#: the requirements fix it. Computed at the moment of failure, so nothing has
#: to wake up and reschedule anything — a job becomes due because time passed.
BACKOFF_BASE_SECONDS = 10

#: What `indexing_jobs.last_error` may hold. The column allows two kilobytes.
REASON_MAX_BYTES = 2 * 1024
TRUNCATION_MARK = "…[truncated]"


def backoff_seconds(attempts: int) -> int:
    """How long a job waits after its `attempts`-th failure."""
    if attempts < 1:
        raise ValueError("a job that has not been attempted cannot back off")
    return int(BACKOFF_BASE_SECONDS * 2**attempts)
