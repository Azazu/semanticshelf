"""The contract every embedder owes, checked the same way for fake and real.

The unit suite runs these against the deterministic embedders; the on-demand
suite runs the same functions against CLIP, so "the real one behaves like the
fake the rest of the tests trust" is asserted rather than assumed.
"""

from collections.abc import Sequence

import numpy as np
from PIL.Image import Image

from app.ml.base import Embedder, EmbeddingResult

TOLERANCE = 1e-5


def assert_result_shape(result: EmbeddingResult, *, count: int, dim: int) -> None:
    assert result.vectors.dtype == np.float32, result.vectors.dtype
    assert result.vectors.shape == (count, dim), result.vectors.shape
    assert len(result.truncated) == count


def assert_unit_rows(vectors: np.ndarray) -> None:
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=TOLERANCE), norms


def assert_text_conformance(embedder: Embedder, texts: Sequence[str]) -> None:
    result = embedder.embed_text(texts)
    assert_result_shape(result, count=len(texts), dim=embedder.dim)
    assert_unit_rows(result.vectors)


def assert_image_conformance(embedder: Embedder, images: Sequence[Image]) -> None:
    result = embedder.embed_images(images)
    assert_result_shape(result, count=len(images), dim=embedder.dim)
    assert_unit_rows(result.vectors)


def assert_batch_keeps_order(embedder: Embedder, texts: Sequence[str]) -> None:
    """One call over n inputs equals n calls over one input, row for row."""
    batched = embedder.embed_text(texts).vectors
    one_by_one = np.stack([embedder.embed_text([text]).vectors[0] for text in texts])
    assert np.allclose(batched, one_by_one, atol=TOLERANCE)


def assert_empty_batch_is_empty(embedder: Embedder) -> None:
    result = embedder.embed_images([])
    assert_result_shape(result, count=0, dim=embedder.dim)
