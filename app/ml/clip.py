"""CLIP: text and images into one shared space, on the CPU.

`torch` and `transformers` are imported inside the functions that use them.
This module is named by the registry's factory table, which the application
factory imports, so a top-level import would pull a few hundred megabytes of
runtime into every test run, every CLI invocation and every `--help`. A unit
test walks `app/` and fails if such an import appears.

Everything here is a single process on the CPU: there is no device setting and
no distributed path (requirements §2.3). Batch size and thread count are
configuration, because the reasonable values differ between a laptop and a
container with two cores.
"""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL.Image import Image

from app.domain import CLIP_VIT_L14, dimension_of
from app.ml.base import EmbeddingResult, check_checkpoint_width, empty, normalise

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

#: Embedded once at load to see how wide this checkpoint's vectors really are.
WIDTH_PROBE: Final = "a photograph"


def _batches[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Split a request into forward passes. Memory, not speed, sets the size:
    a batch is a tensor, and a large one on a small container is a crash."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


class ClipEmbedder:
    """An `Embedder` over a CLIP checkpoint. Build it with `load`."""

    def __init__(self, model: Any, processor: Any, *, batch_size: int) -> None:
        self._model = model
        self._processor = processor
        self._batch_size = batch_size

    @property
    def key(self) -> str:
        return CLIP_VIT_L14

    @property
    def dim(self) -> int:
        return dimension_of(CLIP_VIT_L14)

    @classmethod
    def load(cls, settings: "Settings") -> "ClipEmbedder":
        """Read the checkpoint from the configured cache, downloading it once.

        The cache directory is explicit so the weights land where the operator
        expects and a container can mount them, instead of in whichever home
        directory the process happens to run under.
        """
        import torch
        from transformers import AutoProcessor, CLIPModel

        if settings.torch_num_threads > 0:
            # Zero means "torch decides", which is right on a laptop and wrong
            # in a container with a CPU quota, where oversubscription is slower.
            torch.set_num_threads(settings.torch_num_threads)

        cache = settings.model_cache
        cache.mkdir(parents=True, exist_ok=True)
        name = settings.clip_model_name
        processor = AutoProcessor.from_pretrained(name, cache_dir=cache)
        model = CLIPModel.from_pretrained(name, cache_dir=cache)
        model.eval()

        embedder = cls(model, processor, batch_size=settings.embed_batch_size)
        # Ask the checkpoint rather than its configuration: pointing a key at
        # the wrong weights is caught here, before any vector reaches storage.
        observed = int(embedder.embed_text([WIDTH_PROBE]).vectors.shape[1])
        check_checkpoint_width(CLIP_VIT_L14, embedder.dim, observed)
        return embedder

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            return empty(self.dim)
        rows = [self._text_features(batch) for batch in _batches(list(texts), self._batch_size)]
        return EmbeddingResult(
            vectors=normalise(np.concatenate(rows)), truncated=self._truncation_flags(texts)
        )

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        if not images:
            return empty(self.dim)
        rows = [self._image_features(batch) for batch in _batches(list(images), self._batch_size)]
        return EmbeddingResult(
            vectors=normalise(np.concatenate(rows)), truncated=(False,) * len(images)
        )

    def _text_features(self, texts: Sequence[str]) -> np.ndarray:
        import torch

        inputs = self._processor(
            text=list(texts), return_tensors="pt", padding=True, truncation=True
        )
        with torch.inference_mode():
            features = self._model.get_text_features(**inputs)
        return self._projected(features)

    def _image_features(self, images: Sequence[Image]) -> np.ndarray:
        import torch

        # CLIP's processor expects three channels; a palette or greyscale file
        # is a normal thing to index, so convert rather than refuse.
        inputs = self._processor(
            images=[image.convert("RGB") for image in images], return_tensors="pt"
        )
        with torch.inference_mode():
            features = self._model.get_image_features(**inputs)
        return self._projected(features)

    @staticmethod
    def _projected(features: Any) -> np.ndarray:
        """The embedding out of a tower's output, as an array.

        transformers 5 returns the tower's own output object from both
        `get_*_features` and puts the projected embedding in `pooler_output`;
        version 4 returned that tensor directly. The real-model test is what
        catches this moving again.
        """
        tensor = getattr(features, "pooler_output", features)
        return np.asarray(tensor.cpu().numpy())

    def _truncation_flags(self, texts: Sequence[str]) -> tuple[bool, ...]:
        """Which inputs did not fit.

        Tokenised a second time without a limit: the model's own call cuts
        silently, and the length before that cut is the only honest evidence
        that the answer describes less than the caller asked about.
        """
        splitter = self._processor.tokenizer
        limit = int(splitter.model_max_length)
        whole = splitter(list(texts), truncation=False, padding=False)["input_ids"]
        return tuple(len(ids) > limit for ids in whole)
