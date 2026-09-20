"""Indexing jobs.

Only what this change needs: put work on the queue and read an asset's jobs.
Claiming, leases, retries and the status transitions arrive with the background
indexing change, which owns that protocol.
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import EMBEDDING_MODELS, IndexingJob
from app.models import IndexingJob as IndexingJobRow
from app.repositories.embeddings import UnknownModelError


def to_domain(row: IndexingJobRow) -> IndexingJob:
    return IndexingJob(
        id=row.id,
        asset_id=row.asset_id,
        model=row.model,
        status=row.status,
        attempts=row.attempts,
        available_at=row.available_at,
        lease_expires_at=row.lease_expires_at,
        last_error=row.last_error,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class IndexingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, asset_id: UUID, model: str) -> IndexingJob:
        """Queue extraction of one model's vector for one asset."""
        if model not in EMBEDDING_MODELS:
            raise UnknownModelError(f"unknown embedding model: {model!r}")
        row = IndexingJobRow(asset_id=asset_id, model=model)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return to_domain(row)

    async def add_for_models(
        self, *, asset_id: UUID, models: Sequence[str] | None = None
    ) -> list[IndexingJob]:
        """Queue every enabled model for one asset, in registry order."""
        keys = list(models) if models is not None else list(EMBEDDING_MODELS)
        return [await self.add(asset_id=asset_id, model=key) for key in keys]

    async def list_for_asset(self, asset_id: UUID) -> list[IndexingJob]:
        """An asset's jobs, newest first per model."""
        statement = (
            sa.select(IndexingJobRow)
            .where(IndexingJobRow.asset_id == asset_id)
            .order_by(
                IndexingJobRow.model,
                IndexingJobRow.created_at.desc(),
                IndexingJobRow.id.desc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [to_domain(row) for row in rows]
