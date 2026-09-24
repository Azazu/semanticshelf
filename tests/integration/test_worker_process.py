"""The worker as a process: real signals, real children, one real queue.

What a signal does to a runner cannot be asserted about a task — a task is not
sent SIGTERM and does not die by one — so these tests spawn the worker's own
runtime (`tests/worker_child.py`) and talk to it the way an operator's terminal
or a supervisor does.

Nothing here sleeps to hope. Every wait is a rendezvous through a file the child
writes (`held-<pid>` when it is inside claimed work, `signalled-<pid>` when a
signal reached its handler) or through the queue's own state, and every wait is
bounded and fails naming what it waited for.
"""

import asyncio
import hashlib
import io
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14
from app.repositories.assets import AssetRepository
from app.repositories.jobs import IndexingJobRepository
from app.storage import MediaStorage

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TABLES = "assets, embeddings, indexing_jobs"
#: Long enough for a child to start, connect and claim on a loaded machine;
#: short enough that a test which will never pass says so.
PATIENCE_SECONDS = 60.0
POLL_SECONDS = 0.02


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def barrier(tmp_path: Path) -> Path:
    directory = tmp_path / "barrier"
    directory.mkdir()
    return directory


@pytest.fixture
def settings(db_settings: Settings, media_root: Path) -> Settings:
    return db_settings.model_copy(update={"media_root": media_root})


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


async def stored_asset(
    sessions: async_sessionmaker[AsyncSession],
    media_root: Path,
    settings: Settings,
    *,
    seed: int = 0,
) -> UUID:
    """An asset with its file and its work, as an upload would leave it."""
    storage = MediaStorage.at(media_root)
    data = picture_bytes(seed)
    asset_id = uuid4()
    staged = storage.stage(asset_id)
    storage.fill(staged, [data])
    storage.publish(staged, storage.original(asset_id, "png"))

    async with sessions() as session, session.begin():
        asset = await AssetRepository(session).add(
            asset_id=asset_id,
            sha256=hashlib.sha256(data).hexdigest(),
            content_type="image/png",
            file_ext="png",
            width=400,
            height=200,
            size_bytes=len(data),
            source="upload",
        )
        await IndexingJobRepository(session).add_for_models(
            asset_id=asset.id, models=settings.enabled_models
        )
    return asset.id


# --- talking to a child ----------------------------------------------------------


class Child:
    """A worker process, and the rendezvous the test shares with it."""

    def __init__(self, process: subprocess.Popen[str], barrier: Path) -> None:
        self.process = process
        self.barrier = barrier

    @property
    def pid(self) -> int:
        return self.process.pid

    def held(self) -> Path:
        return self.barrier / f"held-{self.pid}"

    def signalled(self) -> Path:
        return self.barrier / f"signalled-{self.pid}"

    def ready(self) -> Path:
        return self.barrier / f"ready-{self.pid}"

    def wait_until_ready(self) -> None:
        """Until its handlers are installed: a signal before that finds the
        default disposition, which kills a process that has claimed nothing."""
        until(self.ready().exists, what=f"child {self.pid} to install its handlers")

    def wait_until_holding(self) -> None:
        until(self.held().exists, what=f"child {self.pid} to hold claimed work")

    def wait_until_signalled(self) -> None:
        until(self.signalled().exists, what=f"child {self.pid} to acknowledge a signal")

    def send(self, number: int) -> None:
        self.process.send_signal(number)

    def output(self, *, timeout: float = PATIENCE_SECONDS) -> str:
        return self.process.communicate(timeout=timeout)[0]


def until(ready: Callable[[], bool], *, what: str, timeout: float = PATIENCE_SECONDS) -> None:
    """Wait for something to become true, and say what it was if it never does."""
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() > deadline:
            raise AssertionError(f"waited {timeout:.0f}s for {what}")
        time.sleep(POLL_SECONDS)


def release(barrier: Path) -> None:
    (barrier / "release").write_text("go")


def start(settings: Settings, barrier: Path, **overrides: str) -> Child:
    """The worker's own runtime, in a process of its own."""
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "MEDIA_ROOT": str(settings.media_root),
        "ENABLED_MODELS": ",".join(settings.enabled_models),
        "WORKER_BARRIER_DIR": str(barrier),
        "WORKER_POLL_SECONDS": "0.05",
        "WORKER_BATCH_SIZE": "1",
        "JOB_LEASE_SECONDS": "600",
        "LOG_JSON": "1",
        **overrides,
    }
    process = subprocess.Popen(  # noqa: S603 - the command is built here, not taken from input
        [sys.executable, "-m", "tests.worker_child"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return Child(process, barrier)


@pytest.fixture
def spawn() -> Iterator[Callable[..., Child]]:
    """Start children, and make sure not one of them outlives the test.

    A worker that survives its test keeps claiming from the same database and
    quietly ruins every test after it — which is exactly what happened the first
    time these tests were run, when a timeout left one behind.
    """
    started: list[Child] = []

    def spawning(settings: Settings, barrier: Path, **overrides: str) -> Child:
        child = start(settings, barrier, **overrides)
        started.append(child)
        return child

    yield spawning

    for child in started:
        if child.process.poll() is None:
            child.process.kill()
        with suppress(subprocess.TimeoutExpired):
            child.process.communicate(timeout=10)


def run_once(
    spawning: Callable[..., Child], settings: Settings, barrier: Path, **overrides: str
) -> str:
    """One batch in a child that ends by itself, and what it printed."""
    child = spawning(settings, barrier, WORKER_ONCE="1", **overrides)
    return child.output()


async def job_of(engine: AsyncEngine, asset_id: UUID) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                sa.text("SELECT status, attempts FROM indexing_jobs WHERE asset_id = :id"),
                {"id": str(asset_id)},
            )
        ).one()


