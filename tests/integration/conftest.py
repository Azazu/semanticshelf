"""Fixtures for the tests that need a real pgvector database.

`DATABASE_URL` must point at a database migrated to head (`make migrate`);
CI does that before running the marked suite. Each test starts from an empty
store: truncating `assets` cascades to embeddings and jobs.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.core.settings import Settings
from app.db.engine import create_engine, create_session_factory

TABLES = "assets, embeddings, indexing_jobs"


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    try:
        return Settings(log_json=True, log_level="warning")
    except ValidationError:
        pytest.skip("DATABASE_URL is not set: start the database and set it (see the how-to)")


@pytest.fixture
async def engine(db_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(db_settings)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
        await session.rollback()


class Explain(Executable, ClauseElement):
    """`EXPLAIN <statement>` with the statement's own parameters.

    Building the command as a string would not do: a parameter followed by a
    cast (`:p::JSONB`) is not recognised by `text()`, and a JSONB or a vector
    value has no literal renderer. Compiling the statement inside this element
    keeps the plan honest — it is the plan of exactly what the repository runs.
    """

    inherit_cache = False

    def __init__(self, statement: ClauseElement) -> None:
        self.statement = statement


@compiles(Explain, "postgresql")
def compile_explain(element: Explain, compiler: Any, **kw: Any) -> str:
    return "EXPLAIN " + compiler.process(element.statement, **kw)


async def explain(session: AsyncSession, statement: ClauseElement, *, no_seqscan: bool) -> str:
    """The plan of a statement, as one string.

    With `no_seqscan` the planner is told sequential scans are expensive, which
    is how a fixture of a few rows can still show which index *can* serve a
    query. A query no index can serve stays a sequential scan regardless.
    """
    if no_seqscan:
        await session.execute(sa.text("SET LOCAL enable_seqscan = off"))
    rows = (await session.execute(Explain(statement))).scalars().all()
    return "\n".join(rows)
