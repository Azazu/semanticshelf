"""The queue against a real database: claiming, leases, ownership and repeats.

Everything here needs PostgreSQL, because what is under test is what the
database guarantees — `SKIP LOCKED`, the visibility of a committed claim, and
the conditional updates that decide who is allowed to finish.

Assets are created directly rather than through the API: the upload schedules a
drain of its own, and a background runner racing these tests would make them
say nothing. The drain has its own tests, where that is the point.
"""

import asyncio
import hashlib
import io
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, Asset, dimension_of
from app.ml.pool import create_pool
from app.repositories.assets import AssetRepository
from app.repositories.jobs import IndexingJobRepository
from app.services import indexing
from app.storage import MediaStorage

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"
CLIP_WIDTH = dimension_of(CLIP_VIT_L14)
EXPIRE_THE_LEASE = sa.text("UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 s'")


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
def settings(db_settings: Settings, media_root: Path) -> Settings:
    return db_settings.model_copy(update={"media_root": media_root})


@pytest.fixture
def storage(media_root: Path) -> MediaStorage:
    return MediaStorage.at(media_root)


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = create_pool(settings)
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
async def holder(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session a test can hold a lock in, outside the service's own."""
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def stored_asset(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    *,
    seed: int = 0,
) -> Asset:
    """An asset with its files and its work, as an upload would leave it."""
    data = picture_bytes(seed)
    asset_id = uuid4()
    for path in (storage.original(asset_id, "png"), storage.thumbnail(asset_id)):
        staged = storage.stage(asset_id)
        storage.fill(staged, [data])
        storage.publish(staged, path)

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
    return asset


async def job_row(engine: AsyncEngine, asset_id: UUID) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                sa.text(
                    "SELECT id, status, attempts, last_error, lease_expires_at, available_at "
                    "FROM indexing_jobs WHERE asset_id = :id"
                ),
                {"id": str(asset_id)},
            )
        ).one()


