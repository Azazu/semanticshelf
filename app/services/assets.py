"""The asset use cases: create one from an upload, read it, list, edit, remove.

The order of the write is the whole point of `create`, and it is the order the
specification fixes: both files in place, then the row. A failure after the
files removes them; a crash between them leaves files with no row, which is the
one residue the design permits and which `storage prune` finds.

Every blocking step — reading the upload, decoding, encoding the thumbnail,
writing to disk — runs in a worker thread. This is Starlette's shared pool, not
the inference pool of change 4: that one is sized for model work, and a burst
of uploads must not stall embedding.
"""

import hashlib
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

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


class DuplicateAssetError(Exception):
    """Those bytes are already stored, under the asset this names."""

    def __init__(self, existing_asset_id: UUID) -> None:
        super().__init__(f"asset already exists: {existing_asset_id}")
        self.existing_asset_id = existing_asset_id


@dataclass(frozen=True, slots=True)
class StagedUpload:
    path: Path
    sha256: str
    size_bytes: int


def _hashing_chunks(source: BinaryIO, digest: "hashlib._Hash") -> Iterator[bytes]:
    while chunk := source.read(CHUNK_BYTES):
        digest.update(chunk)
        yield chunk


def stage_upload(storage: MediaStorage, asset_id: UUID, source: BinaryIO) -> StagedUpload:
    """Copy the upload into the asset's directory under a temporary name,
    hashing it in the same pass. Blocking; called in a worker thread."""
    digest = hashlib.sha256()
    source.seek(0)
    staged = storage.stage(asset_id)
    size = storage.fill(staged, _hashing_chunks(source, digest))
    return StagedUpload(path=staged, sha256=digest.hexdigest(), size_bytes=size)


def publish_files(
    storage: MediaStorage, asset_id: UUID, staged: StagedUpload, facts: images.ImageFacts
) -> None:
    """Both files into place: the thumbnail first, then the original.

    Blocking; called in a worker thread. Either may fail, and the caller
    removes whatever exists — an asset is both files and a row, or nothing.
    """
    thumbnail_bytes = images.thumbnail(staged.path)
    staged_thumbnail = storage.stage(asset_id)
    storage.fill(staged_thumbnail, [thumbnail_bytes])
    storage.publish(staged_thumbnail, storage.thumbnail(asset_id))
    storage.publish(staged.path, storage.original(asset_id, facts.file_ext))


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
    """An asset from an upload, or nothing at all.

    The transaction opens before the first byte is written and holds the shared
    media lock for the whole of it, so `storage prune` cannot run while these
    files exist without their row (`app/db/locks.py`).
    """
    asset_id = uuid.uuid4()
    repository = AssetRepository(session)
    staged: StagedUpload | None = None
    try:
        # Staging and inspection happen before the transaction. A staged file
        # is not the asset's file: losing one costs this upload and nothing
        # else, while losing a published file would break the invariant, which
        # is why the lock below covers publication and the row rather than the
        # whole call. It also keeps every refusal — format, size, dimensions —
        # off the database entirely.
        staged = await run_in_threadpool(stage_upload, storage, asset_id, source)
        facts = await run_in_threadpool(images.inspect, staged.path, settings)

        async with session.begin():
            await hold_media_shared(session)
            existing = await repository.get_by_sha256(staged.sha256)
            if existing is not None:
                raise DuplicateAssetError(existing.id)
            await run_in_threadpool(publish_files, storage, asset_id, staged, facts)
            return await repository.add(
                asset_id=asset_id,
                sha256=staged.sha256,
                content_type=facts.content_type,
                file_ext=facts.file_ext,
                width=facts.width,
                height=facts.height,
                size_bytes=staged.size_bytes,
                source=asset_source,
                original_filename=original_filename,
                tags=tags,
                meta=meta,
            )
    except BaseException as exc:
        # One cleanup path for every failure, including the duplicate found
        # before any file was published: what this upload wrote, it takes back.
        await run_in_threadpool(_clean_up, storage, asset_id, staged)
        if isinstance(exc, IntegrityError) and staged is not None:
            # A duplicate that slipped past the check above — only a concurrent
            # upload of the same bytes can cause it, and the constraint is what
            # decides. The transaction is already rolled back, so this reads in
            # a new one.
            won = await repository.get_by_sha256(staged.sha256)
            if won is not None:
                raise DuplicateAssetError(won.id) from exc
        raise


def _clean_up(storage: MediaStorage, asset_id: UUID, staged: StagedUpload | None) -> None:
    """Blocking; called in a worker thread."""
    if staged is not None:
        storage.discard(staged.path)
    storage.remove_any(asset_id)
