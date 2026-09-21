"""The media root: derived paths, atomic publication, removal and the walk."""

import uuid
from pathlib import Path
from uuid import UUID

import pytest

from app.storage import STAGING_SUFFIX, THUMBNAIL_SUFFIX, MediaStorage, UnsafePathError, asset_id_of

ASSET = UUID("0f9b1d2c-3e4f-4a5b-8c7d-9e0f1a2b3c4d")


@pytest.fixture
def storage(tmp_path: Path) -> MediaStorage:
    return MediaStorage.at(tmp_path)


def test_the_shard_is_the_first_two_hex_characters(storage: MediaStorage) -> None:
    assert storage.shard(ASSET).name == "0f"
    assert storage.original(ASSET, "jpg").parent == storage.shard(ASSET)


def test_the_names_carry_the_identifier_and_the_format(storage: MediaStorage) -> None:
    assert storage.original(ASSET, "png").name == f"{ASSET}.png"
    assert storage.thumbnail(ASSET).name == f"{ASSET}{THUMBNAIL_SUFFIX}"


def test_an_unknown_format_is_refused(storage: MediaStorage) -> None:
    for value in ["exe", "jpg/../../etc/passwd", "", "../png"]:
        with pytest.raises(UnsafePathError):
            storage.original(ASSET, value)


def test_every_derived_path_stays_under_the_root(storage: MediaStorage) -> None:
    for asset_id in (ASSET, uuid.uuid4(), UUID(int=0), UUID(int=(1 << 128) - 1)):
        for path in (
            storage.shard(asset_id),
            storage.original(asset_id, "webp"),
            storage.thumbnail(asset_id),
            storage.stage(asset_id),
        ):
            assert path.resolve().is_relative_to(storage.root)


def test_a_symbolic_link_out_of_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    storage = MediaStorage.at(root)
    # A link planted where a shard would be: resolving it leaves the root.
    (root / ASSET.hex[:2]).symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        storage.original(ASSET, "jpg")


def test_a_file_is_visible_only_under_its_final_name(storage: MediaStorage) -> None:
    staged = storage.stage(ASSET)
    final = storage.original(ASSET, "jpg")

    size = storage.fill(staged, [b"one", b"two"])

    assert size == 6
    assert staged.exists() and not final.exists()
    assert staged.name.endswith(STAGING_SUFFIX)

    storage.publish(staged, final)

    assert final.read_bytes() == b"onetwo"
    assert not staged.exists()


def test_removal_tolerates_a_file_that_is_already_gone(storage: MediaStorage) -> None:
    staged = storage.stage(ASSET)
    storage.fill(staged, [b"x"])
    storage.publish(staged, storage.original(ASSET, "jpg"))

    storage.remove(ASSET, "jpg")  # the thumbnail was never written
    storage.remove(ASSET, "jpg")  # and again, on nothing at all

    assert not storage.original(ASSET, "jpg").exists()


def test_the_walk_finds_what_the_writer_wrote(storage: MediaStorage) -> None:
    staged = storage.stage(ASSET)
    storage.fill(staged, [b"x"])
    storage.publish(staged, storage.original(ASSET, "jpg"))
    left_behind = storage.stage(ASSET)
    storage.fill(left_behind, [b"y"])

    found = {path: mtime for path, mtime in storage.walk()}

    assert storage.original(ASSET, "jpg") in found
    assert left_behind in found
    assert all(isinstance(mtime, float) for mtime in found.values())


def test_a_stored_name_reveals_its_asset(storage: MediaStorage) -> None:
    assert asset_id_of(storage.original(ASSET, "jpg")) == ASSET
    assert asset_id_of(storage.thumbnail(ASSET)) == ASSET
    assert asset_id_of(storage.stage(ASSET)) is None
    assert asset_id_of(Path("/tmp/not-an-asset.jpg")) is None
