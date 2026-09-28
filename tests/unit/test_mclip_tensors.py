"""A checkpoint that does not fill the architecture is refused.

`load_state_dict(strict=False)` is what lets one known leftover through — a
buffer transformers persisted in 4.x and derives in 5.x — and what it reports
is then the whole point. A tensor the architecture expects and the file does
not carry stays at its random initialisation: the model loads, produces vectors
of the right width, passes the width probe, and ranks with one layer of noise
in it. No width check can see that, which is why this one exists.

The adapter's own module is imported here, not the weights: `check_tensors` is
arithmetic over two lists of names.
"""

import pytest

from app.domain import MCLIP_XLMR_L14
from app.ml.base import CheckpointTensorsError
from app.ml.mclip import KNOWN_EXTRA_TENSORS, check_tensors


def test_a_checkpoint_that_fills_the_architecture_is_accepted() -> None:
    check_tensors([], [])


def test_the_one_known_leftover_is_accepted() -> None:
    check_tensors([], sorted(KNOWN_EXTRA_TENSORS))


def test_a_missing_tensor_is_refused() -> None:
    """The dangerous one: a layer that stays random and answers anyway."""
    with pytest.raises(CheckpointTensorsError) as refusal:
        check_tensors(["encoder.layer.11.attention.self.query.weight"], [])

    message = str(refusal.value)
    assert MCLIP_XLMR_L14 in message
    assert "encoder.layer.11.attention.self.query.weight" in message


def test_a_tensor_this_architecture_has_no_place_for_is_refused() -> None:
    with pytest.raises(CheckpointTensorsError) as refusal:
        check_tensors([], ["something.else.entirely"])

    assert "something.else.entirely" in str(refusal.value)


def test_the_known_leftover_does_not_excuse_the_others() -> None:
    with pytest.raises(CheckpointTensorsError) as refusal:
        check_tensors([], [*KNOWN_EXTRA_TENSORS, "something.else.entirely"])

    message = str(refusal.value)
    assert "something.else.entirely" in message
    for known in KNOWN_EXTRA_TENSORS:
        assert known not in message, "the refusal names what is wrong, not what is fine"
