"""Where the planner changes its mind about a narrowed vector search.

One narrowing, one page, one corpus — measured across selectivity, across the
two plans PostgreSQL may choose, with and without the statistics that let it
choose, and with pgvector's iterative scan on and off. What comes out is the
table in `docs/how-to/benchmarks.md`, and what it is for is the decision change
12 could not take from a single measurement: a narrowed search is answered one
way when the narrowing is broad and another when it is selective, and only one
of those two ways can run out of budget.

**It never touches the tables the service uses.** The corpus is built in a
schema of its own, created here and dropped here, inside the database
`DATABASE_URL` names. That is not tidiness: a benchmark that truncated the
service's tables would be a published command that erases a corpus, and on a
machine where one database serves development and the integration suite it
would do exactly that — it did, to this repository's demo corpus, while these
measurements were being taken. The structure is copied from the real tables
(`LIKE ... INCLUDING ALL`), so the indexes measured are the service's own
indexes and cannot drift from them, and `to_regclass` is checked before a single
row is written.

    uv run python scripts/filter_benchmark.py --assets 3000 --seed 7
"""

import argparse
import asyncio
import math
import random
import re
import sys
import time
from dataclasses import dataclass
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.settings import Settings
from app.db.engine import create_engine
from app.domain import CLIP_VIT_L14, Narrowing, dimension_of
from app.repositories.embeddings import EmbeddingRepository
from app.services.search import effort_for, rows_needed

#: The schema everything below lives in, and nothing outside it is written to.
DEFAULT_SCHEMA = "filter_benchmark"
#: A schema name is interpolated into DDL, so it is checked rather than trusted
#: — the same rule the service applies to everything that arrives from outside.
SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,48}$")

TABLES = ("assets", "embeddings")
MODEL = CLIP_VIT_L14
DIMENSION = dimension_of(MODEL)

#: One asset in N carries the tag the search narrows to. Broad to rare, which
#: is the axis the planner changes its mind along.
SELECTIVITIES = (2, 5, 20, 100, 300)
#: The service's own default page, so the effort below is the effort a request
#: would get rather than one invented for the measurement.
LIMIT = 20


def tag_of(every: int) -> str:
    return f"every_{every}"


def plane_vector(x: float, y: float) -> list[float]:
    values = [0.0] * DIMENSION
    values[0], values[1] = x, y
    return values


@dataclass(frozen=True, slots=True)
class Measurement:
    """One cell of the table: what was asked, how it was answered, what it cost."""

    every: int
    analysed: bool
    iterative: str
    plan: str
    rows: int
    asked: int
    milliseconds: float
    #: The plan as the database printed it, for `--plans`: a table saying which
    #: of three shapes answered is worth little without one of them in full.
    explained: str = ""


# --- the corpus, in a schema of its own -----------------------------------------


async def build(connection: AsyncConnection, *, schema: str, assets: int, seed: int) -> None:
    """The schema, the tables copied from the service's own, and the rows.

    The copy carries every index the real tables have, the partial HNSW index
    over the dimension cast included (ADR-001), so what is measured here is what
    a request meets. Autovacuum is switched off on the copies: a background
    ANALYZE arriving mid-run would silently turn the statistics-free half of the
    table into something else.
    """
    await connection.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    await connection.execute(sa.text(f"CREATE SCHEMA {schema}"))
    for table in TABLES:
        await connection.execute(
            sa.text(f"CREATE TABLE {schema}.{table} (LIKE public.{table} INCLUDING ALL)")
        )
        await connection.execute(
            sa.text(f"ALTER TABLE {schema}.{table} SET (autovacuum_enabled = false)")
        )
    await connection.execute(sa.text(f"SET search_path TO {schema}, public"))
    await guard(connection, schema=schema)

    order = list(range(assets))
    random.Random(seed).shuffle(order)
    rows, vectors = [], []
    for position, rank in enumerate(order):
        identifier = uuid4()
        tags = [tag_of(every) for every in SELECTIVITIES if position % every == 0]
        angle = (rank + 1) * (math.pi / 2) / (assets + 2)
        rows.append(
            {
                "id": identifier,
                "sha256": f"{rank:064d}",
                "tags": tags or ["none"],
            }
        )
        vectors.append(
            {
                "asset_id": identifier,
                "model": MODEL,
                "vector": str(plane_vector(math.cos(angle), math.sin(angle))),
            }
        )
    await connection.execute(
        sa.text(
            "INSERT INTO assets (id, sha256, content_type, file_ext, width, height,"
            " size_bytes, source, tags, meta) VALUES (:id, :sha256, 'image/png', 'png',"
            " 64, 64, 1024, 'upload', :tags, '{}'::jsonb)"
        ),
        rows,
    )
    await connection.execute(
        sa.text(
            "INSERT INTO embeddings (asset_id, model, vector) "
            "VALUES (:asset_id, :model, CAST(:vector AS vector))"
        ),
        vectors,
    )


async def guard(connection: AsyncConnection, *, schema: str) -> None:
    """Refuse to write unless every unqualified name resolves inside the schema.

    The one check between this script and the corpus of whoever runs it: with
    the search path set, `assets` must be *this* schema's `assets`. If the copy
    failed, or the path did not take, the next statement would write to the
    service's own table — so there is no next statement.
    """
    for table in TABLES:
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


async def hnsw_index(connection: AsyncConnection, *, schema: str) -> str:
    """The name of the copied vector index for this model's dimension."""
    name = (
        await connection.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = :schema"
                " AND tablename = 'embeddings' AND indexdef LIKE :shape"
            ),
            {"schema": schema, "shape": f"%hnsw%vector({DIMENSION})%"},
        )
    ).scalar_one()
    return str(name)


