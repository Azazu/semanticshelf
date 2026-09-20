"""The `indexing_jobs` table: extraction work queued per asset and model.

This change creates the table and reads it; claiming, leases, retries and the
`FOR UPDATE SKIP LOCKED` query belong to the background-indexing change, which
also decides whether a pair keeps one row or a history of attempts.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain import JOB_STATUSES
from app.models.asset import sql_value_list


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # When the job may next be claimed; the retry backoff moves it forward.
    available_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(f"status IN {sql_value_list(JOB_STATUSES)}", name="status"),
        sa.CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        # The claim query of the worker: due jobs in the order they became due.
        sa.Index("ix_jobs_claim", "status", "available_at"),
        # The index status of one asset: its latest job per model.
        sa.Index("ix_jobs_asset", "asset_id", "model", sa.text("created_at DESC")),
    )
