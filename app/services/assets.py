"""The asset use cases: create one from an upload, read it, list, edit, remove.

`create_asset` is where the order matters, and the order answers two questions
at once: what a crash may leave behind, and what `storage prune` may find.

An upload is read into a temporary file **outside the media root** and inspected
there, so every refusal — wrong format, too many pixels, too small — costs
nothing but a temporary file and never touches the database. Only once the
picture is known good does the transaction open, take the shared media lock and
move the bytes under the root. Everything that exists under the media root
therefore exists either published or while this upload holds the lock, which is
what makes prune safe without any assumption about how long an upload takes.

Every blocking step — reading, decoding, encoding the thumbnail, writing to
disk — runs in a worker thread. This is Starlette's shared pool, not the
inference pool of change 4: that one is sized for model work, and a burst of
uploads must not stall embedding.
"""

import hashlib
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.settings import Settings
from app.db.locks import hold_media_shared
from app.domain import Asset
from app.repositories.assets import AssetRepository
from app.services import images
from app.storage import MediaStorage

#: Read in pieces so that neither the hash nor the copy holds the file in memory.
CHUNK_BYTES = 1024 * 1024

log = structlog.stdlib.get_logger(__name__)


class DuplicateAssetError(Exception):
    """Those bytes are already stored, under the asset this names."""

    def __init__(self, existing_asset_id: UUID) -> None:
        super().__init__(f"asset already exists: {existing_asset_id}")
        self.existing_asset_id = existing_asset_id


@dataclass(frozen=True, slots=True)
class Received:
    """An upload as it sits outside the media root: its bytes, its hash, its size."""

    path: Path
    sha256: str
    size_bytes: int


def _hashing_chunks(source: BinaryIO, digest: "hashlib._Hash") -> Iterator[bytes]:
    while chunk := source.read(CHUNK_BYTES):
        digest.update(chunk)
        yield chunk


class StagingLocationError(RuntimeError):
    """The temporary directory lies inside the media root.

    Then a received file would be visible to `storage prune` before the upload
    holds the shared claim, which is exactly the race the protocol removes. It
    is a deployment mistake — `MEDIA_ROOT` set to the temporary directory, or
    above it — and it is refused rather than worked around.
    """


def receive(storage: MediaStorage, source: BinaryIO) -> Received:
    """Copy the upload to a temporary file outside the media root, hashing it in
    the same pass. Blocking; called in a worker thread.

    Outside the root on purpose: nothing `storage prune` walks may contain a
    file this upload has not yet earned the right to keep. The location comes
    from the platform (`TMPDIR` and its kin), so this checks rather than
    assumes — the readiness probe reports the same misconfiguration before any
    traffic arrives.
    """
    digest = hashlib.sha256()
    source.seek(0)
    handle, name = tempfile.mkstemp(prefix="semanticshelf-upload-")
    temporary = Path(name)
    if temporary.resolve().is_relative_to(storage.root):
        temporary.unlink(missing_ok=True)
        raise StagingLocationError(
            "the temporary directory lies inside the media root; "
            "set TMPDIR outside it, or move MEDIA_ROOT"
        )
    size = 0
    try:
        with open(handle, "wb") as sink:
            for chunk in _hashing_chunks(source, digest):
                sink.write(chunk)
                size += len(chunk)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return Received(path=temporary, sha256=digest.hexdigest(), size_bytes=size)


def publish_files(
    storage: MediaStorage, asset_id: UUID, received: Received, facts: images.ImageFacts
) -> None:
    """Both files into place, under the lock the caller holds.

    Each is copied to a staging name in the asset's own directory, flushed and
    renamed, so nothing is ever visible half-written under a served name. A
    failure removes whatever this upload has already put under the root.
    """
    staged: list[Path] = []
    try:
        thumbnail_bytes = images.thumbnail(received.path)
        staged.append(storage.stage(asset_id))
        storage.fill(staged[-1], [thumbnail_bytes])
        storage.publish(staged[-1], storage.thumbnail(asset_id))

        staged.append(storage.stage(asset_id))
        with received.path.open("rb") as source:
            storage.fill(staged[-1], iter(lambda: source.read(CHUNK_BYTES), b""))
        storage.publish(staged[-1], storage.original(asset_id, facts.file_ext))
    except BaseException:
        # Every path this call created, whether it was published or not: a
        # failure between the write and the rename would otherwise leave a
        # staging file that only this frame ever knew the name of.
        for path in staged:
            storage.discard(path)
        storage.remove_any(asset_id)
        raise


