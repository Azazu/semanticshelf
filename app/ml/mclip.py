"""A multilingual text tower that answers in CLIP ViT-L/14's space.

The checkpoint is M-CLIP's XLM-RoBERTa large, trained to put text where OpenAI
CLIP ViT-L/14 puts the pictures it describes. So a query in any of the 48
languages it was trained on can be ranked against the vectors this service
already stores under `clip-vit-l14` — nothing is re-indexed, and nothing is
stored under this key at all.

The model is a transformer, a mean pool over the attention mask, and one linear
layer. That is stated here rather than imported: the package the model card
recommends had its last release in June 2022 and does not load under the
transformers this project pins. Both repositories it reads are pinned to a
revision, because the numbers in ADR-005 are evidence about those bytes and a
branch can move under them.

`torch` and `transformers` are imported inside the functions that use them, for
the reason `app/ml/clip.py` gives.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL.Image import Image

from app.domain import MCLIP_XLMR_L14, dimension_of
from app.ml.base import (
    EmbeddingResult,
    ImagesNotSupportedError,
    batches,
    check_checkpoint_width,
    empty,
    normalise,
)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

#: Embedded once at load to see how wide this checkpoint's vectors really are.
WIDTH_PROBE: Final = "a photograph"

#: The two tensors that are not the transformer's: the projection into the
#: image space, which is what makes this checkpoint an M-CLIP one at all.
HEAD_WEIGHT: Final = "LinearTransformation.weight"
HEAD_BIAS: Final = "LinearTransformation.bias"
#: What the checkpoint calls the transformer's own tensors.
TRANSFORMER_PREFIX: Final = "transformer."
#: The field of the checkpoint's config that names the architecture to build.
BASE_FIELD: Final = "modelBase"
CHECKPOINT_FILE: Final = "pytorch_model.bin"
CONFIG_FILE: Final = "config" + ".json"


class MclipEmbedder:
    """An `Embedder` over the M-CLIP text tower. Build it with `load`."""

    def __init__(self, transformer: Any, head: Any, splitter: Any, *, batch_size: int) -> None:
        self._transformer = transformer
        self._head = head
        self._splitter = splitter
        self._batch_size = batch_size

    @property
    def key(self) -> str:
        return MCLIP_XLMR_L14

    @property
    def dim(self) -> int:
        """The width of the space this answers in, which is not its own."""
        return dimension_of(MCLIP_XLMR_L14)

    @classmethod
    def load(cls, settings: "Settings") -> "MclipEmbedder":
        """Assemble the tower from the pinned checkpoint.

        `weights_only=True` reads tensors and nothing else: this checkpoint is
        a pickle, the repository's safetensors copy exists only in an unmerged
        pull request, and a file that may run code on load is not something to
        trust because it is popular.
        """
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoConfig, AutoModel, AutoTokenizer

        if settings.torch_num_threads > 0:
            torch.set_num_threads(settings.torch_num_threads)

        cache = settings.model_cache
        cache.mkdir(parents=True, exist_ok=True)
        name = settings.mclip_model_name
        revision = settings.mclip_revision

        described = json.loads(
            Path(hf_hub_download(name, CONFIG_FILE, cache_dir=cache, revision=revision)).read_text(
                encoding="utf-8"
            )
        )
        weights = torch.load(
            hf_hub_download(name, CHECKPOINT_FILE, cache_dir=cache, revision=revision),
            map_location="cpu",
            weights_only=True,
        )

        # The architecture comes from a second repository, named by the
        # checkpoint's own config; its weights do not, because this checkpoint
        # already carries them.
        base = AutoConfig.from_pretrained(
            str(described[BASE_FIELD]), cache_dir=cache, revision=settings.mclip_base_revision
        )
        transformer = AutoModel.from_config(base)
        transformer.load_state_dict(
            {
                key.removeprefix(TRANSFORMER_PREFIX): value
                for key, value in weights.items()
                if key.startswith(TRANSFORMER_PREFIX)
            },
            strict=False,
        )
        head = torch.nn.Linear(
            in_features=int(weights[HEAD_WEIGHT].shape[1]),
            out_features=int(weights[HEAD_WEIGHT].shape[0]),
        )
        head.load_state_dict({"weight": weights[HEAD_WEIGHT], "bias": weights[HEAD_BIAS]})
        transformer.eval()
        head.eval()

        splitter = AutoTokenizer.from_pretrained(name, cache_dir=cache, revision=revision)
        embedder = cls(transformer, head, splitter, batch_size=settings.embed_batch_size)
        # Ask the assembled tower, not the config: a checkpoint that projects
        # into another width answers a question about another space.
        observed = int(embedder.embed_text([WIDTH_PROBE]).vectors.shape[1])
        check_checkpoint_width(MCLIP_XLMR_L14, embedder.dim, observed)
        return embedder

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            return empty(self.dim)
        rows = [self._features(batch) for batch in batches(list(texts), self._batch_size)]
        return EmbeddingResult(
            vectors=normalise(np.concatenate(rows)), truncated=self._truncation_flags(texts)
        )

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        """Always a refusal: this is a text tower, and it has no image side.

        An empty batch is refused too, for the reason `app/ml/dinov2.py` gives
        about the mirror case: a silent success would let a caller believe
        pictures are supported until the first real one.
        """
        raise ImagesNotSupportedError(f"model {MCLIP_XLMR_L14!r} has no image tower; it takes text")

    def _features(self, texts: Sequence[str]) -> np.ndarray:
        import torch

        pieces = self._splitter(list(texts), return_tensors="pt", padding=True, truncation=True)
        with torch.inference_mode():
            hidden = self._transformer(**pieces)[0]
            present = pieces["attention_mask"]
            # Mean over the pieces that are really there: padding must not pull
            # a short query toward the middle of the space.
            pooled = (hidden * present.unsqueeze(2)).sum(dim=1) / present.sum(dim=1)[:, None]
            projected = self._head(pooled)
        return np.asarray(projected.cpu().numpy())

    def _truncation_flags(self, texts: Sequence[str]) -> tuple[bool, ...]:
        """Which inputs did not fit, split a second time without a limit.

        The model's own call cuts silently, and the length before that cut is
        the only honest evidence that the answer describes less than the caller
        asked about. It is what the API returns as `query_truncated`.
        """
        limit = int(self._splitter.model_max_length)
        whole = self._splitter(list(texts), truncation=False, padding=False)["input_ids"]
        return tuple(len(ids) > limit for ids in whole)
