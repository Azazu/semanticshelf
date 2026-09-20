"""The repository's own guard, before a wrong vector reaches the wire.

The database enforces the same rule; this check exists so the failure names the
model and the widths instead of surfacing as a constraint violation.
"""

import pytest

from app.repositories.embeddings import (
    UnknownModelError,
    VectorDimensionError,
    checked_dimension,
)


def test_a_known_model_with_the_right_width_passes() -> None:
    assert checked_dimension("clip-vit-l14", [0.0] * 768) == 768
    assert checked_dimension("dinov2-large", [0.0] * 1024) == 1024


def test_an_unknown_model_is_named() -> None:
    with pytest.raises(UnknownModelError, match="no-such-model"):
        checked_dimension("no-such-model", [0.0] * 768)


def test_a_wrong_width_names_both_numbers() -> None:
    with pytest.raises(VectorDimensionError, match="768 dimensions, got 1024"):
        checked_dimension("clip-vit-l14", [0.0] * 1024)


def test_an_empty_vector_is_a_wrong_width() -> None:
    with pytest.raises(VectorDimensionError):
        checked_dimension("clip-vit-l14", [])
