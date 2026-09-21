"""The registry: nothing early, once under concurrency, and failures forgotten."""

import threading

import pytest

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, IMPLEMENTED_MODELS, UnknownModelError
from app.ml import registry
from app.ml.base import Embedder
from app.ml.fake import FakeEmbedder

DIM = 16
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


@pytest.fixture(autouse=True)
def empty_registry() -> None:
    registry.clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)


class CountingFactory:
    """A stand-in adapter that records how often it was actually built."""

    def __init__(self, *, fails: int = 0, delay: float = 0.0) -> None:
        self.calls = 0
        self.fails = fails
        self.delay = delay
        self.lock = threading.Lock()

    def __call__(self, settings: Settings) -> Embedder:
        with self.lock:
            self.calls += 1
            failing = self.calls <= self.fails
        if self.delay:  # widen the window a racing caller has to squeeze into
            threading.Event().wait(self.delay)
        if failing:
            raise RuntimeError("the hub is unreachable")
        return FakeEmbedder(CLIP_VIT_L14, DIM)


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> CountingFactory:
    counting = CountingFactory()
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, counting)
    return counting


def test_the_table_of_factories_matches_what_the_build_declares() -> None:
    # Two tables state the same fact — the settings guard reads one, the
    # registry the other. They drift the moment nobody compares them.
    assert frozenset(registry.FACTORIES) == IMPLEMENTED_MODELS


def test_nothing_is_loaded_until_a_key_is_asked_for(
    factory: CountingFactory, settings: Settings
) -> None:
    assert registry.loaded_keys() == frozenset()
    assert factory.calls == 0

    registry.get_embedder(CLIP_VIT_L14, settings)

    assert registry.loaded_keys() == frozenset({CLIP_VIT_L14})
    assert factory.calls == 1


def test_asking_twice_returns_the_same_object_without_loading_again(
    factory: CountingFactory, settings: Settings
) -> None:
    first = registry.get_embedder(CLIP_VIT_L14, settings)
    second = registry.get_embedder(CLIP_VIT_L14, settings)

    assert first is second
    assert factory.calls == 1


def test_many_threads_asking_at_once_load_exactly_once(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    counting = CountingFactory(delay=0.05)
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, counting)
    threads_count = 8
    start = threading.Barrier(threads_count)
    results: list[Embedder] = []
    results_lock = threading.Lock()

    def ask() -> None:
        start.wait()
        embedder = registry.get_embedder(CLIP_VIT_L14, settings)
        with results_lock:
            results.append(embedder)

    threads = [threading.Thread(target=ask) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert counting.calls == 1
    assert len(results) == threads_count
    assert all(embedder is results[0] for embedder in results)


def test_a_failed_load_is_not_remembered(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    counting = CountingFactory(fails=1)
    monkeypatch.setitem(registry.FACTORIES, CLIP_VIT_L14, counting)

    with pytest.raises(RuntimeError):
        registry.get_embedder(CLIP_VIT_L14, settings)
    assert registry.loaded_keys() == frozenset()

    recovered = registry.get_embedder(CLIP_VIT_L14, settings)
    assert recovered.dim == DIM
    assert counting.calls == 2


def test_a_key_the_configuration_did_not_enable_is_refused(
    factory: CountingFactory, settings: Settings
) -> None:
    disabled = settings.model_copy(update={"enabled_models": ()})

    with pytest.raises(UnknownModelError, match=CLIP_VIT_L14):
        registry.get_embedder(CLIP_VIT_L14, disabled)
    assert factory.calls == 0


def test_an_enabled_key_without_an_adapter_is_refused(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # The safety net for the two tables above drifting apart in a live build.
    monkeypatch.delitem(registry.FACTORIES, CLIP_VIT_L14)

    with pytest.raises(UnknownModelError, match="no adapter"):
        registry.get_embedder(CLIP_VIT_L14, settings)
