"""What the vector index gives up, per model, and what each family costs.

Every search this service answers is approximate: an HNSW scan returns the
neighbours it found, not provably the nearest ones. This command measures by how
much. For each model it builds a corpus, builds each index the store could be
served by — the shipped one as the migration declares it, and the alternatives —
and reports, against an **exact** ranking of the same corpus: how much of the
true top ten each index returns at the effort the service uses, how that moves as
the search knob is raised, what one page costs, and what the index cost to build
and to hold. ADR-002 is written from its output.

The ground truth is read with no vector index in existence and the planner's
index scans switched off, and the plan of that statement is checked before a
figure is taken from it: a ground truth produced by the index it grades would
report a perfect score for everything and look like success.

**It never touches the tables the service uses.** The corpus is built in a schema
of its own, created and dropped by the run, inside the database `DATABASE_URL`
names. That promise lives in `bench_schema.py`, which both measurement commands
import; why it exists and what it refuses is written there.

    uv run python scripts/index_benchmark.py --assets 10000 --seed 7
"""

import argparse
import asyncio
import math
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import bench_schema
import numpy as np
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.core.settings import Settings
from app.db.engine import create_engine
from app.domain import EMBEDDING_MODELS, Narrowing
from app.repositories.embeddings import EmbeddingRepository
from app.services.search import effort_for, rows_needed

#: The schema everything below lives in, and nothing outside it is written to.
DEFAULT_SCHEMA = "index_benchmark"

TABLES = ("assets", "embeddings")

#: The service's own default page, so the effort below is the effort a request
#: would get rather than one invented for the measurement.
LIMIT = 20
#: Recall is measured over the ten nearest: NFR-PERF-4's recall@10.
TOP = 10

#: The corpus is clustered, not uniform. In 768 dimensions a uniform sample of
#: the sphere has no neighbours to find — every pair is nearly orthogonal and the
#: tenth nearest is barely nearer than the ten-thousandth — so recall over it
#: would measure how an index broke a near-tie. Embeddings are clustered, and an
#: index is easy exactly where the data is clustered; these two constants say how
#: clustered this corpus is, and they are printed with the results.
CENTROIDS = 64
#: How far a vector sits from its centroid, as a share of a unit vector, before
#: normalisation. 0.5 puts a vector at cosine ≈ 0.89 of its own centroid and
#: ≈ 0 of the others.
SPREAD = 0.5

#: How many queries every figure is averaged over.
QUERIES = 50

#: The range NFR-PERF-4 names, with the service's default (40) among its steps.
EF_SEARCH_CURVE = (20, 40, 80, 120, 200)
#: IVFFlat's knob. Steps beyond a configuration's `lists` are dropped, and the
#: value pgvector's documentation starts from — `sqrt(lists)` — is added.
PROBE_CURVE = (1, 2, 5, 10, 20)

#: One asset in this many carries the tag the narrowing probe asks for.
NARROWING = 100
NARROWING_TAG = f"every_{NARROWING}"

#: What an iterative scan may be set to; which of them a family accepts is read
#: from the database, not decided here (design decision 8).
ITERATIVE_VALUES = ("off", "relaxed_order", "strict_order")


# --- the plan of exactly what runs -----------------------------------------------


class Explain(Executable, ClauseElement):
    """`EXPLAIN <statement>` with the statement's own parameters.

    The measurement times the statement the repository builds, with its values
    bound, because that is what a request runs. Explaining a *rendered* copy of
    it instead is how change 12's first table came to name one plan and time
    another. The integration suite has the same element for the same reason
    (`tests/integration/conftest.py`); it is not shared, because a script may not
    import the tests and the service is not the place for a measurement tool.
    """

    inherit_cache = False

    def __init__(self, statement: ClauseElement) -> None:
        self.statement = statement


@compiles(Explain, "postgresql")
def compile_explain(element: Explain, compiler: Any, **kw: Any) -> str:
    return "EXPLAIN " + compiler.process(element.statement, **kw)


# --- what is measured ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Configuration:
    """One index the store's vectors could be served by."""

    key: str
    family: str
    parameters: str
    name: str
    ddl: str
    knob: str
    curve: tuple[int, ...]
    #: The setting a deployment would actually run at: the effort the service
    #: sets for its own page, or the family's own default where it sets none.
    shipped: int


