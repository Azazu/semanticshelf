"""The queue's policy and its three steps: claim, execute, finish.

The mechanics of the rows — the claim query, the lease, the conditional
finishes — live in `app/repositories/jobs.py`. What lives here is everything
that decides: how long a failure waits, what a failure is allowed to say, and
what the three steps do between them.

The three are separate on purpose. `claim` commits before any work starts, so
a crash cannot lose the fact that the rows were taken. `execute` holds no
transaction while it reads a file and runs a model. `finish` opens its own
transaction and writes the vector and the job's new state together, under the
ownership the claim handed out — if the job has since been reclaimed, reset, or
deleted with its asset, nothing lands at all.
"""

import asyncio
import os
import signal
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.domain import EMBEDDING_MODELS, INLINE_RUNNER, IndexingJob, UnknownModelError
from app.ml.pool import acquire, run_in_pool
from app.repositories.assets import AssetRepository
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.jobs import ClaimedJob, IndexingJobRepository, MissingWork
from app.services import images
from app.storage import MediaStorage

#: The delay before a failed attempt becomes due again: 2^attempts × 10s, as
#: the requirements fix it. Computed at the moment of failure, so nothing has
#: to wake up and reschedule anything — a job becomes due because time passed.
BACKOFF_BASE_SECONDS = 10

#: What `indexing_jobs.last_error` may hold. The column allows two kilobytes.
REASON_MAX_BYTES = 2 * 1024
TRUNCATION_MARK = "…[truncated]"

#: Why a unit of work is still queued when a runner has stopped waiting for it.
QUEUED_WAITING = "waiting in the queue"
QUEUED_HELD = "held by a runner"

log = structlog.stdlib.get_logger(__name__)


class IndexingFailure(Exception):
    """A failure this service raises, and whose message it therefore wrote.

    The distinction is not decoration: a reason may carry the message of one of
    these, because the text is ours. Any other exception contributes its class
    name alone — nothing can tell which parts of a library's message came from
    the picture it was reading.
    """


class ModelNotEnabled(IndexingFailure):
    """The job names a model this build is not configured to run."""


class StoredFileMissing(IndexingFailure):
    """The asset's original is not on disk any more."""


class StoredFileUnusable(IndexingFailure):
    """The asset's original no longer passes the inspection an upload passes."""


class OwnershipLost(Exception):
    """Raised inside a finishing transaction to roll the whole thing back."""


def backoff_seconds(attempts: int) -> int:
    """How long a job waits after its `attempts`-th failure."""
    if attempts < 1:
        raise ValueError("a job that has not been attempted cannot back off")
    return int(BACKOFF_BASE_SECONDS * 2**attempts)


def bounded(text: str) -> str:
    """The reason, cut to what the column holds, with the cut visible."""
    encoded = text.encode("utf-8")
    if len(encoded) <= REASON_MAX_BYTES:
        return text
    room = REASON_MAX_BYTES - len(TRUNCATION_MARK.encode("utf-8"))
    return encoded[:room].decode("utf-8", errors="ignore") + TRUNCATION_MARK


def reason_for(error: BaseException) -> str:
    """What goes into `last_error`: the class always, the message only if ours."""
    if isinstance(error, IndexingFailure):
        return bounded(f"{type(error).__name__}: {error}")
    return bounded(type(error).__name__)


@dataclass(frozen=True, slots=True)
class Executed:
    """What a successful execution produced."""

    claimed: ClaimedJob
    vector: tuple[float, ...]


async def claim(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    limit: int | None = None,
    asset_ids: Sequence[UUID] | None = None,
) -> list[ClaimedJob]:
    """Take due work and commit the claim, so every other runner can see it.

    Each step opens its own session. They are three transactions with real
    work between them, and sharing one session would tie them together — as it
    did until a test found `finish` unable to begin, because the read inside
    `execute` had already opened a transaction on it.
    """
    async with session_factory() as session, session.begin():
        return await IndexingJobRepository(session).claim(
            limit=limit if limit is not None else settings.worker_batch_size,
            lease_seconds=settings.job_lease_seconds,
            asset_ids=asset_ids,
        )


