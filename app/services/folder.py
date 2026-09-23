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
import json
import os
import stat
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.settings import Settings
from app.domain import FILE_EXTENSIONS
from app.repositories.assets import AssetRepository
from app.services import images, indexing
from app.services.assets import DuplicateAssetError, create_asset, receive
from app.services.indexing import WorkReport
from app.services.tagging import MetadataError, TagError, check_metadata, normalise_tags
from app.storage import MediaStorage

#: Suffixes worth opening: the extensions the service stores, plus `.jpeg`,
#: which is the same format under its other spelling. The suffix only decides
#: what is worth reading — what a file *is* is decided by decoding it, exactly
#: as at upload.
CANDIDATE_SUFFIXES = frozenset({f".{extension}" for extension in FILE_EXTENSIONS} | {".jpeg"})

#: Never through a symbolic link, never blocking on a fifo or a device node,
#: never inherited by a child process.
OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

#: A picture may be accompanied by a file of the same name carrying that
#: picture's tags and metadata. It is read exactly as a picture is — through a
#: descriptor opened relative to the directory the walk holds — because a
#: sidecar read by path would hand back every hole `O_NOFOLLOW` closes.
SIDECAR_SUFFIX = ".json"
#: The metadata bound is 8 KiB (`tagging.METADATA_MAX_BYTES`); the file also
#: carries the tags, so it is allowed twice that and no more.
SIDECAR_MAX_BYTES = 16 * 1024

SKIP_SYMLINK = "a symbolic link"
SKIP_NOT_REGULAR = "not a regular file"
SKIP_NO_PICTURE_SUFFIX = "not named like a picture"
SKIP_VANISHED = "it vanished during the walk"
SKIP_UNREADABLE = "it could not be opened"

log = structlog.stdlib.get_logger(__name__)


class DirectoryUnusableError(Exception):
    """The directory named for the run cannot be walked at all."""


@dataclass(frozen=True, slots=True)
class Root:
    """The directory a run works in: resolved once, and then held open.

    `path` is what the report names; `fd` is what everything else is relative
    to. They cannot disagree: the path is read back from the descriptor, so the
    directory a run reports is the directory it holds. The name may be replaced
    a moment later — by a link to another tree, by a file, by nothing — and the
    run still reads, and still names, the directory it opened.
    """

    path: Path
    fd: int


@dataclass(frozen=True, slots=True)
class Skipped:
    """An entry the walk did not read, and why."""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class Candidate:
    """A regular file, open. The handle is closed when the walk moves on.

    `sidecar` holds the bytes of the file named after this one, when there is
    one and it could be read; `sidecar_refusal` says why it could not, and a
    picture whose sidecar could not be read is refused rather than imported
    without what it says.
    """

    path: Path
    handle: BinaryIO
    sidecar: bytes | None = None
    sidecar_refusal: str | None = None


def _open_directory(directory: Path) -> int:
    """The one open of the root. A seam: a test replaces the name here to prove
    that the descriptor and the path a run reports cannot disagree."""
    return os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def _path_of(descriptor: int, *, named: Path) -> Path:
    """What that descriptor actually refers to.

    Not resolved from the name: resolving a path and then opening it are two
    steps, and between them the name can come to mean another directory — which
    would leave a run reading one tree and reporting another.

    `/proc` answers this directly on Linux. Where it is missing, the name is
    resolved and then **proved** to be this very directory: the descriptor's
    device and inode against the resolved path's. A name that no longer leads
    to the directory being held is not a worse label for it, it is a different
    directory, and the run refuses rather than report it.
    """
    try:
        return Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    except OSError:
        pass
    resolved = named.expanduser().resolve()
    held = os.fstat(descriptor)
    try:
        candidate = os.stat(resolved)
    except OSError as error:
        raise DirectoryUnusableError(
            f"{named} could not be identified after it was opened: {error.strerror}"
        ) from error
    if (candidate.st_dev, candidate.st_ino) != (held.st_dev, held.st_ino):
        raise DirectoryUnusableError(
            f"{named} stopped being the directory that was opened; nothing was read"
        )
    return resolved


def open_root(directory: Path) -> Root:
    """Open the named directory once, or refuse naming what is wrong with it.

    A run may be pointed at a symbolic link to a directory: the open follows it,
    once, and everything after that — what is walked, and what the report names
    — comes from the descriptor it returned. The name is never consulted again,
    and there is no window between deciding what it means and holding it.
    """
    try:
        descriptor = _open_directory(directory.expanduser())
    except NotADirectoryError as error:
        raise DirectoryUnusableError(f"not a directory: {directory}") from error
    except FileNotFoundError as error:
        raise DirectoryUnusableError(f"no such directory: {directory}") from error
    except OSError as error:
        raise DirectoryUnusableError(f"{directory} could not be read: {error.strerror}") from error
    try:
        return Root(_path_of(descriptor, named=directory), descriptor)
    except BaseException:
        os.close(descriptor)  # a refusal leaves no descriptor behind
        raise


