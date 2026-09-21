"""What the walk reads, what it refuses, and what it says about the rest.

Everything here is decided before a database or a model is involved, so these
run in `make check`. The tree each test builds is the point: a symbolic link
out of it, a link to its own parent, a fifo, a document, a file whose name
lies, and a picture two directories down.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.services import folder
from app.services.folder import Candidate, DirectoryUnusableError, Skipped

PICTURE = b"\x89PNG\r\n\x1a\n and then some bytes"


def tree(root: Path) -> Path:
    """A directory with one of everything the walk has to have an answer for."""
    outside = root / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"not ours")

    inside = root / "folder"
    (inside / "sub").mkdir(parents=True)
    (inside / "picture.png").write_bytes(PICTURE)
    (inside / "sub" / "deep.jpeg").write_bytes(PICTURE)
    (inside / "notes.txt").write_bytes(b"a document")
    (inside / "lying.png").write_bytes(b"still a document")
    (inside / "link-out.png").symlink_to(outside / "secret.png")
    (inside / "link-in.png").symlink_to(inside / "picture.png")
    (inside / "loop").symlink_to(inside, target_is_directory=True)
    os.mkfifo(inside / "pipe.png")
    return inside


def outcomes(entries: Iterator[Candidate | Skipped]) -> dict[str, str]:
    """Each entry by its path, as either its first bytes or its skip reason."""
    seen: dict[str, str] = {}
    for entry in entries:
        key = str(entry.path)
        assert key not in seen, f"{key} was visited twice"
        seen[key] = (
            entry.handle.read(4).decode("latin-1") if isinstance(entry, Candidate) else entry.reason
        )
    return seen


def test_the_walk_answers_for_every_entry_of_the_top_level(tmp_path: Path) -> None:
    inside = tree(tmp_path)

    seen = outcomes(folder.walk(inside))

    assert seen == {
        "picture.png": "\x89PNG",
        "notes.txt": folder.SKIP_NO_PICTURE_SUFFIX,
        "lying.png": "stil",  # the bytes decide later, not the walk
        "link-out.png": folder.SKIP_SYMLINK,
        "link-in.png": folder.SKIP_SYMLINK,
        "pipe.png": folder.SKIP_NOT_REGULAR,
    }, "a subdirectory is out of scope without --recursive, and says nothing"


def test_the_recursive_walk_reaches_the_subdirectories(tmp_path: Path) -> None:
    inside = tree(tmp_path)

    seen = outcomes(folder.walk(inside, recursive=True))

    assert seen["sub/deep.jpeg"] == "\x89PNG", "`.jpeg` is worth opening too"
    assert seen["loop"] == folder.SKIP_SYMLINK, "the link to its own parent is reported"
    assert seen["picture.png"] == "\x89PNG"


def test_a_link_to_its_own_parent_does_not_make_the_walk_endless(tmp_path: Path) -> None:
    inside = tree(tmp_path)

    entries = list(folder.walk(inside, recursive=True))

    paths = [str(entry.path) for entry in entries]
    assert len(paths) == len(set(paths)), "each real file is read at most once"
    assert not [path for path in paths if path.startswith("loop/")], "nothing beyond the link"


def test_the_walk_is_sorted(tmp_path: Path) -> None:
    inside = tmp_path / "folder"
    inside.mkdir()
    for name in ("c.png", "a.png", "b.png"):
        (inside / name).write_bytes(PICTURE)

    assert [str(entry.path) for entry in folder.walk(inside)] == ["a.png", "b.png", "c.png"]


# --- what is validated is the descriptor -------------------------------------


def test_an_entry_swapped_for_a_link_between_listing_and_opening_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race the walk exists to survive: the name was a picture when it was
    listed and is a link to somewhere else when it is opened."""
    inside = tree(tmp_path)
    original = folder._open_candidate

    def swap_then_open(name: str, dir_fd: int) -> int:
        if name == "picture.png":
            os.unlink(inside / name)
            (inside / name).symlink_to(tmp_path / "outside" / "secret.png")
        return original(name, dir_fd)

    monkeypatch.setattr(folder, "_open_candidate", swap_then_open)

    seen = outcomes(folder.walk(inside))

    assert seen["picture.png"] == folder.SKIP_SYMLINK
    assert "not ours" not in seen.values(), "nothing from outside the folder was read"


