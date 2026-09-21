"""The delay a failed job waits before it is due again."""

import pytest

from app.services.indexing import BACKOFF_BASE_SECONDS, backoff_seconds


@pytest.mark.parametrize(
    ("attempts", "expected"), [(1, 20), (2, 40), (3, 80), (4, 160), (10, 10 * 2**10)]
)
def test_the_delay_doubles_with_every_attempt(attempts: int, expected: int) -> None:
    assert backoff_seconds(attempts) == expected


def test_the_first_delay_is_twice_the_base() -> None:
    # Stated because the formula is 2^attempts, not 2^(attempts-1): the first
    # failure already waits twice the base, which is what the requirement says.
    assert backoff_seconds(1) == 2 * BACKOFF_BASE_SECONDS


def test_a_job_that_was_never_attempted_cannot_back_off() -> None:
    with pytest.raises(ValueError, match="not been attempted"):
        backoff_seconds(0)
