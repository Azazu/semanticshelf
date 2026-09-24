"""Which runner carries out the work, and how a command says it did not.

One question — may this process execute what it just queued? — asked in one
place by four callers. The answer is a deployment's fact, and a fact stated in
four places drifts in four directions; these tests are what keeps it one.
"""

import pytest

from app.core.settings import Settings
from app.domain import INLINE_RUNNER, WORKER_RUNNER
from app.services.indexing import carries_out_work, queued_because
from tests.conftest import UNREACHABLE_DATABASE_URL


def settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[arg-type]
        _env_file=None, database_url=UNREACHABLE_DATABASE_URL, **overrides
    )


def test_a_deployment_nobody_configured_indexes_what_it_accepts() -> None:
    assert settings().indexing_runner == INLINE_RUNNER
    assert carries_out_work(settings()) is True


def test_configured_for_a_runner_of_its_own_nothing_else_executes() -> None:
    assert carries_out_work(settings(indexing_runner=WORKER_RUNNER)) is False


def test_a_runner_this_service_does_not_have_is_refused_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("INDEXING_RUNNER", "cron")

    with pytest.raises(ValueError, match="indexing_runner"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_environment_chooses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("INDEXING_RUNNER", "worker")

    assert carries_out_work(Settings(_env_file=None)) is False  # type: ignore[call-arg]


# --- what a command says when it left the work queued ----------------------------


def test_nothing_is_said_when_the_command_carried_the_work_out() -> None:
    assert queued_because(asked_to_leave_it=False, settings=settings()) is None


def test_the_flag_is_named_when_the_flag_decided() -> None:
    said = queued_because(asked_to_leave_it=True, settings=settings())

    assert said is not None
    assert "--no-index" in said
    assert "INDEXING_RUNNER" not in said, "the deployment did not decide this one"


def test_the_setting_is_named_when_the_setting_decided() -> None:
    said = queued_because(asked_to_leave_it=False, settings=settings(indexing_runner=WORKER_RUNNER))

    assert said is not None
    assert "INDEXING_RUNNER=worker" in said
    assert "--no-index" not in said


def test_both_are_named_when_both_said_so() -> None:
    """They cannot contradict each other — they say the same thing from two
    directions — so both are reported rather than one winning silently."""
    said = queued_because(asked_to_leave_it=True, settings=settings(indexing_runner=WORKER_RUNNER))

    assert said is not None
    assert "--no-index" in said and "INDEXING_RUNNER=worker" in said


def test_it_names_what_will_carry_the_work_out() -> None:
    said = queued_because(asked_to_leave_it=True, settings=settings())

    assert said is not None and "semanticshelf worker" in said
