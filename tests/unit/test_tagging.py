"""Tags, metadata and the filename: one normalisation, used wherever they enter."""

import json

import pytest

from app.services.tagging import (
    FILENAME_MAX_LENGTH,
    MAX_TAGS,
    METADATA_MAX_BYTES,
    METADATA_MAX_DEPTH,
    MetadataError,
    TagError,
    check_metadata,
    merge_metadata,
    normalise_filename,
    normalise_tags,
    parse_metadata,
    split_tag_fields,
)


def test_case_and_spacing_collapse_into_one_tag() -> None:
    assert normalise_tags([" Dragon ", "DRAGON", "dragon"]) == ("dragon",)


def test_order_is_the_order_first_seen() -> None:
    assert normalise_tags(["castle", "dragon", "castle"]) == ("castle", "dragon")


def test_compatibility_forms_are_the_same_tag() -> None:
    # NFKC folds the full-width characters onto the ASCII ones.
    assert normalise_tags(["ｄｒａｇｏｎ", "dragon"]) == ("dragon",)


@pytest.mark.parametrize(
    "value", ["-leading", "_leading", "with space", "tag!", "ПРИВЕТ", "x" * 65]
)
def test_a_tag_outside_the_pattern_is_refused_by_name(value: str) -> None:
    with pytest.raises(TagError) as excinfo:
        normalise_tags([value])
    assert repr(value) in str(excinfo.value)


def test_a_blank_entry_is_ignored_rather_than_refused() -> None:
    # A trailing comma is a typo, not an error worth a 422.
    assert split_tag_fields(["dragon,"]) == ("dragon",)
    assert normalise_tags(["dragon", "  "]) == ("dragon",)


def test_more_tags_than_allowed_are_refused() -> None:
    with pytest.raises(TagError, match=str(MAX_TAGS)):
        normalise_tags([f"tag{number}" for number in range(MAX_TAGS + 1)])


def test_tags_arrive_as_repeated_fields_or_one_comma_separated_field() -> None:
    assert split_tag_fields(["dragon", "castle"]) == split_tag_fields(["dragon,castle"])
    assert split_tag_fields(["dragon, castle", "fog"]) == ("dragon", "castle", "fog")


def test_metadata_must_be_an_object() -> None:
    for value in ["[]", '"text"', "12", "null"]:
        with pytest.raises(MetadataError, match="object"):
            parse_metadata(value)


def test_metadata_is_bounded_at_its_boundary() -> None:
    # The guard's own boundary, tested away from any parser: at the bound it
    # passes, one byte over it does not.
    filler = "x" * (METADATA_MAX_BYTES - len('{"a":""}'))
    at_bound = json.dumps({"a": filler}, separators=(",", ":"))
    assert len(at_bound.encode()) == METADATA_MAX_BYTES
    assert parse_metadata(at_bound) == {"a": filler}

    over = json.dumps({"a": filler + "x"}, separators=(",", ":"))
    with pytest.raises(MetadataError, match=str(METADATA_MAX_BYTES)):
        parse_metadata(over)


def test_metadata_deeper_than_allowed_is_refused() -> None:
    deep: object = "leaf"
    for _ in range(METADATA_MAX_DEPTH):
        deep = {"level": deep}
    with pytest.raises(MetadataError, match=str(METADATA_MAX_DEPTH)):
        check_metadata(deep)


def test_metadata_at_the_depth_bound_is_accepted() -> None:
    deep: object = "leaf"
    for _ in range(METADATA_MAX_DEPTH - 1):
        deep = {"level": deep}
    assert check_metadata(deep)


def test_malformed_metadata_json_is_refused() -> None:
    with pytest.raises(MetadataError, match="valid JSON"):
        parse_metadata("{not json")


def test_absent_metadata_is_an_empty_object() -> None:
    assert parse_metadata(None) == {}
    assert parse_metadata("   ") == {}


def test_a_null_patch_clears_metadata_and_a_value_replaces_it() -> None:
    assert merge_metadata({"a": 1}, None) == {}
    assert merge_metadata({"a": 1}, {"b": 2}) == {"b": 2}


def test_a_filename_keeps_only_its_last_segment() -> None:
    assert normalise_filename("../../etc/passwd") == "passwd"
    assert normalise_filename(r"C:\\Users\\ada\\photo.jpg") == "photo.jpg"
    assert normalise_filename("dir/sub/picture.png") == "picture.png"


def test_a_filename_loses_its_control_characters() -> None:
    assert normalise_filename("pho\x00to\x07.jpg") == "photo.jpg"
    assert normalise_filename("line\nbreak.jpg") == "linebreak.jpg"


def test_a_filename_is_trimmed_to_the_stored_bound() -> None:
    long_name = "a" * 400 + ".jpg"
    trimmed = normalise_filename(long_name)
    assert trimmed is not None and len(trimmed) == FILENAME_MAX_LENGTH


def test_a_filename_with_nothing_usable_left_is_none() -> None:
    assert normalise_filename("") is None
    assert normalise_filename("   ") is None
    assert normalise_filename("../../") is None
    assert normalise_filename(None) is None


def test_a_non_latin_filename_survives() -> None:
    assert normalise_filename("дракон.jpg") == "дракон.jpg"
