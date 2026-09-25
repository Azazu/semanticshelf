"""The guard both measurement commands stand on, against a real database.

`scripts/filter_benchmark.py` and `scripts/index_benchmark.py` each have their
own suite that runs the published command end to end. What is asserted here is
the module underneath them, directly and at its failure modes: a schema is
created rather than taken over, nothing is written until every unqualified name
resolves inside it, and the drop is of a schema this run made.

The one that is not hypothetical: an early version of the filter benchmark
truncated the service's own tables and erased this repository's demo corpus.
`guard()` is what stands between a published command and that.
"""

from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from tests.scripts import script_module

pytestmark = pytest.mark.integration

guard = script_module("bench_schema")

SCHEMA = "bench_schema_tests"
TABLES = ("assets", "embeddings")


@pytest.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as opened:
        yield opened
    async with engine.begin() as cleanup:
        await cleanup.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


async def test_a_schema_is_created_rather_than_taken_over(connection: AsyncConnection) -> None:
    await guard.own(connection, schema=SCHEMA)

    with pytest.raises(guard.SchemaInUse) as refused:
        await guard.own(connection, schema=SCHEMA)

    assert "already exists" in str(refused.value)
    assert "--schema" in str(refused.value), "and it says what to do instead"


async def test_what_it_copies_is_what_a_request_meets(connection: AsyncConnection) -> None:
    """`LIKE ... INCLUDING ALL`, so the indexes measured are the migration's."""
    await guard.own(connection, schema=SCHEMA)
    await guard.prepare(connection, schema=SCHEMA, tables=TABLES)

    copied = await connection.execute(
        sa.text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = :schema"
            " AND tablename = 'embeddings' AND indexdef LIKE '%hnsw%'"
        ),
        {"schema": SCHEMA},
    )
    definitions = [str(one) for (one,) in copied]
    assert len(definitions) == 2, "one partial HNSW index per model (ADR-001)"
    assert all("m='16', ef_construction='64'" in one or "m = 16" in one for one in definitions), (
        definitions
    )


async def test_nothing_is_written_while_a_name_resolves_to_the_service_s_own_table(
    connection: AsyncConnection,
) -> None:
    """The catastrophic case, made to happen on purpose.

    If the copy failed, or the search path did not take, then `assets` is the
    service's `assets` and the next statement of a benchmark would write
    thousands of rows into it — or truncate it. So there is no next statement:
    the guard resolves every unqualified name it is about to use and refuses.
    """
    await guard.own(connection, schema=SCHEMA)
    await connection.execute(sa.text("SET LOCAL search_path TO public"))

    with pytest.raises(SystemExit) as refused:
        await guard.guard(connection, schema=SCHEMA, tables=TABLES)

    message = str(refused.value)
    assert "refusing to run" in message
    assert "public.assets" in message, "it names what the name actually resolved to"


async def test_a_name_that_resolves_nowhere_is_refused_too(
    connection: AsyncConnection,
) -> None:
    """A schema that exists but holds no copy: `to_regclass` answers nothing,
    which is not the schema's own table either."""
    await guard.own(connection, schema=SCHEMA)
    await connection.execute(sa.text(f"SET LOCAL search_path TO {SCHEMA}"))

    with pytest.raises(SystemExit):
        await guard.guard(connection, schema=SCHEMA, tables=TABLES)


async def test_the_drop_removes_the_schema_it_was_given(connection: AsyncConnection) -> None:
    await guard.own(connection, schema=SCHEMA)
    await guard.prepare(connection, schema=SCHEMA, tables=TABLES)

    await guard.drop(connection, schema=SCHEMA)

    found = await connection.execute(sa.text("SELECT to_regnamespace(:s)"), {"s": SCHEMA})
    assert found.scalar_one() is None
    # And the service's own is untouched by any of it.
    still = await connection.execute(sa.text("SELECT to_regclass('public.assets')"))
    assert still.scalar_one() is not None
