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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.settings import Settings
from app.domain import FILE_EXTENSIONS
from app.repositories.assets import AssetRepository
from app.services import images
from app.services.assets import DuplicateAssetError, create_asset, receive
from app.services.tagging import MetadataError, check_metadata, normalise_tags
from app.storage import MediaStorage

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

log = structlog.stdlib.get_logger(__name__)


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


# --- importing what the walk found -------------------------------------------
#
# One asset at a time, each through `app/services/assets.py::create_asset` and
# nothing else: the import adds no rule to the pipeline, it only feeds it.

#: Where a file's path relative to the imported directory is recorded. It is
#: metadata because a path is text; `original_filename` keeps the guarantee
#: change 5 gave it, that it holds one name and no directory.
SOURCE_PATH_KEY = "source_path"

CREATED = "created"
ALREADY_STORED = "already stored"
REFUSED = "refused"
SKIPPED = "skipped"

#: What a file may be refused for. Anything else is not a refusal but a failure
#: of the run, and is left to the caller.
REFUSALS = (
    images.UndecodableImageError,
    images.UnsupportedFormatError,
    images.ImageTooLargeError,
    images.ImageTooSmallError,
)


@dataclass(frozen=True, slots=True)
class FileOutcome:
    """What happened to one file the walk considered."""

    path: Path
    state: str
    reason: str | None = None
    asset_id: UUID | None = None


@dataclass(slots=True)
class ImportReport:
    """Everything a run did, in the order it did it."""

    directory: Path
    dry_run: bool
    files: list[FileOutcome] = field(default_factory=list)

    def count(self, state: str) -> int:
        return sum(1 for outcome in self.files if outcome.state == state)

    @property
    def created_assets(self) -> list[UUID]:
        return [
            outcome.asset_id
            for outcome in self.files
            if outcome.state == CREATED and outcome.asset_id is not None
        ]


def metadata_for(relative: Path, meta: Mapping[str, Any]) -> dict[str, Any]:
    """The run's metadata with the recorded origin last, so a run cannot
    overwrite where the file came from — by accident or otherwise."""
    return check_metadata({**dict(meta), SOURCE_PATH_KEY: str(relative)})


async def import_one(
    candidate: Candidate,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    tags: Sequence[str],
    meta: Mapping[str, Any],
) -> FileOutcome:
    """Store one file through the upload pipeline, or say why it was not.

    Only the refusals an upload gives are outcomes here. Anything else — a
    database that went away, a disk that filled — is a failure of the run and
    is left to the caller, because continuing past it would import a folder
    into nothing.
    """
    try:
        recorded = metadata_for(candidate.path, meta)
    except MetadataError as error:  # the bound a long path can push it over
        return FileOutcome(candidate.path, REFUSED, reason=str(error))
    try:
        asset = await create_asset(
            session=session,
            storage=storage,
            settings=settings,
            source=candidate.handle,
            original_filename=candidate.path.name,
            tags=tags,
            meta=recorded,
            asset_source="folder",
        )
    except DuplicateAssetError as duplicate:
        return FileOutcome(candidate.path, ALREADY_STORED, asset_id=duplicate.existing_asset_id)
    except REFUSALS as refusal:
        return FileOutcome(candidate.path, REFUSED, reason=str(refusal))
    return FileOutcome(candidate.path, CREATED, asset_id=asset.id)


async def examine_one(
    candidate: Candidate,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    meta: Mapping[str, Any],
) -> FileOutcome:
    """What `import_one` would do, without doing it.

    The same steps up to the write: the bytes are read and hashed into a
    temporary file outside the media root, inspected through the same
    inspection, and the hash is looked up the same way. Then the temporary file
    goes and nothing else has happened.

    The lookup opens and closes a transaction of its own, so the session is as
    clean afterwards as `create_asset` leaves it. A read that left one open
    would make the next file — dry run or not — fail to begin its own.
    """
    try:
        metadata_for(candidate.path, meta)  # for its refusal; a dry run stores nothing
    except MetadataError as error:
        return FileOutcome(candidate.path, REFUSED, reason=str(error))

    received = await run_in_threadpool(receive, storage, candidate.handle)
    try:
        try:
            await run_in_threadpool(images.inspect, received.path, settings)
        except REFUSALS as refusal:
            return FileOutcome(candidate.path, REFUSED, reason=str(refusal))
        # In its own transaction, and ended here: a read left open would be a
        # transaction the next file's `create_asset` cannot begin inside.
        async with session.begin():
            existing = await AssetRepository(session).get_by_sha256(received.sha256)
    finally:
        await run_in_threadpool(_discard, received.path)

    if existing is not None:
        return FileOutcome(candidate.path, ALREADY_STORED, asset_id=existing.id)
    return FileOutcome(candidate.path, CREATED)


def _discard(path: Path) -> None:
    """Blocking; called in a worker thread. Never raises."""
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - nothing to do about it here
        log.warning("temporary file could not be removed", file=str(path))


async def import_folder(
    directory: Path,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    recursive: bool = False,
    tags: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
    dry_run: bool = False,
) -> ImportReport:
    """Import a directory, and account for every file it held.

    The run's tags and metadata are checked once, before anything is read, so
    a folder cannot be half imported under a tag the service then rejects.
    """
    normalised = normalise_tags(tags)
    given = check_metadata(dict(meta or {}))
    report = ImportReport(directory=resolve_directory(directory), dry_run=dry_run)

    for entry in walk(directory, recursive=recursive):
        if isinstance(entry, Skipped):
            report.files.append(FileOutcome(entry.path, SKIPPED, reason=entry.reason))
            continue
        if dry_run:
            outcome = await examine_one(
                entry, session=session, storage=storage, settings=settings, meta=given
            )
        else:
            outcome = await import_one(
                entry,
                session=session,
                storage=storage,
                settings=settings,
                tags=normalised,
                meta=given,
            )
        report.files.append(outcome)
    return report
