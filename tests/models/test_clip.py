"""The real checkpoint, once.

Marked `models`, so neither `make check` nor CI ever runs it: it downloads
about 1.7 GB the first time and needs the network. It is the only evidence
that the adapter and the contract agree about the actual weights — everything
else in the suite runs against the deterministic stand-in.

Run it with `make test-models`.
"""

from collections.abc import Iterator

import pytest
from PIL import Image as PILImage
from PIL.Image import Image

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, dimension_of
from app.ml.clip import ClipEmbedder
from tests.embedder_conformance import (
    assert_batch_keeps_order,
    assert_empty_batch_is_empty,
    assert_image_conformance,
    assert_text_conformance,
)

pytestmark = pytest.mark.models

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"
LONG_TEXT = "a red dragon over a ruined castle in the fog, " * 40


@pytest.fixture(scope="module")
def embedder() -> Iterator[ClipEmbedder]:
    """Loaded once for the whole module: the download and the read are the
    expensive part, and the adapter holds no per-test state."""
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)
    yield ClipEmbedder.load(settings)


def picture(colour: tuple[int, int, int]) -> Image:
    return PILImage.new("RGB", (64, 64), color=colour)


def test_it_reports_the_key_and_width_the_registry_declares(embedder: ClipEmbedder) -> None:
    assert embedder.key == CLIP_VIT_L14
    assert embedder.dim == dimension_of(CLIP_VIT_L14) == 768


def test_text_satisfies_the_contract(embedder: ClipEmbedder) -> None:
    assert_text_conformance(embedder, ["a red dragon in the fog", "a castle"])
    assert_batch_keeps_order(embedder, ["dragon", "castle", "fog", "a photograph of a cat"])


def test_images_satisfy_the_contract(embedder: ClipEmbedder) -> None:
    assert_image_conformance(embedder, [picture((200, 20, 20)), picture((20, 20, 200))])


def test_an_empty_batch_touches_nothing(embedder: ClipEmbedder) -> None:
    assert_empty_batch_is_empty(embedder)


def test_a_greyscale_image_is_accepted(embedder: ClipEmbedder) -> None:
    grey = PILImage.new("L", (64, 64), color=128)
    assert embedder.embed_images([grey]).vectors.shape == (1, embedder.dim)


def test_text_longer_than_the_context_is_reported_as_truncated(embedder: ClipEmbedder) -> None:
    result = embedder.embed_text(["a castle", LONG_TEXT])

    assert result.truncated == (False, True)
    assert result.vectors.shape == (2, embedder.dim)


def test_a_batch_larger_than_the_batch_size_is_split_and_keeps_order(
    embedder: ClipEmbedder,
) -> None:
    # The default batch size is 8; ten inputs prove the loop stitches the
    # forward passes back together in the caller's order.
    texts = [f"a photograph of {number} apples" for number in range(10)]
    whole = embedder.embed_text(texts).vectors
    one_by_one = [embedder.embed_text([text]).vectors[0] for text in texts]

    assert whole.shape == (10, embedder.dim)
    for index, single in enumerate(one_by_one):
        assert float(whole[index] @ single) > 0.999
