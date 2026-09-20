"""Embedding models behind one protocol.

Importing this package pulls in no model runtime: the adapters import `torch`
and `transformers` inside their load functions, so `make check` never drags a
few hundred megabytes into a test run. A unit test enforces that.
"""

from app.ml.base import (
    CheckpointWidthError,
    Embedder,
    EmbeddingResult,
    TextNotSupportedError,
    ZeroVectorError,
    check_checkpoint_width,
    normalise,
)

__all__ = [
    "CheckpointWidthError",
    "Embedder",
    "EmbeddingResult",
    "TextNotSupportedError",
    "ZeroVectorError",
    "check_checkpoint_width",
    "normalise",
]