async def execute(
    claimed: ClaimedJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
) -> Executed:
    """Read the stored original and embed it, holding no connection meanwhile."""
    job = claimed.job
    if job.model not in settings.enabled_models:
        raise ModelNotEnabled(f"model {job.model!r} is not enabled in this build")

    async with session_factory() as session:
        asset = await AssetRepository(session).get(job.asset_id)
    if asset is None:
        # The asset went, and the cascade took this job with it; the finish
        # would match nothing anyway.
        raise StoredFileMissing(f"asset {job.asset_id} no longer exists")

    path = storage.original(asset.id, asset.file_ext)
    try:
        picture = await run_in_pool(pool, images.open_for_inference, path, settings)
    except FileNotFoundError as error:
        raise StoredFileMissing("the stored original is not on disk") from error
    except (
        images.UndecodableImageError,
        images.UnsupportedFormatError,
        images.ImageTooLargeError,
        images.ImageTooSmallError,
    ) as error:
        # What is on disk now is not what was accepted at upload.
        raise StoredFileUnusable(f"{type(error).__name__}: {error}") from error

    embedder = await acquire(pool, job.model, settings)
    result = await run_in_pool(pool, embedder.embed_images, [picture])
    return Executed(claimed=claimed, vector=tuple(float(value) for value in result.vectors[0]))


