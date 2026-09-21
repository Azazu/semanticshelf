"""The inference pool: loading and embedding both stay off the event loop.

The timings here are deliberately coarse. The assertion is not "fast" but
"something else ran at all while the model was busy", which is false by a wide
margin when the call happens inline on the loop.
"""

import asyncio
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14
from app.ml import registry
from app.ml.base import Embedder, EmbeddingResult
from app.ml.fake import FakeEmbedder
from app.ml.pool import acquire, create_pool, run_in_pool, warm_up

DIM = 16
BLOCKING = 0.2  # how long the stand-in pretends to work
TICK = 0.01  # how often the other task wants the loop back
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


@pytest.fixture(autouse=True)
def empty_registry() -> None:
    registry.clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = create_pool(settings)
    try:
        yield executor
    finally:
        executor.shutdown(wait=True)


class SlowEmbedder(FakeEmbedder):
    """Deterministic like its parent, but it holds its thread for a while."""

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        threading.Event().wait(BLOCKING)
        return super().embed_text(texts)


def slow_factory(settings: Settings) -> Embedder:
    threading.Event().wait(BLOCKING)
    return FakeEmbedder(CLIP_VIT_L14, DIM)


async def count_ticks_during(awaitable: object) -> tuple[int, object]:
    """Await something while a second task counts how often it gets the loop."""
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(TICK)

    ticker = asyncio.create_task(tick())
    await asyncio.sleep(0)  # let the ticker reach its first await
    try:
        result = await awaitable  # type: ignore[misc]
    finally:
        ticker.cancel()
    return ticks, result


async def test_work_submitted_through_the_helper_runs_on_another_thread(
    pool: ThreadPoolExecutor,
) -> None:
    here = threading.current_thread()
    there = await run_in_pool(pool, threading.current_thread)

    assert there is not here
    assert there.name.startswith("inference")


async def test_the_pool_runs_as_many_threads_as_the_configuration_asks_for(
    settings: Settings,
) -> None:
    configured = create_pool(settings.model_copy(update={"inference_workers": 3}))
    together = threading.Barrier(3)
    try:
        # Each task waits for the other two: it returns only if all three run at once.
        results = await asyncio.gather(*(run_in_pool(configured, together.wait) for _ in range(3)))
    finally:
        configured.shutdown(wait=True)

    assert sorted(results) == [0, 1, 2]


async def test_the_loop_keeps_running_while_an_embed_is_in_flight(
    pool: ThreadPoolExecutor,
) -> None:
    embedder = SlowEmbedder(CLIP_VIT_L14, DIM)

    ticks, result = await count_ticks_during(run_in_pool(pool, embedder.embed_text, ["dragon"]))

    assert isinstance(result, EmbeddingResult)
    assert result.vectors.shape == (1, DIM)
    assert ticks > 5, f"the loop only got {ticks} turns while the model worked"


async def test_the_loop_keeps_running_while_a_model_is_loading(
    pool: ThreadPoolExecutor, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, slow_factory)

    ticks, embedder = await count_ticks_during(acquire(pool, CLIP_VIT_L14, settings))

    assert isinstance(embedder, FakeEmbedder)
    assert ticks > 5, f"the loop only got {ticks} turns while the model loaded"


async def test_acquiring_twice_loads_once_and_shares_the_result(
    pool: ThreadPoolExecutor, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    loads = 0

    def counting(settings: Settings) -> Embedder:
        nonlocal loads
        loads += 1
        return FakeEmbedder(CLIP_VIT_L14, DIM)

    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, counting)

    first, second = await asyncio.gather(
        acquire(pool, CLIP_VIT_L14, settings), acquire(pool, CLIP_VIT_L14, settings)
    )

    assert first is second
    assert loads == 1


async def test_warm_up_loads_the_named_keys_and_nothing_else(
    pool: ThreadPoolExecutor, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, slow_factory)

    assert await warm_up(pool, settings) == ()
    assert registry.loaded_keys() == frozenset()

    warming = settings.model_copy(update={"model_warmup": (CLIP_VIT_L14,)})
    assert await warm_up(pool, warming) == (CLIP_VIT_L14,)
    assert registry.loaded_keys() == frozenset({CLIP_VIT_L14})