@contextmanager
def opened_root(directory: Path) -> Iterator[Root]:
    """`open_root`, closed again whatever happens."""
    root = open_root(directory)
    try:
        yield root
    finally:
        os.close(root.fd)


def _open_candidate(name: str, dir_fd: int) -> int:
    """The one open in this module. A seam: a test replaces the entry here to
    prove that what is validated is the descriptor and not the name."""
    return os.open(name, OPEN_FLAGS, dir_fd=dir_fd)


def _read_sidecar(name: str, dir_fd: int) -> tuple[bytes | None, str | None]:
    """The sidecar's bytes, or why they could not be read.

    Opened relative to the descriptor the walk holds, never by path, and judged
    by `fstat` on what was opened: a sidecar swapped for a symbolic link between
    the walk listing its picture and this open is refused by the kernel, not by
    a name check that could be raced.

    Called only for a name the walk has just listed, which is what makes every
    failure here a refusal: a picture with no sidecar never reaches this
    function, so "not there" can only mean "not there any more".
    """
    try:
        descriptor = _open_candidate(name, dir_fd)
    except OSError as error:
        # This is only reached for a sidecar the walk just listed, so a name
        # that is gone now is one that vanished between the two — not a picture
        # without a sidecar. Losing that difference would import the picture
        # without the provenance the run had already seen it carry.
        return None, _refusal(error)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None, SKIP_NOT_REGULAR
    except OSError as error:
        os.close(descriptor)
        return None, _refusal(error)
    try:
        with open(descriptor, "rb", closefd=True) as handle:
            raw = handle.read(SIDECAR_MAX_BYTES + 1)
    except OSError as error:
        return None, _refusal(error)
    if len(raw) > SIDECAR_MAX_BYTES:
        return None, f"larger than the {SIDECAR_MAX_BYTES} bytes a sidecar may have"
    return raw, None


def _refusal(error: OSError) -> str:
    if error.errno == errno.ELOOP:
        return SKIP_SYMLINK
    if error.errno == errno.ENOENT:
        return SKIP_VANISHED
    return SKIP_UNREADABLE


def _sidecars_in(files: Sequence[str]) -> set[str]:
    """Which of these names belong to a picture beside them.

    One rule, used by the counter and by the walk: the two must agree about
    what an entry is, or a progress bar and a report count different things.
    """
    here = set(files)
    return {
        f"{Path(name).stem}{SIDECAR_SUFFIX}"
        for name in here
        if Path(name).suffix.lower() in CANDIDATE_SUFFIXES
    } & here


def count_entries(root: Root, *, recursive: bool = False) -> int:
    """How many entries a walk of this root would yield.

    Names only: nothing is opened, nothing is read. It exists so a terminal can
    draw a bar with a total, and it is a total, not a promise — a tree that
    changes between this and the walk changes the answer. It counts from the
    same descriptor the walk uses, so the two cannot be looking at different
    directories.
    """
    entries = 0
    for _, directories, files, dir_fd in os.fwalk(".", dir_fd=root.fd, follow_symlinks=False):
        # A sidecar is not an entry the walk reports — it belongs to its picture
        # — so counting it here would leave the bar one short for every pair.
        entries += len(set(files) - _sidecars_in(files))
        if recursive:
            entries += sum(
                1 for name in directories if stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode)
            )
        else:
            directories.clear()
    return entries


def walk(root: Root, *, recursive: bool = False) -> Iterator[Candidate | Skipped]:
    """Every entry of the root, in order: opened, or skipped with a reason.

    It takes a `Root` rather than a path because the root is resolved once, by
    whoever opened it, and walked by descriptor from there: nothing here
    consults the name again.

    A candidate's handle is valid until the next entry is requested — the walk
    owns it and closes it, so an abandoned iteration leaks nothing.
    """
    for base, directories, files, dir_fd in os.fwalk(".", dir_fd=root.fd, follow_symlinks=False):
        here = Path(base)
        directories.sort()
        if recursive:
            for name in directories:
                if stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode):
                    yield Skipped(here / name, SKIP_SYMLINK)
        else:
            directories.clear()

        sidecars = _sidecars_in(files)
        for name in sorted(files):
            relative = here / name
            if name in sidecars:
                continue  # it belongs to a picture: not a candidate of its own
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
            sidecar_name = f"{Path(name).stem}{SIDECAR_SUFFIX}"
            raw, refusal = (
                _read_sidecar(sidecar_name, dir_fd) if sidecar_name in sidecars else (None, None)
            )
            handle = open(descriptor, "rb", closefd=True)
            try:
                yield Candidate(relative, handle, sidecar=raw, sidecar_refusal=refusal)
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
    #: `None` when the run was a dry run or was asked to leave the work queued.
    work: WorkReport | None = None

    def count(self, state: str) -> int:
        return sum(1 for outcome in self.files if outcome.state == state)

    @property
    def created_assets(self) -> list[UUID]:
        return [
            outcome.asset_id
            for outcome in self.files
            if outcome.state == CREATED and outcome.asset_id is not None
        ]


