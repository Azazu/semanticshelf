"""The deterministic embedder: stable across processes, and honest about what it is."""

import hashlib
import subprocess
import sys

import numpy as np
import pytest

from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.ml.base import TextNotSupportedError
from app.ml.fake import FakeEmbedder, labelled_image

DIM = 32


def embedder(*, supports_text: bool = True) -> FakeEmbedder:
    return FakeEmbedder(CLIP_VIT_L14, DIM, supports_text=supports_text)


def test_the_same_input_gives_the_same_vector_in_another_process() -> None:
    # Compared as raw bytes: a decimal rendering would lose float32 precision
    # and turn an exact property into an approximate one.
    here = embedder().embed_text(["a red dragon in the fog"]).vectors[0]
    program = (
        "import hashlib;"
        "from app.ml.fake import FakeEmbedder;"
        f"v = FakeEmbedder({CLIP_VIT_L14!r}, {DIM}).embed_text(['a red dragon in the fog']).vectors[0];"
        "print(hashlib.sha256(v.tobytes()).hexdigest())"
    )
    finished = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == hashlib.sha256(here.tobytes()).hexdigest()


def test_different_inputs_give_different_vectors() -> None:
    vectors = embedder().embed_text(["dragon", "castle"]).vectors
    assert not np.allclose(vectors[0], vectors[1])


def test_text_and_the_image_of_the_same_label_land_together() -> None:
    fake = embedder()
    text = fake.embed_text(["dragon"]).vectors[0]
    same = fake.embed_images([labelled_image("dragon")]).vectors[0]
    other = fake.embed_images([labelled_image("castle")]).vectors[0]

    assert float(text @ same) > float(text @ other)


def test_an_image_without_a_label_still_gets_a_stable_vector() -> None:
    from PIL import Image as PILImage

    plain = PILImage.new("RGB", (4, 4), color=(9, 9, 9))
    first = embedder().embed_images([plain]).vectors[0]
    second = embedder().embed_images([plain]).vectors[0]
    assert np.array_equal(first, second)


def test_an_image_only_model_refuses_text_and_names_itself() -> None:
    fake = FakeEmbedder(DINOV2_LARGE, DIM, supports_text=False)
    with pytest.raises(TextNotSupportedError, match=DINOV2_LARGE):
        fake.embed_text(["dragon"])
    # It still embeds images.
    assert fake.embed_images([labelled_image("dragon")]).vectors.shape == (1, DIM)


def test_nothing_is_reported_as_truncated() -> None:
    result = embedder().embed_text(["short", "also short"])
    assert result.truncated == (False, False)
