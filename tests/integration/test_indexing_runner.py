"""The runner that lives in the API process: what an upload sets going.

Stage 1 has no worker process — the queue is drained by a background task the
upload schedules. These tests are about that task: that it runs after the
response rather than inside it, that it takes the batch it is allowed to take
and no more, and that a model never runs on the event loop.
"""

import asyncio
import io
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import EmbeddingResult
from app.ml.fake import FakeEmbedder
from app.ml.pool import create_pool
from app.services import indexing
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"
CLIP_WIDTH = dimension_of(CLIP_VIT_L14)


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


async def vectors_and_states(engine: AsyncEngine) -> tuple[int, list[str]]:
    async with engine.connect() as connection:
        vectors = (
            await connection.execute(sa.text("SELECT count(*) FROM embeddings"))
        ).scalar_one()
        states = (
            (await connection.execute(sa.text("SELECT status FROM indexing_jobs ORDER BY status")))
            .scalars()
            .all()
        )
    return int(vectors), list(states)


class RecordsWhenTheBodyWentOut:
    """An ASGI wrapper that notes the moment the last body message is sent.

    The only way to show that the client did not wait for the indexing is to
    compare two instants: when the response left, and when the model was
    called. A background task runs after the body — an awaited call could not.
    """

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.sent_at: float | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        async def recording(message: Any) -> None:
            if message["type"] == "http.response.body" and not message.get("more_body"):
                self.sent_at = time.monotonic()
            await send(message)

        await self.app(scope, receive, recording)


async def test_an_upload_is_indexed_after_its_response_has_gone_out(
    app: FastAPI, engine: AsyncEngine
) -> None:
    embedder = FakeEmbedder(CLIP_VIT_L14, CLIP_WIDTH)
    real_embed = embedder.embed_images
    called_at: list[float] = []

    def note(images: Any) -> EmbeddingResult:
        called_at.append(time.monotonic())
        return real_embed(images)

    embedder.embed_images = note  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: embedder
    registry.clear()
    recorder = RecordsWhenTheBodyWentOut(app)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=recorder, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 201, response.text
    assert recorder.sent_at is not None and called_at, "both instants were observed"
    assert called_at[0] > recorder.sent_at, "the model ran only after the client had its answer"
    vectors, states = await vectors_and_states(engine)
    assert (vectors, states) == (1, ["done"]), "and the vector is there afterwards"


async def test_an_upload_whose_work_cannot_be_done_still_succeeds(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    """A drain that fails must not reach the client: the asset is stored, the
    response is a 201, and the job waits for its next attempt."""

    def refuse(images: Any) -> EmbeddingResult:
        raise RuntimeError("the model fell over")

    embedder = FakeEmbedder(CLIP_VIT_L14, CLIP_WIDTH)
    embedder.embed_images = refuse  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: embedder
    registry.clear()

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 201, response.text
    vectors, states = await vectors_and_states(engine)
    assert (vectors, states) == (0, ["pending"]), "the work waits for its next attempt"
    async with engine.connect() as connection:
        reason = (
            await connection.execute(sa.text("SELECT last_error FROM indexing_jobs"))
        ).scalar_one()
    assert reason == "RuntimeError", "a foreign failure leaves only its class"


async def test_a_drain_takes_the_batch_it_is_allowed_and_no_more(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
    client: httpx.AsyncClient,
) -> None:
    """More work than the bound: one run takes the bound and leaves the rest.

    A runner that drained while work remained would never end — and this one
    lives in the process that answers requests.
    """
    bounded = settings.model_copy(update={"worker_batch_size": 2})
    for seed in range(5):
        response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
        assert response.status_code == 201, response.text
    # Every upload drained its own job; put them all back to have five due.
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE indexing_jobs SET status = 'pending', attempts = 0, "
                "finished_at = NULL, lease_expires_at = NULL, available_at = now()"
            )
        )

    taken = await indexing.run_batch(
        session_factory=sessions, storage=storage, settings=bounded, pool=pool
    )

    assert taken == 2
    _, states = await vectors_and_states(engine)
    assert sorted(states) == ["done", "done", "pending", "pending", "pending"]


async def test_the_event_loop_keeps_running_while_a_model_is_busy(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    client: httpx.AsyncClient,
) -> None:
    """Inference goes to the pool, so the loop is free while it runs.

    Same shape as the pool tests of change 4: a slow embed is started, and the
    loop must keep ticking meanwhile. If the model ran on the loop, the ticks
    would stop dead for the whole of it.
    """
    slow = FakeEmbedder(CLIP_VIT_L14, CLIP_WIDTH)
    real_embed = slow.embed_images

    def sluggish(images: Any) -> EmbeddingResult:
        time.sleep(0.3)
        return real_embed(images)

    slow.embed_images = sluggish  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: slow
    registry.clear()
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})
    assert response.status_code == 201, response.text
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE indexing_jobs SET status = 'pending', attempts = 0, "
                "finished_at = NULL, lease_expires_at = NULL, available_at = now()"
            )
        )

    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(tick())
    try:
        taken = await indexing.run_batch(
            session_factory=sessions, storage=storage, settings=settings, pool=pool
        )
    finally:
        ticker.cancel()

    assert taken == 1
    assert ticks > 10, f"the loop was blocked while the model ran (ticks: {ticks})"