async def finish(executed: Executed, *, session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """Write the vector and mark the work done, together, if we still own it."""
    job = executed.claimed.job
    try:
        async with session_factory() as session, session.begin():
            landed = await IndexingJobRepository(session).mark_done(
                job.id, executed.claimed.owned_until
            )
            if not landed:
                raise OwnershipLost
            await EmbeddingRepository(session).upsert(
                asset_id=job.asset_id, model=job.model, vector=executed.vector
            )
    except OwnershipLost:
        log.info("indexing result discarded", job_id=str(job.id), cause="no longer the owner")
        return False
    return True


async def fail(
    claimed: ClaimedJob,
    error: BaseException,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> bool:
    """Put the work back with a delay, or end it once the attempts are spent."""
    job = claimed.job
    reason = reason_for(error)
    async with session_factory() as session, session.begin():
        repository = IndexingJobRepository(session)
        if job.attempts >= settings.job_max_attempts:
            landed = await repository.mark_failed(job.id, claimed.owned_until, reason)
        else:
            landed = await repository.return_to_queue(
                job.id,
                claimed.owned_until,
                delay_seconds=backoff_seconds(job.attempts),
                reason=reason,
            )
    if not landed:
        log.info("indexing failure discarded", job_id=str(job.id), cause="no longer the owner")
    return landed


async def run_batch(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    asset_ids: Sequence[UUID] | None = None,
) -> int:
    """Claim a bounded batch, work through it, and report how many were taken.

    Bounded on purpose: a runner that drained while work remained would never
    end, and this one lives inside the process that serves requests. With
    `asset_ids` the batch is restricted to those assets' work, which is how a
    runner finishes work it created itself rather than whatever is due.
    """
    claimed = await claim(session_factory, settings, asset_ids=asset_ids)
    for one in claimed:
        try:
            executed = await execute(
                one,
                session_factory=session_factory,
                storage=storage,
                settings=settings,
                pool=pool,
            )
        except Exception as error:
            await fail(one, error, session_factory=session_factory, settings=settings)
            continue
        await finish(executed, session_factory=session_factory)
    return len(claimed)


async def drain(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    asset_ids: Sequence[UUID] | None = None,
) -> None:
    """The background task an upload schedules. Never raises into the server."""
    try:
        taken = await run_batch(
            session_factory=session_factory,
            storage=storage,
            settings=settings,
            pool=pool,
            asset_ids=asset_ids,
        )
        if taken:
            log.info("indexing batch finished", jobs=taken)
    except Exception:
        log.exception("indexing batch failed")


# --- which runner carries out the work ----------------------------------------


def carries_out_work(settings: Settings) -> bool:
    """May this process execute the work it just queued?

    One question, asked in one place, by everything that would otherwise index:
    the upload and reindex paths of the API, and the two commands that finish
    what they imported. Under `INDEXING_RUNNER=worker` the answer is no for all
    of them, and `semanticshelf worker` is the only runner (FR-IDX-2, FR-CLI-1).

    A fact about a deployment stated in four places drifts in four directions,
    which is the whole reason this is a function and not a comparison.
    """
    return settings.indexing_runner == INLINE_RUNNER


def queued_because(*, asked_to_leave_it: bool, settings: Settings) -> str | None:
    """Why the work a command created was left queued — or `None` if it was not.

    Two instructions can say the same thing from different directions: `--no-
    index` is about this run, `INDEXING_RUNNER=worker` is about the deployment.
    They never contradict each other, and a summary that said "queued" without
    saying which of them decided it would leave an operator guessing at their
    own configuration.
    """
    reasons = []
    if asked_to_leave_it:
        reasons.append("--no-index")
    if not carries_out_work(settings):
        reasons.append(f"INDEXING_RUNNER={settings.indexing_runner}")
    if not reasons:
        return None
    return f"work left queued ({', '.join(reasons)}); `semanticshelf worker` carries it out"


# --- a runner of its own ------------------------------------------------------


class Stop:
    """What asks a runner to end, and what an idle runner waits on.

    One object rather than a flag, because the loop's idle wait *is* the wait
    for it (change 13, design decision 2): a runner that is doing nothing ends
    the moment it is asked to, and a runner that is working notices between
    batches — which is what finishing the batch you hold means mechanically.
    """

    def __init__(self) -> None:
        self._asked = asyncio.Event()

    def ask(self) -> None:
        """Ask the runner to end after the work it holds."""
        self._asked.set()

    @property
    def asked(self) -> bool:
        return self._asked.is_set()

    async def wait(self, seconds: float) -> bool:
        """Wait up to `seconds` to be asked. True when asked, False on timeout."""
        try:
            await asyncio.wait_for(self._asked.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True


#: What a runner is asked to stop with. `SIGINT` is here because a terminal is
#: where a person stops one, and it should behave like a supervisor's `SIGTERM`
#: rather than like a traceback.
STOP_SIGNALS: Final[tuple[int, ...]] = (signal.SIGTERM, signal.SIGINT)


def die_by(number: int) -> None:
    """End this process the way the signal means to, not the way we would.

    The default disposition is restored and the signal re-raised at this
    process, so a supervisor sees the status it expects — rather than an exit
    code this project invented for "asked twice". Work in flight returns by its
    lease, exactly as it would after a crash, because that is what this is.
    """
    signal.signal(number, signal.SIG_DFL)
    os.kill(os.getpid(), number)


class StopSignals:
    """The policy: the first request is polite, the second is not.

    The first sets the token — the runner finishes the batch it holds and ends.
    The second gives the process to the operating system. What a forced end does
    NOT do is report totals: collecting them is a delay, and removing the delay
    is the only reason the second request exists (change 13, design decision 3).
    """

    def __init__(self, stop: Stop, *, die: Callable[[int], None] = die_by) -> None:
        self._stop = stop
        self._die = die

    def deliver(self, number: int) -> None:
        if self._stop.asked:
            log.warning("worker forced", signal=signal.Signals(number).name)
            self._die(number)
            return
        log.info("worker stopping", signal=signal.Signals(number).name)
        self._stop.ask()


def install_stop_handlers(
    loop: asyncio.AbstractEventLoop,
    deliver: Callable[[int], None],
    *,
    signals: Iterable[int] = STOP_SIGNALS,
) -> None:
    """Wire `deliver` to each signal, on the loop rather than in the middle of
    whatever was running: a handler that sets a token the loop is already
    waiting on needs nothing else to be async-safe."""
    for number in signals:
        loop.add_signal_handler(number, deliver, number)


@dataclass(slots=True)
class WorkerRun:
    """What one run of a runner did, for the caller to report."""

    batches: int = 0
    units: int = 0


async def run_worker(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    stop: Stop,
    once: bool = False,
) -> WorkerRun:
    """Work the queue until asked to stop — the runner that is its own process.

    Three lines of policy around `run_batch`, and every one of them is a
    decision the design names. A batch that took something is followed by
    another at once, because more may be due. A batch that took nothing is
    followed by a wait — and that wait is the wait for `stop`, so being asked
    while idle ends the run immediately instead of a poll interval later. The
    request to stop is read **between** batches and never inside one: work
    already claimed is finished, and nothing new is taken.

    It prints nothing. What it did comes back as a value, because the command
    owns the output and this owns the work.
    """
    run = WorkerRun()
    # Asked before anything else: a stop that arrived while the handlers were
    # being installed, or while the last idle wait was timing out, must not be
    # answered with one more claim. "Stop taking new work" is read here.
    while not stop.asked:
        taken = await run_batch(
            session_factory=session_factory, storage=storage, settings=settings, pool=pool
        )
        if taken:
            run.batches += 1
            run.units += taken
            log.info("worker batch finished", jobs=taken)
        if once or stop.asked:
            break
        if taken:
            continue  # more may be due; look again without waiting
        if await stop.wait(settings.worker_poll_seconds):
            break
    return run


# --- finishing a named set of work -------------------------------------------


@dataclass(slots=True)
class WorkReport:
    """What became of a named set of work: done, still queued, or given up on."""

    indexed: int = 0
    queued: list[tuple[UUID, str]] = field(default_factory=list)
    failed: list[tuple[UUID, str]] = field(default_factory=list)


def unfinished(statuses: Mapping[UUID, Mapping[str, str]]) -> list[UUID]:
    """The assets among these whose work is still waiting or running."""
    return [
        asset_id
        for asset_id, per_model in statuses.items()
        if any(state in ("pending", "running") for state in per_model.values())
    ]


async def finish_work(
    asset_ids: Sequence[UUID],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    on_progress: Callable[[int], None] | None = None,
) -> WorkReport:
    """Carry out the work of these assets — and only theirs.

    The queue may hold anything else, however old and however much of it: the
    claims here name these assets, so a command that created work finishes what
    it started instead of being satisfied by someone else's backlog.

    It stops when none of this work is unfinished, or when a pass claims nothing
    while some still is — work another runner holds, or work waiting out the
    delay before its next attempt. It does not sleep to outlast that delay: what
    it could not do is reported, not waited for.
    """
    work = WorkReport()
    if not asset_ids:
        return work  # nothing was named, so there is nothing of ours to do

    passes = len(asset_ids) * settings.job_max_attempts + 1
    for _ in range(passes):
        async with session_factory() as session:
            statuses = await status_of(session, asset_ids)
        still_going = unfinished(statuses)
        if on_progress is not None:
            on_progress(len(asset_ids) - len(still_going))
        if not still_going:
            break
        taken = await run_batch(
            session_factory=session_factory,
            storage=storage,
            settings=settings,
            pool=pool,
            asset_ids=still_going,
        )
        if not taken:
            break

    async with session_factory() as session:
        statuses = await status_of(session, asset_ids)
        for asset_id in asset_ids:
            states = statuses.get(asset_id, {})
            if all(state == "done" for state in states.values()) and states:
                work.indexed += 1
                continue
            for model, state in sorted(states.items()):
                if state == "done":
                    continue
                if state == "failed":
                    work.failed.append((asset_id, await recorded_reason(session, asset_id, model)))
                else:
                    work.queued.append(
                        (asset_id, QUEUED_HELD if state == "running" else QUEUED_WAITING)
                    )
    return work


async def recorded_reason(session: AsyncSession, asset_id: UUID, model: str) -> str:
    """What the queue recorded about a job that failed for good.

    The other way round from `reason_for`, which turns an exception into the
    text that is stored: this reads that text back out.
    """
    for job in await jobs_of(session, asset_id):
        if job.model == model and job.last_error:
            return job.last_error
    return "no reason recorded"


# --- work for what is already stored ------------------------------------------


@dataclass(slots=True)
class BackfillReport:
    """What `index missing` did for one model."""

    model: str
    queued: list[UUID] = field(default_factory=list)
    skipped_failed: list[UUID] = field(default_factory=list)
    #: `None` when the run was asked to leave the work queued.
    work: WorkReport | None = None


class HeldElsewhere(RuntimeError):
    """Another runner is writing this key right now, and may hold other weights."""


@dataclass
class RebuildReport:
    """What a rebuild or a replacement did, in the states an operator acts on.

    `queued` is what this run created; `carried_over` is work an earlier run
    left that this one finished — the two are apart because a run that reports
    only what it queued looks idle after a crash it is in fact repairing.
    `not_yet_due` and `held` are why a run may be over without the corpus being
    rebuilt, and `skipped_failed` is the work only an explicit reset may touch.
    """

    model: str
    queued: list[UUID] = field(default_factory=list)
    carried_over: list[UUID] = field(default_factory=list)
    skipped_failed: list[UUID] = field(default_factory=list)
    not_yet_due: list[UUID] = field(default_factory=list)
    held: list[UUID] = field(default_factory=list)
    #: `None` when nothing was executed — `--no-index`, or a runner of its own.
    work: WorkReport | None = None

    @property
    def complete(self) -> bool:
        """Did this run leave the key owing nothing?

        "Nothing to do right now" is not the same statement, which is why a
        retry serving its backoff and a live claim both count against it.
        """
        left = bool(self.not_yet_due or self.held or self.skipped_failed)
        outstanding_after = bool(self.work.queued) if self.work is not None else True
        return not left and not outstanding_after


async def rebuild(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    model: str,
    answering_for: str | None = None,
    index: bool = True,
    refuse_while_held: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> RebuildReport:
    """Queue a selection's work and carry out everything of it that is runnable.

    Two selections share this: a **rebuild** of a key (`answering_for` is None)
    queues the assets that already have a vector under it, and a **replacement**
    queues the assets another key answers for and this one does not.

    What is new here, and the reason this is not `backfill`: the run carries out
    the work its selection **already had outstanding** as well as the work it
    queued. `backfill` drains only what it queued, and the selection passes over
    assets whose work is already waiting — so after a crash a re-run of it
    queues nothing, drains nothing, and reports success over a corpus it never
    touched.

    `refuse_while_held` is the repair's precondition (ADR-007): a live claim is
    a process writing this key right now, and nothing in the store can say which
    checkpoint it holds. An expired claim is not grounds to refuse — it is what
    an interrupted repair leaves, and a runner that wakes after its lease has
    gone cannot land its result: a finish matches only the lease expiry its own
    claim wrote.
    """
    if model not in settings.enabled_models:
        raise ModelNotEnabled(f"model {model!r} is not enabled in this build")

    async with session_factory() as session, session.begin():
        owed = await IndexingJobRepository(session).outstanding(model=model)
    if refuse_while_held and owed.held:
        raise HeldElsewhere(
            f"{len(owed.held)} unit(s) of work for {model!r} are claimed by another runner; "
            "let it finish or restart it, then run this again"
        )

    async with session_factory() as session, session.begin():
        repository = IndexingJobRepository(session)
        created = (
            await repository.queue_rebuild(model=model)
            if answering_for is None
            else await repository.queue_replacing(model=model, answering_for=answering_for)
        )

    report = RebuildReport(
        model=model,
        queued=list(created.queued),
        carried_over=list(owed.drainable),
        skipped_failed=list(created.skipped_failed),
        not_yet_due=list(owed.not_yet_due),
        held=list(owed.held),
    )
    if index:
        report.work = await finish_work(
            [*report.queued, *report.carried_over],
            session_factory=session_factory,
            storage=storage,
            settings=settings,
            pool=pool,
            on_progress=on_progress,
        )
    return report


async def queue_missing(
    *, session_factory: async_sessionmaker[AsyncSession], settings: Settings, model: str
) -> MissingWork:
    """Queue the work a model has none of, for assets that are already stored.

    An operator's act, never the service's own: nothing here is called at start,
    in the lifespan or from a background task, because a service that began
    writing rows and burning CPU because someone restarted it would be a worse
    service than one that waits to be asked.
    """
    if model not in settings.enabled_models:
        raise ModelNotEnabled(f"model {model!r} is not enabled in this build")
    async with session_factory() as session, session.begin():
        return await IndexingJobRepository(session).queue_missing(model=model)


async def backfill(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    model: str,
    index: bool = True,
    on_progress: Callable[[int], None] | None = None,
) -> BackfillReport:
    """Queue one model's missing work and then carry it out.

    The same drain `index-folder` uses, over the assets this run queued. It
    claims by asset rather than by model, so an asset that also had another
    model's work waiting gets that done too — which is the queue doing its job,
    and is reported as it happens.
    """
    missing = await queue_missing(session_factory=session_factory, settings=settings, model=model)
    report = BackfillReport(
        model=model, queued=missing.queued, skipped_failed=missing.skipped_failed
    )
    if index:
        report.work = await finish_work(
            missing.queued,
            session_factory=session_factory,
            storage=storage,
            settings=settings,
            pool=pool,
            on_progress=on_progress,
        )
    return report


async def describe_plan(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    model: str,
    answering_for: str | None,
    retire: bool,
) -> list[str]:
    """What a run would do, without doing any of it.

    The work is hours of CPU on one machine, so the count comes first and it is
    cheap: three statements, no model loaded, nothing queued. A command that
    began a three-hour job because its name sounded additive would be a bad
    command.
    """
    async with session_factory() as session, session.begin():
        jobs = IndexingJobRepository(session)
        embeddings = EmbeddingRepository(session)
        owed = await jobs.outstanding(model=model)
        if answering_for is None:
            subject = f"rebuild {model}"
            to_compute = await embeddings.count_for(model=model)
        else:
            subject = f"fill {model} for what {answering_for} answers for"
            to_compute = await embeddings.uncovered(key=answering_for, by=model)
        uncovered = (
            await embeddings.uncovered(key=answering_for, by=model)
            if answering_for is not None
            else 0
        )

    lines = [
        f"plan: {subject}",
        f"vectors to compute: {to_compute}",
        f"already waiting: {len(owed.drainable)}",
    ]
    if owed.held:
        lines.append(f"held by another runner: {len(owed.held)}")
    if owed.not_yet_due:
        lines.append(f"retry not yet due: {len(owed.not_yet_due)}")
    if owed.failed:
        lines.append(f"failed, needs an explicit reset: {len(owed.failed)}")
    if not carries_out_work(settings):
        lines.append("this deployment's queue has a runner of its own: work would be queued only")
    if retire and answering_for is not None:
        lines.append(
            f"retirement: would delete {answering_for}'s vectors"
            if uncovered == 0 and owed.blocking == 0 and not owed.drainable
            else f"retirement: would be refused — {uncovered} asset(s) not covered, "
            f"{len(owed.drainable) + owed.blocking} unit(s) of work outstanding"
        )
    lines.append("nothing was queued or computed; pass --apply to do it")
    return lines


async def retire(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    key: str,
    replaced_by: str,
) -> list[str]:
    """Delete a key's vectors, or say why not.

    Both keys' queue locks are held for the whole of it, in an order sorted by
    key name so it does not depend on which is being retired. Coverage inside
    the deleting statement stops a race against the queue; the locks stop two
    retirements in opposite directions from each seeing itself covered, deleting
    disjoint rows, and leaving an asset with neither vector.
    """
    async with session_factory() as session, session.begin():
        jobs = IndexingJobRepository(session)
        await jobs.lock_models(sorted({key, replaced_by}))
        owed = await jobs.outstanding(model=replaced_by)
        if owed.drainable or owed.blocking:
            return [
                f"retirement refused: {len(owed.drainable) + owed.blocking} unit(s) of work for "
                f"{replaced_by!r} are outstanding, so a count of what it covers describes a "
                "corpus that is still changing"
            ]
        embeddings = EmbeddingRepository(session)
        uncovered = await embeddings.uncovered(key=key, by=replaced_by)
        if uncovered:
            return [
                f"retirement refused: {uncovered} asset(s) have a {key!r} vector and no "
                f"{replaced_by!r} one"
            ]
        removed = await embeddings.retire(key=key, replaced_by=replaced_by)

    lines = [f"retired: {removed} vector(s) of {key!r} deleted"]
    if key in settings.enabled_models:
        lines.append(
            f"{key!r} is still enabled in this build: the next upload will queue work for it. "
            "Removing it from ENABLED_MODELS is configuration, and yours to change."
        )
    return lines


def describe_rebuild(report: RebuildReport, *, settings: Settings) -> list[str]:
    """What a run did, in the states an operator acts on."""
    lines = [
        f"model: {report.model}",
        f"queued: {len(report.queued)}",
        f"carried over from an earlier run: {len(report.carried_over)}",
    ]
    if report.skipped_failed:
        lines.append(
            f"skipped (failed work): {len(report.skipped_failed)} — only an explicit reset "
            "runs those again"
        )
    if report.not_yet_due:
        lines.append(f"retry not yet due: {len(report.not_yet_due)} — cannot be run now")
    if report.held:
        lines.append(f"held by another runner: {len(report.held)}")
    work = report.work
    if work is None:
        reason = queued_because(asked_to_leave_it=False, settings=settings)
        lines.append(f"indexing: not run{f' ({reason})' if reason else ''}")
    else:
        lines.append(f"indexed: {work.indexed}")
        lines.append(f"still queued: {len(work.queued)}")
        lines.append(f"failed: {len(work.failed)}")
        lines.extend(f"  failed  {asset_id} — {why}" for asset_id, why in work.failed)
    lines.append(
        "complete: the key owes nothing"
        if report.complete
        else "not complete: something is still outstanding, so this is not a rebuilt corpus"
    )
    return lines


def describe_backfill(reports: Sequence[BackfillReport]) -> list[str]:
    """The reports as lines for a terminal, in the shape `index-folder` uses."""
    lines: list[str] = []
    for report in reports:
        lines.append(f"model: {report.model}")
        lines.append(f"queued: {len(report.queued)}")
        lines.append(f"skipped (failed work): {len(report.skipped_failed)}")
        if report.skipped_failed:
            lines.append(
                "  their work for this model gave up; "
                "POST /api/v1/assets/{id}/reindex runs it again"
            )
        work = report.work
        if work is None:
            lines.append("indexing: not run")
            continue
        if not report.queued:
            lines.append("indexing: nothing to do")
            continue
        lines.append(f"indexed: {work.indexed}")
        lines.append(f"still queued: {len(work.queued)}")
        lines.extend(f"  queued  {asset_id} — {why}" for asset_id, why in work.queued)
        lines.append(f"failed: {len(work.failed)}")
        lines.extend(f"  failed  {asset_id} — {reason}" for asset_id, reason in work.failed)
    return lines


# --- what the API shows -------------------------------------------------------
#
# These take the request's own session: they are reads and one small write on
# behalf of a caller who is waiting, not steps of a runner.


def known_models(models: Sequence[str]) -> tuple[str, ...]:
    """The named models, or a refusal naming the first the service has never
    heard of. Enabled is not required: work queued for a model that was later
    switched off is still work an operator may want to reset."""
    for model in models:
        if model not in EMBEDDING_MODELS:
            raise UnknownModelError(f"unknown model: {model!r}")
    return tuple(models)


async def status_of(
    session: AsyncSession, asset_ids: Sequence[UUID]
) -> Mapping[UUID, Mapping[str, str]]:
    """`index_status` for a page of assets: the newest job per model, derived."""
    return await IndexingJobRepository(session).latest_status_for(asset_ids)


async def jobs_of(session: AsyncSession, asset_id: UUID) -> list[IndexingJob]:
    """An asset's work with its attempts, timestamps and last reason."""
    return await IndexingJobRepository(session).list_for_asset(asset_id)


async def reset_work(
    session: AsyncSession, asset_id: UUID, *, models: Sequence[str] | None = None
) -> list[str]:
    """Put an asset's work — all of it, or the models named — back in the queue.

    The only way failed work runs again. Returns the model of every job it
    reset, which is what the answer reports: asking for a model whose work this
    asset never had resets nothing and says so.

    The transaction is committed rather than opened: the endpoint has already
    read the asset to answer 404 for one that is not stored, so this session is
    inside a transaction by the time it gets here, and `session.begin()` would
    refuse to open a second one.
    """
    reset = await IndexingJobRepository(session).reset(asset_id, models)
    await session.commit()
    return reset
