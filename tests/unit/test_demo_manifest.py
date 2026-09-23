"""The manifest: what is read out of the archive, and what may be taken from it.

Every zip here is built in the test, so nothing is downloaded and nothing about
the real dataset is assumed beyond its shape, which was read from a real COCO
archive before the change was designed.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.services import demo_dataset
from app.services.demo_dataset import (
    ACCEPTED_LICENCES,
    MANIFEST_MEMBER,
    ManifestError,
    read_manifest,
    select,
    tag_of,
    tags_of,
    wanted,
)
from app.services.tagging import MAX_TAGS, TagError, normalise_tag

# The eight licences a COCO manifest declares, read from the real
# `image_info_test2017.json` on 2026-09-22.
LICENCES = [
    {
        "id": 1,
        "name": "Attribution-NonCommercial-ShareAlike License",
        "url": "http://creativecommons.org/licenses/by-nc-sa/2.0/",
    },
    {
        "id": 2,
        "name": "Attribution-NonCommercial License",
        "url": "http://creativecommons.org/licenses/by-nc/2.0/",
    },
    {
        "id": 3,
        "name": "Attribution-NonCommercial-NoDerivs License",
        "url": "http://creativecommons.org/licenses/by-nc-nd/2.0/",
    },
    {"id": 4, "name": "Attribution License", "url": "http://creativecommons.org/licenses/by/2.0/"},
    {
        "id": 5,
        "name": "Attribution-ShareAlike License",
        "url": "http://creativecommons.org/licenses/by-sa/2.0/",
    },
    {
        "id": 6,
        "name": "Attribution-NoDerivs License",
        "url": "http://creativecommons.org/licenses/by-nd/2.0/",
    },
    {"id": 7, "name": "No known copyright restrictions", "url": "http://flickr.com/commons/usage/"},
    {"id": 8, "name": "United States Government Work", "url": "http://www.usa.gov/copyright.shtml"},
]


def manifest(images: list[dict[str, Any]], **rest: Any) -> dict[str, Any]:
    return {"licenses": LICENCES, "images": images, **rest}


def archive(path: Path, *, member: str = MANIFEST_MEMBER, body: bytes | None = None) -> Path:
    body = json.dumps(manifest([])).encode() if body is None else body
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(member, body)
    return path


# --- the archive --------------------------------------------------------------


def test_the_member_is_read_by_its_exact_name(tmp_path: Path) -> None:
    read = read_manifest(archive(tmp_path / "a.zip"))

    assert read["licenses"] == LICENCES


def test_an_archive_without_the_member_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match=MANIFEST_MEMBER):
        read_manifest(archive(tmp_path / "a.zip", member="annotations/something_else.json"))


def test_a_member_that_escapes_the_archive_is_not_read(tmp_path: Path) -> None:
    """The exact name is the whole defence: `../` is not the member we ask for,
    so it is refused for the same reason a missing member is."""
    with pytest.raises(ManifestError, match=MANIFEST_MEMBER):
        read_manifest(archive(tmp_path / "a.zip", member=f"../{MANIFEST_MEMBER}"))


def test_a_member_above_the_bound_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size the member declares decides, so nothing is decompressed to find
    out — which is what keeps a zip bomb from being read at all."""
    monkeypatch.setattr(demo_dataset, "MEMBER_MAX_BYTES", 64)
    body = json.dumps(manifest([{"id": index, "license": 4} for index in range(20)])).encode()
    assert len(body) > 64

    with pytest.raises(ManifestError, match="64"):
        read_manifest(archive(tmp_path / "a.zip", body=body))


def test_something_that_is_not_an_archive_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    path.write_bytes(b"not a zip at all")

    with pytest.raises(ManifestError, match="readable archive"):
        read_manifest(path)


def test_a_member_that_is_not_json_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not JSON"):
        read_manifest(archive(tmp_path / "a.zip", body=b"[not json"))


def test_a_member_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not an object"):
        read_manifest(archive(tmp_path / "a.zip", body=b"[1, 2, 3]"))


# --- the licence filter --------------------------------------------------------


@pytest.mark.parametrize("licence_id", [4, 5, 7, 8])
def test_a_picture_under_an_accepted_licence_is_taken(licence_id: int) -> None:
    selection = select(manifest([{"id": 10, "license": licence_id}]))

    assert [picture.identifier for picture in selection.pictures] == [10]
    assert selection.pictures[0].licence in ACCEPTED_LICENCES
    assert selection.refused_for_licence == 0


@pytest.mark.parametrize(
    ("licence_id", "why"),
    [(1, "non-commercial"), (2, "non-commercial"), (3, "non-commercial"), (6, "no derivatives")],
    ids=["by-nc-sa", "by-nc", "by-nc-nd", "by-nd"],
)
def test_a_picture_under_a_licence_that_is_not_accepted_is_refused(
    licence_id: int, why: str
) -> None:
    """NoDerivs is refused although it permits redistribution: the service
    re-encodes a thumbnail of everything it stores, and that is a derivative."""
    selection = select(manifest([{"id": 10, "license": licence_id}]))

    assert selection.pictures == ()
    assert selection.refused_for_licence == 1, why


