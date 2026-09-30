"""What the store can be asked before a model is replaced.

Three questions, all of them one statement against a real store and none of
them loading a model: which assets a rebuild would touch, how far a replacement
has got, and what a key still owes. They live here rather than against a
stand-in because each is a statement, and a statement is the thing being
tested.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Asset, dimension_of
from app.repositories import AssetRepository, EmbeddingRepository
from app.repositories.jobs import IndexingJobRepository

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings(db_settings: Settings, tmp_path: Path) -> Settings:
    root = tmp_path / "media"
    root.mkdir()
    return db_settings.model_copy(update={"media_root": root})


async def add_asset(session: AsyncSession, seed: int) -> Asset:
    return await AssetRepository(session).add(
        sha256=f"{seed:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024 * seed,
        source="upload",
    )


def a_vector(model: str, seed: int) -> list[float]:
    values = [0.0] * dimension_of(model)
    values[0] = 1.0
    values[1] = seed / 100.0
    return values


async def give_vector(session: AsyncSession, asset: Asset, model: str, seed: int = 1) -> None:
    await EmbeddingRepository(session).upsert(
        asset_id=asset.id, model=model, vector=a_vector(model, seed)
    )


# --- the selection a rebuild needs ---------------------------------------------


async def test_a_rebuild_queues_the_assets_that_already_have_a_vector(
    session: AsyncSession,
) -> None:
    """The mirror of the missing-work selection, and the whole difference
    between them: a rebuild exists to replace what is already there."""
    with_vector = await add_asset(session, 1)
    without = await add_asset(session, 2)
    await give_vector(session, with_vector, DINOV2_LARGE)
    await session.commit()

    queued = (await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)).queued
    await session.commit()

    assert queued == [with_vector.id]
    assert without.id not in queued


async def test_a_rebuild_of_a_key_nothing_is_stored_under_queues_nothing(
    session: AsyncSession,
) -> None:
    await add_asset(session, 1)
    await session.commit()

    queued = (await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)).queued

    assert queued == []


async def test_a_rebuild_does_not_look_at_another_key(session: AsyncSession) -> None:
    """An asset with CLIP's vector and not DINOv2's is not DINOv2's to rebuild."""
    asset = await add_asset(session, 1)
    await give_vector(session, asset, CLIP_VIT_L14)
    await session.commit()

    queued = (await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)).queued

    assert queued == []


async def test_a_rebuild_passes_over_what_already_has_work(session: AsyncSession) -> None:
    asset = await add_asset(session, 1)
    await give_vector(session, asset, DINOV2_LARGE)
    await session.commit()
    first = (await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)).queued
    await session.commit()

    second = (await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)).queued

    assert first == [asset.id]
    assert second == []


# --- how far a replacement has got ---------------------------------------------


async def test_a_replacement_that_covers_everything_leaves_nothing_uncovered(
    session: AsyncSession,
) -> None:
    asset = await add_asset(session, 1)
    await give_vector(session, asset, CLIP_VIT_L14)
    await give_vector(session, asset, DINOV2_LARGE)
    await session.commit()

    uncovered = await EmbeddingRepository(session).uncovered(key=CLIP_VIT_L14, by=DINOV2_LARGE)

    assert uncovered == 0


async def test_an_incomplete_replacement_says_how_many(session: AsyncSession) -> None:
    for seed in (1, 2, 3):
        asset = await add_asset(session, seed)
        await give_vector(session, asset, CLIP_VIT_L14, seed)
        if seed == 1:
            await give_vector(session, asset, DINOV2_LARGE, seed)
    await session.commit()

    uncovered = await EmbeddingRepository(session).uncovered(key=CLIP_VIT_L14, by=DINOV2_LARGE)

    assert uncovered == 2


async def test_an_empty_corpus_is_covered_by_definition(session: AsyncSession) -> None:
    assert await EmbeddingRepository(session).uncovered(key=CLIP_VIT_L14, by=DINOV2_LARGE) == 0


async def test_the_count_is_not_symmetric(session: AsyncSession) -> None:
    """`uncovered(a, b)` and `uncovered(b, a)` are different questions, and a
    retirement that confused them would delete the wrong key's vectors."""
    asset = await add_asset(session, 1)
    await give_vector(session, asset, CLIP_VIT_L14)
    await session.commit()
    repository = EmbeddingRepository(session)

    assert await repository.uncovered(key=CLIP_VIT_L14, by=DINOV2_LARGE) == 1
    assert await repository.uncovered(key=DINOV2_LARGE, by=CLIP_VIT_L14) == 0


# --- what a key still owes -----------------------------------------------------


async def test_nothing_outstanding_is_five_empty_lists(session: AsyncSession) -> None:
    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.drainable == []
    assert owed.blocking == 0


async def test_work_waiting_is_this_run_to_carry_out(session: AsyncSession) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=DINOV2_LARGE)
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.waiting == [asset.id]
    assert owed.drainable == [asset.id]
    assert owed.blocking == 0


async def test_a_retry_not_yet_due_is_neither_drainable_nor_done(session: AsyncSession) -> None:
    """It cannot be run now by anyone, and a run that counted it as done would
    claim a corpus it has not rebuilt."""
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=DINOV2_LARGE)
    await session.execute(
        sa.text("UPDATE indexing_jobs SET available_at = now() + interval '1 hour'")
    )
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.not_yet_due == [asset.id]
    assert owed.drainable == []
    assert owed.blocking == 1


async def test_a_live_claim_belongs_to_someone_else(session: AsyncSession) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=DINOV2_LARGE)
    await session.commit()
    await IndexingJobRepository(session).claim(limit=1, lease_seconds=300)
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.held == [asset.id]
    assert owed.drainable == []


async def test_an_expired_claim_belongs_to_nobody(session: AsyncSession) -> None:
    """Which is why a run may carry it out: a runner that wakes after its lease
    has gone cannot land its result anyway."""
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=DINOV2_LARGE)
    await session.commit()
    await IndexingJobRepository(session).claim(limit=1, lease_seconds=300)
    await session.execute(
        sa.text("UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 minute'")
    )
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.expired == [asset.id]
    assert owed.drainable == [asset.id]
    assert owed.held == []


async def test_a_live_claim_and_an_expired_one_are_different_answers(
    session: AsyncSession,
) -> None:
    """The repair refuses on the first and carries out the second, so a query
    that blurred them would either block recovery or overwrite a live writer."""
    held, expired = await add_asset(session, 1), await add_asset(session, 2)
    repository = IndexingJobRepository(session)
    await repository.add(asset_id=held.id, model=DINOV2_LARGE)
    await repository.add(asset_id=expired.id, model=DINOV2_LARGE)
    await session.commit()
    await repository.claim(limit=2, lease_seconds=300)
    await session.execute(
        sa.text(
            "UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 minute' "
            "WHERE asset_id = :asset_id"
        ),
        {"asset_id": expired.id},
    )
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.held == [held.id]
    assert owed.expired == [expired.id]


async def test_failed_work_is_reported_and_left_alone(session: AsyncSession) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=DINOV2_LARGE)
    await session.execute(sa.text("UPDATE indexing_jobs SET status = 'failed'"))
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.failed == [asset.id]
    assert owed.drainable == []
    assert owed.blocking == 1


async def test_another_key_is_not_this_key_s_debt(session: AsyncSession) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=CLIP_VIT_L14)
    await session.commit()

    owed = await IndexingJobRepository(session).outstanding(model=DINOV2_LARGE)

    assert owed.drainable == []
    assert owed.blocking == 0
