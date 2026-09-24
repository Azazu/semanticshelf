"""The published measurement command, run against a store that is not empty.

`scripts/filter_benchmark.py` builds thousands of rows and drops them again. On
this machine one database serves development and this suite, so a version of it
that wrote to the service's own tables would erase whatever is in them — which
is not a hypothetical: it happened to this repository's demo corpus while change
12 was being measured. What is asserted here is the promise the script makes
instead: the corpus it builds lives in a schema of its own, and afterwards that
schema is gone and every row that was there before still is.
"""

import asyncio
import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, dimension_of

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "filter_benchmark.py"
TABLES = "assets, embeddings, indexing_jobs"


def benchmark() -> ModuleType:
    """The script, imported as a module — it is not a package."""
    spec = importlib.util.spec_from_file_location("filter_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def seed(session: AsyncSession) -> list[UUID]:
    """A small store of the kind a person would be sorry to lose: assets with
    vectors and work queued for them."""
    identifiers = [uuid4() for _ in range(3)]
    async with session.begin():
        for index, identifier in enumerate(identifiers):
            await session.execute(
                sa.text(
                    "INSERT INTO assets (id, sha256, content_type, file_ext, width, height,"
                    " size_bytes, source, tags, meta) VALUES (:id, :sha256, 'image/png', 'png',"
                    " 64, 64, 1024, 'upload', ARRAY['every_2'], '{}'::jsonb)"
                ),
                {"id": identifier, "sha256": f"{index:064d}"},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO embeddings (asset_id, model, vector) "
                    "VALUES (:asset_id, :model, CAST(:vector AS vector))"
                ),
                {
                    "asset_id": identifier,
                    "model": CLIP_VIT_L14,
                    "vector": str([0.0] * dimension_of(CLIP_VIT_L14)),
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO indexing_jobs (asset_id, model, status) "
                    "VALUES (:asset_id, :model, 'pending')"
                ),
                {"asset_id": identifier, "model": CLIP_VIT_L14},
            )
    return identifiers


async def rows_of(session: AsyncSession, table: str) -> list[UUID]:
    async with session.begin():
        found = await session.execute(sa.text(f"SELECT id FROM public.{table} ORDER BY id"))
        return [identifier for (identifier,) in found]


async def test_the_published_command_leaves_a_populated_store_untouched(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command exactly as `docs/how-to/benchmarks.md` prints it, with its
    default arguments, against a store that holds rows."""
    module = benchmark()
    await seed(session)
    before = {table: await rows_of(session, table) for table in ("assets", "embeddings")}
    assert before["assets"], "the fixture is the point of this test"

    # In a thread of its own: the script owns an event loop, and this test is
    # already running in one.
    assert await asyncio.to_thread(module.main, []) == 0

    after = {table: await rows_of(session, table) for table in ("assets", "embeddings")}
    assert after == before, "every row that was there is still there"
    assert "| matches |" in capsys.readouterr().out, "and it printed its table"


async def test_the_schema_it_built_in_is_gone(session: AsyncSession) -> None:
    module = benchmark()
    await seed(session)

    await asyncio.to_thread(module.main, ["--assets", "50"])

    async with session.begin():
        left = await session.execute(
            sa.text("SELECT to_regnamespace(:schema)"), {"schema": module.DEFAULT_SCHEMA}
        )
    assert left.scalar_one() is None, "the schema it created is dropped, whatever happened"


async def test_it_refuses_a_schema_name_it_would_have_to_quote(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """The name is interpolated into DDL, so it is checked rather than trusted
    — including against the one name that would make it write to the service's
    own tables."""
    module = benchmark()
    await seed(session)

    for refused in ("public", 'x"; DROP SCHEMA public CASCADE; --', "Filter_Benchmark"):
        with pytest.raises(SystemExit) as raised:
            module.main(["--schema", refused])
        assert raised.value.code == 2, refused

    assert await rows_of(session, "assets"), "and nothing was touched"
