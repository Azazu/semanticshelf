"""Fixtures for the tests that need a real pgvector database.

`DATABASE_URL` must point at a database migrated to head (`make migrate`);
CI does that before running the marked suite. Each test starts from an empty
store: truncating `assets` cascades to embeddings and jobs.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.core.settings import Settings
from app.db.engine import create_engine, create_session_factory
from app.domain import CLIP_VIT_L14
from tests.fake_models import fake_models

TABLES = "assets, embeddings, indexing_jobs"


@pytest.fixture(autouse=True)
def fake_model() -> Iterator[None]:
    """No integration test loads real weights — not even by accident.

    An upload drains the queue in the background, so any test that posts a
    picture reaches the model registry and would pull down a checkpoint. Every
    implemented key is replaced, not only the one a test names: both are
    enabled by default, so an upload queues work for both, and CI sets no
    `ENABLED_MODELS` at all. The real adapters have their own suite
    (`-m models`), which does not run here.
    """
    with fake_models():
        yield


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    """The environment's database, and one model.

    One model on purpose, whatever the environment says: most of this suite is
    about the queue, the store and the pages, and a second enabled model only
    doubles every job row it counts. What two models actually change — two
    units of work per upload, two rankings, an `index_status` with two keys —
    is asserted where it belongs, by tests that ask for both
    (`test_asset_upload.py`, `test_search_image.py`).

    Pinning it here also makes the suite say what it runs rather than inherit
    it: CI sets no `ENABLED_MODELS` at all, and the default is every model this
    build implements.
    """
    try:
        settings = Settings(log_json=True, log_level="warning")
    except ValidationError:
        pytest.skip("DATABASE_URL is not set: start the database and set it (see the how-to)")
    return settings.model_copy(update={"enabled_models": (CLIP_VIT_L14,)})


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
