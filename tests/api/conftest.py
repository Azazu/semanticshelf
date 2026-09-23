"""Fixtures for the api suite.

These tests run against the app factory with no database and no weights. The
second half of that is not automatic: an endpoint that embeds a query will
happily load a real checkpoint if nothing stops it, which is a download in CI
and minutes of CPU here. So nothing in this suite can reach a real model.
"""

from collections.abc import Iterator

import pytest

from tests.fake_models import fake_models


@pytest.fixture(autouse=True)
def fake_model() -> Iterator[None]:
    """Every implemented model without its weights, for every api test.

    Every one, not only CLIP: both keys are enabled by default (FR-IDX-1), so
    faking one would leave the other reachable. The real adapters have their
    own suite (`-m models`).
    """
    with fake_models():
        yield
