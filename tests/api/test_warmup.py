"""What starting the application does, and does not, load."""

import threading
from collections.abc import Iterator

import pytest

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14
from app.main import create_app
from app.ml import registry
from app.ml.base import Embedder
from app.ml.fake import FakeEmbedder

DIM = 16


class RecordingFactory:
    """Stands in for the real adapter and remembers who loaded it, and how often."""

    def __init__(self) -> None:
        self.calls = 0
        self.threads: list[threading.Thread] = []

    def __call__(self, settings: Settings) -> Embedder:
        self.calls += 1
        self.threads.append(threading.current_thread())
        return FakeEmbedder(CLIP_VIT_L14, DIM)


@pytest.fixture(autouse=True)
def empty_registry() -> None:
    registry.clear()


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingFactory]:
    recording = RecordingFactory()
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, recording)
    yield recording


async def test_starting_without_warm_up_loads_nothing(
    test_settings: Settings, factory: RecordingFactory
) -> None:
    app = create_app(test_settings)

    async with app.router.lifespan_context(app):
        assert factory.calls == 0
        assert registry.loaded_keys() == frozenset()
        assert app.state.inference_pool is not None  # the threads exist, the models do not


async def test_a_named_key_is_loaded_once_at_start_on_a_pool_thread(
    test_settings: Settings, factory: RecordingFactory
) -> None:
    app = create_app(test_settings.model_copy(update={"model_warmup": (CLIP_VIT_L14,)}))
    serving = threading.current_thread()

    async with app.router.lifespan_context(app):
        assert factory.calls == 1
        assert registry.loaded_keys() == frozenset({CLIP_VIT_L14})
        loader = factory.threads[0]
        assert loader is not serving
        assert loader.name.startswith("inference")


async def test_the_pool_is_shut_down_with_the_application(test_settings: Settings) -> None:
    app = create_app(test_settings)

    async with app.router.lifespan_context(app):
        pool = app.state.inference_pool

    with pytest.raises(RuntimeError, match="shutdown"):
        pool.submit(int)
