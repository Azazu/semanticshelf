"""The names in the database are the names the application declares.

A constraint name is an interface: migrations drop and alter constraints by
name, and a database error carries it. Nothing in Alembic compares check
constraints, so a schema whose names drifted from the metadata stays silent
until a later migration fails against it — which is exactly what happened
between revisions 0002 and 0003.

The comparison is by set, per table, so an extra constraint fails as loudly as
a missing one.
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

import app.models  # noqa: F401  — importing registers every table on the metadata
from app.db.base import Base

pytestmark = pytest.mark.integration

#: Primary keys, unique constraints, foreign keys and check constraints: the
#: four kinds the application declares. Indexes are not constraints and live in
#: `pg_index`; the vector indexes are covered by the storage tests.
DECLARED_KINDS = ("p", "u", "f", "c")

# `contype` is PostgreSQL's one-byte "char", which the async driver refuses to
# bind from a Python string, so the kinds are rendered into the statement. They
# are the constant above, never input.
CATALOG_NAMES = sa.text(
    "SELECT conrelid::regclass::text AS table_name, conname "
    "FROM pg_constraint "
    "WHERE connamespace = 'public'::regnamespace "
    "AND contype::text IN (" + ", ".join(f"'{kind}'" for kind in DECLARED_KINDS) + ")"
)


def declared_names() -> dict[str, set[str]]:
    return {
        table.name: {str(constraint.name) for constraint in table.constraints}
        for table in Base.metadata.sorted_tables
    }


async def catalog_names(engine: AsyncEngine, tables: set[str]) -> dict[str, set[str]]:
    async with engine.connect() as connection:
        rows = await connection.execute(CATALOG_NAMES)
        found: dict[str, set[str]] = {table: set() for table in tables}
        for table_name, name in rows:
            if table_name in found:
                found[table_name].add(name)
    return found


async def test_every_constraint_carries_the_name_the_application_declares(
    engine: AsyncEngine,
) -> None:
    declared = declared_names()
    found = await catalog_names(engine, set(declared))

    assert found == declared, {
        table: {
            "in the database only": sorted(found[table] - declared[table]),
            "declared only": sorted(declared[table] - found[table]),
        }
        for table in declared
        if found[table] != declared[table]
    }


async def test_the_application_owns_at_least_the_tables_it_declares(
    engine: AsyncEngine,
) -> None:
    # Without this, the comparison above would pass on an empty schema: a
    # table that does not exist contributes no rows and no names.
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        present = {name for (name,) in rows}

    assert {table.name for table in Base.metadata.sorted_tables} <= present