@dataclass(frozen=True, slots=True)
class Build:
    """What it cost to have the index at all."""

    model: str
    configuration: str
    parameters: str
    knob: str
    #: The setting a deployment would run this index at.
    shipped: int
    seconds: float
    bytes: int


@dataclass(frozen=True, slots=True)
class Point:
    """One configuration at one setting of its search knob."""

    model: str
    configuration: str
    knob: str
    setting: int
    recall: float
    worst: float
    p95: float
    index_used: str


@dataclass(frozen=True, slots=True)
class Narrowed:
    """What a narrowed page returns under a family's strictest iterative scan."""

    model: str
    configuration: str
    accepted: tuple[str, ...]
    iterative: str
    rows: int
    asked: int


# --- the arithmetic, which is tested on its own ----------------------------------


def recall_at(found: Sequence[UUID], truth: Sequence[UUID]) -> float:
    """The share of the true nearest that the index actually returned.

    A set intersection over identifiers: an index that returns a row at the same
    distance as a true neighbour but not that neighbour has missed it, which is
    the conservative reading and the one a user would recognise.
    """
    if not truth:
        raise ValueError("recall against an empty ranking is not a number")
    return len(set(found) & set(truth)) / len(truth)


def percentile(samples: Sequence[float], share: float) -> float:
    """The nearest-rank percentile: the `ceil(share × n)`-th smallest sample.

    Stated rather than inherited, because the several definitions disagree by a
    sample or two and the document quotes this one.
    """
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


# --- the corpus ------------------------------------------------------------------


def centres_of(rng: np.random.Generator, *, count: int, dim: int) -> np.ndarray:
    """`count` unit vectors, the clusters everything else is built around."""
    raw = rng.standard_normal((count, dim))
    return raw / np.linalg.norm(raw, axis=1, keepdims=True)


def around(
    rng: np.random.Generator, centres: np.ndarray, *, count: int, spread: float
) -> np.ndarray:
    """`count` unit vectors scattered around those centres.

    The noise is scaled by `1/sqrt(dim)` so that `spread` means the same thing at
    768 and at 1024 dimensions: without it, noise of a fixed variance per
    coordinate grows with the width and drowns the centroid.
    """
    dim = centres.shape[1]
    picks = rng.integers(0, len(centres), size=count)
    noise = rng.standard_normal((count, dim)) * (spread / math.sqrt(dim))
    raw = centres[picks] + noise
    return (raw / np.linalg.norm(raw, axis=1, keepdims=True)).astype(np.float32)


