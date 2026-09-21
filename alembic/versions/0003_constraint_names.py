"""Rename the check constraints to the names the application declares.

Revision ID: 0003_constraint_names
Revises: 0002_asset_schema
Create Date: 2026-09-21

Revision 0002 passed names that already began with `ck_<table>_`, and the
metadata's naming convention (`ck_%(table_name)s_%(constraint_name)s`) wrapped
the pattern around them a second time, so every check constraint in the
database stutters while the application declares the short form. Nothing else
drifted: primary keys, foreign keys, unique constraints and indexes already
carry exactly the declared names.

The pairs are written out here rather than derived from `Base.metadata`: a
migration is a historical record, and a convention that changes later must not
silently rewrite what this revision did.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_constraint_names"
down_revision: str | None = "0002_asset_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: table, the name 0002 left in the database, the name the application declares.
RENAMES: tuple[tuple[str, str, str], ...] = (
    ("assets", "ck_assets_ck_assets_content_type", "ck_assets_content_type"),
    ("assets", "ck_assets_ck_assets_file_ext", "ck_assets_file_ext"),
    ("assets", "ck_assets_ck_assets_source", "ck_assets_source"),
    ("assets", "ck_assets_ck_assets_width_positive", "ck_assets_width_positive"),
    ("assets", "ck_assets_ck_assets_height_positive", "ck_assets_height_positive"),
    ("assets", "ck_assets_ck_assets_size_positive", "ck_assets_size_positive"),
    (
        "embeddings",
        "ck_embeddings_ck_embeddings_model_dimension",
        "ck_embeddings_model_dimension",
    ),
    (
        "indexing_jobs",
        "ck_indexing_jobs_ck_indexing_jobs_status",
        "ck_indexing_jobs_status",
    ),
    (
        "indexing_jobs",
        "ck_indexing_jobs_ck_indexing_jobs_attempts_not_negative",
        "ck_indexing_jobs_attempts_not_negative",
    ),
)


def rename(table: str, old: str, new: str) -> None:
    """A catalog update: no table is rewritten and no row is read.

    Unconditional on purpose. Every database came from 0002, so every old name
    is there; a rename that quietly did nothing would hide a schema nobody
    designed. The identifiers are constants of this file, never input.
    """
    op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    for table, old, new in RENAMES:
        rename(table, old, new)


def downgrade() -> None:
    for table, old, new in RENAMES:
        rename(table, new, old)
