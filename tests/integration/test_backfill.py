"""`index missing`: what it queues, what it passes over, and what two of them do.

The selection is one statement against a real store, and its concurrency
guarantee is an advisory lock — neither can be tested against a stand-in, so
both live here. What the command prints is here too, because it builds its own
settings and opens a database exactly as it does in a terminal.
"""

import asyncio
import io
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner, Result

from app.cli import app as cli
from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Asset, dimension_of
from app.main import create_app
from app.repositories import AssetRepository, EmbeddingRepository
from app.repositories.jobs import IndexingJobRepository
from app.services import indexing
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"
DINO_DIM = dimension_of(DINOV2_LARGE)
BOTH = (CLIP_VIT_L14, DINOV2_LARGE)


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
    """Both models enabled: a backfill is the command for the one that arrived
    after the pictures did."""
    return db_settings.model_copy(update={"media_root": media_root, "enabled_models": BOTH})


def a_vector(seed: int) -> list[float]:
    values = [0.0] * DINO_DIM
    values[0] = 1.0
    values[1] = seed / 100.0
    return values


async def add_asset(repository: AssetRepository, seed: int) -> Asset:
    return await repository.add(
        sha256=f"{seed:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024 * seed,
        source="upload",
    )


async def queued_for(engine: AsyncEngine, model: str) -> list[UUID]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT asset_id FROM indexing_jobs WHERE model = :model ORDER BY created_at"),
            {"model": model},
        )
    return [asset_id for (asset_id,) in rows]


async def a_store_of_every_kind(engine: AsyncEngine) -> dict[str, Asset]:
    """One asset of each kind the selection has to tell apart."""
    factory = create_session_factory(engine)
    async with factory() as session:
        assets = AssetRepository(session)
        embeddings = EmbeddingRepository(session)
        indexed = await add_asset(assets, 1)
        waiting = await add_asset(assets, 2)
        gave_up = await add_asset(assets, 3)
        nothing = await add_asset(assets, 4)
        await embeddings.upsert(asset_id=indexed.id, model=DINOV2_LARGE, vector=a_vector(1))
        for asset, status in ((waiting, "pending"), (gave_up, "failed")):
            await session.execute(
                sa.text(
                    "INSERT INTO indexing_jobs (asset_id, model, status, last_error) "
                    "VALUES (:id, :model, :status, 'RuntimeError')"
                ),
                {"id": str(asset.id), "model": DINOV2_LARGE, "status": status},
            )
        await session.commit()
    return {"indexed": indexed, "waiting": waiting, "gave_up": gave_up, "nothing": nothing}


# --- what is queued -----------------------------------------------------------


async def test_only_an_asset_with_neither_a_vector_nor_work_is_queued(
    engine: AsyncEngine, settings: Settings
) -> None:
    store = await a_store_of_every_kind(engine)

    missing = await indexing.queue_missing(
        session_factory=create_session_factory(engine), settings=settings, model=DINOV2_LARGE
    )

    assert missing.queued == [store["nothing"].id]
    assert missing.skipped_failed == [store["gave_up"].id]
    assert await queued_for(engine, DINOV2_LARGE) == [
        store["waiting"].id,
        store["gave_up"].id,
        store["nothing"].id,
    ], "the two that were already there, and the one this run added"


async def test_work_that_gave_up_is_passed_over_rather_than_retried(
    engine: AsyncEngine, settings: Settings
) -> None:
    """FR-IDX-5: a reset is the only thing that runs failed work again. A fresh
    row with a fresh attempt budget would be that retry under another name.
    """
    store = await a_store_of_every_kind(engine)

    await indexing.queue_missing(
        session_factory=create_session_factory(engine), settings=settings, model=DINOV2_LARGE
    )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text("SELECT status, attempts FROM indexing_jobs WHERE asset_id = :id"),
                {"id": str(store["gave_up"].id)},
            )
        ).all()
    assert rows == [("failed", 0)], "one row, still failed, with no new budget"


