"""Where an asset's bytes live.

This is the only module in the application that builds a path under the media
root, and it builds every one of them from an identifier the service generated
and a format it detected. Nothing a client sends — a filename, a header, a
parameter — reaches a path: the original filename is text we store, never a
path component. A unit test walks adversarial values through every public
function and asserts that each either lands under the resolved root or is
refused.

A file becomes visible only under its final name: it is written to a temporary
name in its own directory, flushed to disk and renamed, which is atomic within
a directory. A crash therefore leaves either nothing or a complete file, never
a half-written one under the name the service serves.
"""

import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.domain import FILE_EXTENSIONS

#: The suffix of the thumbnail beside the original. Its format is fixed: the
#: thumbnail is always WebP, whatever the original is.
THUMBNAIL_SUFFIX = ".thumb.webp"
#: How many hex characters of the identifier name the directory. Two gives 256
#: directories, which keeps any one of them small enough to list.
SHARD_LENGTH = 2
#: Written while a file is being made, and never served.
STAGING_SUFFIX = ".part"


class UnsafePathError(ValueError):
    """A value that would build a path outside the media root."""


@dataclass(frozen=True, slots=True)
class MediaStorage:
    """The media root, and every operation that touches it."""

    root: Path

    @classmethod
    def at(cls, root: Path) -> "MediaStorage":
        """Resolve the root once, so every containment check compares against
        the same absolute path even if the process changes directory."""
        return cls(root=root.resolve())

    # --- the paths -----------------------------------------------------------

    def _checked(self, path: Path) -> Path:
        """The last line: whatever built this path, it stays under the root."""
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root):
            raise UnsafePathError("the derived path leaves the media root")
        return resolved

    def shard(self, asset_id: UUID) -> Path:
        """The directory holding one asset's files."""
        return self._checked(Path(asset_id.hex[:SHARD_LENGTH]))

    def original(self, asset_id: UUID, file_ext: str) -> Path:
        if file_ext not in FILE_EXTENSIONS:
            raise UnsafePathError(f"unknown file extension: {file_ext!r}")
        return self._checked(Path(asset_id.hex[:SHARD_LENGTH]) / f"{asset_id}.{file_ext}")

    def thumbnail(self, asset_id: UUID) -> Path:
        return self._checked(Path(asset_id.hex[:SHARD_LENGTH]) / f"{asset_id}{THUMBNAIL_SUFFIX}")

    # --- writing -------------------------------------------------------------

    def stage(self, asset_id: UUID) -> Path:
        """A temporary path in the asset's own directory, created on demand.

        In the same directory as the final name on purpose: a rename is atomic
        only within one filesystem, and this guarantees it is one.
        """
        directory = self.shard(asset_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{asset_id}.{uuid.uuid4().hex}{STAGING_SUFFIX}"

    @staticmethod
    def fill(staged: Path, chunks: Iterable[bytes]) -> int:
        """Write chunks to a staged file, flush them to disk, return the size.

        A failure anywhere — the source, the write, the flush — removes what
        was written. A half-file under a staging name is still rubbish someone
        has to clean up, and the code that would have to know its path is the
        code that just failed.
        """
        written = 0
        try:
            with staged.open("wb") as handle:
                for chunk in chunks:
                    handle.write(chunk)
                    written += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
        return written

    @staticmethod
    def publish(staged: Path, final: Path) -> None:
        """Make a staged file visible under the name the service serves."""
        staged.replace(final)

    # --- removing and walking ------------------------------------------------

    @staticmethod
    def discard(path: Path) -> None:
        """Remove a file that may already be gone."""
        path.unlink(missing_ok=True)

    def remove(self, asset_id: UUID, file_ext: str) -> None:
        """Remove both of an asset's files, tolerating either being absent."""
        self.discard(self.original(asset_id, file_ext))
        self.discard(self.thumbnail(asset_id))

    def remove_any(self, asset_id: UUID) -> None:
        """Everything belonging to an asset, whatever format it turned out to
        be. Used when an upload fails before its format is even known."""
        self.discard(self.thumbnail(asset_id))
        for file_ext in FILE_EXTENSIONS:
            self.discard(self.original(asset_id, file_ext))

    def walk(self) -> Iterator[tuple[Path, float]]:
        """Every file under the root with the time it was last modified.

        Used by `storage prune` alone; it yields staged files too, because a
        staged file left behind is exactly the rubbish prune is there to find.
        """
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                yield path, path.stat().st_mtime


def asset_id_of(path: Path) -> UUID | None:
    """The asset a stored file belongs to, or `None` when the name is not one
    the service writes. Reading the name is enough: the identifier is in it."""
    name = path.name
    if name.endswith(STAGING_SUFFIX):
        return None
    stem = name[: -len(THUMBNAIL_SUFFIX)] if name.endswith(THUMBNAIL_SUFFIX) else path.stem
    try:
        return UUID(stem)
    except ValueError:
        return None