# --- the measurement -------------------------------------------------------------


def classify(plan: str, *, index: str) -> str:
    """Which of the two ways answered it — read from the plan, not assumed."""
    if index in plan:
        return "vector index"
    if "Seq Scan on embeddings" in plan:
        return "sequential scan"
    return "exact, narrowed rows"


async def measure(
    connection: AsyncConnection,
    *,
    schema: str,
    every: int,
    iterative: str,
    analysed: bool,
    index: str,
    settings: Settings,
) -> Measurement:
    """One narrowing, one page, under one set of the planner's options."""
    needed = rows_needed(limit=LIMIT, offset=0)
    statement = EmbeddingRepository(None).nearest_statement(  # type: ignore[arg-type]
        model=MODEL,
        vector=plane_vector(1.0, 0.0),
        limit=needed,
        narrowing=Narrowing(tags_all=(tag_of(every),)),
    )
    effort = effort_for(settings=settings, limit=LIMIT, offset=0)
    await connection.execute(sa.text(f"SET hnsw.ef_search = {effort}"))
    await connection.execute(sa.text(f"SET hnsw.iterative_scan = {iterative}"))

    # One SQL string, explained and then run. Explaining a statement with its
    # values in it and running the same statement with *parameters* is how a
    # table comes to name one plan and time another: the planner is free to
    # choose differently for a parameterised statement, and it does.
    sql = compiled(statement)
    plan = "\n".join(line for (line,) in await connection.exec_driver_sql(f"EXPLAIN {sql}"))
    await connection.exec_driver_sql(sql)  # warm: the second run is the one timed
    started = time.perf_counter()
    rows = (await connection.exec_driver_sql(sql)).all()
    elapsed = (time.perf_counter() - started) * 1000

    return Measurement(
        every=every,
        analysed=analysed,
        iterative=iterative,
        plan=classify(plan, index=index),
        rows=len(rows),
        asked=needed,
        milliseconds=elapsed,
        explained=plan,
    )


def compiled(statement: sa.Select[object]) -> str:
    """The statement as SQL, with its values in it — for EXPLAIN, which takes a
    statement rather than a statement and parameters."""
    return str(
        statement.compile(
            dialect=sa.dialects.postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


async def run(*, assets: int, seed: int, schema: str) -> list[Measurement]:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(settings)
    measurements: list[Measurement] = []
    try:
        async with engine.begin() as connection:
            await build(connection, schema=schema, assets=assets, seed=seed)
            index = await hnsw_index(connection, schema=schema)
            for analysed in (False, True):
                if analysed:
                    await connection.execute(
                        sa.text(f"ANALYZE {schema}.assets, {schema}.embeddings")
                    )
                for every in SELECTIVITIES:
                    for iterative in ("off", "strict_order"):
                        measurements.append(
                            await measure(
                                connection,
                                schema=schema,
                                every=every,
                                iterative=iterative,
                                analysed=analysed,
                                index=index,
                                settings=settings,
                            )
                        )
    finally:
        async with engine.begin() as connection:
            await connection.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()
    return measurements


def table_of(measurements: list[Measurement], *, assets: int, seed: int, effort: int) -> str:
    """The measurements as the Markdown table the how-to carries."""
    lines = [
        f"Corpus: {assets} assets, one vector each of `{MODEL}`, seed {seed}. "
        f"Page: limit {LIMIT}, so {rows_needed(limit=LIMIT, offset=0)} rows are asked for, "
        f"at `hnsw.ef_search` {effort}.",
        "",
        "| matches | statistics | iterative_scan | plan | rows of asked | ms |",
        "|---|---|---|---|---|---|",
    ]
    for one in measurements:
        lines.append(
            f"| 1 in {one.every} | {'fresh' if one.analysed else 'none'} | {one.iterative} "
            f"| {one.plan} | {one.rows} of {one.asked} | {one.milliseconds:.1f} |"
        )
    return "\n".join(lines)


def plans_of(measurements: list[Measurement]) -> str:
    """One plan per shape that answered, printed once with what produced it."""
    lines: list[str] = []
    for shape in dict.fromkeys(one.plan for one in measurements):
        first = next(one for one in measurements if one.plan == shape)
        lines += [
            "",
            f"### {shape} — 1 in {first.every}, statistics "
            f"{'fresh' if first.analysed else 'none'}, iterative_scan {first.iterative}",
            "",
            "```text",
            first.explained,
            "```",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--assets", type=int, default=3000, help="how many assets to build")
    parser.add_argument("--seed", type=int, default=7, help="the shuffle's seed")
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help="the schema to build in, create and drop (never the service's own)",
    )
    parser.add_argument(
        "--plans",
        action="store_true",
        help="print one full plan per shape that answered, under the table",
    )
    parsed = parser.parse_args(argv)
    if not SCHEMA_PATTERN.match(parsed.schema):
        parser.error(f"not a schema name this script will create: {parsed.schema!r}")
    if parsed.schema == "public":  # pragma: no cover - refused by the pattern above
        parser.error("public is where the service's tables are")

    measurements = asyncio.run(run(assets=parsed.assets, seed=parsed.seed, schema=parsed.schema))
    settings = Settings()  # type: ignore[call-arg]
    print(
        table_of(
            measurements,
            assets=parsed.assets,
            seed=parsed.seed,
            effort=effort_for(settings=settings, limit=LIMIT, offset=0),
        )
    )
    if parsed.plans:
        print(plans_of(measurements))
    return 0


if __name__ == "__main__":
    sys.exit(main())
