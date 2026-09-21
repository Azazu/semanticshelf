"""Fixtures for the api suite.

These tests run against the app factory with no database and no weights. The
second half of that is not automatic: an endpoint that embeds a query will
happily load a real checkpoint if nothing stops it, which is a download in CI
and minutes of CPU here. So nothing in this suite can reach a real model.
"""

from collections.abc import Iterator

import pytest

from app.domain import CLIP_VIT_L14, dimension_of
from app.ml import registry
from app.ml.fake import FakeEmbedder


@pytest.fixture(autouse=True)
def fake_model() -> Iterator[None]:
    """CLIP without the weights, for every api test.

    The factory is replaced rather than the registry's contents, so the lazy
    load inside the application still runs its normal path; only what it builds
    is fake. The real adapter has its own suite (`-m models`).
    """
    registry.clear()
    original = dict(registry.FACTORIES)
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: FakeEmbedder(
        CLIP_VIT_L14, dimension_of(CLIP_VIT_L14)
    )
    yield
    registry.FACTORIES.clear()
    registry.FACTORIES.update(original)
    registry.clear()
