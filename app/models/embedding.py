"""The `embeddings` table: one vector per asset and model.

The column is an untyped `vector`, so one table holds every model. What keeps
the models apart is the constraint below and one index per key over the
dimension-cast expression; ADR-001 records why this layout was chosen and what
the cast costs the reader who forgets it.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain import EMBEDDING_MODELS, vector_index_name

HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64


def dimension_check() -> str:
    """One CHECK carrying both the model allowlist and each model's dimension.

    An unknown key satisfies no branch, so the same constraint that fixes the
    width also rejects a model the schema has never heard of.
    """
    return " OR ".join(
        f"(model = '{key}' AND vector_dims(vector) = {dimension})"
        for key, dimension in EMBEDDING_MODELS.items()
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    # Set when the vector was written; a replacement moves it forward.
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        # The identity of an embedding, and the upsert target of re-extraction.
        # Its index also serves lookups by asset alone.
        sa.UniqueConstraint("asset_id", "model", name="uq_embeddings_asset_model"),
        sa.CheckConstraint(dimension_check(), name="model_dimension"),
        # Declared so a later autogenerate does not propose dropping what the
        # migration created; Alembic does not compare expression indexes, and
        # the migration remains the only place that builds them.
        *(
            sa.Index(
                vector_index_name(key),
                sa.text(f"(vector::vector({dimension})) vector_cosine_ops"),
                postgresql_using="hnsw",
                postgresql_where=sa.text(f"model = '{key}'"),
            )
            for key, dimension in EMBEDDING_MODELS.items()
        ),
    )