async def counts(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as connection:
        jobs = (
            await connection.execute(sa.text("SELECT count(*) FROM indexing_jobs"))
        ).scalar_one()
        vectors = (
            await connection.execute(sa.text("SELECT count(*) FROM embeddings"))
        ).scalar_one()
    return int(jobs), int(vectors)


# --- claiming -----------------------------------------------------------------


async def test_a_claim_takes_due_work_and_leaves_a_lease(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)

    claimed = await indexing.claim(sessions, settings)

    assert [one.job.asset_id for one in claimed] == [asset.id]
    assert claimed[0].job.attempts == 1
    row = await job_row(engine, asset.id)
    assert row.status == "running"
    assert row.lease_expires_at == claimed[0].owned_until


async def test_two_claimers_never_take_the_same_job(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)

    first, second = await asyncio.gather(
        indexing.claim(sessions, settings), indexing.claim(sessions, settings)
    )

    assert sorted([len(first), len(second)]) == [0, 1]
    assert (await job_row(engine, asset.id)).attempts == 1, "one claim, one attempt"


async def test_a_claimer_passes_over_work_another_holds(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    holder: AsyncSession,
) -> None:
    """What `SKIP LOCKED` buys. The two-claimer test above cannot show it:
    without the clause the second claimer blocks, re-reads and still finds
    nothing, which looks the same. Here it must take the *other* row, and
    promptly."""
    await stored_asset(sessions, storage, settings, seed=1)
    await stored_asset(sessions, storage, settings, seed=2)

    await holder.begin()
    held = await IndexingJobRepository(holder).claim(limit=1, lease_seconds=60)
    assert len(held) == 1
    try:
        other = await asyncio.wait_for(indexing.claim(sessions, settings, limit=1), timeout=5)
    finally:
        await holder.rollback()

    assert len(other) == 1, "it took the free row rather than waiting for the held one"
    assert other[0].job.id != held[0].job.id


async def test_an_expired_lease_is_reclaimed_once_and_counts_an_attempt(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    claimed = await indexing.claim(sessions, settings)
    async with engine.begin() as connection:
        await connection.execute(EXPIRE_THE_LEASE)

    reclaimed = await indexing.claim(sessions, settings)
    once_more = await indexing.claim(sessions, settings)

    assert [one.job.id for one in reclaimed] == [claimed[0].job.id]
    assert reclaimed[0].job.attempts == 2
    assert once_more == [], "the reclaim took it exactly once"
    assert (await job_row(engine, asset.id)).attempts == 2


async def test_a_valid_lease_is_not_reclaimable(
    sessions: async_sessionmaker[AsyncSession], storage: MediaStorage, settings: Settings
) -> None:
    await stored_asset(sessions, storage, settings)
    assert await indexing.claim(sessions, settings)

    assert await indexing.claim(sessions, settings) == []


# --- finishing ----------------------------------------------------------------


async def test_a_vector_and_the_finish_land_together(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    claimed = await indexing.claim(sessions, settings)
    executed = await indexing.execute(
        claimed[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )

    assert await indexing.finish(executed, session_factory=sessions) is True

    row = await job_row(engine, asset.id)
    assert (row.status, row.last_error, row.lease_expires_at) == ("done", None, None)
    assert await counts(engine) == (1, 1)


async def test_the_same_work_executed_twice_leaves_one_vector(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    await stored_asset(sessions, storage, settings)
    first = await indexing.claim(sessions, settings)
    executed = await indexing.execute(
        first[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )
    assert await indexing.finish(executed, session_factory=sessions) is True

    # The same delivery again: the queue put it back for any reason at all.
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE indexing_jobs SET status = 'pending', lease_expires_at = NULL, "
                "available_at = now()"
            )
        )
    again = await indexing.claim(sessions, settings)
    executed_again = await indexing.execute(
        again[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )
    assert await indexing.finish(executed_again, session_factory=sessions) is True

    assert await counts(engine) == (1, 1), "the second write replaced the first"


async def test_a_failure_inside_the_finish_leaves_neither(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    claimed = await indexing.claim(sessions, settings)
    executed = await indexing.execute(
        claimed[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )

    from app.repositories.embeddings import EmbeddingRepository

    async def refuse(self: EmbeddingRepository, **kwargs: object) -> None:
        raise RuntimeError("the vector write gave up")

    monkeypatch.setattr(EmbeddingRepository, "upsert", refuse)

    with pytest.raises(RuntimeError):
        await indexing.finish(executed, session_factory=sessions)

    assert (await job_row(engine, asset.id)).status == "running"
    assert await counts(engine) == (1, 0), "the completion rolled back with the vector"


# --- ownership ----------------------------------------------------------------


async def test_a_late_success_after_a_reclaim_lands_nowhere(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    slow = await indexing.claim(sessions, settings)
    executed = await indexing.execute(
        slow[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )
    async with engine.begin() as connection:
        await connection.execute(EXPIRE_THE_LEASE)
    assert await indexing.claim(sessions, settings), "a second runner took it"

    assert await indexing.finish(executed, session_factory=sessions) is False

    row = await job_row(engine, asset.id)
    assert (row.status, row.attempts) == ("running", 2), "the second runner still holds it"
    assert await counts(engine) == (1, 0), "the late vector did not land either"


async def test_a_late_retry_after_a_reclaim_lands_nowhere(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    slow = await indexing.claim(sessions, settings)
    async with engine.begin() as connection:
        await connection.execute(EXPIRE_THE_LEASE)
    assert await indexing.claim(sessions, settings)

    landed = await indexing.fail(
        slow[0], RuntimeError("late"), session_factory=sessions, settings=settings
    )

    assert landed is False
    row = await job_row(engine, asset.id)
    assert (row.status, row.attempts, row.last_error) == ("running", 2, None)


async def test_a_late_exhaustion_after_a_reclaim_lands_nowhere(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    spent = settings.model_copy(update={"job_max_attempts": 1})
    slow = await indexing.claim(sessions, spent)
    async with engine.begin() as connection:
        await connection.execute(EXPIRE_THE_LEASE)
    assert await indexing.claim(sessions, spent)

    landed = await indexing.fail(
        slow[0], RuntimeError("late"), session_factory=sessions, settings=spent
    )

    assert landed is False
    assert (await job_row(engine, asset.id)).status == "running"


async def test_a_late_finish_after_a_reset_lands_nowhere(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    slow = await indexing.claim(sessions, settings)
    executed = await indexing.execute(
        slow[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).reset(asset.id)

    assert await indexing.finish(executed, session_factory=sessions) is False

    row = await job_row(engine, asset.id)
    assert (row.status, row.attempts, row.lease_expires_at) == ("pending", 0, None)
    assert await counts(engine) == (1, 0)


async def test_work_whose_asset_was_deleted_ends_quietly(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    """And the batch it was part of carries on: the runner discards one result
    and finishes the next job as if nothing had happened."""
    doomed = await stored_asset(sessions, storage, settings, seed=3)
    survivor = await stored_asset(sessions, storage, settings, seed=4)
    claimed = await indexing.claim(sessions, settings)
    assert len(claimed) == 2
    executed = [
        await indexing.execute(
            one, session_factory=sessions, storage=storage, settings=settings, pool=pool
        )
        for one in claimed
    ]
    async with sessions() as session, session.begin():
        await AssetRepository(session).delete(doomed.id)

    landed = [await indexing.finish(one, session_factory=sessions) for one in executed]

    by_asset = dict(zip([one.claimed.job.asset_id for one in executed], landed, strict=True))
    assert by_asset == {doomed.id: False, survivor.id: True}
    assert await counts(engine) == (1, 1), "the cascade took the work; the survivor's vector landed"


# --- failure ------------------------------------------------------------------


async def test_a_failure_returns_the_job_with_a_delay(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    claimed = await indexing.claim(sessions, settings)

    assert await indexing.fail(
        claimed[0], RuntimeError("transient"), session_factory=sessions, settings=settings
    )

    row = await job_row(engine, asset.id)
    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "RuntimeError")
    async with engine.connect() as connection:
        due_in = (
            await connection.execute(
                sa.text("SELECT available_at - now() FROM indexing_jobs WHERE asset_id = :id"),
                {"id": str(asset.id)},
            )
        ).scalar_one()
    assert due_in > timedelta(seconds=15), "it waits its backoff before becoming due"
    assert await indexing.claim(sessions, settings) == [], "and nothing claims it meanwhile"


async def test_a_failure_with_no_attempts_left_ends_the_job(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    spent = settings.model_copy(update={"job_max_attempts": 1})
    claimed = await indexing.claim(sessions, spent)

    assert await indexing.fail(
        claimed[0], RuntimeError("final"), session_factory=sessions, settings=spent
    )

    row = await job_row(engine, asset.id)
    assert (row.status, row.last_error) == ("failed", "RuntimeError")
    assert await indexing.claim(sessions, spent) == [], "nothing claims a failed job"


# --- what execution refuses ---------------------------------------------------


async def test_a_stored_file_that_no_longer_passes_inspection_fails_the_work(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    storage.original(asset.id, "png").write_bytes(b"this is not a picture any more")
    claimed = await indexing.claim(sessions, settings)

    with pytest.raises(indexing.StoredFileUnusable):
        await indexing.execute(
            claimed[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
        )

    assert await counts(engine) == (1, 0)


async def test_a_stored_file_beyond_the_pixel_cap_fails_before_it_is_decoded(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    buffer = io.BytesIO()
    Image.new("RGB", (4000, 4000), color=(1, 2, 3)).save(buffer, format="PNG")
    storage.original(asset.id, "png").write_bytes(buffer.getvalue())
    tight = settings.model_copy(update={"max_image_pixels": 10_000})
    claimed = await indexing.claim(sessions, tight)

    with pytest.raises(indexing.StoredFileUnusable, match="ImageTooLargeError"):
        await indexing.execute(
            claimed[0], session_factory=sessions, storage=storage, settings=tight, pool=pool
        )


async def test_a_greyscale_stored_file_is_converted_and_succeeds(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    buffer = io.BytesIO()
    Image.new("L", (400, 200), color=128).save(buffer, format="PNG")
    storage.original(asset.id, "png").write_bytes(buffer.getvalue())
    claimed = await indexing.claim(sessions, settings)

    executed = await indexing.execute(
        claimed[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
    )

    assert len(executed.vector) == CLIP_WIDTH
    assert await indexing.finish(executed, session_factory=sessions) is True


async def test_a_missing_stored_file_fails_the_work(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    storage.original(asset.id, "png").unlink()
    claimed = await indexing.claim(sessions, settings)

    with pytest.raises(indexing.StoredFileMissing):
        await indexing.execute(
            claimed[0], session_factory=sessions, storage=storage, settings=settings, pool=pool
        )


async def test_a_job_naming_a_model_this_build_does_not_run_fails(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET model = 'dinov2-large' WHERE asset_id = :id"),
            {"id": str(asset.id)},
        )
    spent = settings.model_copy(update={"job_max_attempts": 1})
    claimed = await indexing.claim(sessions, spent)

    with pytest.raises(indexing.ModelNotEnabled, match="dinov2-large") as raised:
        await indexing.execute(
            claimed[0], session_factory=sessions, storage=storage, settings=spent, pool=pool
        )
    assert await indexing.fail(claimed[0], raised.value, session_factory=sessions, settings=spent)

    row = await job_row(engine, asset.id)
    assert row.status == "failed", "it ends rather than waiting for a model that is not coming"
    assert row.last_error.startswith("ModelNotEnabled: model 'dinov2-large'")


# --- claims a runner restricts to its own assets -------------------------------


async def test_a_restricted_claim_takes_only_the_assets_it_names(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    """The queue may hold anything else, however much of it: a runner that
    created work of its own finishes that, not whatever is due first."""
    older = [await stored_asset(sessions, storage, settings, seed=seed) for seed in (1, 2, 3, 4)]
    mine = await stored_asset(sessions, storage, settings, seed=5)

    claimed = await indexing.claim(sessions, settings, asset_ids=[mine.id])

    assert [one.job.asset_id for one in claimed] == [mine.id]
    async with engine.connect() as connection:
        untouched = (
            await connection.execute(
                sa.text("SELECT count(*) FROM indexing_jobs WHERE status = 'pending'")
            )
        ).scalar_one()
    assert untouched == len(older), "everything else is still claimable by anyone"


async def test_a_restricted_claim_that_finds_nothing_of_its_own_takes_nothing(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    other = await stored_asset(sessions, storage, settings, seed=1)
    mine = await stored_asset(sessions, storage, settings, seed=2)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET status = 'done' WHERE asset_id = :id"),
            {"id": str(mine.id)},
        )

    assert await indexing.claim(sessions, settings, asset_ids=[mine.id]) == []

    row = await job_row(engine, other.id)
    assert (row.status, row.attempts) == ("pending", 0), "the other asset's work is untouched"


async def test_two_restricted_claimers_never_take_the_same_job(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)

    first, second = await asyncio.gather(
        indexing.claim(sessions, settings, asset_ids=[asset.id]),
        indexing.claim(sessions, settings, asset_ids=[asset.id]),
    )

    assert sorted([len(first), len(second)]) == [0, 1]
    assert (await job_row(engine, asset.id)).attempts == 1, "one claim, one attempt"


async def test_a_restricted_claim_still_leases_and_counts_its_attempt(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    asset = await stored_asset(sessions, storage, settings)

    claimed = await indexing.claim(sessions, settings, asset_ids=[asset.id])

    row = await job_row(engine, asset.id)
    assert (row.status, row.attempts) == ("running", 1)
    assert row.lease_expires_at == claimed[0].owned_until
