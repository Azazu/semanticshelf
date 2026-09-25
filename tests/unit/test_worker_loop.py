"""The runner's loop: what it takes, when it waits, and what ends it.

The loop is three lines of policy around `run_batch`, and every one of them is
a decision somebody could reverse without a test noticing: a batch that took
something must be followed by another at once, a batch that took nothing must
be followed by a wait, and that wait must be the wait for the stop — not a
sleep with a check afterwards, which would make a stop take a whole interval.

`run_batch` is replaced here. What it does needs a database and has its own
suite; what the loop does with its answer does not.
"""

import asyncio
from typing import Any, cast

import pytest

from app.core.settings import Settings
from app.services import indexing
from app.services.indexing import Stop, run_worker
from tests.conftest import UNREACHABLE_DATABASE_URL


def settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[arg-type]
        _env_file=None, database_url=UNREACHABLE_DATABASE_URL, **overrides
    )


class Batches:
    """A queue of answers `run_batch` gives, and a record of when it was asked."""

    def __init__(self, *answers: int) -> None:
        self.answers = list(answers)
        self.calls = 0

    async def __call__(self, **kwargs: Any) -> int:
        self.calls += 1
        return self.answers.pop(0) if self.answers else 0


async def worker(
    monkeypatch: pytest.MonkeyPatch,
    batches: Batches,
    *,
    stop: Stop,
    once: bool = False,
    poll: float = 0.05,
) -> indexing.WorkerRun:
    monkeypatch.setattr(indexing, "run_batch", batches)
    return await run_worker(
        session_factory=cast(Any, None),
        storage=cast(Any, None),
        settings=settings(worker_poll_seconds=poll),
        pool=cast(Any, None),
        stop=stop,
        once=once,
    )


# --- what it takes --------------------------------------------------------------


async def test_it_works_through_what_is_due_and_then_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two batches with work, then nothing — and the third answer is what makes
    it wait rather than spin."""
    batches = Batches(4, 3)
    stop = Stop()

    async def ask_soon() -> None:
        await asyncio.sleep(0.01)
        stop.ask()

    asyncio.ensure_future(ask_soon())
    run = await worker(monkeypatch, batches, stop=stop, poll=5.0)

    assert (run.batches, run.units) == (2, 7), "both batches, and what they held"
    assert batches.calls == 3, "it asked again after each batch that took something"


async def test_a_stop_that_arrived_first_takes_no_work_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window Gate 2 found: a signal can arrive while the handlers are being
    installed, or while the last idle wait is timing out. A loop that claims
    first and asks afterwards answers it with one more batch — of work that is
    due, and that it then has to finish before it may end."""
    batches = Batches(4, 4)
    stop = Stop()
    stop.ask()

    run = await worker(monkeypatch, batches, stop=stop, poll=10.0)

    assert batches.calls == 0, "nothing was claimed after the stop was asked for"
    assert (run.batches, run.units) == (0, 0)


async def test_a_stop_that_arrived_first_stops_even_a_single_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--once` means one batch at most, not one batch regardless."""
    batches = Batches(4)
    stop = Stop()
    stop.ask()

    run = await worker(monkeypatch, batches, stop=stop, once=True, poll=10.0)

    assert batches.calls == 0
    assert (run.batches, run.units) == (0, 0)


async def test_a_batch_that_took_nothing_is_not_counted_and_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idle runner is silent: a log line per empty pass would fill a
    deployment's logs with the fact that nothing happened."""
    said: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        indexing,
        "log",
        type(
            "Recorder",
            (),
            {"info": lambda _self, event, **fields: said.append((event, fields))},
        )(),
    )
    stop = Stop()

    async def ask_after_the_first(**kwargs: object) -> int:
        stop.ask()
        return 0

    run = await worker(monkeypatch, cast(Any, ask_after_the_first), stop=stop, poll=10.0)

    assert (run.batches, run.units) == (0, 0)
    assert said == [], "nothing was taken, so nothing is reported"


async def test_a_batch_that_took_something_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    said: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        indexing,
        "log",
        type(
            "Recorder",
            (),
            {"info": lambda _self, event, **fields: said.append((event, fields))},
        )(),
    )
    stop = Stop()

    async def ask_after_the_first(**kwargs: object) -> int:
        stop.ask()
        return 2

    await worker(monkeypatch, cast(Any, ask_after_the_first), stop=stop, poll=10.0)

    assert said == [("worker batch finished", {"jobs": 2})]


# --- when it waits ---------------------------------------------------------------


async def test_an_idle_loop_waits_its_interval_before_asking_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batches = Batches(0, 0, 5)
    stop = Stop()

    async def ask_after_three_passes() -> None:
        while batches.calls < 3:
            await asyncio.sleep(0.005)
        stop.ask()

    asyncio.ensure_future(ask_after_three_passes())
    started = asyncio.get_running_loop().time()
    run = await worker(monkeypatch, batches, stop=stop, poll=0.05)
    elapsed = asyncio.get_running_loop().time() - started

    assert batches.calls >= 3
    assert run.units == 5, "it kept looking, and found the work when it arrived"
    assert elapsed >= 0.1, "two empty passes waited their interval each"


async def test_a_stop_while_idle_ends_it_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one that fails if the wait is a sleep with a check afterwards: the
    interval here is ten seconds, and this test may not take them."""
    stop = Stop()

    async def ask_once_it_is_idle() -> None:
        await asyncio.sleep(0.01)
        stop.ask()

    asyncio.ensure_future(ask_once_it_is_idle())
    started = asyncio.get_running_loop().time()
    await asyncio.wait_for(worker(monkeypatch, Batches(0), stop=stop, poll=10.0), timeout=2.0)
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1.0, "it ended when it was asked, not when the interval ran out"


async def test_a_stop_is_read_between_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asked while a batch is in flight, the loop finishes that batch and takes
    nothing more."""
    batches = Batches(4, 4, 4)
    stop = Stop()

    original = batches.__call__

    async def ask_during_the_first(**kwargs: Any) -> int:
        taken = await original(**kwargs)
        stop.ask()
        return taken

    run = await worker(monkeypatch, cast(Any, ask_during_the_first), stop=stop, poll=10.0)

    assert (run.batches, run.units) == (1, 4), "the batch it held, and nothing after it"
    assert batches.calls == 1


# --- one batch on request ---------------------------------------------------------


async def test_once_takes_a_single_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    batches = Batches(4, 4)

    run = await worker(monkeypatch, batches, stop=Stop(), once=True, poll=10.0)

    assert batches.calls == 1
    assert (run.batches, run.units) == (1, 4)


async def test_once_over_an_empty_queue_returns_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No wait: a single batch means a single batch, work or no work."""
    batches = Batches(0)

    run = await asyncio.wait_for(
        worker(monkeypatch, batches, stop=Stop(), once=True, poll=10.0), timeout=2.0
    )

    assert batches.calls == 1
    assert (run.batches, run.units) == (0, 0)
