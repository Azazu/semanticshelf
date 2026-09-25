"""The index measurement, against a real database.

Two things are asserted here. The first is the promise every published
measurement command makes: it builds in a schema of its own and the store it
finds is the store it leaves (`scripts/bench_schema.py`). The second is that the
figures it prints mean what ADR-002 will say they mean — that the ranking it
grades against is exact, that the index under measurement is the one that
answered, and that a figure of 1.00 is a found ranking rather than a measurement
unable to report a miss.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, EMBEDDING_MODELS, dimension_of
from tests.scripts import script_module

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"
#: Every table the service owns, and the promise is about all three.
STORE_TABLES = ("assets", "embeddings", "indexing_jobs")

#: The schema the tests below build in. It belongs to this file: `own()` refuses
#: a name already taken, so a schema left behind by a crashed run would fail
#: every test here rather than be measured over.
SCHEMA = "index_benchmark_tests"
#: Small enough for CI to build in seconds, large enough that an index asked to
#: look one candidate deep misses most of the ranking.
ASSETS = 2000
#: The requirement bounds the *mean* over at least fifty queries, so the guard
#: averages over fifty too — a bound checked over five would be a different
#: statistic wearing the same number (Gate 1 round 1, finding 2).
QUERIES = 50


def benchmark() -> ModuleType:
    """The script, imported as a module — it is not a package."""
    return script_module("index_benchmark")


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


# --- a corpus to measure over -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Corpus:
    """A built corpus in a schema of its own, and what measures over it."""

    module: ModuleType
    schema: str
    definitions: dict[str, str]
    queries: dict[str, np.ndarray]

    def shipped(self, model: str) -> tuple[str, str]:
        return self.module.shipped_for(self.definitions, dimension=dimension_of(model))


@pytest.fixture
async def corpus(engine: AsyncEngine) -> AsyncIterator[Corpus]:
    module = benchmark()
    async with engine.begin() as connection:
        await module.bench_schema.own(connection, schema=SCHEMA)
    try:
        async with engine.begin() as connection:
            await module.bench_schema.prepare(connection, schema=SCHEMA, tables=module.TABLES)
            definitions = await module.bare(connection, schema=SCHEMA)
            queries = await module.fill_corpus(connection, schema=SCHEMA, assets=ASSETS, seed=7)
            await connection.execute(sa.text(f"ANALYZE {SCHEMA}.assets, {SCHEMA}.embeddings"))
        yield Corpus(module=module, schema=SCHEMA, definitions=definitions, queries=queries)
    finally:
        async with engine.begin() as connection:
            await module.bench_schema.drop(connection, schema=SCHEMA)


# --- the promise about the store ---------------------------------------------------


async def seed(session: AsyncSession) -> list[UUID]:
    """A small store of the kind a person would be sorry to lose."""
    identifiers = [uuid4() for _ in range(3)]
    async with session.begin():
        for index, identifier in enumerate(identifiers):
            await session.execute(
                sa.text(
                    "INSERT INTO assets (id, sha256, content_type, file_ext, width, height,"
                    " size_bytes, source, tags, meta) VALUES (:id, :sha256, 'image/png', 'png',"
                    " 64, 64, 1024, 'upload', ARRAY['every_100'], '{}'::jsonb)"
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


async def store(session: AsyncSession) -> dict[str, list[UUID]]:
    return {table: await rows_of(session, table) for table in STORE_TABLES}


async def namespace(session: AsyncSession, schema: str) -> int | None:
    async with session.begin():
        found = await session.execute(sa.text("SELECT to_regnamespace(:s)"), {"s": schema})
        return found.scalar_one()


async def test_the_published_command_leaves_a_populated_store_untouched(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command as the how-to prints it, only smaller: the published run
    builds ten thousand assets per model, which is a measurement rather than a
    test."""
    module = benchmark()
    await seed(session)
    before = await store(session)
    assert all(before[table] for table in STORE_TABLES), "the fixture is the point of this test"

    # In a thread of its own: the script owns an event loop, and this test is
    # already running in one.
    assert await asyncio.to_thread(module.main, ["--assets", "500", "--queries", "3"]) == 0

    assert await store(session) == before, "every row that was there is still there"
    printed = capsys.readouterr().out
    assert "| recall@10 |" in printed, "and it printed its tables"
    assert "| index | iterative_scan accepts |" in printed


