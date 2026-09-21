"""The two properties every vector in this service has, and the checkpoint guard."""

import numpy as np
import pytest

from app.ml.base import (
    CheckpointWidthError,
    EmbeddingResult,
    ZeroVectorError,
    check_checkpoint_width,
    empty,
    normalise,
)


def test_a_plain_vector_becomes_unit_length() -> None:
    result = normalise(np.array([[3.0, 4.0]]))
    assert result.dtype == np.float32
    assert np.allclose(result, [[0.6, 0.8]])


def test_an_already_unit_vector_is_unchanged() -> None:
    given = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    assert np.allclose(normalise(given), given)


def test_every_row_of_a_batch_is_normalised_on_its_own() -> None:
    result = normalise(np.array([[3.0, 4.0], [0.0, 2.0], [-1.0, 0.0]]))
    assert np.allclose(np.linalg.norm(result, axis=1), 1.0)


def test_a_zero_vector_is_refused_rather_than_turned_into_nan() -> None:
    with pytest.raises(ZeroVectorError):
        normalise(np.array([[1.0, 1.0], [0.0, 0.0]]))


def test_a_one_dimensional_array_is_refused() -> None:
    with pytest.raises(ValueError, match="2-dimensional"):
        normalise(np.array([1.0, 0.0]))


def test_empty_has_the_declared_width_and_no_rows() -> None:
    result = empty(768)
    assert result.vectors.shape == (0, 768)
    assert result.truncated == ()


def test_a_result_needs_one_flag_per_vector() -> None:
    with pytest.raises(ValueError, match="one truncation flag"):
        EmbeddingResult(vectors=np.zeros((2, 3), dtype=np.float32), truncated=(False,))


def test_a_checkpoint_of_the_declared_width_passes() -> None:
    assert check_checkpoint_width("clip-vit-l14", 768, 768) is None


@pytest.mark.parametrize("observed", [512, 1024], ids=["narrower", "wider"])
def test_a_checkpoint_of_another_width_is_refused_with_both_numbers(observed: int) -> None:
    with pytest.raises(CheckpointWidthError) as excinfo:
        check_checkpoint_width("clip-vit-l14", 768, observed)
    message = str(excinfo.value)
    assert "clip-vit-l14" in message
    assert "768" in message and str(observed) in message
