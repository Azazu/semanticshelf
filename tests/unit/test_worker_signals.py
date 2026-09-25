"""What a signal does to a runner, asserted without killing the test runner.

The policy is two lines — the first request sets the token, the second hands the
process to the operating system — and both are easy to get wrong in ways nothing
notices: a second signal that only sets the token again leaves a forced stop
waiting for work that will never finish, and a forced stop that exits with a
code of this project's own invention lies to whatever is supervising it.

`die` is replaced here. What it does is asserted separately, with `signal.signal`
and `os.kill` replaced, because the real one ends the process running the test.
"""

import os
import signal

import pytest

from app.services.indexing import STOP_SIGNALS, Stop, StopSignals, die_by


def test_the_first_request_is_polite() -> None:
    stop = Stop()
    died: list[int] = []
    signals = StopSignals(stop, die=died.append)

    signals.deliver(signal.SIGTERM)

    assert stop.asked, "the runner is asked to finish what it holds and end"
    assert died == [], "and nothing was forced"


def test_the_second_request_is_not() -> None:
    stop = Stop()
    died: list[int] = []
    signals = StopSignals(stop, die=died.append)

    signals.deliver(signal.SIGTERM)
    signals.deliver(signal.SIGTERM)

    assert died == [signal.SIGTERM], "the process is given to the signal it was sent"


def test_a_second_request_of_another_kind_forces_too() -> None:
    """Whichever arrives second: a person pressing Ctrl-C after a supervisor's
    SIGTERM means the same thing."""
    stop = Stop()
    died: list[int] = []
    signals = StopSignals(stop, die=died.append)

    signals.deliver(signal.SIGTERM)
    signals.deliver(signal.SIGINT)

    assert died == [signal.SIGINT]


def test_a_forced_end_restores_the_default_disposition_and_re_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanism of `die_by`, with both of its effects replaced — the real
    one ends this process, which is the point of it."""
    dispositions: list[tuple[int, object]] = []
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        signal, "signal", lambda number, handler: dispositions.append((number, handler))
    )
    monkeypatch.setattr(os, "kill", lambda pid, number: killed.append((pid, number)))

    die_by(signal.SIGTERM)

    assert dispositions == [(signal.SIGTERM, signal.SIG_DFL)], "the default, not ours"
    assert killed == [(os.getpid(), signal.SIGTERM)], "sent to this process, after the restore"


def test_both_signals_a_runner_answers_to() -> None:
    assert STOP_SIGNALS == (signal.SIGTERM, signal.SIGINT)
