"""The real style descriptor, once.

Marked `models`, so neither `make check` nor CI ever runs it: it reads about
1.7 GB and needs the network the first time. It also needs the `style`
dependency group, which nothing installs implicitly — run it with

    uv run --group style pytest -m models tests/models/test_style_candidate.py

and it skips rather than fails when that group is absent.

What is asserted here is what no test without the weights can see: that the
checkpoint pours into the tower with nothing missing and nothing left over,
that what comes out is the width the style head declares, and that the adapter
refuses a checkpoint one tensor short instead of ranking with a layer of noise
in it.
"""

from collections.abc import Iterator

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL.Image import Image as Picture

from app.core.settings import Settings
from app.ml.base import CheckpointTensorsError
from tests.embedder_conformance import TOLERANCE, assert_image_conformance
from tests.scripts import script_module

pytest.importorskip("open_clip", reason="the `style` dependency group is not installed")

candidate = script_module("style_candidate")

pytestmark = pytest.mark.models

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


def configured() -> Settings:
    return Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)  # type: ignore[call-arg]


def picture(shift: int) -> Picture:
    """A gradient that differs from its neighbours, built rather than read."""
    image = PILImage.new("RGB", (96, 96))
    pixels = image.load()
    assert pixels is not None
    for x in range(96):
        for y in range(96):
            pixels[x, y] = ((x * 2 + shift) % 256, (y * 2 + shift) % 256, (x + y + shift) % 256)
    return image


@pytest.fixture(scope="module")
def state() -> Iterator[dict[str, object]]:
    """Read once: the download and the unpickling are the expensive part."""
    yield candidate.read_state(configured().model_cache)


@pytest.fixture(scope="module")
def embedder(state: dict[str, object]) -> Iterator[object]:
    yield candidate.StyleCandidate.build(state, batch_size=4)


def test_the_checkpoint_fills_the_tower_exactly(state: dict[str, object]) -> None:
    """Nothing missing and nothing left over — the claim the proposal makes,
    asserted against the file rather than quoted from a probe."""
    candidate.StyleCandidate.build(state, batch_size=2)


def test_the_vectors_are_the_width_the_style_head_declares(embedder: object) -> None:
    assert embedder.dim == candidate.WIDTH  # type: ignore[attr-defined]

    result = embedder.embed_images([picture(0)])  # type: ignore[attr-defined]

    assert result.vectors.shape == (1, candidate.WIDTH)


def test_it_keeps_the_contract_every_embedder_here_keeps(embedder: object) -> None:
    assert_image_conformance(embedder, [picture(0), picture(70), picture(140)])  # type: ignore[arg-type]


def test_a_batch_comes_back_in_the_order_it_was_given(embedder: object) -> None:
    """The batch size is 4 and there are five pictures, so this crosses a
    forward pass: a stitched-together result that lost the order would rank
    every picture against the wrong one."""
    images = [picture(shift) for shift in (0, 50, 100, 150, 200)]

    batched = embedder.embed_images(images).vectors  # type: ignore[attr-defined]
    one_by_one = np.stack(
        [embedder.embed_images([image]).vectors[0] for image in images]  # type: ignore[attr-defined]
    )

    assert np.allclose(batched, one_by_one, atol=TOLERANCE)


def test_embedding_nothing_touches_nothing(embedder: object) -> None:
    result = embedder.embed_images([])  # type: ignore[attr-defined]

    assert result.vectors.shape == (0, candidate.WIDTH)


def test_a_checkpoint_one_tensor_short_is_refused(state: dict[str, object]) -> None:
    """The demonstrated failing input for the tensor guard: with the guard
    removed this build succeeds and the tower keeps one randomly initialised
    layer, which the width check cannot see."""
    short = {
        name: tensor for name, tensor in state.items() if not name.endswith(".attn.in_proj_weight")
    }

    with pytest.raises(CheckpointTensorsError, match="missing"):
        candidate.StyleCandidate.build(short, batch_size=2)