def corpus_of(*, stored: int, queries: int, dim: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The vectors to store and the vectors to ask with, from one seed.

    The queries come from the same centres as the corpus but are not members of
    it: a query that is already stored has itself as its nearest neighbour, which
    every index finds and which measures nothing.
    """
    rng = np.random.default_rng([seed, dim])
    centres = centres_of(rng, count=CENTROIDS, dim=dim)
    return (
        around(rng, centres, count=stored, spread=SPREAD),
        around(rng, centres, count=queries, spread=SPREAD),
    )


def literal(vector: np.ndarray) -> str:
    """A vector as pgvector reads it. Seven significant digits: the column is
    float4, so more would be written and then thrown away."""
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"


def batched(rows: list[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


async def fill_corpus(
    connection: AsyncConnection, *, schema: str, assets: int, seed: int
) -> dict[str, np.ndarray]:
    """The copied tables filled: one asset row per asset, one vector per model.

    Returns the query vectors per model — they are made from the same seeded
    stream as the corpus and are needed by the measurement, not by the store.
    """
    identifiers = [uuid4() for _ in range(assets)]
    rows = [
        {
            "id": identifier,
            "sha256": f"{position:064d}",
            "tags": [NARROWING_TAG] if position % NARROWING == 0 else ["none"],
        }
        for position, identifier in enumerate(identifiers)
    ]
    for batch in batched(rows, 1000):
        await connection.execute(
            sa.text(
                "INSERT INTO assets (id, sha256, content_type, file_ext, width, height,"
                " size_bytes, source, tags, meta) VALUES (:id, :sha256, 'image/png', 'png',"
                " 64, 64, 1024, 'upload', :tags, '{}'::jsonb)"
            ),
            batch,
        )

    asked: dict[str, np.ndarray] = {}
    for model, dimension in EMBEDDING_MODELS.items():
        stored, queries = corpus_of(stored=assets, queries=QUERIES, dim=dimension, seed=seed)
        asked[model] = queries
        vectors = [
            {"asset_id": identifier, "model": model, "vector": literal(vector)}
            for identifier, vector in zip(identifiers, stored, strict=True)
        ]
        for batch in batched(vectors, 500):
            await connection.execute(
                sa.text(
                    "INSERT INTO embeddings (asset_id, model, vector) "
                    "VALUES (:asset_id, :model, CAST(:vector AS vector))"
                ),
                batch,
            )
    return asked


# --- the indexes -----------------------------------------------------------------


async def vector_indexes(connection: AsyncConnection, *, schema: str) -> dict[str, str]:
    """Every vector index on the copied embeddings table: name -> definition."""
    found = await connection.execute(
        sa.text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = :schema"
            " AND tablename = 'embeddings'"
            " AND (indexdef LIKE '%hnsw%' OR indexdef LIKE '%ivfflat%')"
        ),
        {"schema": schema},
    )
    return {str(name): str(definition) for name, definition in found}


async def bare(connection: AsyncConnection, *, schema: str) -> dict[str, str]:
    """Strip the embeddings copy to its rows, and keep what rebuilds its indexes.

    Two reasons, one measurement each. The corpus is loaded into a table with no
    index, so a build time afterwards is the whole cost of having that index
    rather than a remainder. And every configuration is then measured with
    exactly one index in existence (design decision 5): with the unique key still
    there, the planner answers an ordering query by reading it and sorting —
    measured, on a corpus of 500 — and the table would say `hnsw` while timing
    something else.

    The vector indexes are handed back as the definitions the database printed,
    which is how the shipped configuration is rebuilt: its DDL comes from the
    migration through `LIKE ... INCLUDING ALL`, never from a copy in this file.
    """
    definitions = await vector_indexes(connection, schema=schema)
    constraints = await connection.execute(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:table AS regclass)"
            " AND contype IN ('p', 'u')"
        ),
        {"table": f"{schema}.embeddings"},
    )
    for (name,) in constraints:
        await connection.execute(
            sa.text(f'ALTER TABLE {schema}.embeddings DROP CONSTRAINT "{name}"')
        )
    remaining = await connection.execute(
        sa.text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = :schema"
            " AND tablename = 'embeddings'"
        ),
        {"schema": schema},
    )
    for (name,) in remaining:
        await connection.execute(sa.text(f'DROP INDEX {schema}."{name}"'))
    return definitions


def shipped_for(definitions: dict[str, str], *, dimension: int) -> tuple[str, str]:
    """The migration's own index for one width, read from the database.

    Read rather than written out here: the shipped configuration under
    measurement has to be the one a request meets, and a copy of its DDL in this
    file could drift from `0002_asset_schema` without anyone noticing.
    """
    for name, definition in definitions.items():
        if f"vector({dimension})" in definition and "hnsw" in definition:
            return name, definition
    raise SystemExit(f"refusing to run: no shipped HNSW index for vector({dimension})")


def configurations(
    model: str, *, dimension: int, rows: int, shipped: tuple[str, str], settings: Settings
) -> list[Configuration]:
    """The indexes this model's vectors are measured on.

    `lists` follows pgvector's own guidance — `rows / 1000` up to a million rows,
    `sqrt(rows)` above it — and both are measured here, the second as the finer
    partitioning it would become on a larger corpus. The probe steps include
    `sqrt(lists)`, which is where that documentation says to start.
    """
    key = model.replace("-", "_")
    shipped_name, shipped_ddl = shipped
    effort = effort_for(settings=settings, limit=LIMIT, offset=0)
    guidance = max(1, rows // 1000)
    finer = max(1, round(math.sqrt(rows)))
    cast = f"((vector::vector({dimension})) vector_cosine_ops)"
    where = f"WHERE model = '{model}'"

    def ivfflat(lists: int) -> Configuration:
        name = f"ix_bench_ivfflat_{lists}_{key}"
        steps = sorted({step for step in PROBE_CURVE if step <= lists} | {round(math.sqrt(lists))})
        return Configuration(
            key=f"ivfflat lists {lists}",
            family="ivfflat",
            parameters=f"lists = {lists}",
            name=name,
            ddl=f"CREATE INDEX {name} ON embeddings USING ivfflat {cast}"
            f" WITH (lists = {lists}) {where}",
            knob="ivfflat.probes",
            curve=tuple(steps),
            # The service sets no probes, so a deployment runs at pgvector's own
            # default of one.
            shipped=1,
        )

    wider = f"ix_bench_hnsw_wide_{key}"
    return [
        Configuration(
            key="hnsw shipped",
            family="hnsw",
            parameters="m = 16, ef_construction = 64",
            name=shipped_name,
            ddl=shipped_ddl,
            knob="hnsw.ef_search",
            curve=EF_SEARCH_CURVE,
            shipped=effort,
        ),
        Configuration(
            key="hnsw wider",
            family="hnsw",
            parameters="m = 32, ef_construction = 128",
            name=wider,
            ddl=f"CREATE INDEX {wider} ON embeddings USING hnsw {cast}"
            f" WITH (m = 32, ef_construction = 128) {where}",
            knob="hnsw.ef_search",
            curve=EF_SEARCH_CURVE,
            shipped=effort,
        ),
        ivfflat(guidance),
        ivfflat(finer),
    ]


async def create(
    connection: AsyncConnection, *, configuration: Configuration, model: str, schema: str
) -> Build:
    """Build one index, timed, and measure what it takes to hold."""
    started = time.perf_counter()
    await connection.execute(sa.text(configuration.ddl))
    seconds = time.perf_counter() - started
    size = (
        await connection.execute(
            # `CAST(... AS ...)` rather than `::`: `text()` does not recognise a
            # parameter followed by a cast operator.
            sa.text("SELECT pg_relation_size(CAST(:name AS regclass))"),
            {"name": f"{schema}.{configuration.name}"},
        )
    ).scalar_one()
    return Build(
        model=model,
        configuration=configuration.key,
        parameters=configuration.parameters,
        knob=configuration.knob.split(".")[1],
        shipped=configuration.shipped,
        seconds=seconds,
        bytes=int(size),
    )


async def drop_vector_indexes(connection: AsyncConnection, *, schema: str) -> None:
    for name in await vector_indexes(connection, schema=schema):
        await connection.execute(sa.text(f"DROP INDEX {schema}.{name}"))


# --- the measurement -------------------------------------------------------------


def page_statement(*, model: str, vector: np.ndarray, narrowed: bool = False) -> sa.Select[Any]:
    """The statement a request runs for one page — the repository's own."""
    return EmbeddingRepository(None).nearest_statement(  # type: ignore[arg-type]
        model=model,
        vector=vector.tolist(),
        limit=rows_needed(limit=LIMIT, offset=0),
        narrowing=Narrowing(tags_all=(NARROWING_TAG,)) if narrowed else None,
    )


async def plan_of(connection: AsyncConnection, statement: sa.Select[Any]) -> str:
    rows = (await connection.execute(Explain(statement))).scalars().all()
    return "\n".join(rows)


def brief(plan: str) -> str:
    """A plan short enough to read in a message. Every line of this one carries
    the query vector in full — a thousand numbers — and none of them is the
    point."""
    return "\n".join(
        line if len(line) <= 120 else f"{line[:120]}… ({len(line)} characters)"
        for line in plan.splitlines()
    )


async def exact_top(
    connection: AsyncConnection, *, model: str, vector: np.ndarray, checked: bool
) -> list[UUID]:
    """The truly nearest `TOP` assets, read from every stored vector.

    No vector index exists while this runs — they are dropped before the corpus
    is loaded and built one at a time afterwards — and the planner's index scans
    are switched off as well. The first query of each model has its plan read:
    if anything in it is an index scan, the run stops rather than grading an
    approximation against another approximation.
    """
    statement = EmbeddingRepository(None).nearest_statement(  # type: ignore[arg-type]
        model=model, vector=vector.tolist(), limit=TOP
    )
    await connection.execute(sa.text("SET LOCAL enable_indexscan = off"))
    await connection.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    # Explicitly on, not merely left alone: a disabled scan is expensive rather
    # than impossible, so in a transaction where sequential scans were switched
    # off as well the planner answers this with the very index it is being
    # graded against — which is a test in the suite, not a hypothesis.
    await connection.execute(sa.text("SET LOCAL enable_seqscan = on"))
    if checked:
        refuse_if_approximate(await plan_of(connection, statement))
    return [row.asset_id for row in await connection.execute(statement)]


def refuse_if_approximate(plan: str) -> None:
    """Stop unless the ground truth was read from the rows themselves."""
    if "Index Scan" in plan or "Index Only Scan" in plan:
        raise SystemExit(
            "refusing to run: the exact ranking was answered by an index, so it is not a "
            f"ground truth. Its plan was:\n{brief(plan)}"
        )


async def sweep(
    connection: AsyncConnection,
    *,
    model: str,
    configuration: Configuration,
    queries: np.ndarray,
    truths: Sequence[Sequence[UUID]],
) -> list[Point]:
    """One configuration across its knob, against the exact rankings.

    Sequential scans are switched off for this transaction. What is measured
    here is what an index gives up, so it has to be the index that answers: on a
    corpus small enough — and at several selectivities on a large one — the
    planner would rather read every vector and sort, which is a true fact about
    the planner (change 12 measured exactly that) and tells us nothing about
    recall. The plan is read afterwards and the configuration's own index has to
    be in it.
    """
    points: list[Point] = []
    await connection.execute(sa.text("SET LOCAL enable_seqscan = off"))
    await connection.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    for setting in configuration.curve:
        await connection.execute(sa.text(f"SET LOCAL {configuration.knob} = {setting}"))
        # A knob that was sent but did not take gives a flat curve that looks
        # like an index with nothing to gain from it, so it is read back.
        applied = (
            await connection.execute(
                sa.text("SELECT current_setting(:knob)"), {"knob": configuration.knob}
            )
        ).scalar_one()
        if int(applied) != setting:
            raise SystemExit(
                f"refusing to report: {configuration.knob} is {applied!r} inside the "
                f"transaction that was told to set it to {setting}"
            )
        # Warm: the first execution of a shape also prepares it, and that cost
        # belongs to no measurement.
        await connection.execute(page_statement(model=model, vector=queries[0]))

        timings: list[float] = []
        recalls: list[float] = []
        for vector, truth in zip(queries, truths, strict=True):
            statement = page_statement(model=model, vector=vector)
            started = time.perf_counter()
            rows = (await connection.execute(statement)).all()
            timings.append((time.perf_counter() - started) * 1000)
            recalls.append(recall_at([row.asset_id for row in rows][:TOP], truth))

        plan = await plan_of(connection, page_statement(model=model, vector=queries[0]))
        if configuration.name not in plan:
            raise SystemExit(
                f"refusing to report: {configuration.key} was measured on a plan that does "
                f"not use {configuration.name}:\n{brief(plan)}"
            )
        points.append(
            Point(
                model=model,
                configuration=configuration.key,
                knob=configuration.knob.split(".")[1],
                setting=setting,
                recall=sum(recalls) / len(recalls),
                worst=min(recalls),
                p95=percentile(timings, 0.95),
                index_used=configuration.name,
            )
        )
    return points


async def accepted_iterative(connection: AsyncConnection, *, family: str) -> tuple[str, ...]:
    """Which iterative-scan values this family accepts — asked of the database.

    The candidates are named here; whether each one exists is pgvector's answer,
    and the difference between the families is the point (design decision 8).
    """
    # The extension's settings exist in a session only once its library is
    # loaded, and until then PostgreSQL accepts `hnsw.anything = whatever` as a
    # placeholder for an extension that may yet arrive. Probing before a vector
    # has been touched would therefore report every value as accepted by every
    # family — a lie in exactly the direction that matters here.
    await connection.execute(sa.text("SELECT CAST('[1,0]' AS vector) <=> CAST('[0,1]' AS vector)"))
    accepted: list[str] = []
    for value in ITERATIVE_VALUES:
        try:
            async with connection.begin_nested():
                await connection.execute(sa.text(f"SET LOCAL {family}.iterative_scan = {value}"))
        except DBAPIError:
            continue
        accepted.append(value)
    return tuple(accepted)


async def narrowed_page(
    connection: AsyncConnection, *, model: str, configuration: Configuration, vector: np.ndarray
) -> Narrowed:
    """What a narrowed page returns under the strictest iterative scan available.

    Change 12's contract — a narrowed search fills its page or says it stopped at
    a bound — rests on an iterative scan that keeps the distance order. Whether a
    family can give that at all decides more than its latency does.
    """
    accepted = await accepted_iterative(connection, family=configuration.family)
    # The strictest the family has: `ITERATIVE_VALUES` runs from weakest to
    # strictest and only the accepted ones are left.
    strictest = accepted[-1] if accepted else "off"
    # The index has to be the plan here too: a narrowed page answered by reading
    # every vector says nothing about what the index does with a narrowing.
    await connection.execute(sa.text("SET LOCAL enable_seqscan = off"))
    await connection.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    await connection.execute(
        sa.text(f"SET LOCAL {configuration.family}.iterative_scan = {strictest}")
    )
    await connection.execute(sa.text(f"SET LOCAL {configuration.knob} = {configuration.shipped}"))
    rows = (
        await connection.execute(page_statement(model=model, vector=vector, narrowed=True))
    ).all()
    return Narrowed(
        model=model,
        configuration=configuration.key,
        accepted=accepted,
        iterative=strictest,
        rows=len(rows),
        asked=rows_needed(limit=LIMIT, offset=0),
    )


# --- the run ---------------------------------------------------------------------


@asynccontextmanager
async def inside(engine: AsyncEngine, *, schema: str) -> Any:
    """A transaction whose unqualified names are this benchmark's own.

    The search path is set for the transaction and checked in it: the statements
    below are the service's own and name `embeddings` unqualified, so every one
    of them is one resolution away from the store.
    """
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"SET LOCAL search_path TO {schema}, public"))
        await bench_schema.guard(connection, schema=schema, tables=TABLES)
        yield connection


