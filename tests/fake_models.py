"""Every model this build implements, faked.

A suite that must never load weights cannot fake only the model it happens to
use today: the moment a second key is enabled by default, an upload queues work
for it and something downstream loads it for real — a download in CI and
minutes of CPU here. So the registry is replaced key by key, from
`IMPLEMENTED_MODELS`, and each stand-in takes what its real counterpart takes
(`MODEL_MODALITIES`), so a test that asks DINOv2 for text is refused here for
the same reason it would be refused in production.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from app.domain import IMPLEMENTED_MODELS, dimension_of, modality_of
from app.ml import registry
from app.ml.fake import FakeEmbedder


def fake_for(key: str) -> FakeEmbedder:
    """The stand-in for one key: its width, and what it can be asked."""
    return FakeEmbedder(key, dimension_of(key), supports_text=modality_of(key).text)


@contextmanager
def fake_models() -> Iterator[None]:
    """Replace every factory with a fake, and put the table back afterwards.

    The factories are replaced rather than the registry's contents, so the lazy
    load inside the application still runs its normal path; only what it builds
    is fake.
    """
    registry.clear()
    original = dict(registry.FACTORIES)
    for key in IMPLEMENTED_MODELS:
        registry.FACTORIES[key] = lambda _settings, key=key: fake_for(key)
    try:
        yield
    finally:
        registry.FACTORIES.clear()
        registry.FACTORIES.update(original)
        registry.clear()
