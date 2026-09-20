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

from app.domain import Embedding, NeighbourHit, dimension_of
from app.models import Embedding as EmbeddingRow

UNIQUE_CONSTRAINT = "uq_embeddings_asset_model"


class UnknownModelError(LookupError):
    """A model key the application does not declare."""


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

    def nearest_statement(
        self, *, model: str, vector: Sequence[float], limit: int
    ) -> sa.Select[Any]:
        """The statement `nearest()` runs. Exposed so a test can read its plan."""
        dimension = checked_dimension(model, vector)
        distance = sa.cast(EmbeddingRow.vector, Vector(dimension)).cosine_distance(list(vector))
        return (
            sa.select(EmbeddingRow.asset_id, distance.label("distance"))
            .where(EmbeddingRow.model == model)
            .order_by(distance)
            .limit(limit)
        )

    async def nearest(
        self, *, model: str, vector: Sequence[float], limit: int
    ) -> list[NeighbourHit]:
        """The closest assets under one model, nearest first."""
        rows = await self._session.execute(
            self.nearest_statement(model=model, vector=vector, limit=limit)
        )
        return [NeighbourHit(asset_id=row.asset_id, distance=float(row.distance)) for row in rows]
