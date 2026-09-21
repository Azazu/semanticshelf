"""Importing a directory of pictures: the walk, and what it refuses to read.

A path is not a thing. It is a name that can mean something else a microsecond
later, and this is the only part of the service that reads names it did not
generate — so nothing here decides anything from a path. The walk holds a
descriptor for the directory it is in (`os.fwalk`), opens each candidate
relative to that descriptor, and asks the *descriptor* what it got:

- `O_NOFOLLOW` makes the kernel refuse a symbolic link outright, so no link,
  wherever it points, is ever read;
- `O_NONBLOCK` makes the open of a fifo or a device return instead of hanging
  the run forever;
- `os.fstat` on the descriptor then decides whether this is a regular file,
  and the bytes that are read come from that same descriptor.

An entry replaced between being listed and being opened therefore cannot become
something else behind the walk's back: the check and the read are of one object.
"""

import errno
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.domain import FILE_EXTENSIONS

#: Suffixes worth opening: the extensions the service stores, plus `.jpeg`,
#: which is the same format under its other spelling. The suffix only decides
#: what is worth reading — what a file *is* is decided by decoding it, exactly
#: as at upload.
CANDIDATE_SUFFIXES = frozenset({f".{extension}" for extension in FILE_EXTENSIONS} | {".jpeg"})

#: Never through a symbolic link, never blocking on a fifo or a device node,
#: never inherited by a child process.
OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

SKIP_SYMLINK = "a symbolic link"
SKIP_NOT_REGULAR = "not a regular file"
SKIP_NO_PICTURE_SUFFIX = "not named like a picture"
SKIP_VANISHED = "it vanished during the walk"
SKIP_UNREADABLE = "it could not be opened"


class DirectoryUnusableError(Exception):
    """The directory named for the run cannot be walked at all."""


@dataclass(frozen=True, slots=True)
class Skipped:
    """An entry the walk did not read, and why."""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class Candidate:
    """A regular file, open. The handle is closed when the walk moves on."""

    path: Path
    handle: BinaryIO


def resolve_directory(directory: Path) -> Path:
    """The directory to walk, resolved once, or a refusal naming what is wrong.

    Resolved once and up front: a run may be pointed at a symbolic link to a
    directory, and everything after this point is about the directory it named.
    """
    root = directory.expanduser().resolve()
    if not root.exists():
        raise DirectoryUnusableError(f"no such directory: {directory}")
    if not root.is_dir():
        raise DirectoryUnusableError(f"not a directory: {directory}")
    try:
        os.scandir(root).close()
    except OSError as error:
        raise DirectoryUnusableError(f"{directory} could not be read: {error.strerror}") from error
    return root


def _open_candidate(name: str, dir_fd: int) -> int:
    """The one open in this module. A seam: a test replaces the entry here to
    prove that what is validated is the descriptor and not the name."""
    return os.open(name, OPEN_FLAGS, dir_fd=dir_fd)


def _refusal(error: OSError) -> str:
    if error.errno == errno.ELOOP:
        return SKIP_SYMLINK
    if error.errno == errno.ENOENT:
        return SKIP_VANISHED
    return SKIP_UNREADABLE


def walk(directory: Path, *, recursive: bool = False) -> Iterator[Candidate | Skipped]:
    """Every entry of the directory, in order: opened, or skipped with a reason.

    A candidate's handle is valid until the next entry is requested — the walk
    owns it and closes it, so an abandoned iteration leaks nothing.
    """
    root = resolve_directory(directory)
    for base, directories, files, dir_fd in os.fwalk(root, follow_symlinks=False):
        here = Path(base).relative_to(root)
        directories.sort()
        if recursive:
            for name in directories:
                if stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode):
                    yield Skipped(here / name, SKIP_SYMLINK)
        else:
            directories.clear()

        for name in sorted(files):
            relative = here / name
            if Path(name).suffix.lower() not in CANDIDATE_SUFFIXES:
                yield Skipped(relative, SKIP_NO_PICTURE_SUFFIX)
                continue
            try:
                descriptor = _open_candidate(name, dir_fd)
            except OSError as error:
                yield Skipped(relative, _refusal(error))
                continue
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    os.close(descriptor)
                    yield Skipped(relative, SKIP_NOT_REGULAR)
                    continue
            except OSError as error:
                os.close(descriptor)
                yield Skipped(relative, _refusal(error))
                continue
            handle = open(descriptor, "rb", closefd=True)
            try:
                yield Candidate(relative, handle)
            finally:
                handle.close()
