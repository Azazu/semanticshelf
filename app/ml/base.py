"""What every embedding model looks like from the outside.

The contract is deliberately small: a key, a width known without loading
anything, and two calls that return unit-length `float32` rows. Everything the
service does with vectors — storing them, ranking them, comparing scores —
rests on those two properties, so they are enforced here once rather than
trusted in each adapter.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL.Image import Image

#: Row-major `float32`, shape `(n, dim)`, every row of unit length.
Vectors = np.ndarray


class TextNotSupportedError(RuntimeError):
    """Text was asked of a model that has no text tower."""


class ZeroVectorError(ValueError):
    """A vector of length zero cannot be normalised, and must not become `nan`."""


class CheckpointWidthError(RuntimeError):
    """A checkpoint produces vectors of a width its model key does not declare."""


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors, and whether each input had to be cut to fit the model.

    `truncated` is all `False` for images; it exists so a text caller can pass
    the fact on instead of quietly answering a different question.
    """

    vectors: Vectors
    truncated: tuple[bool, ...]

    def __post_init__(self) -> None:
        if len(self.truncated) != len(self.vectors):
            raise ValueError("one truncation flag per vector is required")


class Embedder(Protocol):
    """A model the service can embed with. Structural: adapters inherit nothing."""

    @property
    def key(self) -> str:
        """The stable model key, which is part of an embedding's identity."""

    @property
    def dim(self) -> int:
        """The width of the vectors this model produces, known without loading."""

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        """Embed text. Raises `TextNotSupportedError` when there is no text tower."""

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        """Embed images."""


def normalise(vectors: np.ndarray) -> Vectors:
    """Return `float32` rows of unit length.

    Cosine similarity is then the dot product, which is what makes the stored
    vectors of one model directly comparable and the index meaningful. A row of
    length zero has no direction, so it is refused rather than divided into
    `nan` values that would poison every comparison it touches.
    """
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError(f"expected a 2-dimensional array, got shape {matrix.shape}")
    norms = np.linalg.norm(matrix, axis=1)
    if bool(np.any(norms == 0)):
        raise ZeroVectorError("a zero-length vector cannot be normalised")
    return (matrix / norms[:, None]).astype(np.float32)


def empty(dim: int) -> EmbeddingResult:
    """The result of embedding nothing: no rows, no flags, no model touched."""
    return EmbeddingResult(vectors=np.empty((0, dim), dtype=np.float32), truncated=())


def check_checkpoint_width(key: str, declared: int, observed: int) -> None:
    """Refuse a checkpoint whose width is not the one its key declares.

    The readiness probe compares the application's declaration with the schema;
    it cannot see inside a checkpoint. This is the only place where pointing a
    key at the wrong weights is caught, and it runs at load — before a vector
    exists, so nothing wrong can reach storage.
    """
    if declared != observed:
        raise CheckpointWidthError(
            f"model {key!r} declares {declared} dimensions, "
            f"but the configured checkpoint produces {observed}"
        )
