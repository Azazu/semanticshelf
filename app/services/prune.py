"""Reconciling the media root with the store.

Two kinds of disagreement exist, and both come from the write order an asset
needs: files are published before the row, so a crash between them leaves files
nobody owns; and a file can be lost or unlinked under the service, leaving a
row whose bytes are gone.

Neither is repaired while an upload is in flight. An upload between its
publication and its row looks exactly like the first case, and it may be
delayed without bound, so this takes the exclusive media lock that every upload
holds in shared form and simply does not run when it cannot have it
(`app/db/locks.py`). The grace period below is a second, weaker line for the
case the lock cannot cover — a run pointed at a store some other service writes.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.locks import try_take_media_exclusive
from app.repositories.assets import AssetRepository
from app.repositories.jobs import IndexingJobRepository
from app.storage import MediaStorage, asset_id_of

#: What an asset whose file is gone is told to its indexing work.
FILE_MISSING = "file-missing"


@dataclass(frozen=True, slots=True)
class PruneReport:
    """What was found, and what was done about it."""

    ran: bool
    orphan_files: tuple[Path, ...] = ()
    assets_missing_files: tuple[UUID, ...] = ()
    ignored_young: int = 0
    applied: bool = False
    removed_files: tuple[Path, ...] = ()
    failed_jobs: int = 0

    @property
    def clean(self) -> bool:
        return not self.orphan_files and not self.assets_missing_files


async def prune(
    session: AsyncSession,
    storage: MediaStorage,
    *,
    min_age_seconds: int,
    apply: bool,
    now: float | None = None,
) -> PruneReport:
    """Report — and, when asked, repair — what the store and the disk disagree on."""
    async with session.begin():
        if not await try_take_media_exclusive(session):
            return PruneReport(ran=False)

        cutoff = (now if now is not None else time.time()) - min_age_seconds
        found = await run_in_threadpool(list, storage.walk())
        candidates = [path for path, modified in found if modified <= cutoff]
        ignored_young = len(found) - len(candidates)

        assets = AssetRepository(session)
        owners = {path: asset_id_of(path) for path in candidates}
        known = await assets.existing_ids([owner for owner in owners.values() if owner is not None])
        orphans = tuple(
            path for path, owner in owners.items() if owner is None or owner not in known
        )

        stored = await assets.stored_files()
        present = await run_in_threadpool(_assets_with_both_files, storage, stored)
        missing = tuple(asset_id for asset_id, _ in stored if asset_id not in present)

        if not apply:
            return PruneReport(
                ran=True,
                orphan_files=orphans,
                assets_missing_files=missing,
                ignored_young=ignored_young,
            )

        for path in orphans:
            await run_in_threadpool(storage.discard, path)
        jobs = IndexingJobRepository(session)
        failed = 0
        for asset_id in missing:
            failed += await jobs.fail_for_asset(asset_id, FILE_MISSING)

        return PruneReport(
            ran=True,
            orphan_files=orphans,
            assets_missing_files=missing,
            ignored_young=ignored_young,
            applied=True,
            removed_files=orphans,
            failed_jobs=failed,
        )


def _assets_with_both_files(storage: MediaStorage, stored: Sequence[tuple[UUID, str]]) -> set[UUID]:
    """Which assets still have both of their files. Blocking; one thread hop for
    the whole store rather than one per asset."""
    return {
        asset_id
        for asset_id, file_ext in stored
        if storage.original(asset_id, file_ext).exists() and storage.thumbnail(asset_id).exists()
    }


def describe(report: PruneReport) -> list[str]:
    """The report as lines for a terminal."""
    if not report.ran:
        return ["an upload is in flight; nothing was examined or changed"]
    lines = [
        f"orphan files: {len(report.orphan_files)}",
        f"assets with missing files: {len(report.assets_missing_files)}",
        f"ignored as too young: {report.ignored_young}",
    ]
    lines.extend(f"  orphan  {path.name}" for path in report.orphan_files)
    lines.extend(f"  missing {asset_id}" for asset_id in report.assets_missing_files)
    if report.applied:
        lines.append(
            f"removed {len(report.removed_files)} file(s); "
            f"marked {report.failed_jobs} job(s) failed with {FILE_MISSING!r}"
        )
    else:
        lines.append("nothing was changed; pass --apply to act")
    return lines