async def create_asset(
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    source: BinaryIO,
    original_filename: str | None,
    tags: Sequence[str],
    meta: Mapping[str, Any],
    asset_source: str = "upload",
) -> Asset:
    """An asset from an upload, or nothing at all."""
    asset_id = uuid.uuid4()
    repository = AssetRepository(session)
    received = await run_in_threadpool(receive, storage, source)
    try:
        facts = await run_in_threadpool(images.inspect, received.path, settings)
        try:
            async with session.begin():
                # From here until the commit this upload holds the shared media
                # lock, and everything it writes under the root is covered by it.
                await hold_media_shared(session)
                existing = await repository.get_by_sha256(received.sha256)
                if existing is not None:
                    raise DuplicateAssetError(existing.id)
                await run_in_threadpool(publish_files, storage, asset_id, received, facts)
                return await repository.add(
                    asset_id=asset_id,
                    sha256=received.sha256,
                    content_type=facts.content_type,
                    file_ext=facts.file_ext,
                    width=facts.width,
                    height=facts.height,
                    size_bytes=received.size_bytes,
                    source=asset_source,
                    original_filename=original_filename,
                    tags=tags,
                    meta=meta,
                )
        except BaseException as exc:
            await run_in_threadpool(storage.remove_any, asset_id)
            if isinstance(exc, IntegrityError):
                # A duplicate that slipped past the check above — only a
                # concurrent upload of the same bytes can cause it, and the
                # constraint is what decides. The transaction is already rolled
                # back, so this reads in a new one.
                won = await repository.get_by_sha256(received.sha256)
                if won is not None:
                    raise DuplicateAssetError(won.id) from exc
            raise
    finally:
        await run_in_threadpool(_discard_temporary, received.path)


def _discard_temporary(path: Path) -> None:
    """Blocking; called in a worker thread. Never raises."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - a temporary directory that fights back
        log.warning("temporary upload could not be removed", error=type(exc).__name__)


async def get_asset(session: AsyncSession, asset_id: UUID) -> Asset | None:
    """One asset, or nothing."""
    return await AssetRepository(session).get(asset_id)


async def list_assets(
    session: AsyncSession,
    *,
    tags_all: Sequence[str] = (),
    tags_any: Sequence[str] = (),
    source: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Asset], bool]:
    """A page of assets, newest first, and whether more exist after it."""
    return await AssetRepository(session).page(
        tags_all=tags_all, tags_any=tags_any, source=source, limit=limit, offset=offset
    )


async def update_asset(
    session: AsyncSession,
    asset_id: UUID,
    *,
    tags: Sequence[str] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> Asset | None:
    """Replace what an edit may change. `None` means "leave this alone"."""
    async with session.begin():
        return await AssetRepository(session).set_tags_and_meta(asset_id, tags=tags, meta=meta)


async def delete_asset(session: AsyncSession, storage: MediaStorage, asset_id: UUID) -> bool:
    """Remove an asset, everything derived from it, and then its files.

    The row goes first, in one transaction with its embeddings and jobs; the
    files follow after the commit. A file that will not go is logged and left
    to `storage prune`: the row is already gone, so failing the request would
    only answer 404 on the retry.
    """
    async with session.begin():
        repository = AssetRepository(session)
        asset = await repository.get(asset_id)
        if asset is None:
            return False
        await repository.delete(asset_id)

    await run_in_threadpool(_remove_files, storage, asset)
    return True


def _remove_files(storage: MediaStorage, asset: Asset) -> None:
    """Blocking; called in a worker thread. Never raises."""
    try:
        storage.remove(asset.id, asset.file_ext)
    except OSError as exc:
        log.warning(
            "stored file could not be removed",
            asset_id=str(asset.id),
            error=type(exc).__name__,
        )
