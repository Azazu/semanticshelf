"""DINOv2: what a picture looks like, with no words anywhere near it.

CLIP puts text and images in one space, which is what makes it answer "a red
dragon". DINOv2 has no text tower at all: it was trained on images alone, so
its vectors describe appearance rather than description, and asking it for text
is a mistake the adapter refuses rather than approximates.

`torch` and `transformers` are imported inside the functions that use them, for
the reason `app/ml/clip.py` gives: the registry's factory table is imported by
the application factory, and a top-level import here would pull the whole model
runtime into every test run and every `--help`.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL import Image as PILImage
from PIL.Image import Image

from app.domain import DINOV2_LARGE, dimension_of
from app.ml.base import (
    EmbeddingResult,
    TextNotSupportedError,
    batches,
    check_checkpoint_width,
    empty,
    normalise,
)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

#: Embedded once at load to see how wide this checkpoint's vectors really are.
#: Any picture does: the processor resizes whatever it is given.
WIDTH_PROBE_SIZE: Final = (32, 32)


class Dinov2Embedder:
    """An `Embedder` over a DINOv2 checkpoint. Build it with `load`."""

    def __init__(self, model: Any, processor: Any, *, batch_size: int) -> None:
        self._model = model
        self._processor = processor
        self._batch_size = batch_size

    @property
    def key(self) -> str:
        return DINOV2_LARGE

    @property
    def dim(self) -> int:
        return dimension_of(DINOV2_LARGE)

    @classmethod
    def load(cls, settings: "Settings") -> "Dinov2Embedder":
        """Read the checkpoint from the configured cache, downloading it once."""
        import torch
        from transformers import AutoModel, AutoProcessor

        if settings.torch_num_threads > 0:
            torch.set_num_threads(settings.torch_num_threads)

        cache = settings.model_cache
        cache.mkdir(parents=True, exist_ok=True)
        name = settings.dinov2_model_name
        # `AutoProcessor`, not `AutoImageProcessor`: in transformers 5 the
        # latter is a placeholder unless `torchvision` is installed, while this
        # one resolves the Pillow-backed processor the checkpoint declares
        # (`BitImageProcessorPil`). The project depends on `torch` alone, and a
        # second image stack for one resize is not worth installing.
        processor = AutoProcessor.from_pretrained(name, cache_dir=cache)
        model = AutoModel.from_pretrained(name, cache_dir=cache)
        model.eval()

        embedder = cls(model, processor, batch_size=settings.embed_batch_size)
        # Ask the checkpoint rather than its configuration, exactly as the CLIP
        # adapter does: a key pointed at the wrong weights is caught here,
        # before any vector reaches storage.
        probe = PILImage.new("RGB", WIDTH_PROBE_SIZE, color=(127, 127, 127))
        observed = int(embedder.embed_images([probe]).vectors.shape[1])
        check_checkpoint_width(DINOV2_LARGE, embedder.dim, observed)
        return embedder

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        """Always a refusal: this model has no text tower to ask.

        It refuses an empty batch too. Answering `empty()` there would let a
        caller believe text is supported until the first real query, which is
        the confusion this whole class exists to prevent.
        """
        raise TextNotSupportedError(f"model {DINOV2_LARGE!r} has no text tower; it takes pictures")

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        if not images:
            return empty(self.dim)
        rows = [self._image_features(batch) for batch in batches(list(images), self._batch_size)]
        return EmbeddingResult(
            vectors=normalise(np.concatenate(rows)), truncated=(False,) * len(images)
        )

    def _image_features(self, images: Sequence[Image]) -> np.ndarray:
        """The CLS token after the final layer norm, which is what `dinov2-large`
        means by an embedding.

        `Dinov2Model.forward` applies its own `layernorm` to the encoder's last
        hidden state and returns row 0 of it as `pooler_output`, so that
        attribute *is* the normalised CLS token — read from the installed
        `transformers` (5.17), not assumed. The alternative, mean-pooling the
        patch tokens, is a different space with the same width, which is why
        this reads one named attribute instead of slicing a tensor itself.
        """
        import torch

        # Three channels, like the upload path: a greyscale or palette file is
        # an ordinary thing to index.
        inputs = self._processor(
            images=[image.convert("RGB") for image in images], return_tensors="pt"
        )
        with torch.inference_mode():
            outputs = self._model(**inputs)
        return np.asarray(outputs.pooler_output.cpu().numpy())