async def test_asking_twice_queues_nothing_the_second_time(
    engine: AsyncEngine, settings: Settings
) -> None:
    factory = create_session_factory(engine)
    await a_store_of_every_kind(engine)

    first = await indexing.queue_missing(
        session_factory=factory, settings=settings, model=DINOV2_LARGE
    )
    second = await indexing.queue_missing(
        session_factory=factory, settings=settings, model=DINOV2_LARGE
    )

    assert len(first.queued) == 1
    assert second.queued == []
    assert len(await queued_for(engine, DINOV2_LARGE)) == 3


async def test_a_store_that_needs_nothing_queues_nothing(
    engine: AsyncEngine, settings: Settings
) -> None:
    missing = await indexing.queue_missing(
        session_factory=create_session_factory(engine), settings=settings, model=DINOV2_LARGE
    )

    assert missing.queued == []
    assert missing.skipped_failed == []


async def test_the_other_model_is_untouched(engine: AsyncEngine, settings: Settings) -> None:
    await a_store_of_every_kind(engine)

    await indexing.queue_missing(
        session_factory=create_session_factory(engine), settings=settings, model=DINOV2_LARGE
    )

    assert await queued_for(engine, CLIP_VIT_L14) == []


async def test_a_model_this_build_does_not_run_is_refused(
    engine: AsyncEngine, db_settings: Settings
) -> None:
    with pytest.raises(indexing.ModelNotEnabled, match=DINOV2_LARGE):
        await indexing.queue_missing(
            session_factory=create_session_factory(engine),
            settings=db_settings.model_copy(update={"enabled_models": (CLIP_VIT_L14,)}),
            model=DINOV2_LARGE,
        )


# --- two of them at once ------------------------------------------------------


async def test_a_second_backfill_waits_for_the_first_and_then_finds_nothing(
    engine: AsyncEngine, settings: Settings
) -> None:
    """The guarantee the queue's own schema cannot give: `indexing_jobs` has no
    unique constraint on (asset, model), so nothing but the advisory lock keeps
    two runs from both finding the same asset unqueued.

    The two transactions are made to overlap rather than hoped to: the first is
    held open after it has queued everything, and the second is started and must
    still be waiting. Without the lock it does not wait — it selects against a
    store where nothing is queued yet and inserts a second row for every asset.
    """
    factory = create_session_factory(engine)
    async with factory() as session:
        assets = AssetRepository(session)
        created = [await add_asset(assets, seed) for seed in range(1, 6)]
        await session.commit()

    async with factory() as first:
        async with first.begin():
            queued = await IndexingJobRepository(first).queue_missing(model=DINOV2_LARGE)
            assert sorted(queued.queued) == sorted(asset.id for asset in created)

            second = asyncio.create_task(
                indexing.queue_missing(
                    session_factory=factory, settings=settings, model=DINOV2_LARGE
                )
            )
            await asyncio.sleep(0.2)
            assert not second.done(), "it ran while the first transaction was still open"
        # The first commits here, and the second may proceed.
        result = await asyncio.wait_for(second, timeout=10)

    assert result.queued == [], "everything it would have queued is already queued"
    assert sorted(await queued_for(engine, DINOV2_LARGE)) == sorted(
        asset.id for asset in created
    ), "one row per asset, no more"


# --- the command --------------------------------------------------------------


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    """The command builds its own settings, so the test speaks to it the way an
    operator does: through the environment."""
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("MEDIA_ROOT", str(settings.media_root))
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("ENABLED_MODELS", ",".join(BOTH))


async def run_cli(*arguments: str) -> Result:
    """The command in a thread of its own: it is a synchronous entry point that
    calls `asyncio.run`, and the test's own loop must not be the one it finds."""
    return await asyncio.to_thread(CliRunner().invoke, cli, list(arguments))


def stored_picture(root: Path, asset: Asset) -> None:
    """The original the runner will read, at the path the storage derives."""
    original = MediaStorage.at(root).original(asset.id, "png")
    original.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(30, 90, 200)).save(buffer, format="PNG")
    original.write_bytes(buffer.getvalue())


