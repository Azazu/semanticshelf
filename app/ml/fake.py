"""A deterministic embedder that needs no weights, no network and no runtime.

It exists so the rest of the system can be tested — ordering, thresholds,
pagination, model isolation — without loading a model. Vectors come from a hash
of the input, so the same text gives the same vector in another process and a
fixture written today still holds tomorrow.

What it does **not** do is see. Text and an image agree when the image carries
the same label in its `info` dictionary, which a test helper writes; the fake
models the *relationship* a real joint model has between its two towers, and no
result it produces is evidence about CLIP.
"""

import hashlib
from collections.abc import Sequence

import numpy as np
from PIL.Image import Image

from app.ml.base import EmbeddingResult, TextNotSupportedError, Vectors, empty, normalise

#: The field a test helper writes into `Image.info` to tie an image to a word.
IMAGE_LABEL_FIELD = "fake_label"


def vector_for(label: str, dim: int) -> np.ndarray:
    """A stable pseudo-random direction for a label.

    Derived from SHAKE-256 rather than from a seeded generator: the bytes of a
    hash do not change between library versions, so a vector recorded in a test
    stays valid.
    """
    raw = hashlib.shake_256(label.encode("utf-8")).digest(dim * 4)
    words = np.frombuffer(raw, dtype="<u4").astype(np.float64)
    return words / float(2**32) - 0.5


def label_of(image: Image) -> str:
    """The word an image stands for, or a stable label derived from its pixels."""
    label = image.info.get(IMAGE_LABEL_FIELD)
    if isinstance(label, str) and label:
        return label
    return hashlib.shake_256(image.tobytes()).hexdigest(16)


class FakeEmbedder:
    """Satisfies `Embedder` without a model.

    `supports_text=False` gives an image-only model, which is what a
    DINOv2-shaped adapter looks like from the outside.
    """

    def __init__(self, key: str, dim: int, *, supports_text: bool = True) -> None:
        self._key = key
        self._dim = dim
        self._supports_text = supports_text

    @property
    def key(self) -> str:
        return self._key

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def supports_text(self) -> bool:
        return self._supports_text

    def _vectors(self, labels: Sequence[str]) -> Vectors:
        if not labels:
            return empty(self._dim).vectors
        return normalise(np.stack([vector_for(label, self._dim) for label in labels]))

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        if not self._supports_text:
            raise TextNotSupportedError(f"model {self._key!r} has no text tower")
        return EmbeddingResult(vectors=self._vectors(texts), truncated=(False,) * len(texts))

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        labels = [label_of(image) for image in images]
        return EmbeddingResult(vectors=self._vectors(labels), truncated=(False,) * len(images))


def labelled_image(label: str, size: tuple[int, int] = (8, 8)) -> Image:
    """A tiny image the fake will recognise as standing for `label`."""
    from PIL import Image as PILImage

    image = PILImage.new("RGB", size, color=(1, 2, 3))
    image.info[IMAGE_LABEL_FIELD] = label
    return image
