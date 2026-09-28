"""The real multilingual tower, once.

Marked `models`, so neither `make check` nor CI ever runs it: it reads about
2.2 GB and needs the network the first time. It is the only evidence that the
hand-assembled adapter and the contract agree about the actual weights —
everything else in the suite runs against the deterministic stand-in.

Two things here are not in the other model tests, and both are the point of
this adapter existing: the vectors are the width of *another* model's space,
and a query in a language CLIP cannot read still lands beside the right
picture — which is checked here only as a direction, never as a number. The
numbers are `scripts/multilingual_benchmark.py` and ADR-005.

Run it with `make test-models`.
"""

from collections.abc import Iterator

import pytest
from PIL import Image as PILImage

from app import domain
from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, MCLIP_XLMR_L14, dimension_of
from app.ml.base import CheckpointWidthError, ImagesNotSupportedError
from app.ml.clip import ClipEmbedder
from app.ml.mclip import MclipEmbedder
from tests.embedder_conformance import (
    assert_batch_keeps_order,
    assert_empty_text_batch_is_empty,
    assert_text_conformance,
)

pytestmark = pytest.mark.models

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"
#: XLM-RoBERTa's context is 512 pieces; this is comfortably past it.
LONG_TEXT = "красный дракон над разрушенным замком в тумане, " * 80


def configured() -> Settings:
    return Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)  # type: ignore[call-arg]


@pytest.fixture(scope="module")
def embedder() -> Iterator[MclipEmbedder]:
    """Loaded once for the whole module: the read is the expensive part, and
    the adapter holds no per-test state."""
    yield MclipEmbedder.load(configured())


def test_it_answers_in_the_space_it_declares(embedder: MclipEmbedder) -> None:
    assert embedder.key == MCLIP_XLMR_L14
    assert embedder.dim == dimension_of(CLIP_VIT_L14) == 768


def test_text_satisfies_the_contract(embedder: MclipEmbedder) -> None:
    assert_text_conformance(embedder, ["зебра в траве", "ein Elefant"])
    assert_batch_keeps_order(embedder, ["зебра", "un éléphant", "tennis", "un semáforo rojo"])


def test_an_empty_batch_touches_nothing(embedder: MclipEmbedder) -> None:
    # The text side, because this embedder has no other: `embed_images([])`
    # is a refusal here, which its own test asserts.
    assert_empty_text_batch_is_empty(embedder)


def test_it_refuses_pictures_rather_than_answering_from_nowhere(
    embedder: MclipEmbedder,
) -> None:
    with pytest.raises(ImagesNotSupportedError) as refusal:
        embedder.embed_images([PILImage.new("RGB", (8, 8), color=(10, 20, 30))])

    assert MCLIP_XLMR_L14 in str(refusal.value)


def test_a_query_past_the_context_is_cut_and_says_so(embedder: MclipEmbedder) -> None:
    # Both in one batch: the flag belongs to its input, not to the call.
    result = embedder.embed_text(["зебра в траве", LONG_TEXT])

    assert result.truncated == (False, True)
    assert result.vectors.shape == (2, embedder.dim)


def test_a_batch_larger_than_the_batch_size_is_split_and_keeps_order(
    embedder: MclipEmbedder,
) -> None:
    texts = [f"фотография {number} яблок" for number in range(10)]
    whole = embedder.embed_text(texts).vectors
    one_by_one = [embedder.embed_text([text]).vectors[0] for text in texts]

    assert whole.shape == (10, embedder.dim)
    for index, single in enumerate(one_by_one):
        assert float(whole[index] @ single) > 0.999


def test_a_russian_query_lands_beside_the_picture_english_lands_beside() -> None:
    """The claim the whole change rests on, as a direction rather than a score.

    Two pictures the image tower can tell apart, one query in Russian: the
    encoder must put it nearer the right one — in vectors produced by the image
    tower of *another* checkpoint, which is what "answers in that space" means.
    """
    settings = configured()
    pictures = [
        PILImage.new("RGB", (224, 224), color=(220, 30, 30)),
        PILImage.new("RGB", (224, 224), color=(30, 30, 220)),
    ]
    seen = ClipEmbedder.load(settings).embed_images(pictures).vectors
    asked = MclipEmbedder.load(settings).embed_text(["красный квадрат"]).vectors[0]

    assert float(seen[0] @ asked) > float(seen[1] @ asked)


def test_a_checkpoint_whose_width_is_not_the_space_s_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard, watched to refuse — from the declaration's side.

    What it protects against is a key pointed at weights that are not what it
    says: substituting a checkpoint of another width, which the settings allow.
    Moving the declared width instead makes the same disagreement without a
    second 2 GB download, and exercises the adapter's own call to the guard
    rather than the shared helper in isolation.
    """
    monkeypatch.setitem(domain.EMBEDDING_MODELS, CLIP_VIT_L14, 512)

    with pytest.raises(CheckpointWidthError) as refusal:
        MclipEmbedder.load(configured())

    assert MCLIP_XLMR_L14 in str(refusal.value)
    assert "512" in str(refusal.value) and "768" in str(refusal.value)
