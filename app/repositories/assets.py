"""Asset records."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Asset
from app.models import Asset as AssetRow

DEFAULT_LIMIT = 50


def to_domain(row: AssetRow) -> Asset:
    return Asset(
        id=row.id,
        created_at=row.created_at,
        sha256=row.sha256,
        content_type=row.content_type,
        file_ext=row.file_ext,
        width=row.width,
        height=row.height,
        size_bytes=row.size_bytes,
        original_filename=row.original_filename,
        source=row.source,
        tags=tuple(row.tags),
        meta=dict(row.meta),
    )


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        sha256: str,
        content_type: str,
        file_ext: str,
        width: int,
        height: int,
        size_bytes: int,
        source: str,
        original_filename: str | None = None,
        tags: Sequence[str] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> Asset:
        """Insert one asset. The store rejects a duplicate content hash and any
        value outside the domains it enforces."""
        row = AssetRow(
            sha256=sha256,
            content_type=content_type,
            file_ext=file_ext,
            width=width,
            height=height,
            size_bytes=size_bytes,
            source=source,
            original_filename=original_filename,
            tags=list(tags),
            meta=dict(meta or {}),
        )
        self._session.add(row)
        await self._session.flush()
        # The id and the timestamp are server defaults.
        await self._session.refresh(row)
        return to_domain(row)

    async def get(self, asset_id: UUID) -> Asset | None:
        row = await self._session.get(AssetRow, asset_id)
        return to_domain(row) if row is not None else None

    async def get_by_sha256(self, sha256: str) -> Asset | None:
        row = (
            await self._session.execute(sa.select(AssetRow).where(AssetRow.sha256 == sha256))
        ).scalar_one_or_none()
        return to_domain(row) if row is not None else None

    async def delete(self, asset_id: UUID) -> bool:
        """Remove an asset with its embeddings and jobs. True when a row went."""
        statement = sa.delete(AssetRow).where(AssetRow.id == asset_id).returning(AssetRow.id)
        removed = (await self._session.execute(statement)).scalar_one_or_none()
        return removed is not None

    def find_statement(
        self,
        *,
        tags_all: Sequence[str] = (),
        tags_any: Sequence[str] = (),
        meta: Mapping[str, Any] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> sa.Select[Any]:
        """The statement `find()` runs. Exposed so a test can read its plan."""
        statement = sa.select(AssetRow)
        if tags_all:
            statement = statement.where(AssetRow.tags.contains(list(tags_all)))
        if tags_any:
            statement = statement.where(AssetRow.tags.overlap(list(tags_any)))
        if meta:
            statement = statement.where(AssetRow.meta.contains(dict(meta)))
        return statement.order_by(AssetRow.created_at.desc(), AssetRow.id.desc()).limit(limit)

    async def find(
        self,
        *,
        tags_all: Sequence[str] = (),
        tags_any: Sequence[str] = (),
        meta: Mapping[str, Any] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Asset]:
        """Assets matching every containment filter given, newest first.

        `tags_all` and `meta` are containment (`@>`), `tags_any` is overlap
        (`&&`); each is served by one of the GIN indexes on the table.
        """
        statement = self.find_statement(
            tags_all=tags_all, tags_any=tags_any, meta=meta, limit=limit
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [to_domain(row) for row in rows]
