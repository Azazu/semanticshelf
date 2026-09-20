"""The `assets` table: one row per stored image."""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain import ASSET_SOURCES, CONTENT_TYPES, FILE_EXTENSIONS


def sql_value_list(values: tuple[str, ...]) -> str:
    """`('a', 'b')` for a CHECK constraint. The values are repository constants."""
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # The content hash is the identity of the bytes: it carries deduplication.
    sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    content_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_ext: Mapped[str] = mapped_column(sa.Text, nullable=False)
    width: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    height: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    # Metadata only: the stored file is named after the id, never after this.
    original_filename: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    __table_args__ = (
        sa.UniqueConstraint("sha256", name="uq_assets_sha256"),
        sa.CheckConstraint(f"content_type IN {sql_value_list(CONTENT_TYPES)}", name="content_type"),
        sa.CheckConstraint(f"file_ext IN {sql_value_list(FILE_EXTENSIONS)}", name="file_ext"),
        sa.CheckConstraint(f"source IN {sql_value_list(ASSET_SOURCES)}", name="source"),
        sa.CheckConstraint("width > 0", name="width_positive"),
        sa.CheckConstraint("height > 0", name="height_positive"),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"),
        # Listing order: newest first, the id breaking ties.
        sa.Index("ix_assets_created", sa.text("created_at DESC"), sa.text("id DESC")),
        # Containment over tags and metadata, the two filter surfaces of search.
        sa.Index("ix_assets_tags", "tags", postgresql_using="gin"),
        sa.Index(
            "ix_assets_meta",
            "meta",
            postgresql_using="gin",
            postgresql_ops={"meta": "jsonb_path_ops"},
        ),
    )
