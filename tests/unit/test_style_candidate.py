"""How the candidate's checkpoint is read, checked without reading it.

The file `scripts/style_candidate.py` loads is a training checkpoint with
pickled objects in it, so `weights_only=True` refuses it until four globals are
named. That list, and the rule that the check is never simply turned off, are
the security-relevant part of this change; both are checked here, where no
weights are needed and therefore where CI can see them.
"""

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.ml.base import CheckpointTensorsError
from tests.scripts import script_module

candidate = script_module("style_candidate")
CheckpointArchitectureError = candidate.CheckpointArchitectureError


def torch_gelu() -> object:
    """A stand-in for what `open_clip`'s plain `ViT-L-14` builds."""
    return type("GELU", (), {})()


def quick_gelu() -> object:
    """A stand-in for what the checkpoint was trained under."""
    return type("QuickGELU", (), {})()


REPOSITORY = Path(__file__).resolve().parents[2]


def named(entry: object) -> str:
    """What `torch.serialization.safe_globals` is told to accept an object as."""
    if isinstance(entry, tuple):
        return str(entry[1])
    return f"{entry.__module__}.{entry.__qualname__}"  # type: ignore[attr-defined]


# --- the allowlist -------------------------------------------------------------


def test_the_allowlist_is_exactly_these_four_globals() -> None:
    """Exactly: an entry added later is an entry nobody argued for."""
    assert [named(entry) for entry in candidate.allowlist()] == [
        "numpy.core.multiarray.scalar",
        "numpy.dtype",
        "numpy.dtypes.Float64DType",
        "argparse.Namespace",
    ]


def test_each_entry_is_the_object_it_claims_to_be() -> None:
    """The names above are strings; these are the objects they stand for."""
    entries = candidate.allowlist()

    assert entries[0][0] is np._core.multiarray.scalar
    assert entries[1] is np.dtype
    assert entries[2] is np.dtypes.Float64DType
    assert entries[3] is argparse.Namespace


def test_the_scalar_constructor_is_allowlisted_under_its_legacy_path() -> None:
    """numpy moved the module to `numpy._core`; the pickle in this checkpoint
    still names `numpy.core`, so the string and the object disagree on purpose.
    Listing it under its real module would leave the load refused."""
    listed, name = candidate.allowlist()[0]

    assert listed.__module__ == "numpy._core.multiarray"
    assert name == "numpy.core.multiarray.scalar"


# --- the check is never turned off ---------------------------------------------


def test_no_source_file_turns_the_pickle_check_off() -> None:
    """`weights_only` off would let any object in a checkpoint run code on
    load. Prose may name it — the design and the ADR have to explain what was
    refused and why — so what is swept is everything that is not a document.
    """
    disabled = "weights_only" + "=False"
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split("\0")

    carrying = []
    for name in (entry for entry in tracked if entry and not entry.endswith(".md")):
        path = REPOSITORY / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if disabled in text:
            carrying.append(name)

    assert carrying == []


def test_the_sweep_can_see_the_thing_it_forbids(tmp_path: Path) -> None:
    """The check above passes trivially if the needle is wrong; this is the
    same comparison against a file that does carry it."""
    written = tmp_path / "loader.py"
    written.write_text("torch.load(path, " + "weights_only" + "=False)", encoding="utf-8")

    assert ("weights_only" + "=False") in written.read_text(encoding="utf-8")


# --- what the loader refuses ---------------------------------------------------


def test_a_checkpoint_missing_a_tensor_is_refused() -> None:
    """A tensor the architecture expects and the file does not carry keeps its
    random initialisation: the model loads, answers, and ranks with a layer of
    noise in it, which no width check can see."""
    with pytest.raises(CheckpointTensorsError, match="missing"):
        candidate.check_tensors(["transformer.resblocks.0.attn.in_proj_weight"], [])


def test_a_checkpoint_with_a_tensor_too_many_is_refused() -> None:
    """Not the file this adapter was written against, whatever its width is."""
    with pytest.raises(CheckpointTensorsError, match="unexpected"):
        candidate.check_tensors([], ["proj"])


def test_a_checkpoint_that_fits_the_architecture_passes() -> None:
    candidate.check_tensors([], [])


def test_the_backbone_is_taken_by_prefix_and_renamed() -> None:
    """The style and content heads sit beside the backbone in the same file and
    belong to no part of the tower."""
    state = {
        "module.backbone.conv1.weight": "a",
        "module.backbone.ln_post.bias": "b",
        "module.last_layer_style": "c",
        "module.last_layer_content": "d",
    }

    assert candidate.backbone_of(state) == {"conv1.weight": "a", "ln_post.bias": "b"}


def test_the_tower_is_the_quickgelu_one() -> None:
    """CSD is initialised from OpenAI's CLIP ViT-L/14, whose residual MLPs use
    QuickGELU. `open_clip`'s plain `ViT-L-14` builds `nn.GELU` instead, and no
    tensor check can see the difference because an activation has no
    parameters: the weights load cleanly and the network computes something
    else. The constant is asserted here so CI catches a regression of it; that
    the built tower really carries it is asserted in the models suite."""
    assert candidate.TOWER.endswith("-quickgelu")
    assert candidate.ACTIVATION == "QuickGELU"


def test_a_tower_with_the_wrong_activation_is_refused() -> None:
    class Wrong:
        transformer = type(
            "T", (), {"resblocks": [type("B", (), {"mlp": [None, torch_gelu()]})()]}
        )()

    with pytest.raises(CheckpointArchitectureError, match="QuickGELU"):
        candidate.check_activation(Wrong())


def test_a_tower_with_the_right_activation_passes() -> None:
    class Right:
        transformer = type(
            "T", (), {"resblocks": [type("B", (), {"mlp": [None, quick_gelu()]})()]}
        )()

    candidate.check_activation(Right())


def test_the_checkpoint_is_pinned_to_a_commit() -> None:
    """A revision that moves publishes different numbers under the same
    command, which is the one thing the re-run scenario forbids."""
    assert len(candidate.REVISION) == 40
    assert set(candidate.REVISION) <= set("0123456789abcdef")
