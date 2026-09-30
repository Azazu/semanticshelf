"""Rebuilding a key, and filling one from another.

The engine under both commands is the same, and what is new in it is what these
tests are about: it carries out the work its selection **already had
outstanding**, not only the work it queued. The existing fill does not, which is
why a run interrupted halfway used to be finished by nobody.

Everything here runs against a real store and the deterministic stand-ins; no
weights are loaded.
"""

import io
from collections.abc import AsyncIterator, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import httpx
import numpy as np
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, WORKER_RUNNER, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import normalise
from app.ml.fake import FakeEmbedder, vector_for
from app.ml.pool import create_pool
from app.repositories.jobs import IndexingJobRepository
from app.services import indexing
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
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
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


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


class OtherCheckpoint(FakeEmbedder):
    """The same key, answering with different weights.

    What a checkpoint that moved looks like from the outside: the key is
    unchanged, the width is unchanged, and every vector is different. Nothing in
    the store can tell the two apart, which is the whole reason ADR-007 exists.
    """

    def _vectors(self, labels: Sequence[str]) -> np.ndarray:
        if not labels:
            return super()._vectors(labels)
        return normalise(np.stack([vector_for("moved:" + label, self.dim) for label in labels]))


@contextmanager
def moved_checkpoint() -> Iterator[None]:
    """Point the registry at the other checkpoint, from here on.

    A context manager rather than a fixture, and used around the repair alone:
    installed before the upload it would answer for both, and a test in which
    the corpus was written with the same weights it is repaired to proves
    nothing.
    """
    original = dict(registry.FACTORIES)
    registry.clear()
    registry.FACTORIES[CLIP_VIT_L14] = lambda _: OtherCheckpoint(
        CLIP_VIT_L14, dimension_of(CLIP_VIT_L14)
    )
    try:
        yield
    finally:
        registry.FACTORIES.clear()
        registry.FACTORIES.update(original)
        registry.clear()


async def upload(client: httpx.AsyncClient, seed: int) -> str:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def vectors_of(engine: AsyncEngine, model: str) -> dict[str, list[float]]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT asset_id, vector FROM embeddings WHERE model = :model"),
            {"model": model},
        )
    return {str(asset_id): list(vector) for asset_id, vector in rows}


async def states(engine: AsyncEngine, model: str) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT status FROM indexing_jobs WHERE model = :model ORDER BY created_at"),
            {"model": model},
        )
    return [status for (status,) in rows]


# --- a rebuild replaces what is there ------------------------------------------


async def test_a_rebuild_replaces_a_vector_rather_than_adding_one(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    before = await vectors_of(engine, CLIP_VIT_L14)
    assert len(before) == 1

    with moved_checkpoint():
        report = await indexing.rebuild(
            session_factory=sessions,
            storage=storage,
            settings=settings,
            pool=pool,
            model=CLIP_VIT_L14,
        )

    after = await vectors_of(engine, CLIP_VIT_L14)
    assert len(after) == 1, "a rebuild replaces a row, it does not add one"
    assert list(before) == list(after)
    assert after != before, "the weights moved, so the vector must have"
    assert report.work is not None and report.work.indexed == 1
    assert report.complete


async def test_a_run_finishes_what_an_interrupted_one_left(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """The hole the existing fill has: its selection passes over assets whose
    work is already waiting, and it drains only what it queued — so after a
    crash it queues nothing, drains nothing, and reports success."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert report.queued == [], "the work was already there"
    assert len(report.carried_over) == 1, "and this run carried it out"
    assert report.work is not None and report.work.indexed == 1
    assert await states(engine, CLIP_VIT_L14) == ["done", "done"], (
        "the upload's own job, and the rebuild's — both finished"
    )


async def test_work_a_live_claim_holds_is_left_alone_and_reported(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    async with sessions() as session, session.begin():
        repository = IndexingJobRepository(session)
        await repository.queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert len(report.held) == 1
    assert report.carried_over == []
    assert not report.complete, "a run cannot be complete over work somebody else holds"


async def test_a_repair_refuses_to_begin_while_a_live_claim_is_held(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """A process is writing this key now and nothing can say which checkpoint it
    holds — which is the one thing a repair cannot work around."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)

    with pytest.raises(indexing.HeldElsewhere, match="another runner"):
        await indexing.rebuild(
            session_factory=sessions,
            storage=storage,
            settings=settings,
            pool=pool,
            model=CLIP_VIT_L14,
            refuse_while_held=True,
        )


async def test_a_repair_does_not_refuse_on_an_expired_claim(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """An expired claim is what an interrupted repair leaves. Refusing on it
    would make a repair unable to finish itself, which is what the first draft
    of this change did."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 minute'")
        )

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
        refuse_while_held=True,
    )

    assert len(report.carried_over) == 1
    assert report.work is not None and report.work.indexed == 1


async def test_failed_work_is_neither_queued_nor_run(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET status = 'failed' WHERE model = :model"),
            {"model": CLIP_VIT_L14},
        )

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert report.queued == []
    assert len(report.skipped_failed) == 1
    assert not report.complete, "only an explicit reset runs failed work again"


# --- which runner carries it out -----------------------------------------------


async def test_a_deployment_with_its_own_runner_queues_and_executes_nothing(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """The rule every other creator of work already follows."""
    await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
    worker_only = settings.model_copy(update={"indexing_runner": WORKER_RUNNER})

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=worker_only,
        pool=pool,
        model=CLIP_VIT_L14,
        index=indexing.carries_out_work(worker_only),
    )

    assert len(report.queued) == 1
    assert report.work is None, "nothing is executed where a runner of its own exists"
    lines = indexing.describe_rebuild(report, settings=worker_only)
    assert any("INDEXING_RUNNER=worker" in line for line in lines), lines