async def test_the_command_queues_the_work_and_carries_it_out(
    engine: AsyncEngine, settings: Settings, environment: None
) -> None:
    factory = create_session_factory(engine)
    async with factory() as session:
        asset = await add_asset(AssetRepository(session), 1)
        await session.commit()
    stored_picture(settings.media_root, asset)

    result = await run_cli("index", "missing", "--model", DINOV2_LARGE)

    assert result.exit_code == 0, result.output
    assert f"model: {DINOV2_LARGE}" in result.output
    assert "queued: 1" in result.output
    assert "indexed: 1" in result.output
    assert "skipped (failed work): 0" in result.output
    async with engine.connect() as connection:
        vectors = (
            await connection.execute(
                sa.text("SELECT count(*) FROM embeddings WHERE model = :model"),
                {"model": DINOV2_LARGE},
            )
        ).scalar_one()
    assert vectors == 1


async def test_the_command_says_what_it_passed_over_and_what_runs_it_again(
    engine: AsyncEngine, environment: None
) -> None:
    await a_store_of_every_kind(engine)

    result = await run_cli("index", "missing", "--model", DINOV2_LARGE, "--no-index")

    assert result.exit_code == 0, result.output
    assert "skipped (failed work): 1" in result.output
    assert "reindex" in result.output


async def test_no_index_leaves_the_work_queued(
    engine: AsyncEngine, settings: Settings, environment: None
) -> None:
    factory = create_session_factory(engine)
    async with factory() as session:
        await add_asset(AssetRepository(session), 1)
        await session.commit()

    result = await run_cli("index", "missing", "--model", DINOV2_LARGE, "--no-index")

    assert result.exit_code == 0, result.output
    assert "indexing: not run" in result.output
    async with engine.connect() as connection:
        statuses = (
            await connection.execute(
                sa.text("SELECT status FROM indexing_jobs WHERE model = :model"),
                {"model": DINOV2_LARGE},
            )
        ).scalars()
    assert list(statuses) == ["pending"]


async def test_without_a_model_every_enabled_one_is_backfilled(
    engine: AsyncEngine, environment: None
) -> None:
    factory = create_session_factory(engine)
    async with factory() as session:
        await add_asset(AssetRepository(session), 1)
        await session.commit()

    result = await run_cli("index", "missing", "--no-index")

    assert result.exit_code == 0, result.output
    for model in BOTH:
        assert f"model: {model}" in result.output
        assert len(await queued_for(engine, model)) == 1


async def test_a_model_this_build_does_not_run_is_refused_by_the_command(
    environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLED_MODELS", CLIP_VIT_L14)

    result = await run_cli("index", "missing", "--model", DINOV2_LARGE)

    assert result.exit_code == 2
    assert DINOV2_LARGE in result.output


# --- and nothing else queues work ---------------------------------------------


async def test_nothing_queues_work_by_itself(
    engine: AsyncEngine, settings: Settings, media_root: Path
) -> None:
    """Not at start, not in the lifespan, not in a background task. A service
    that began writing rows and burning CPU because someone restarted it would
    be a worse service than one that waits to be asked.
    """
    factory = create_session_factory(engine)
    async with factory() as session:
        await add_asset(AssetRepository(session), 1)
        await add_asset(AssetRepository(session), 2)
        await session.commit()

    application: FastAPI = create_app(settings)
    async for client in make_client(application):
        assert (await client.get("/health")).status_code == 200

    async with engine.connect() as connection:
        jobs = (
            await connection.execute(sa.text("SELECT count(*) FROM indexing_jobs"))
        ).scalar_one()
    assert jobs == 0, "the lifespan ran, and created no work for the vectors that are missing"


async def test_a_read_of_the_store_creates_no_work_either(
    engine: AsyncEngine, settings: Settings
) -> None:
    factory = create_session_factory(engine)
    async with factory() as session:
        asset = await add_asset(AssetRepository(session), 1)
        await session.commit()

    application: FastAPI = create_app(settings)
    async for client in make_client(application):
        listing: httpx.Response = await client.get("/api/v1/assets")
        assert listing.status_code == 200
        assert (await client.get(f"/api/v1/assets/{asset.id}")).status_code == 200

    async with engine.connect() as connection:
        jobs = (
            await connection.execute(sa.text("SELECT count(*) FROM indexing_jobs"))
        ).scalar_one()
    assert jobs == 0