async def test_the_schema_it_built_in_is_gone(session: AsyncSession) -> None:
    module = benchmark()
    await seed(session)

    await asyncio.to_thread(module.main, ["--assets", "300", "--queries", "2"])

    assert await namespace(session, module.DEFAULT_SCHEMA) is None, (
        "the schema it created is dropped, whatever happened"
    )


async def test_it_refuses_a_schema_name_it_would_have_to_quote(session: AsyncSession) -> None:
    module = benchmark()
    await seed(session)

    for refused in ("public", 'x"; DROP SCHEMA public CASCADE; --', "Index_Benchmark"):
        with pytest.raises(SystemExit) as raised:
            module.main(["--schema", refused])
        assert raised.value.code == 2, refused

    assert await rows_of(session, "assets"), "and nothing was touched"


async def test_a_refused_name_reaches_no_database_at_all(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`public\\n` passes `^...$` — Python's `$` matches before a final newline —
    so the refusal happens at the edge, before anything is connected to."""
    module = benchmark()
    reached: list[dict[str, object]] = []

    async def never_run(**kwargs: object) -> object:
        reached.append(kwargs)
        return None

    monkeypatch.setattr(module, "run", never_run)

    for refused in ("public\n", "public", "pg_catalog", "pg_temp_1", "Index_Benchmark", "x; DROP"):
        with pytest.raises(SystemExit) as raised:
            await asyncio.to_thread(module.main, ["--schema", refused])
        assert raised.value.code == 2, refused

    assert reached == [], "not one of them got as far as a connection"


async def test_a_name_already_taken_is_refused_and_nothing_of_it_is_touched(
    session: AsyncSession,
) -> None:
    module = benchmark()
    schema = "index_benchmark_taken"
    await seed(session)
    async with session.begin():
        await session.execute(sa.text(f"CREATE SCHEMA {schema}"))
        await session.execute(sa.text(f"CREATE TABLE {schema}.mine (id int)"))
        await session.execute(sa.text(f"INSERT INTO {schema}.mine VALUES (1)"))
    before = await store(session)
    try:
        with pytest.raises(SystemExit) as raised:
            await asyncio.to_thread(module.main, ["--schema", schema, "--assets", "50"])

        assert "already exists" in str(raised.value)
        async with session.begin():
            held = await session.execute(sa.text(f"SELECT count(*) FROM {schema}.mine"))
            assert held.scalar_one() == 1, "the table that was there is untouched"
        assert await namespace(session, schema) is not None, "and so is the schema itself"
        assert await store(session) == before
    finally:
        async with session.begin():
            await session.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


# --- the figures mean what they say ------------------------------------------------


async def test_the_ranking_it_grades_against_is_read_from_the_rows(
    engine: AsyncEngine, corpus: Corpus
) -> None:
    module = corpus.module
    query = corpus.queries[CLIP_VIT_L14][0]

    async with module.inside(engine, schema=corpus.schema) as connection:
        truth = await module.exact_top(connection, model=CLIP_VIT_L14, vector=query, checked=True)

    assert len(truth) == module.TOP


async def test_a_ranking_an_index_answered_is_refused_as_a_ground_truth(
    engine: AsyncEngine, corpus: Corpus
) -> None:
    """The guard's input is not hypothetical: with the shipped index in place and
    sequential scans off, the very same statement is answered by that index. The
    run stops on it rather than grading an approximation against itself."""
    module = corpus.module
    name, ddl = corpus.shipped(CLIP_VIT_L14)
    query = corpus.queries[CLIP_VIT_L14][0]
    statement = module.EmbeddingRepository(None).nearest_statement(
        model=CLIP_VIT_L14, vector=query.tolist(), limit=module.TOP
    )

    async with module.inside(engine, schema=corpus.schema) as connection:
        await connection.execute(sa.text(ddl))
        await connection.execute(sa.text("SET LOCAL enable_seqscan = off"))
        approximate = await module.plan_of(connection, statement)

        assert name in approximate, "the index answered it"
        with pytest.raises(SystemExit) as raised:
            module.refuse_if_approximate(approximate)
        assert "not a ground truth" in str(raised.value)

        # And the ground truth's own plan, in the same transaction, is not that.
        await module.exact_top(connection, model=CLIP_VIT_L14, vector=query, checked=True)


async def test_one_configuration_is_measured_on_one_index(
    engine: AsyncEngine, corpus: Corpus
) -> None:
    """Every other index is gone while a configuration is measured, so the plan
    has nothing else to choose and the figures belong to the index named."""
    module = corpus.module
    configuration = shipped_configuration(corpus, CLIP_VIT_L14)

    async with module.inside(engine, schema=corpus.schema) as connection:
        await module.create(
            connection, configuration=configuration, model=CLIP_VIT_L14, schema=corpus.schema
        )
        present = await module.vector_indexes(connection, schema=corpus.schema)
        assert list(present) == [configuration.name]

    points = await sweep_of(engine, corpus, configuration)
    assert {point.index_used for point in points} == {configuration.name}


async def test_an_index_that_looks_one_candidate_deep_reports_a_miss(
    engine: AsyncEngine, corpus: Corpus
) -> None:
    """A measurement that cannot report a miss is not a measurement. Asked to
    keep one candidate, the index cannot hold ten of the ranking; asked for two
    hundred, it finds it."""
    corners = replace(shipped_configuration(corpus, CLIP_VIT_L14), curve=(1, 200))

    points = await sweep_of(engine, corpus, corners)

    shallow, deep = points
    assert shallow.setting == 1 and deep.setting == 200
    assert shallow.recall < 0.5, "an index kept this shallow cannot have found the ranking"
    assert deep.recall > shallow.recall, "and the knob is what made the difference"


@pytest.mark.parametrize("model", sorted(EMBEDDING_MODELS))
async def test_recall_at_the_effort_the_service_ships_with_clears_the_bound(
    engine: AsyncEngine, corpus: Corpus, model: str
) -> None:
    """NFR-PERF-4's bound, on a corpus CI can build in seconds, for **every**
    model the store indexes — the requirement and ADR-002 cover each of them,
    and a regression confined to one width would otherwise leave this green
    (Gate 2 round 1, finding 2). The published measurement is the one at ten
    thousand vectors per model; what this keeps is that the shipped
    configuration does not silently fall off the bound."""
    configuration = shipped_configuration(corpus, model)
    at_shipped = replace(configuration, curve=(configuration.shipped,))

    points = await sweep_of(engine, corpus, at_shipped, model=model)

    assert points[0].recall >= 0.95, (
        f"{model}: mean over {QUERIES} queries, {ASSETS} vectors, "
        f"ef_search {configuration.shipped} (worst single query {points[0].worst})"
    )


async def test_which_iterative_scan_a_family_has_is_the_database_s_answer(
    engine: AsyncEngine, corpus: Corpus
) -> None:
    """The one structural difference between the families: HNSW can keep the
    distance order while it looks further, and IVFFlat cannot. The service's
    narrowed-search contract is written on that."""
    module = corpus.module

    async with module.inside(engine, schema=corpus.schema) as connection:
        hnsw = await module.accepted_iterative(connection, family="hnsw")
        ivfflat = await module.accepted_iterative(connection, family="ivfflat")

    assert "strict_order" in hnsw
    assert "strict_order" not in ivfflat
    assert "off" in hnsw and "off" in ivfflat


# --- helpers ----------------------------------------------------------------------


def shipped_configuration(corpus: Corpus, model: str) -> Any:
    """The configuration the store actually ships, as the script builds it."""
    module = corpus.module
    return next(
        configuration
        for configuration in module.configurations(
            model,
            dimension=dimension_of(model),
            rows=ASSETS,
            shipped=corpus.shipped(model),
            settings=module.Settings(),
        )
        if configuration.key == "hnsw shipped"
    )


async def sweep_of(
    engine: AsyncEngine, corpus: Corpus, configuration: Any, *, model: str = CLIP_VIT_L14
) -> list[Any]:
    """Build the configuration if it is not there, and sweep its knob."""
    module = corpus.module
    queries = corpus.queries[model][:QUERIES]
    async with module.inside(engine, schema=corpus.schema) as connection:
        present = await module.vector_indexes(connection, schema=corpus.schema)
        if configuration.name not in present:
            await module.create(
                connection,
                configuration=configuration,
                model=model,
                schema=corpus.schema,
            )

    async with module.inside(engine, schema=corpus.schema) as connection:
        truths = [
            await module.exact_top(connection, model=model, vector=vector, checked=False)
            for vector in queries
        ]

    async with module.inside(engine, schema=corpus.schema) as connection:
        return list(
            await module.sweep(
                connection,
                model=model,
                configuration=configuration,
                queries=queries,
                truths=truths,
            )
        )
