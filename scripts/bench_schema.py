"""The schema a measurement owns, and the checks that keep it out of the store.

Both published measurement commands — `filter_benchmark.py` and
`index_benchmark.py` — build a corpus of thousands of rows, measure over it and
throw it away. They do that inside a schema of their own, created by the run and
dropped by the run, in the database `DATABASE_URL` names. This module is that
promise written once.

It is shared rather than copied on purpose. A benchmark that truncated the
service's tables would be a published command that erases a corpus, and on a
machine where one database serves development and the integration suite it would
do exactly that — it did, to this repository's demo corpus, while change 12 was
being measured. A second copy of the guard would be a second promise to keep in
step, and a harness that duplicates what it should be exercising cannot fail
when the original breaks (change 13, Gate 2 finding 2). One module, one set of
tests through the commands that import it.

The order a caller uses it in:

    if (why := bench_schema.unusable(name)):   # at the edge, before connecting
        parser.error(why)
    ...
    async with engine.begin() as connection:
        await bench_schema.own(connection, schema=name)      # refuses a name taken
    created = True                                           # ← what the cleanup turns on
    async with engine.begin() as connection:
        await bench_schema.prepare(connection, schema=name, tables=TABLES)
        ...                                                  # write only after this
    finally:
        if created:
            await bench_schema.drop(connection, schema=name)
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection

#: A schema name is interpolated into DDL, so it is checked rather than trusted
#: — the same rule the service applies to everything that arrives from outside.
#:
#: `\Z`, never `$`: Python's `$` also matches before a final newline, so
#: `^...$` accepts `public\n` — which SQL reads as `public` followed by
#: whitespace, and which an equality check against the protected names below
#: would not catch (change 12, Gate 2 finding 1).
SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,48}\Z")

#: Names no benchmark will create whatever the pattern says: where the service's
#: own tables live, and everything the database reserves.
PROTECTED_SCHEMAS = frozenset({"public", "pg_catalog", "information_schema"})


class SchemaInUse(Exception):
    """The name asked for is already somebody's schema."""


def unusable(schema: str) -> str | None:
    """Why a benchmark may not create this name, or `None` if it may.

    Called at the edge — from argument parsing, before anything is connected to
    — and again by the run itself, so a caller that forgets the first one still
    cannot reach a database with a name like `public\\n`.
    """
    if not SCHEMA_PATTERN.match(schema):
        return f"not a schema name a benchmark will create: {schema!r}"
    if schema in PROTECTED_SCHEMAS or schema.startswith("pg_"):
        return f"{schema!r} is where the service's or the database's own tables are"
    return None


async def own(connection: AsyncConnection, *, schema: str) -> None:
    """Create the schema, or refuse the run.

    Plain `CREATE SCHEMA`: no `IF NOT EXISTS`, and above all no `DROP` first.
    A schema that is already there belongs to someone — the default name reused
    between runs, or a schema of the person's own — and the promise here is that
    a run deletes only what it created (change 12, Gate 2 finding 2). Whether
    this succeeded is what the caller's cleanup turns on.
    """
    try:
        await connection.execute(sa.text(f"CREATE SCHEMA {schema}"))
    except ProgrammingError as error:
        raise SchemaInUse(
            f"schema {schema!r} already exists: a benchmark only ever drops a schema it "
            f"created. Remove it yourself, or pass --schema with another name."
        ) from error


async def prepare(connection: AsyncConnection, *, schema: str, tables: Sequence[str]) -> None:
    """The service's tables copied into the schema, and the path that reaches them.

    The copy carries every index the real tables have, the partial HNSW index
    over the dimension cast included (ADR-001), so what a benchmark measures is
    what a request meets and cannot drift from the migration. Autovacuum is
    switched off on the copies: a background ANALYZE arriving mid-run would
    silently turn a statistics-free table into something else.

    Returns with the search path set and `guard` already passed, so the caller's
    next statement may be its first write.
    """
    for table in tables:
        await connection.execute(
            sa.text(f"CREATE TABLE {schema}.{table} (LIKE public.{table} INCLUDING ALL)")
        )
        await connection.execute(
            sa.text(f"ALTER TABLE {schema}.{table} SET (autovacuum_enabled = false)")
        )
    await connection.execute(sa.text(f"SET search_path TO {schema}, public"))
    await guard(connection, schema=schema, tables=tables)


async def guard(connection: AsyncConnection, *, schema: str, tables: Sequence[str]) -> None:
    """Refuse to write unless every unqualified name resolves inside the schema.

    The one check between a benchmark and the corpus of whoever runs it: with
    the search path set, `assets` must be *this* schema's `assets`. If the copy
    failed, or the path did not take, the next statement would write to the
    service's own table — so there is no next statement.
    """
    for table in tables:
        # `to_regclass` alone prints the name unqualified while the schema is in
        # the search path, which is exactly the case this has to tell apart.
        resolved = (
            await connection.execute(
                sa.text(
                    "SELECT namespace.nspname || '.' || class.relname FROM pg_class AS class"
                    " JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace"
                    " WHERE class.oid = to_regclass(:name)"
                ),
                {"name": table},
            )
        ).scalar_one_or_none()
        if resolved != f"{schema}.{table}":
            raise SystemExit(
                f"refusing to run: {table!r} resolves to {resolved!r}, not {schema}.{table}"
            )


async def drop(connection: AsyncConnection, *, schema: str) -> None:
    """Drop the schema the run created — and only ever that one.

    `IF EXISTS` because the cleanup runs after a failure too; the caller's flag,
    not this call, is what makes it a schema this run owns.
    """
    await connection.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


async def vector_index(connection: AsyncConnection, *, schema: str, dimension: int) -> str:
    """The name of the copied HNSW index serving one model's width."""
    name = (
        await connection.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = :schema"
                " AND tablename = 'embeddings' AND indexdef LIKE :shape"
            ),
            {"schema": schema, "shape": f"%hnsw%vector({dimension})%"},
        )
    ).scalar_one()
    return str(name)