@pytest.mark.parametrize(
    "image",
    [{"id": 10}, {"id": 10, "license": 99}, {"id": 10, "license": "4"}],
    ids=["no licence", "an id the table does not define", "an id that is not a number"],
)
def test_a_picture_whose_licence_cannot_be_looked_up_is_refused(image: dict[str, Any]) -> None:
    selection = select(manifest([image]))

    assert selection.pictures == ()
    assert selection.refused_for_licence == 1


def test_an_identifier_that_is_not_a_positive_number_is_refused() -> None:
    """Every name the command writes is built from it, so it is checked here."""
    selection = select(manifest([{"id": "10", "license": 4}, {"id": -1, "license": 4}]))

    assert selection.pictures == ()
    assert selection.refused_for_licence == 2


def test_the_order_is_the_manifests_own_so_a_corpus_is_reproducible() -> None:
    images = [{"id": identifier, "license": 4} for identifier in (30, 10, 20)]

    selection = select(manifest(images))

    assert [picture.identifier for picture in selection.pictures] == [30, 10, 20]


def test_a_count_takes_the_first_pictures_and_zero_takes_none() -> None:
    selection = select(manifest([{"id": identifier, "license": 4} for identifier in (1, 2, 3)]))

    assert [picture.identifier for picture in wanted(selection, count=2)] == [1, 2]
    assert list(wanted(selection, count=0)) == []


# --- labels into tags ----------------------------------------------------------


def test_a_label_of_several_words_becomes_one_tag() -> None:
    assert tag_of("traffic light") == "traffic-light"
    with pytest.raises(TagError):
        normalise_tag("traffic light")  # which is why the conversion exists


def test_a_label_that_cannot_become_a_tag_is_dropped() -> None:
    assert tag_of("—") is None
    assert tag_of("   ") is None
    assert tags_of(["dog", "—", "sports ball"]) == ("dog", "sports-ball")


def test_labels_are_deduplicated_and_bounded() -> None:
    labels = [f"label {index}" for index in range(MAX_TAGS + 5)]

    assert len(tags_of(labels)) == MAX_TAGS
    assert tags_of(["dog", "Dog", "dog"]) == ("dog",)


def test_a_picture_carries_the_labels_of_its_annotations() -> None:
    read = manifest(
        [{"id": 10, "license": 4}],
        categories=[{"id": 1, "name": "traffic light"}, {"id": 2, "name": "dog"}],
        annotations=[
            {"image_id": 10, "category_id": 1},
            {"image_id": 10, "category_id": 2},
            {"image_id": 10, "category_id": 1},
        ],
    )

    picture = select(read).pictures[0]

    assert picture.tags == ("traffic-light", "dog")


def test_a_picture_with_no_annotations_has_no_tags() -> None:
    picture = select(manifest([{"id": 10, "license": 4}])).pictures[0]

    assert picture.tags == ()


def test_the_provenance_names_what_the_dataset_supplies_and_no_more() -> None:
    image = {"id": 39769, "license": 4, "flickr_url": "http://farm9.staticflickr.com/x_z.jpg"}

    provenance = select(manifest([image])).pictures[0].provenance()

    assert provenance["dataset_id"] == "39769"
    assert provenance["licence"] == "http://creativecommons.org/licenses/by/2.0/"
    assert provenance["source_url"] == image["flickr_url"], "where the picture can be seen"
    assert "author" not in provenance, "COCO records none; it is absent rather than invented"


@pytest.mark.parametrize(
    "declared",
    [None, 7, "javascript:alert(1)", "/etc/passwd", "http://" + "x" * 600],
    ids=["absent", "not a string", "not http", "a path", "too long"],
)
def test_an_address_the_manifest_cannot_supply_falls_back_to_the_one_we_built(
    declared: object,
) -> None:
    image: dict[str, Any] = {"id": 39769, "license": 4}
    if declared is not None:
        image["flickr_url"] = declared

    picture = select(manifest([image])).pictures[0]

    assert picture.source_url == picture.fetch_url
    assert picture.fetch_url.endswith("/val2017/000000039769.jpg")


def test_the_address_the_bytes_come_from_is_always_ours() -> None:
    """The manifest may say where a picture can be seen; it never says where
    this command goes."""
    image = {"id": 39769, "license": 4, "flickr_url": "http://elsewhere.example/steal.jpg"}

    picture = select(manifest([image])).pictures[0]

    assert picture.fetch_url.startswith("https://s3.amazonaws.com/images.cocodataset.org/")
    assert picture.source_url == "http://elsewhere.example/steal.jpg"
