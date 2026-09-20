"""Baseline: the pgvector extension.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Reversible while no column uses the vector type (the first schema change
    # that does must keep the extension in its own downgrade).
    op.execute("DROP EXTENSION IF EXISTS vector")
