"""The real DINOv2 checkpoint, once.

Marked `models`, so neither `make check` nor CI ever runs it: it downloads
about 1.2 GB the first time and needs the network. It is the only evidence that
the adapter and the contract agree about the actual weights — everything else
in the suite runs against the deterministic stand-in.

Run it with `make test-models`.
"""

from collections.abc import Iterator

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL.Image import Image

from app.core.settings import Settings
from app.domain import DINOV2_LARGE, dimension_of
from app.ml.base import TextNotSupportedError
from app.ml.dinov2 import Dinov2Embedder
from tests.embedder_conformance import (
    assert_empty_batch_is_empty,
    assert_image_conformance,
)

pytestmark = pytest.mark.models

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


@pytest.fixture(scope="module")
def embedder() -> Iterator[Dinov2Embedder]:
    """Loaded once for the whole module: the download and the read are the
    expensive part, and the adapter holds no per-test state."""
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)
    yield Dinov2Embedder.load(settings)


def stripes(colour: tuple[int, int, int], *, size: int = 96) -> Image:
    """A picture with structure, not a flat field: DINOv2 describes appearance,
    and a solid rectangle gives it almost nothing to describe."""
    picture = PILImage.new("RGB", (size, size), color=(250, 250, 250))
    pixels = picture.load()
    assert pixels is not None
    for y in range(size):
        for x in range(size):
            if (x // 8 + y // 16) % 2 == 0:
                pixels[x, y] = colour
    return picture


def test_it_reports_the_key_and_width_the_registry_declares(embedder: Dinov2Embedder) -> None:
    assert embedder.key == DINOV2_LARGE
    assert embedder.dim == dimension_of(DINOV2_LARGE) == 1024


def test_images_satisfy_the_contract(embedder: Dinov2Embedder) -> None:
    assert_image_conformance(embedder, [stripes((200, 20, 20)), stripes((20, 20, 200))])


def test_an_empty_batch_touches_nothing(embedder: Dinov2Embedder) -> None:
    assert_empty_batch_is_empty(embedder)


def test_text_is_refused_rather_than_approximated(embedder: Dinov2Embedder) -> None:
    with pytest.raises(TextNotSupportedError, match=DINOV2_LARGE):
        embedder.embed_text(["a red dragon"])


def test_the_same_picture_rendered_twice_lands_near_itself(embedder: Dinov2Embedder) -> None:
    """What image→image search means: two encodings of one picture are nearer
    each other than either is to a different picture."""
    original = stripes((200, 20, 20))
    rescaled = original.resize((128, 128)).resize((96, 96))
    other = stripes((20, 20, 200))

    vectors = embedder.embed_images([original, rescaled, other]).vectors
    same = float(np.dot(vectors[0], vectors[1]))
    different = float(np.dot(vectors[0], vectors[2]))

    assert same > different, (same, different)


def test_a_greyscale_image_is_accepted(embedder: Dinov2Embedder) -> None:
    grey = PILImage.new("L", (96, 96), color=128)
    assert embedder.embed_images([grey]).vectors.shape == (1, embedder.dim)


def test_a_batch_larger_than_the_batch_size_is_split_and_keeps_order(
    embedder: Dinov2Embedder,
) -> None:
    # The default batch size is 8; ten inputs prove the loop stitches the
    # forward passes back together in the caller's order.
    images = [stripes((20 * number % 256, 40, 200)) for number in range(10)]
    whole = embedder.embed_images(images).vectors
    one_by_one = [embedder.embed_images([image]).vectors[0] for image in images]

    assert whole.shape == (10, embedder.dim)
    for index, single in enumerate(one_by_one):
        assert float(whole[index] @ single) > 0.999