async def vectors(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(
            (await connection.execute(sa.text("SELECT count(*) FROM embeddings"))).scalar_one()
        )


async def states(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(sa.text("SELECT status FROM indexing_jobs ORDER BY id"))
        return [status for (status,) in rows]


async def attempts_of(engine: AsyncEngine) -> list[int]:
    async with engine.connect() as connection:
        rows = await connection.execute(sa.text("SELECT attempts FROM indexing_jobs ORDER BY id"))
        return [count for (count,) in rows]


async def until_finished(engine: AsyncEngine, *, units: int) -> None:
    """Wait, bounded, for the queue itself to say the work is done."""
    deadline = time.monotonic() + PATIENCE_SECONDS
    while True:
        found = await states(engine)
        if found == ["done"] * units:
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"waited {PATIENCE_SECONDS:.0f}s for {units} units; saw {found}")
        await asyncio.sleep(POLL_SECONDS)


@pytest.fixture
def one_model(db_settings: Settings) -> Settings:
    assert db_settings.enabled_models == (CLIP_VIT_L14,), "the suite pins one model"
    return db_settings


# --- the harness itself -----------------------------------------------------------


async def test_the_child_is_the_runner_and_the_barrier_holds_it(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 2.3: the harness is worth nothing if it is not the same runner, and
    the barrier is worth nothing if the child can pass it unheld."""
    asset_id = await stored_asset(sessions, media_root, settings)
    # `--once` here: this test is about the runtime being the real one, and a
    # single batch ends by itself, so no signal is needed to prove it.
    child = spawn(settings, barrier, WORKER_ONCE="1")

    child.wait_until_holding()
    status, attempts = await job_of(engine, asset_id)
    assert (status, attempts) == ("running", 1), "claimed, and still inside the work"
    assert await vectors(engine) == 0, "held before the vector exists"

    release(barrier)
    output = child.output()

    assert child.process.returncode == 0, output
    assert await job_of(engine, asset_id) == ("done", 1)
    assert await vectors(engine) == 1


# --- a signal, and what it does ---------------------------------------------------


async def test_a_signal_lets_it_finish_the_batch_it_holds(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 2.4: the batch it holds is finished — nothing new is taken."""
    first = await stored_asset(sessions, media_root, settings, seed=1)
    second = await stored_asset(sessions, media_root, settings, seed=2)
    child = spawn(settings, barrier)

    child.wait_until_holding()
    child.send(signal.SIGTERM)
    child.wait_until_signalled()
    release(barrier)
    output = child.output()

    assert child.process.returncode == 0, output
    assert "worker stopped:" in output, "a graceful end reports what it did"
    finished = [await job_of(engine, first), await job_of(engine, second)]
    done = [one for one in finished if one.status == "done"]
    waiting = [one for one in finished if one.status == "pending"]
    assert len(done) == 1 and len(waiting) == 1, finished
    assert waiting[0].attempts == 0, "the other unit was never claimed"
    assert await vectors(engine) == 1, "the vector of the batch it held"


async def test_a_second_signal_ends_it_and_the_lease_covers_the_work(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 2.5: forced, and what it held is claimable — not failed, not lost."""
    asset_id = await stored_asset(sessions, media_root, settings)
    child = spawn(settings, barrier, JOB_LEASE_SECONDS="1")

    child.wait_until_holding()
    child.send(signal.SIGTERM)
    child.wait_until_signalled()
    child.send(signal.SIGTERM)  # while the work is still held: never released
    output = child.output()

    assert child.process.returncode == -signal.SIGTERM, output
    assert "worker forced" in output, "it said it was forced"
    assert "worker stopped:" not in output, "and reported nothing else"
    status, attempts = await job_of(engine, asset_id)
    assert (status, attempts) == ("running", 1), "held by a runner that no longer exists"
    assert await vectors(engine) == 0

    # The lease is what returns it, and nothing else has to happen: a second
    # runner takes it as soon as it has expired. Each pass is one batch, so this
    # is "try again until the lease is old enough", not a poll of hope.
    release(barrier)
    deadline = time.monotonic() + PATIENCE_SECONDS
    while True:
        printed = run_once(spawn, settings, barrier, JOB_LEASE_SECONDS="1")
        status, attempts = await job_of(engine, asset_id)
        if status == "done":
            break
        assert time.monotonic() < deadline, f"the expired claim was never taken: {printed}"
        time.sleep(0.2)

    assert (status, attempts) == ("done", 2), "the second claim counted its own attempt"
    assert await vectors(engine) == 1, "and the work was done once"


async def test_an_idle_runner_stops_promptly_and_reports(
    settings: Settings, barrier: Path, spawn: Callable[..., Child]
) -> None:
    """Task 2.6: an empty queue, so no model is ever loaded and no barrier is
    reached — only the signal and the exit are under test."""
    child = spawn(settings, barrier)

    child.wait_until_ready()
    child.send(signal.SIGTERM)
    output = child.output(timeout=10)

    assert child.process.returncode == 0, output
    assert "worker started:" in output
    assert "worker stopped: 0 batch(es), 0 unit(s)" in output


# --- two runners on one queue -----------------------------------------------------


async def test_two_workers_share_one_queue(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 3.1. Both children are held before either is released, so what this
    proves does not depend on which of them started first."""
    for seed in range(4):
        await stored_asset(sessions, media_root, settings, seed=seed)
    first = spawn(settings, barrier)
    second = spawn(settings, barrier)

    first.wait_until_holding()
    second.wait_until_holding()
    held = {first.held().read_text(), second.held().read_text()}
    assert held == {str(first.pid), str(second.pid)}, "each child holds work of its own"

    release(barrier)
    await until_finished(engine, units=4)
    for child in (first, second):
        child.send(signal.SIGTERM)
    outputs = [child.output() for child in (first, second)]

    assert all(child.process.returncode == 0 for child in (first, second)), outputs
    assert await vectors(engine) == 4, "one vector per asset, none done twice"
    assert await attempts_of(engine) == [1, 1, 1, 1], "no unit was claimed by both"
    assert all("worker stopped:" in output for output in outputs)
    assert all("0 batch(es)" not in output for output in outputs), "both did some of the work"


async def test_a_killed_runner_leaves_its_work_to_the_lease(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 3.3: `SIGKILL`, the case no handler can soften — and the case where
    "the runner is gone, not paused" is true by construction."""
    asset_id = await stored_asset(sessions, media_root, settings)
    child = spawn(settings, barrier, JOB_LEASE_SECONDS="1")

    child.wait_until_holding()
    child.process.kill()
    child.output()

    assert child.process.returncode == -signal.SIGKILL
    assert await job_of(engine, asset_id) == ("running", 1), "held by a runner that is gone"

    release(barrier)
    deadline = time.monotonic() + PATIENCE_SECONDS
    while True:
        printed = run_once(spawn, settings, barrier, JOB_LEASE_SECONDS="1")
        status, attempts = await job_of(engine, asset_id)
        if status == "done":
            break
        assert time.monotonic() < deadline, f"the killed runner's work was never taken: {printed}"
        time.sleep(0.2)

    assert (status, attempts) == ("done", 2), "one attempt per claim"
    assert await vectors(engine) == 1, "and one vector, however many runners saw it"


async def test_a_lease_that_expires_under_a_working_runner_is_at_least_once(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    settings: Settings,
    media_root: Path,
    barrier: Path,
    spawn: Callable[..., Child],
) -> None:
    """Task 3.4: the guarantee stated honestly, with two runners on one unit.

    The first is held inside the work while its lease expires — it is alive and
    computing, not gone — so the second takes the same unit and computes the
    same vector. That is the at-least-once delivery the queue promises. What
    keeps it harmless is not timing: the first runner's completion is fenced by
    the claim it no longer owns (change 6 proves that mechanism in
    `test_a_late_success_after_a_reclaim_lands_nowhere` and its three siblings),
    and the write is an upsert.
    """
    asset_id = await stored_asset(sessions, media_root, settings)
    first = spawn(settings, barrier, JOB_LEASE_SECONDS="1")
    first.wait_until_holding()

    await asyncio.sleep(1.5)  # the lease, which is one second here, expires
    second = spawn(settings, barrier, JOB_LEASE_SECONDS="600", WORKER_ONCE="1")
    second.wait_until_holding()  # it took the very unit the first is still working

    release(barrier)  # both finish their embedding; only one of them owns the claim
    second_output = second.output()
    first.send(signal.SIGTERM)
    first_output = first.output()

    assert second.process.returncode == 0, second_output
    assert first.process.returncode == 0, first_output
    assert "indexing result discarded" in first_output, "the loser said so rather than retrying"
    status, attempts = await job_of(engine, asset_id)
    assert (status, attempts) == ("done", 2), "one attempt per claim"
    assert await vectors(engine) == 1, "computed twice, stored once"
