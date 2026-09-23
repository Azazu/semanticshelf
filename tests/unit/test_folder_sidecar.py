"""A picture's own tags and metadata: what a sidecar may say, and what wins.

The merge rules need no database and no files — a candidate is a path, a handle
and the bytes the walk read beside it — so they are decided here, and the
descriptor discipline that gets those bytes is proved in the integration suite,
where a symbolic link can actually be made.
"""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.folder import (
    SIDECAR_MAX_BYTES,
    Candidate,
    SidecarError,
    combine,
    metadata_for,
    read_sidecar,
)
from app.services.tagging import MAX_TAGS, METADATA_MAX_BYTES


def candidate(sidecar: dict[str, Any] | bytes | None = None, *, refusal: str | None = None):
    raw = sidecar if isinstance(sidecar, bytes) or sidecar is None else json.dumps(sidecar).encode()
    return Candidate(Path("a.png"), io.BytesIO(b""), sidecar=raw, sidecar_refusal=refusal)


# --- what a sidecar may say -----------------------------------------------------


def test_a_sidecar_carries_tags_and_metadata() -> None:
    tags, meta = read_sidecar(
        json.dumps({"tags": ["Dog", "traffic-light"], "meta": {"a": 1}}).encode()
    )

    assert tags == ("dog", "traffic-light")
    assert meta == {"a": 1}


def test_a_sidecar_may_carry_only_one_of_them() -> None:
    assert read_sidecar(b'{"tags": ["dog"]}') == (("dog",), {})
    assert read_sidecar(b'{"meta": {"a": 1}}') == ((), {"a": 1})
    assert read_sidecar(b"{}") == ((), {})


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        (b"[not json", "not JSON"),
        (b"[1, 2]", "not an object"),
        (b'{"tags": "dog"}', "list of strings"),
        (b'{"tags": [1]}', "list of strings"),
        (b'{"meta": [1]}', "an object"),
        (b'{"nonsense": 1}', "unexpected keys"),
        (b'{"tags": ["not a tag"]}', "not a valid tag"),
    ],
    ids=[
        "broken",
        "not an object",
        "tags not a list",
        "tags not strings",
        "meta not an object",
        "unknown key",
        "an unacceptable tag",
    ],
)
def test_a_sidecar_the_service_cannot_accept_is_refused(raw: bytes, why: str) -> None:
    with pytest.raises(SidecarError, match=why):
        read_sidecar(raw)


def test_metadata_beyond_the_bound_is_refused_by_the_rule_that_already_exists() -> None:
    oversized = json.dumps({"meta": {"a": "x" * (METADATA_MAX_BYTES + 1)}}).encode()

    with pytest.raises(SidecarError):
        read_sidecar(oversized)


# --- what wins --------------------------------------------------------------------


def test_a_picture_without_a_sidecar_keeps_the_run_s_own() -> None:
    tags, meta = combine(candidate(), tags=("demo",), meta={"run": 1})

    assert (tags, meta) == (("demo",), {"run": 1})


def test_tags_add_to_the_run_s_and_metadata_merges_over_it() -> None:
    tags, meta = combine(
        candidate({"tags": ["cat"], "meta": {"run": 2, "own": 3}}),
        tags=("demo",),
        meta={"run": 1},
    )

    assert tags == ("demo", "cat")
    assert meta == {"run": 2, "own": 3}


def test_the_recorded_origin_wins_over_a_sidecar_that_names_it() -> None:
    _, meta = combine(candidate({"meta": {"source_path": "somewhere/else"}}), tags=(), meta={})

    recorded = metadata_for(Path("pictures/7/a.png"), meta)

    assert recorded["source_path"] == "pictures/7/a.png"


def test_too_many_tags_between_the_two_are_refused() -> None:
    run_tags = tuple(f"run-{index}" for index in range(MAX_TAGS))

    with pytest.raises(SidecarError, match=str(MAX_TAGS)):
        combine(candidate({"tags": ["one-more"]}), tags=run_tags, meta={})


def test_a_sidecar_that_could_not_be_read_refuses_its_picture() -> None:
    with pytest.raises(SidecarError, match="a symbolic link"):
        combine(candidate(refusal="a symbolic link"), tags=(), meta={})


def test_the_bound_on_a_sidecar_is_larger_than_the_metadata_it_may_carry() -> None:
    assert SIDECAR_MAX_BYTES > METADATA_MAX_BYTES