@dataclass(frozen=True, slots=True)
class Report:
    """Everything one run produced."""

    assets: int
    queries: int
    seed: int
    pgvector: str
    postgres: str
    effort: int
    builds: list[Build]
    points: list[Point]
    narrowings: list[Narrowed]


async def run(*, assets: int, queries: int, seed: int, schema: str) -> Report:
    """Own a schema, measure inside it, and drop it — in that order, and only
    ever that schema.

    The create is a transaction of its own so that owning the name is a fact by
    the time anything else runs: `created` is set after it committed, and the
    cleanup happens only then. A run that is refused the name leaves everything
    exactly as it found it, the name included.
    """
    if (why := bench_schema.unusable(schema)) is not None:
        raise SystemExit(f"refusing to run: {why}")
    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(settings)
    builds: list[Build] = []
    points: list[Point] = []
    narrowings: list[Narrowed] = []
    created = False
    try:
        async with engine.begin() as connection:
            await bench_schema.own(connection, schema=schema)
        created = True

        async with engine.begin() as connection:
            versions = await connection.execute(
                sa.text(
                    "SELECT (SELECT extversion FROM pg_extension WHERE extname = 'vector'),"
                    " current_setting('server_version')"
                )
            )
            pgvector, postgres = versions.one()

        async with engine.begin() as connection:
            await bench_schema.prepare(connection, schema=schema, tables=TABLES)
            # Indexes are built one at a time from here on, so that every
            # measurement has exactly one index it could have used and the plan
            # says which.
            definitions = await bare(connection, schema=schema)
            shipped = {
                model: shipped_for(definitions, dimension=dimension)
                for model, dimension in EMBEDDING_MODELS.items()
            }
            asked = await fill_corpus(connection, schema=schema, assets=assets, seed=seed)
            await connection.execute(sa.text(f"ANALYZE {schema}.assets, {schema}.embeddings"))

        for model, dimension in EMBEDDING_MODELS.items():
            queries_of = asked[model][:queries]
            async with inside(engine, schema=schema) as connection:
                truths = [
                    await exact_top(connection, model=model, vector=vector, checked=position == 0)
                    for position, vector in enumerate(queries_of)
                ]

            for configuration in configurations(
                model,
                dimension=dimension,
                rows=assets,
                shipped=shipped[model],
                settings=settings,
            ):
                async with inside(engine, schema=schema) as connection:
                    builds.append(
                        await create(
                            connection, configuration=configuration, model=model, schema=schema
                        )
                    )
                async with inside(engine, schema=schema) as connection:
                    points += await sweep(
                        connection,
                        model=model,
                        configuration=configuration,
                        queries=queries_of,
                        truths=truths,
                    )
                async with inside(engine, schema=schema) as connection:
                    narrowings.append(
                        await narrowed_page(
                            connection,
                            model=model,
                            configuration=configuration,
                            vector=queries_of[0],
                        )
                    )
                async with inside(engine, schema=schema) as connection:
                    await drop_vector_indexes(connection, schema=schema)
    except bench_schema.SchemaInUse as error:
        raise SystemExit(f"refusing to run: {error}") from error
    finally:
        if created:
            async with engine.begin() as connection:
                await bench_schema.drop(connection, schema=schema)
        await engine.dispose()

    return Report(
        assets=assets,
        queries=queries,
        seed=seed,
        pgvector=str(pgvector),
        postgres=str(postgres),
        effort=effort_for(settings=settings, limit=LIMIT, offset=0),
        builds=builds,
        points=points,
        narrowings=narrowings,
    )


