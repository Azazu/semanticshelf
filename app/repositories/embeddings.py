"""Embeddings, and the only query in the service that reaches a vector index.

The column is untyped, so every vector query must cast it to the model's
dimension: without the cast the expression no longer matches the index and the
plan degrades to a sequential scan (ADR-001). That cast lives here and nowhere
else, and an integration test reads the plan to keep it that way.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Embedding, Narrowing, NeighbourHit, UnknownModelError, dimension_of
from app.models import Asset as AssetRow
from app.models import Embedding as EmbeddingRow
from app.repositories.narrowing import narrowing_clauses

UNIQUE_CONSTRAINT = "uq_embeddings_asset_model"

__all__ = ["UnknownModelError", "VectorDimensionError", "checked_dimension", "EmbeddingRepository"]


class VectorDimensionError(ValueError):
    """A vector whose width is not the one declared for its model."""


def checked_dimension(model: str, vector: Sequence[float]) -> int:
    """The model's dimension, after checking the vector against it.

    The database enforces the same rule; this check exists to fail in the
    caller's terms rather than as a constraint violation, and to keep a wrong
    vector out of the wire.
    """
    try:
        dimension = dimension_of(model)
    except KeyError as exc:
        raise UnknownModelError(f"unknown embedding model: {model!r}") from exc
    if len(vector) != dimension:
        raise VectorDimensionError(
            f"model {model!r} takes {dimension} dimensions, got {len(vector)}"
        )
    return dimension


class EmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, *, asset_id: UUID, model: str, vector: Sequence[float]) -> Embedding:
        """Write the vector for one asset and model, replacing what was there.

        Extraction is delivered at least once, so a repeat must leave one row.
        """
        checked_dimension(model, vector)
        values = list(vector)
        insert = pg_insert(EmbeddingRow).values(asset_id=asset_id, model=model, vector=values)
        statement = insert.on_conflict_do_update(
            constraint=UNIQUE_CONSTRAINT,
            set_={"vector": insert.excluded.vector, "created_at": sa.func.now()},
        ).returning(
            EmbeddingRow.id,
            EmbeddingRow.asset_id,
            EmbeddingRow.model,
            EmbeddingRow.vector,
            EmbeddingRow.created_at,
        )
        row = (await self._session.execute(statement)).one()
        return Embedding(
            id=row.id,
            asset_id=row.asset_id,
            model=row.model,
            vector=tuple(row.vector),
            created_at=row.created_at,
        )

    async def get(self, *, asset_id: UUID, model: str) -> Embedding | None:
        statement = sa.select(EmbeddingRow).where(
            EmbeddingRow.asset_id == asset_id, EmbeddingRow.model == model
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        return Embedding(
            id=row.id,
            asset_id=row.asset_id,
            model=row.model,
            vector=tuple(row.vector),
            created_at=row.created_at,
        )

    async def reachable(
        self,
        *,
        model: str,
        narrowing: Narrowing,
        at_most: int,
        exclude_asset_id: UUID | None = None,
    ) -> int:
        """How many assets the narrowing matches that have this model's vector,
        counted no further than `at_most`.

        The question asked when a narrowed scan returned fewer candidates than
        the answer needed: more matches than the scan reached means the scan
        stopped at its own budget rather than at the end of the ranking (change
        12, design decision 3). It carries the search's model, the search's
        narrowing and the asset an asset's own search excludes, because a count
        of assets alone would count assets this model has never seen, and the
        asking asset itself.

        The bound is what keeps it from being a count of the corpus.
        """
        matching = (
            sa.select(sa.literal(1))
            .select_from(EmbeddingRow)
            .join(AssetRow, AssetRow.id == EmbeddingRow.asset_id)
            .where(EmbeddingRow.model == model, *narrowing_clauses(narrowing))
        )
        if exclude_asset_id is not None:
            matching = matching.where(AssetRow.id != exclude_asset_id)
        bounded = matching.limit(at_most).subquery("reachable")
        found = await self._session.execute(sa.select(sa.func.count()).select_from(bounded))
        return int(found.scalar_one())

    def nearest_statement(
        self,
        *,
        model: str,
        vector: Sequence[float],
        limit: int,
        exclude_asset_id: UUID | None = None,
        narrowing: Narrowing | None = None,
    ) -> sa.Select[Any]:
        """The statement `nearest()` runs. Exposed so a test can read its plan.

        Two selects, and each layer exists for a reason.

        **The window** is what the index answers: the cast ADR-001 requires, the
        model predicate, the narrowing when there is one, and `ORDER BY
        distance` — **one** key, because an HNSW ordering takes exactly one and a
        second turns the index scan into a sort over a bitmap scan. It takes one
        row more than the caller asked for when an asset excludes itself, since
        the next layer removes that row.

        **The narrowing lives here, inside the scan**, joined to `assets`.
        Beside the scan rather than after it: with `hnsw.iterative_scan` off, a
        predicate applied to the scan's *result* is post-filtering, and a
        narrowing that matches one asset in three hundred then answers an empty
        page while the matches sit just past the candidate window — measured, in
        change 12's design. The service turns the iterative scan on for exactly
        these queries.

        **The page** is cut from that window *after* the order is total:
        `ORDER BY distance, asset_id`, then the limit. Cutting first and
        ordering afterwards — which is what this did until change 8's Gate 2 —
        lets the index choose arbitrarily among equally distant rows, so a tie
        that straddles a page boundary can swap, duplicate or lose assets
        between two requests. Ordering the window first makes the identifier the
        tie-break for everything down to the end of the page, so a page whose
        edge does not cut a group of equal distances holds the same items every
        time. Which equally distant rows enter the window at all is still the
        index's choice: a page whose edge does cut such a group carries
        whichever of that group the window held, and nothing here promises
        which.

        **An excluded asset** — the one whose neighbours are being asked for —
        is dropped in the page select, above the window. Above rather than
        inside it, because a predicate inside the window is a filter on an
        approximate index scan, which is the narrowing's business and needs the
        iterative scan the narrowing turns on.

        **The offset and the threshold are not here.** They are applied over
        what this returns, because the number of rows *before* them is what says
        whether the scan was cut short by its own budget or by the end of the
        ranking (change 12, design decision 3) — and an empty page after an
        offset cannot say that. What they do is unchanged: the offset skips, and
        the threshold removes results the page already holds without reaching
        further down for replacements.
        """
        dimension = checked_dimension(model, vector)
        distance = sa.cast(EmbeddingRow.vector, Vector(dimension)).cosine_distance(list(vector))
        window = sa.select(EmbeddingRow.asset_id, distance.label("distance")).where(
            EmbeddingRow.model == model
        )
        if narrowing:
            window = window.join(AssetRow, AssetRow.id == EmbeddingRow.asset_id).where(
                *narrowing_clauses(narrowing)
            )
        reach = (
            window.order_by(distance)
            .limit(limit + (1 if exclude_asset_id is not None else 0))
            .subquery("window")
        )

        rows = sa.select(reach.c.asset_id, reach.c.distance)
        if exclude_asset_id is not None:
            rows = rows.where(reach.c.asset_id != exclude_asset_id)
        return rows.order_by(reach.c.distance, reach.c.asset_id).limit(limit)

    async def nearest(
        self,
        *,
        model: str,
        vector: Sequence[float],
        limit: int,
        exclude_asset_id: UUID | None = None,
        narrowing: Narrowing | None = None,
    ) -> list[NeighbourHit]:
        """The closest assets under one model, nearest first, up to `limit`.

        These are candidates, not a page: the caller applies the offset and the
        threshold over them, and how many came back is what tells a scan that
        ran out of budget from one that reached the end of the ranking.
        """
        rows = await self._session.execute(
            self.nearest_statement(
                model=model,
                vector=vector,
                limit=limit,
                exclude_asset_id=exclude_asset_id,
                narrowing=narrowing,
            )
        )
        return [NeighbourHit(asset_id=row.asset_id, distance=float(row.distance)) for row in rows]
