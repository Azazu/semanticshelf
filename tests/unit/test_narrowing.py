"""What a narrowing is, and what the service refuses to narrow by.

The value and its parser are the only things between a client's query string
and a `WHERE` on the one query this service is built around, so every refusal
here is a test and every refusal names what was wrong.
"""

import dataclasses

import pytest

from app.domain import Narrowing
from app.services.tagging import (
    MAX_META_CONDITIONS,
    NarrowingError,
    parse_narrowing,
)

# --- the value ----------------------------------------------------------------


def test_it_is_frozen() -> None:
    narrowing = Narrowing(tags_all=("dragon",))

    assert dataclasses.is_dataclass(Narrowing)
    with pytest.raises(dataclasses.FrozenInstanceError):
        narrowing.tags_all = ("castle",)  # type: ignore[misc]


def test_an_empty_narrowing_narrows_nothing() -> None:
    """Falsy on purpose: most searches carry one, and it must cost nothing."""
    assert not Narrowing()
    assert not parse_narrowing()


@pytest.mark.parametrize(
    "narrowing",
    [
        Narrowing(tags_all=("dragon",)),
        Narrowing(tags_any=("dragon",)),
        Narrowing(meta={"dataset": "coco"}),
    ],
    ids=["all", "any", "meta"],
)
def test_any_condition_makes_it_narrow(narrowing: Narrowing) -> None:
    assert narrowing


def test_two_built_from_the_same_input_are_equal() -> None:
    first = parse_narrowing(tags_all="dragon,fog", meta=[("dataset", "coco")])
    second = parse_narrowing(tags_all="dragon,fog", meta=[("dataset", "coco")])

    assert first == second


# --- the tags -----------------------------------------------------------------


def test_tags_are_normalised_the_way_a_stored_tag_was() -> None:
    """A tag in a narrowing has to be the tag it must match, or the filter lies."""
    narrowing = parse_narrowing(tags_all=" Dragon , FOG ")

    assert narrowing.tags_all == ("dragon", "fog")


def test_both_tag_conditions_may_be_given_at_once() -> None:
    narrowing = parse_narrowing(tags_all="dragon", tags_any="fog,castle")

    assert narrowing.tags_all == ("dragon",)
    assert narrowing.tags_any == ("fog", "castle")


def test_a_repeated_tag_is_one_tag() -> None:
    assert parse_narrowing(tags_all="dragon,dragon").tags_all == ("dragon",)


@pytest.mark.parametrize(
    "written", ["-dragon", "a" * 65, "драконы", "dragon!"], ids=["dash", "long", "cyrillic", "bang"]
)
def test_a_tag_that_is_not_a_tag_is_refused_by_name(written: str) -> None:
    with pytest.raises(NarrowingError, match="not a valid tag"):
        parse_narrowing(tags_all=written)


def test_a_bad_tag_in_the_any_condition_is_refused_too(  # the other branch of the parser
) -> None:
    with pytest.raises(NarrowingError, match="not a valid tag"):
        parse_narrowing(tags_any="dragon,-fog")


# --- the metadata conditions --------------------------------------------------


def test_metadata_conditions_are_kept_as_written() -> None:
    narrowing = parse_narrowing(meta=[("dataset", "coco-val2017"), ("licence", "by-2.0")])

    assert narrowing.meta == {"dataset": "coco-val2017", "licence": "by-2.0"}


@pytest.mark.parametrize(
    "key",
    ["Dataset", "data-set", "a" * 65, "", "meta.dataset"],
    ids=["upper", "dash", "long", "empty", "dotted"],
)
def test_a_key_outside_the_shape_is_refused_by_name(key: str) -> None:
    with pytest.raises(NarrowingError, match="not a valid metadata key"):
        parse_narrowing(meta=[(key, "value")])


def test_five_conditions_are_allowed() -> None:
    five = [(f"key_{index}", "value") for index in range(MAX_META_CONDITIONS)]

    assert len(parse_narrowing(meta=five).meta) == MAX_META_CONDITIONS


def test_six_conditions_are_refused_with_the_bound() -> None:
    six = [(f"key_{index}", "value") for index in range(MAX_META_CONDITIONS + 1)]

    with pytest.raises(NarrowingError, match=str(MAX_META_CONDITIONS)):
        parse_narrowing(meta=six)


def test_the_same_key_twice_is_refused() -> None:
    """Two values for one key can never both hold. Answering an empty page
    would be guessing at a request that is a mistake."""
    with pytest.raises(NarrowingError, match="given twice"):
        parse_narrowing(meta=[("dataset", "coco"), ("dataset", "unsplash")])
