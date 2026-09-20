"""Every migration is reversible, proven on a database of its own.

Down to base and up again must land on exactly the schema we started from. The
fingerprint is read from the catalog rather than dumped with an external tool,
so the check needs nothing but the connection the suite already has.

For a migration that only creates and drops, the first symptom of a forgotten
`downgrade()` is the second upgrade failing outright; the fingerprint is what
catches the subtler kind, where both directions succeed and differ.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import Settings

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
THROWAWAY_DATABASE = "semanticshelf_roundtrip"
DOMAIN_TABLES = {"assets", "embeddings", "indexing_jobs"}

FINGERPRINT = sa.text("""
    SELECT 'column   ' || table_name || '.' || column_name
           || ' type=' || data_type
           || ' null=' || is_nullable
           || ' default=' || coalesce(column_default, '-')
      FROM information_schema.columns
     WHERE table_schema = 'public'
    UNION ALL
    SELECT 'constraint ' || conrelid::regclass::text || ' ' || conname
           || ' ' || pg_get_constraintdef(oid)
      FROM pg_constraint
     WHERE connamespace = 'public'::regnamespace
    UNION ALL
    SELECT 'index    ' || indexdef
      FROM pg_indexes
     WHERE schemaname = 'public'
     ORDER BY 1
""")


def alembic(url: URL, *arguments: str) -> None:
    """Alembic in a subprocess: its async environment calls `asyncio.run()`,
    which cannot nest inside the test's running loop."""
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        check=True,
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
    )


async def read_fingerprint(url: URL) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(FINGERPRINT)).scalars().all())
    finally:
        await engine.dispose()


async def read_table_names(url: URL) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return set(rows.scalars().all())
    finally:
        await engine.dispose()


@pytest.fixture
async def throwaway_database(db_settings: Settings) -> URL:
    configured = make_url(db_settings.database_url)
    admin_url = configured.set(database="postgres")
    target_url = configured.set(database=THROWAWAY_DATABASE)

    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            try:
                await connection.execute(
                    sa.text(f'DROP DATABASE IF EXISTS "{THROWAWAY_DATABASE}" WITH (FORCE)')
                )
                await connection.execute(sa.text(f'CREATE DATABASE "{THROWAWAY_DATABASE}"'))
            except ProgrammingError as exc:  # insufficient privilege, typically
                pytest.skip(f"cannot create a throwaway database: {type(exc).__name__}")
    finally:
        await engine.dispose()

    yield target_url

    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(
            sa.text(f'DROP DATABASE IF EXISTS "{THROWAWAY_DATABASE}" WITH (FORCE)')
        )
    await engine.dispose()


async def test_down_and_up_again_lands_on_the_same_schema(throwaway_database: URL) -> None:
    alembic(throwaway_database, "upgrade", "head")
    before = await read_fingerprint(throwaway_database)
    assert DOMAIN_TABLES <= await read_table_names(throwaway_database)

    alembic(throwaway_database, "downgrade", "base")
    emptied = await read_table_names(throwaway_database)
    assert not (DOMAIN_TABLES & emptied), f"downgrade left tables behind: {emptied}"

    alembic(throwaway_database, "upgrade", "head")
    after = await read_fingerprint(throwaway_database)

    assert after == before
