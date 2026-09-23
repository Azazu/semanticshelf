"""Asset records."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NO_NARROWING, Asset, Narrowing
from app.models import Asset as AssetRow
from app.repositories.jobs import IndexingJobRepository
from app.repositories.narrowing import narrowing_clauses

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
        asset_id: UUID | None = None,
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
            # Supplied by the caller when the files are written before the row
            # (the upload path needs the identifier to build their names); the
            # column default covers every other caller.
            **({"id": asset_id} if asset_id is not None else {}),
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

    async def by_ids(self, asset_ids: Sequence[UUID]) -> dict[UUID, Asset]:
        """The named assets, by identifier, in one query.

        A mapping rather than a list: the caller has an order of its own — a
        ranking, usually — and looking each asset up one at a time would make a
        page of results a page of queries.
        """
        if not asset_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    sa.select(AssetRow).where(AssetRow.id.in_(list(asset_ids)))
                )
            )
            .scalars()
            .all()
        )
        return {row.id: to_domain(row) for row in rows}

    async def get_by_sha256(self, sha256: str) -> Asset | None:
        row = (
            await self._session.execute(sa.select(AssetRow).where(AssetRow.sha256 == sha256))
        ).scalar_one_or_none()
        return to_domain(row) if row is not None else None

    async def tag_counts(self, *, limit: int) -> list[tuple[str, int]]:
        """Every tag in use with the number of assets carrying it.

        One aggregate rather than a walk in Python: the tags live in an array
        column, so unnesting them is the store's job. Ordered by count, then by
        the tag itself, so that two tags used equally often keep one order.
        """
        tag = sa.func.unnest(AssetRow.tags).label("tag")
        counted = sa.select(tag, sa.func.count().label("assets")).group_by(tag).subquery()
        statement = (
            sa.select(counted.c.tag, counted.c.assets)
            .order_by(counted.c.assets.desc(), counted.c.tag)
            .limit(limit)
        )
        rows = await self._session.execute(statement)
        return [(row.tag, int(row.assets)) for row in rows]

    async def summary(self) -> tuple[int, int]:
        """How many assets are stored, and how many bytes their originals take.

        The bytes are the sizes the assets record, not a walk of the media root:
        the store knows what it stored, and a directory walk would answer a
        different question slowly.
        """
        row = (
            await self._session.execute(
                sa.select(
                    sa.func.count(AssetRow.id),
                    sa.func.coalesce(sa.func.sum(AssetRow.size_bytes), 0),
                )
            )
        ).one()
        return int(row[0]), int(row[1])

    async def stored_files(self) -> list[tuple[UUID, str]]:
        """Every asset with the format of its original: what should be on disk."""
        rows = await self._session.execute(sa.select(AssetRow.id, AssetRow.file_ext))
        return [(row.id, row.file_ext) for row in rows]

    async def existing_ids(self, ids: Sequence[UUID]) -> set[UUID]:
        """Which of these identifiers are stored. Empty input touches nothing."""
        if not ids:
            return set()
        rows = await self._session.execute(sa.select(AssetRow.id).where(AssetRow.id.in_(list(ids))))
        return {row.id for row in rows}

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
        narrowing = Narrowing(
            tags_all=tuple(tags_all), tags_any=tuple(tags_any), meta=dict(meta or {})
        )
        statement = sa.select(AssetRow).where(*narrowing_clauses(narrowing))
        return statement.order_by(AssetRow.created_at.desc(), AssetRow.id.desc()).limit(limit)

    def page_statement(
        self,
        *,
        narrowing: Narrowing = NO_NARROWING,
        source: str | None = None,
        index_status: tuple[str, str] | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> sa.Select[Any]:
        """One page of the listing, plus one row: the extra row is how the
        caller knows more exist without a count that would be stale anyway.

        The narrowing is the same object a search carries and means the same
        thing here (change 12, design decision 4); `source` and `index_status`
        are the listing's own, because neither is a question about a ranking.
        """
        statement = sa.select(AssetRow).where(*narrowing_clauses(narrowing))
        if source is not None:
            statement = statement.where(AssetRow.source == source)
        if index_status is not None:
            model, state = index_status
            # An asset with no work for that model at all does not match: the
            # subquery is null, and null is not equal to anything.
            statement = statement.where(
                IndexingJobRepository.newest_status_of(AssetRow.id, model) == state
            )
        return (
            statement.order_by(AssetRow.created_at.desc(), AssetRow.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )

    async def page(
        self,
        *,
        narrowing: Narrowing = NO_NARROWING,
        source: str | None = None,
        index_status: tuple[str, str] | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[list[Asset], bool]:
        """A page of assets, newest first, and whether more exist after it."""
        rows = (
            (
                await self._session.execute(
                    self.page_statement(
                        narrowing=narrowing,
                        source=source,
                        index_status=index_status,
                        limit=limit,
                        offset=offset,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [to_domain(row) for row in rows[:limit]], len(rows) > limit

    async def set_tags_and_meta(
        self,
        asset_id: UUID,
        *,
        tags: Sequence[str] | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> Asset | None:
        """Replace what an edit may change, leaving anything not given alone."""
        row = await self._session.get(AssetRow, asset_id)
        if row is None:
            return None
        if tags is not None:
            row.tags = list(tags)
        if meta is not None:
            row.meta = dict(meta)
        await self._session.flush()
        await self._session.refresh(row)
        return to_domain(row)

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