class SidecarError(ValueError):
    """A sidecar that cannot be used for the picture it belongs to."""


def read_sidecar(raw: bytes) -> tuple[tuple[str, ...], dict[str, Any]]:
    """What a sidecar says: its tags and its metadata, through the same rules.

    Nothing here is new: the tags go through the normalisation an upload
    applies, the metadata through the same object-and-size check as `--meta`.
    A sidecar only reaches its own picture, so a broken one costs that picture
    and nothing else.
    """
    try:
        content = json.loads(raw)
    except ValueError as error:
        raise SidecarError(f"not JSON: {error}") from error
    if not isinstance(content, dict):
        raise SidecarError("not an object")
    unknown = set(content) - {"tags", "meta"}
    if unknown:
        raise SidecarError(f"unexpected keys: {', '.join(sorted(unknown))}")
    raw_tags = content.get("tags", [])
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
        raise SidecarError("tags must be a list of strings")
    raw_meta = content.get("meta", {})
    if not isinstance(raw_meta, dict):
        raise SidecarError("meta must be an object")
    try:
        tags = normalise_tags(raw_tags)
        meta = check_metadata(raw_meta)
    except (TagError, MetadataError) as error:
        raise SidecarError(str(error)) from error
    return tags, meta


def combine(
    candidate: Candidate, *, tags: Sequence[str], meta: Mapping[str, Any]
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """The run's tags and metadata with this picture's own folded in.

    Tags add to the run's; metadata merges over it. Neither can reach the
    recorded origin, which `metadata_for` writes last whatever either says.
    """
    if candidate.sidecar_refusal is not None:
        raise SidecarError(candidate.sidecar_refusal)
    if candidate.sidecar is None:
        return tuple(tags), dict(meta)
    own_tags, own_meta = read_sidecar(candidate.sidecar)
    try:
        combined = normalise_tags([*tags, *own_tags])
    except TagError as error:
        raise SidecarError(str(error)) from error
    return combined, {**dict(meta), **own_meta}


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
        own_tags, own_meta = combine(candidate, tags=tags, meta=meta)
    except SidecarError as error:
        return FileOutcome(candidate.path, REFUSED, reason=f"its sidecar: {error}")
    try:
        recorded = metadata_for(candidate.path, own_meta)
    except MetadataError as error:  # the bound a long path can push it over
        return FileOutcome(candidate.path, REFUSED, reason=str(error))
    try:
        asset = await create_asset(
            session=session,
            storage=storage,
            settings=settings,
            source=candidate.handle,
            original_filename=candidate.path.name,
            tags=own_tags,
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
    tags: Sequence[str] = (),
    meta: Mapping[str, Any],
    rehearsed: set[str] | None = None,
) -> FileOutcome:
    """What `import_one` would do, without doing it.

    The same steps up to the write: the bytes are read and hashed into a
    temporary file outside the media root, inspected through the same
    inspection, and the hash is looked up the same way. Then the temporary file
    goes and nothing else has happened.

    The lookup opens and closes a transaction of its own, so the session is as
    clean afterwards as `create_asset` leaves it. A read that left one open
    would make the next file — dry run or not — fail to begin its own.

    `rehearsed` carries the hashes this run has already called new, because the
    database cannot: two files of identical bytes in one folder are one asset,
    and a rehearsal that only ever asked the store would call both of them new.
    """
    try:
        # The run's tags, not none of them: a sidecar's tags are added to them,
        # and a rehearsal that left them out could call a picture created that
        # the real run refuses for the two together.
        _, own_meta = combine(candidate, tags=tags, meta=meta)
    except SidecarError as error:
        return FileOutcome(candidate.path, REFUSED, reason=f"its sidecar: {error}")
    try:
        metadata_for(candidate.path, own_meta)  # for its refusal; a dry run stores nothing
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
        already_rehearsed = rehearsed is not None and received.sha256 in rehearsed
        if rehearsed is not None:
            rehearsed.add(received.sha256)
    finally:
        await run_in_threadpool(_discard, received.path)

    if existing is not None:
        return FileOutcome(candidate.path, ALREADY_STORED, asset_id=existing.id)
    if already_rehearsed:
        # A real run would have stored the first of these and found the second
        # already there; the rehearsal says the same.
        return FileOutcome(candidate.path, ALREADY_STORED)
    return FileOutcome(candidate.path, CREATED)


def _discard(path: Path) -> None:
    """Blocking; called in a worker thread. Never raises."""
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - nothing to do about it here
        log.warning("temporary file could not be removed", file=str(path))


async def import_folder(
    directory: Path | Root,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    recursive: bool = False,
    tags: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
    dry_run: bool = False,
    on_file: Callable[[FileOutcome], None] | None = None,
) -> ImportReport:
    """Import a directory, and account for every file it held.

    Given a path, the root is opened here and closed again at the end; given a
    `Root`, the caller's own — which is how the command counts the entries and
    imports them through one descriptor rather than resolving the name twice.

    The run's tags and metadata are checked once, before anything is read, so
    a folder cannot be half imported under a tag the service then rejects.
    """
    if isinstance(directory, Root):
        return await _import(
            directory,
            session=session,
            storage=storage,
            settings=settings,
            recursive=recursive,
            tags=tags,
            meta=meta,
            dry_run=dry_run,
            on_file=on_file,
        )
    with opened_root(directory) as root:
        return await _import(
            root,
            session=session,
            storage=storage,
            settings=settings,
            recursive=recursive,
            tags=tags,
            meta=meta,
            dry_run=dry_run,
            on_file=on_file,
        )


async def _import(
    root: Root,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    recursive: bool,
    tags: Sequence[str],
    meta: Mapping[str, Any] | None,
    dry_run: bool,
    on_file: Callable[[FileOutcome], None] | None,
) -> ImportReport:
    normalised = normalise_tags(tags)
    given = check_metadata(dict(meta or {}))
    report = ImportReport(directory=root.path, dry_run=dry_run)
    #: Hashes this rehearsal has already called new. Without them two files of
    #: identical bytes in one folder would both be reported as created, while a
    #: real run stores the first and counts the second as already stored.
    rehearsed: set[str] = set()

    for entry in walk(root, recursive=recursive):
        if isinstance(entry, Skipped):
            skipped = FileOutcome(entry.path, SKIPPED, reason=entry.reason)
            report.files.append(skipped)
            if on_file is not None:
                on_file(skipped)
            continue
        if dry_run:
            outcome = await examine_one(
                entry,
                session=session,
                storage=storage,
                settings=settings,
                tags=normalised,
                meta=given,
                rehearsed=rehearsed,
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
        if on_file is not None:
            on_file(outcome)
    return report


# --- finishing the work the import created ------------------------------------


async def index_imported(
    report: ImportReport,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    on_progress: Callable[[int], None] | None = None,
) -> WorkReport:
    """Carry out the work this run created — and only that work.

    The loop belongs to the queue, not to the import: `index missing` finishes
    what it queued the same way (`app/services/indexing.py`). What is this
    module's is which assets to name — the ones this run created, so an import
    finishes what it started instead of being satisfied by someone else's
    backlog.
    """
    work = await indexing.finish_work(
        report.created_assets,
        session_factory=session_factory,
        storage=storage,
        settings=settings,
        pool=pool,
        on_progress=on_progress,
    )
    report.work = work
    return work


def describe(report: ImportReport) -> list[str]:
    """The report as lines for a terminal, in the shape `storage prune` uses."""
    lines = [f"folder: {report.directory}" + (" (dry run)" if report.dry_run else "")]
    for state in (CREATED, ALREADY_STORED, REFUSED, SKIPPED):
        lines.append(f"{state}: {report.count(state)}")
    lines.extend(
        f"  {outcome.state:14} {outcome.path} — {outcome.reason}"
        for outcome in report.files
        if outcome.state in (REFUSED, SKIPPED) and outcome.reason
    )
    work = report.work
    if work is None:
        lines.append("indexing: not run" if not report.dry_run else "indexing: nothing to run")
        return lines
    if not report.created_assets:
        lines.append("indexing: nothing to do")
        return lines
    lines.append(f"indexed: {work.indexed}")
    lines.append(f"still queued: {len(work.queued)}")
    lines.extend(f"  queued  {asset_id} — {why}" for asset_id, why in work.queued)
    lines.append(f"failed: {len(work.failed)}")
    lines.extend(f"  failed  {asset_id} — {reason}" for asset_id, reason in work.failed)
    return lines