# --- what it prints --------------------------------------------------------------


def megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def header_of(report: Report) -> str:
    return "\n".join(
        [
            f"Corpus: {report.assets} assets, one vector per asset for every model, "
            f"seed {report.seed}; {CENTROIDS} centroids, spread {SPREAD}, unit length. "
            f"{report.queries} queries from the same centres, none of them stored.",
            "",
            f"Page: limit {LIMIT}, so {rows_needed(limit=LIMIT, offset=0)} rows are asked for; "
            f"the service's own effort for it is `hnsw.ef_search` {report.effort}, and it sets "
            "no `ivfflat.probes` at all, so a deployment runs IVFFlat at pgvector's default "
            "of 1.",
            "",
            f"pgvector {report.pgvector} on PostgreSQL {report.postgres}. Recall is against an "
            f"exact ranking of the same corpus; p95 is the nearest-rank percentile of "
            f"{report.queries} timings, warm, and excludes embedding the query.",
            "",
            "Every figure here is the index's own: the measuring transaction has sequential "
            "scans switched off and the table carries no other index, so the plan is the "
            "index under measurement — checked, per configuration. Whether a planner would "
            "*choose* it on a corpus this size is a different question, and change 12's "
            "section above is where it was measured.",
        ]
    )


def configuration_table(report: Report, *, model: str) -> str:
    """Per index: what it cost to have, and what it gives at the shipped setting."""
    lines = [
        "| index | parameters | build | size | at | recall@10 | worst | p95 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for build in [one for one in report.builds if one.model == model]:
        point = next(
            one
            for one in report.points
            if one.model == model
            and one.configuration == build.configuration
            and one.setting == build.shipped
        )
        lines.append(
            f"| {build.configuration} | {build.parameters} "
            f"| {build.seconds:.1f} s | {megabytes(build.bytes)} | {build.knob} {point.setting} "
            f"| {point.recall:.3f} | {point.worst:.2f} | {point.p95:.1f} |"
        )
    return "\n".join(lines)


def curve_table(report: Report, *, model: str) -> str:
    lines = [
        "| index | setting | recall@10 | worst | p95 ms |",
        "|---|---|---|---|---|",
    ]
    for point in [one for one in report.points if one.model == model]:
        lines.append(
            f"| {point.configuration} | {point.knob} {point.setting} | {point.recall:.3f} "
            f"| {point.worst:.2f} | {point.p95:.1f} |"
        )
    return "\n".join(lines)


def narrowing_table(report: Report, *, model: str) -> str:
    lines = [
        "| index | iterative_scan accepts | measured at | rows of asked |",
        "|---|---|---|---|",
    ]
    for narrowed in [one for one in report.narrowings if one.model == model]:
        lines.append(
            f"| {narrowed.configuration} | {', '.join(narrowed.accepted)} "
            f"| {narrowed.iterative} | {narrowed.rows} of {narrowed.asked} |"
        )
    return "\n".join(lines)


def report_of(report: Report) -> str:
    parts = [header_of(report)]
    for model, dimension in EMBEDDING_MODELS.items():
        parts += [
            "",
            f"## {model} ({dimension} dimensions)",
            "",
            configuration_table(report, model=model),
            "",
            "The curve:",
            "",
            curve_table(report, model=model),
            "",
            f"A narrowing of one asset in {NARROWING}:",
            "",
            narrowing_table(report, model=model),
        ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--assets", type=int, default=10000, help="how many assets to build, per model"
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=QUERIES,
        help=f"how many queries every figure averages, at most {QUERIES}",
    )
    parser.add_argument("--seed", type=int, default=7, help="the corpus's seed")
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help="the schema to build in, create and drop (never the service's own)",
    )
    parsed = parser.parse_args(argv)
    if (why := bench_schema.unusable(parsed.schema)) is not None:
        parser.error(why)
    if not 1 <= parsed.queries <= QUERIES:
        parser.error(f"--queries takes 1 to {QUERIES}")

    report = asyncio.run(
        run(assets=parsed.assets, queries=parsed.queries, seed=parsed.seed, schema=parsed.schema)
    )
    print(report_of(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
