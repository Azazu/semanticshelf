"""The shared contract, run against every embedder that needs no weights.

Adding a model means adding one entry to `EMBEDDERS`. The real adapters run the
same assertions from `tests/models/`, so the contract is one definition rather
than two.
"""

import pytest

from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.ml.base import Embedder
from app.ml.fake import FakeEmbedder, labelled_image
from tests.embedder_conformance import (
    assert_batch_keeps_order,
    assert_empty_batch_is_empty,
    assert_image_conformance,
    assert_text_conformance,
)

EMBEDDERS: list[tuple[str, Embedder]] = [
    ("fake-with-text", FakeEmbedder(CLIP_VIT_L14, 768)),
    ("fake-image-only", FakeEmbedder(DINOV2_LARGE, 1024, supports_text=False)),
]
IDS = [name for name, _ in EMBEDDERS]


@pytest.mark.parametrize("embedder", [e for _, e in EMBEDDERS], ids=IDS)
def test_key_and_width_are_readable_without_loading(embedder: Embedder) -> None:
    assert isinstance(embedder.key, str) and embedder.key
    assert isinstance(embedder.dim, int) and embedder.dim > 0


@pytest.mark.parametrize("embedder", [e for _, e in EMBEDDERS], ids=IDS)
def test_images_conform(embedder: Embedder) -> None:
    assert_image_conformance(embedder, [labelled_image("dragon"), labelled_image("castle")])


@pytest.mark.parametrize("embedder", [e for _, e in EMBEDDERS], ids=IDS)
def test_an_empty_batch_touches_nothing(embedder: Embedder) -> None:
    assert_empty_batch_is_empty(embedder)


@pytest.mark.parametrize(
    "embedder",
    [e for _, e in EMBEDDERS if getattr(e, "supports_text", True)],
    ids=["fake-with-text"],
)
def test_text_conforms(embedder: Embedder) -> None:
    assert_text_conformance(embedder, ["a red dragon in the fog", "a castle"])
    assert_batch_keeps_order(embedder, ["dragon", "castle", "fog"])
