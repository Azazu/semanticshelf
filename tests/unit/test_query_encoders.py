"""The table that says which space an encoder answers in.

A query encoder embeds words into a space it does not own. Two things have to
be true of the table for that to mean anything, and neither is checked by the
type system: an encoder's key is not a storage key (nothing may ever be written
under it), and the space it names exists (a space that does not exist holds no
pictures to rank). Both are one line to get wrong and silent afterwards.

What this file does **not** check is that the encoder really lands in that
space. No code can: it is a property of how the model was trained, and the
measurement in ADR-005 is what holds it up.
"""

import pytest

from app.domain import (
    CLIP_VIT_L14,
    DINOV2_LARGE,
    EMBEDDING_MODELS,
    IMPLEMENTED_QUERY_ENCODERS,
    MCLIP_XLMR_L14,
    QUERY_ENCODERS,
    UnknownModelError,
    dimension_of,
    is_query_encoder,
    modality_of,
    space_of,
)


def test_no_encoder_key_is_a_storage_key() -> None:
    # The `model` column of `embeddings` carries storage keys forever; an
    # encoder key appearing there would be a row nothing can ever rank.
    assert not (frozenset(QUERY_ENCODERS) & frozenset(EMBEDDING_MODELS))


def test_every_encoder_answers_in_a_space_the_application_knows() -> None:
    for encoder, space in QUERY_ENCODERS.items():
        assert space in EMBEDDING_MODELS, f"{encoder} answers in unknown space {space}"


def test_an_encoder_pointed_at_an_unknown_space_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check above, watched to fail — otherwise it asserts a coincidence."""
    monkeypatch.setitem(QUERY_ENCODERS, "planted-encoder", "no-such-model")  # type: ignore[arg-type]

    unknown = [key for key, space in QUERY_ENCODERS.items() if space not in EMBEDDING_MODELS]

    assert unknown == ["planted-encoder"]
    with pytest.raises(KeyError):
        dimension_of("planted-encoder")


def test_every_implemented_encoder_is_in_the_table() -> None:
    assert IMPLEMENTED_QUERY_ENCODERS <= frozenset(QUERY_ENCODERS)


def test_an_encoder_is_as_wide_as_the_space_it_answers_in() -> None:
    # Not "768" written twice: the width is the space's, and saying so here is
    # what keeps the two from drifting when a space is ever re-keyed.
    assert dimension_of(MCLIP_XLMR_L14) == dimension_of(CLIP_VIT_L14)


def test_a_search_with_an_encoder_ranks_its_space() -> None:
    assert space_of(MCLIP_XLMR_L14) == CLIP_VIT_L14
    assert space_of(CLIP_VIT_L14) == CLIP_VIT_L14
    assert space_of(DINOV2_LARGE) == DINOV2_LARGE


def test_a_key_nobody_declares_has_no_space() -> None:
    with pytest.raises(UnknownModelError):
        space_of("no-such-key")


def test_an_encoder_takes_words_and_not_pictures() -> None:
    modality = modality_of(MCLIP_XLMR_L14)

    assert (modality.text, modality.images) == (True, False)
    assert modality.described == "text"


def test_telling_the_two_kinds_apart() -> None:
    assert is_query_encoder(MCLIP_XLMR_L14)
    assert not is_query_encoder(CLIP_VIT_L14)
    assert not is_query_encoder("no-such-key")
