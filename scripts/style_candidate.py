"""The style descriptor this change measures, and the care its file needs.

**What it is.** `tomg-group-umd/CSD-ViT-L` — Contrastive Style Descriptors,
from *Measuring Style Similarity in Diffusion Models* (2024), initialised from
CLIP ViT-L/14's image encoder and trained on a style-labelled subset of LAION.
Licence cc-by-4.0, declared.

**Why it is not loaded the way every other model here is.** Its `config.json`
says `{"model_type": "custom"}` and the weights file is a *training* checkpoint
— `model_state_dict`, `opt_bb`, `opt_proj`, `iter`, `args`, `fp16_scaler` — in
OpenAI CLIP's own module layout. There is nothing for `transformers` to build,
so the tower comes from `open_clip`, which builds exactly that layout, and the
`module.backbone.*` tensors are poured into it.

**One order only.** CSD replaces CLIP's own 1024->768 projection with two heads
of its own, so `visual.proj` is removed *before* the load. Removed after, the
same call reports `proj` missing: "nothing missing" is a statement about a
sequence, not about the weights alone.

**The load is a security decision.** `weights_only=True` refuses this file,
because it carries pickled objects beside the tensors. Turning that flag off is
not the answer — it would let any object in the file run code on load, which is
the thing the flag exists to stop, and a unit test sweeps every non-document
file in the repository to keep anyone from reaching for it. What unblocks the
load instead is `allowlist()`: four named globals, each of which builds one
value and runs nothing else. That does not make the weights trustworthy, which
nothing can; it bounds what reading them can do.

This module lives under `scripts/` because nothing in the service loads it. If
ADR-006 says the key is worth a migration, the change that ships it moves the
adapter into `app/ml/` under the `Embedder` protocol.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL.Image import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ml.base import (  # noqa: E402
    CheckpointTensorsError,
    EmbeddingResult,
    batches,
    check_checkpoint_width,
    empty,
    normalise,
)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

#: The repository and the exact commit read from it. Pinned for the reason
#: every checkpoint here is pinned: a revision that moves publishes different
#: numbers under the same command.
CHECKPOINT: Final = "tomg-group-umd/CSD-ViT-L"
REVISION: Final = "5bc26a6fb0487f3f00a2a7313135103a005b1b67"
CHECKPOINT_FILE: Final = "pytorch_model.bin"

#: The architecture the weights are poured into, built by `open_clip`.
#:
#: **The `-quickgelu` suffix is not a detail.** CSD is initialised from OpenAI's
#: CLIP ViT-L/14, whose residual MLPs use QuickGELU — the checkpoint on disk
#: declares `hidden_act: quick_gelu`. `open_clip`'s plain `ViT-L-14` config sets
#: `quick_gelu: false` and builds `nn.GELU` instead, and **a state dict cannot
#: detect the difference**, because an activation carries no tensors: the load
#: reports nothing missing and nothing unexpected while the network computes
#: something else. Built the wrong way, every vector moves — cosine 0.93 against
#: the right one on this corpus, which is far more than enough to move a
#: published number.
TOWER: Final = "ViT-L-14-quickgelu"
#: What an activation with no parameters looks like when it is the right one.
#: Asserted at load, because nothing else in the pipeline can see it.
ACTIVATION: Final = "QuickGELU"
#: Where the tensors sit inside the training checkpoint.
STATE: Final = "model_state_dict"
BACKBONE_PREFIX: Final = "module.backbone."
#: CSD's own projection, applied to the pooled output of the backbone. The
#: content head beside it is what this measurement is not about.
STYLE_HEAD: Final = "module.last_layer_style"

#: What the table calls it. Not a key: nothing is stored under this name, and
#: whether it ever becomes one is what the measurement decides.
LABEL: Final = "csd-vit-l"
#: The width of the style head, checked against the checkpoint at load.
WIDTH: Final = 768


def allowlist() -> list[Any]:
    """The four globals `weights_only=True` is told to accept, and why each one.

    Three are types — a dtype, one concrete dtype class, and the plain
    attribute bag `argparse` builds its parsed arguments in. The fourth is
    numpy's own scalar constructor, a builtin whose documentation says it
    exists mainly for pickle support: it takes a dtype and the bytes of one
    value and returns that value. Each entry builds a value and runs nothing
    else — no module, no callable that reaches the filesystem, no class whose
    `__reduce__` executes. That property is what makes a named allowlist a
    different thing from turning the check off.

    `numpy.core.multiarray.scalar` is listed under its *legacy* module path on
    purpose: numpy moved the module to `numpy._core`, and the pickle in this
    file still names the old one.
    """
    return [
        # The only one that needs a name beside it, for the reason above.
        (np._core.multiarray.scalar, "numpy.core.multiarray.scalar"),
        np.dtype,
        np.dtypes.Float64DType,
        argparse.Namespace,
    ]


def check_tensors(missing: Sequence[str], unexpected: Sequence[str]) -> None:
    """Refuse a checkpoint that does not fill the architecture, or overfills it.

    Missing is fatal: a tensor the architecture expects and the file does not
    carry keeps its random initialisation, and the result is a model that
    loads, answers, and ranks with one layer of noise in it — which no width
    check can see. Unexpected is fatal too: this architecture is not the one
    the file was written for.
    """
    if missing or unexpected:
        raise CheckpointTensorsError(
            f"checkpoint for {LABEL!r} does not match the architecture: "
            f"missing {sorted(missing) or 'nothing'}, "
            f"unexpected {sorted(unexpected) or 'nothing'}"
        )


def check_activation(visual: Any) -> None:
    """Refuse a tower whose residual MLPs are not the checkpoint's activation.

    The tensor check cannot see this: an activation has no parameters, so a
    network built with the wrong one loads cleanly and answers differently.
    This is the only place the architecture is compared with what the weights
    were trained under.
    """
    built = type(visual.transformer.resblocks[0].mlp[1]).__name__
    if built != ACTIVATION:
        raise CheckpointArchitectureError(
            f"{LABEL!r} needs {ACTIVATION} in its residual MLPs, as OpenAI's CLIP ViT-L/14 "
            f"was trained with, and this tower was built with {built}: the weights would "
            "load without complaint and compute something else"
        )


def read_state(cache: Path) -> dict[str, Any]:
    """Download the checkpoint once, at the pinned revision, and read it."""
    import torch
    from huggingface_hub import hf_hub_download

    cache.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(CHECKPOINT, CHECKPOINT_FILE, revision=REVISION, cache_dir=str(cache))
    with torch.serialization.safe_globals(allowlist()):
        loaded = torch.load(path, map_location="cpu", weights_only=True)
    state: dict[str, Any] = loaded[STATE]
    return state


def backbone_of(state: dict[str, Any]) -> dict[str, Any]:
    """The tensors of the CLIP tower, under the names that tower knows."""
    return {
        name.removeprefix(BACKBONE_PREFIX): tensor
        for name, tensor in state.items()
        if name.startswith(BACKBONE_PREFIX)
    }


class CheckpointArchitectureError(RuntimeError):
    """A checkpoint poured into an architecture that is not the one it was
    trained under, in a way no tensor can reveal."""


class StyleCandidate:
    """The candidate behind the same small contract the service's models keep."""

    def __init__(self, visual: Any, preprocess: Any, head: Any, *, batch_size: int) -> None:
        self._visual = visual
        self._preprocess = preprocess
        self._head = head
        self._batch_size = batch_size

    @property
    def key(self) -> str:
        return LABEL

    @property
    def dim(self) -> int:
        return WIDTH

    @classmethod
    def build(cls, state: dict[str, Any], *, batch_size: int) -> "StyleCandidate":
        """Pour a state dict into the tower. Separate from reading the file so a
        test can hand it a checkpoint with one tensor taken out."""
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(TOWER)
        visual = model.visual
        check_activation(visual)
        # Before the load, not after: see the module docstring.
        visual.proj = None
        report = visual.load_state_dict(backbone_of(state), strict=False)
        check_tensors(report.missing_keys, report.unexpected_keys)
        visual.eval()
        head = state[STYLE_HEAD]
        check_checkpoint_width(LABEL, WIDTH, int(head.shape[1]))
        return cls(visual, preprocess, head, batch_size=batch_size)

    @classmethod
    def load(cls, settings: "Settings") -> "StyleCandidate":
        """Read the checkpoint from the configured cache and build the tower."""
        import torch

        if settings.torch_num_threads > 0:
            torch.set_num_threads(settings.torch_num_threads)
        return cls.build(read_state(settings.model_cache), batch_size=settings.embed_batch_size)

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        if not images:
            return empty(self.dim)
        rows = [self._features(batch) for batch in batches(list(images), self._batch_size)]
        return EmbeddingResult(
            vectors=normalise(np.concatenate(rows)), truncated=(False,) * len(images)
        )

    def _features(self, images: Sequence[Image]) -> np.ndarray:
        import torch

        batch = torch.stack([self._preprocess(image) for image in images])
        with torch.inference_mode():
            pooled = self._visual(batch)
            vectors = pooled @ self._head
        return np.asarray(vectors.cpu().numpy())
