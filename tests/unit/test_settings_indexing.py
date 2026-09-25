"""The indexing settings: their defaults, their ranges, and the environment."""

import pytest
from pydantic import ValidationError

from app.core.settings import Settings

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=VALID_URL, **overrides)  # type: ignore[arg-type]


def test_defaults_are_exactly_what_the_requirements_fix() -> None:
    s = settings()
    assert s.job_lease_seconds == 600
    assert s.job_max_attempts == 3
    assert s.worker_batch_size == 4
    assert s.worker_poll_seconds == 2.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"job_lease_seconds": 0},
        {"job_max_attempts": 0},
        {"worker_batch_size": 0},
        {"job_lease_seconds": -1},
        {"worker_poll_seconds": 0},
        {"worker_poll_seconds": -0.5},
    ],
    ids=["lease", "attempts", "batch", "negative", "poll zero", "poll negative"],
)
def test_a_setting_that_is_not_positive_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)


def test_every_indexing_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("JOB_LEASE_SECONDS", "60")
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("WORKER_BATCH_SIZE", "16")
    monkeypatch.setenv("WORKER_POLL_SECONDS", "0.25")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.job_lease_seconds == 60
    assert s.job_max_attempts == 5
    assert s.worker_batch_size == 16
    assert s.worker_poll_seconds == 0.25
