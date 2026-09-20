"""Assets, embeddings and indexing jobs.

Revision ID: 0002_asset_schema
Revises: 0001_baseline
Create Date: 2026-09-20

The model keys and their dimensions are written out here rather than imported
from the application: a migration is a historical record, and importing a
constant that later changes would silently rewrite what this revision means. A
unit test holds this copy and `app.domain.EMBEDDING_MODELS` together.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_asset_schema"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy; see the module docstring.
MODEL_DIMENSIONS: dict[str, int] = {
    "clip-vit-l14": 768,
    "dinov2-large": 1024,
}
CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
FILE_EXTENSIONS = ("jpg", "png", "webp")
ASSET_SOURCES = ("upload", "folder")
JOB_STATUSES = ("pending", "running", "done", "failed")

# pgvector's defaults, stated where they are used so a change is a reviewed
# diff. Tuning them needs recall and latency numbers: ADR-002.
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64


def values(items: Sequence[str]) -> str:
    return "(" + ", ".join(f"'{item}'" for item in items) + ")"


def dimension_check() -> str:
    """One CHECK carrying both the model allowlist and each model's dimension."""
    return " OR ".join(
        f"(model = '{key}' AND vector_dims(vector) = {dimension})"
        for key, dimension in MODEL_DIMENSIONS.items()
    )


def vector_index_name(model: str) -> str:
    return "ix_embeddings_" + model.replace("-", "_")


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("file_ext", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("sha256", name="uq_assets_sha256"),
        sa.CheckConstraint(
            f"content_type IN {values(CONTENT_TYPES)}", name="ck_assets_content_type"
        ),
        sa.CheckConstraint(f"file_ext IN {values(FILE_EXTENSIONS)}", name="ck_assets_file_ext"),
        sa.CheckConstraint(f"source IN {values(ASSET_SOURCES)}", name="ck_assets_source"),
        sa.CheckConstraint("width > 0", name="ck_assets_width_positive"),
        sa.CheckConstraint("height > 0", name="ck_assets_height_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_assets_size_positive"),
    )
    op.create_index("ix_assets_created", "assets", [sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_assets_tags", "assets", ["tags"], postgresql_using="gin")
    op.create_index(
        "ix_assets_meta",
        "assets",
        ["meta"],
        postgresql_using="gin",
        postgresql_ops={"meta": "jsonb_path_ops"},
    )

    op.create_table(
        "embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        # Untyped on purpose: one table holds every model, and the dimension is
        # fixed per model by the CHECK below and by the per-model index (ADR-001).
        sa.Column("vector", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embeddings"),
        sa.UniqueConstraint("asset_id", "model", name="uq_embeddings_asset_model"),
        sa.CheckConstraint(dimension_check(), name="ck_embeddings_model_dimension"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name="fk_embeddings_asset_id_assets",
            ondelete="CASCADE",
        ),
    )
    for key, dimension in MODEL_DIMENSIONS.items():
        op.execute(
            f"CREATE INDEX {vector_index_name(key)} ON embeddings "
            f"USING hnsw ((vector::vector({dimension})) vector_cosine_ops) "
            f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION}) "
            f"WHERE model = '{key}'"
        )

    op.create_table(
        "indexing_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "available_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_indexing_jobs"),
        sa.CheckConstraint(f"status IN {values(JOB_STATUSES)}", name="ck_indexing_jobs_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_indexing_jobs_attempts_not_negative"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name="fk_indexing_jobs_asset_id_assets",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_jobs_claim", "indexing_jobs", ["status", "available_at"])
    op.create_index(
        "ix_jobs_asset", "indexing_jobs", ["asset_id", "model", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints; the children go first
    # because both reference assets.
    op.drop_table("indexing_jobs")
    op.drop_table("embeddings")
    op.drop_table("assets")
