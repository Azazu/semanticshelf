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

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.ml.pool import acquire, run_in_pool
from app.repositories.assets import AssetRepository
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.jobs import ClaimedJob, IndexingJobRepository
from app.services import images
from app.storage import MediaStorage

#: The delay before a failed attempt becomes due again: 2^attempts × 10s, as
#: the requirements fix it. Computed at the moment of failure, so nothing has
#: to wake up and reschedule anything — a job becomes due because time passed.
BACKOFF_BASE_SECONDS = 10

#: What `indexing_jobs.last_error` may hold. The column allows two kilobytes.
REASON_MAX_BYTES = 2 * 1024
TRUNCATION_MARK = "…[truncated]"

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
) -> int:
    """Claim a bounded batch, work through it, and report how many were taken.

    Bounded on purpose: a runner that drained while work remained would never
    end, and this one lives inside the process that serves requests.
    """
    claimed = await claim(session_factory, settings)
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
) -> None:
    """The background task an upload schedules. Never raises into the server."""
    try:
        taken = await run_batch(
            session_factory=session_factory, storage=storage, settings=settings, pool=pool
        )
        if taken:
            log.info("indexing batch finished", jobs=taken)
    except Exception:
        log.exception("indexing batch failed")