def test_an_entry_swapped_for_a_fifo_between_listing_and_opening_does_not_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = tree(tmp_path)
    original = folder._open_candidate

    def swap_then_open(name: str, dir_fd: int) -> int:
        if name == "picture.png":
            os.unlink(inside / name)
            os.mkfifo(inside / name)
        return original(name, dir_fd)

    monkeypatch.setattr(folder, "_open_candidate", swap_then_open)

    seen = outcomes(folder.walk(inside))

    assert seen["picture.png"] == folder.SKIP_NOT_REGULAR


def test_an_entry_that_vanishes_between_listing_and_opening_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = tree(tmp_path)
    original = folder._open_candidate

    def remove_then_open(name: str, dir_fd: int) -> int:
        if name == "picture.png":
            os.unlink(inside / name)
        return original(name, dir_fd)

    monkeypatch.setattr(folder, "_open_candidate", remove_then_open)

    assert outcomes(folder.walk(inside))["picture.png"] == folder.SKIP_VANISHED


def test_a_file_that_cannot_be_opened_is_reported(tmp_path: Path) -> None:
    inside = tmp_path / "folder"
    inside.mkdir()
    forbidden = inside / "locked.png"
    forbidden.write_bytes(PICTURE)
    forbidden.chmod(0o000)
    try:
        seen = outcomes(folder.walk(inside))
    finally:
        forbidden.chmod(0o600)

    assert seen["locked.png"] == folder.SKIP_UNREADABLE


# --- the directory itself -----------------------------------------------------


def test_a_directory_that_is_not_there_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DirectoryUnusableError, match="no such directory"):
        list(folder.walk(tmp_path / "nowhere"))


def test_a_path_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    picture = tmp_path / "picture.png"
    picture.write_bytes(PICTURE)

    with pytest.raises(DirectoryUnusableError, match="not a directory"):
        list(folder.walk(picture))


def test_a_directory_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    closed = tmp_path / "closed"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        with pytest.raises(DirectoryUnusableError, match="could not be read"):
            list(folder.walk(closed))
    finally:
        closed.chmod(0o700)


def test_a_link_to_a_directory_is_walked_as_that_directory(tmp_path: Path) -> None:
    inside = tmp_path / "folder"
    inside.mkdir()
    (inside / "picture.png").write_bytes(PICTURE)
    named = tmp_path / "by-link"
    named.symlink_to(inside, target_is_directory=True)

    assert outcomes(folder.walk(named)) == {"picture.png": "\x89PNG"}


def test_a_link_to_something_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    picture = tmp_path / "picture.png"
    picture.write_bytes(PICTURE)
    named = tmp_path / "by-link"
    named.symlink_to(picture)

    with pytest.raises(DirectoryUnusableError, match="not a directory"):
        list(folder.walk(named))


def test_an_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert list(folder.walk(empty, recursive=True)) == []


def test_a_directory_of_nothing_worth_reading_says_so(tmp_path: Path) -> None:
    inside = tmp_path / "documents"
    inside.mkdir()
    (inside / "notes.txt").write_bytes(b"a document")
    (inside / "report.pdf").write_bytes(b"another one")

    seen = outcomes(folder.walk(inside))

    assert seen == {
        "notes.txt": folder.SKIP_NO_PICTURE_SUFFIX,
        "report.pdf": folder.SKIP_NO_PICTURE_SUFFIX,
    }


def test_the_handle_of_an_abandoned_walk_is_closed(tmp_path: Path) -> None:
    """The walk owns the descriptor: stopping early must not leak one."""
    inside = tmp_path / "folder"
    inside.mkdir()
    (inside / "a.png").write_bytes(PICTURE)
    (inside / "b.png").write_bytes(PICTURE)

    entries = folder.walk(inside)
    first = next(entries)
    assert isinstance(first, Candidate)
    entries.close()

    assert first.handle.closed
