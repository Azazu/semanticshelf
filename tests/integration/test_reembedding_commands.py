"""Rebuilding a key, and filling one from another.

The engine under both commands is the same, and what is new in it is what these
tests are about: it carries out the work its selection **already had
outstanding**, not only the work it queued. The existing fill does not, which is
why a run interrupted halfway used to be finished by nobody.

Everything here runs against a real store and the deterministic stand-ins; no
weights are loaded.
"""

import asyncio
import io
from collections.abc import AsyncIterator, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner, Result

from app.cli import app as cli
from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, WORKER_RUNNER, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import normalise
from app.ml.fake import FakeEmbedder, vector_for
from app.ml.pool import create_pool
from app.repositories.jobs import IndexingJobRepository
from app.services import indexing
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def settings(db_settings: Settings, media_root: Path) -> Settings:
    return db_settings.model_copy(update={"media_root": media_root})


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
def storage(media_root: Path) -> MediaStorage:
    return MediaStorage.at(media_root)


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = create_pool(settings)
    yield executor
    executor.shutdown(wait=True)


class OtherCheckpoint(FakeEmbedder):
    """The same key, answering with different weights.

    What a checkpoint that moved looks like from the outside: the key is
    unchanged, the width is unchanged, and every vector is different. Nothing in
    the store can tell the two apart, which is the whole reason ADR-007 exists.
    """

    def _vectors(self, labels: Sequence[str]) -> np.ndarray:
        if not labels:
            return super()._vectors(labels)
        return normalise(np.stack([vector_for("moved:" + label, self.dim) for label in labels]))


@contextmanager
def moved_checkpoint() -> Iterator[None]:
    """Point the registry at the other checkpoint, from here on.

    A context manager rather than a fixture, and used around the repair alone:
    installed before the upload it would answer for both, and a test in which
    the corpus was written with the same weights it is repaired to proves
    nothing.
    """
    original = dict(registry.FACTORIES)
    registry.clear()
    registry.FACTORIES[CLIP_VIT_L14] = lambda _: OtherCheckpoint(
        CLIP_VIT_L14, dimension_of(CLIP_VIT_L14)
    )
    try:
        yield
    finally:
        registry.FACTORIES.clear()
        registry.FACTORIES.update(original)
        registry.clear()


def _parsed(raw: object) -> list[float]:
    """pgvector comes back as its text form over a raw connection."""
    return [float(part) for part in str(raw).strip("[]").split(",")]


def vectors_of_label(key: str, asset_id: object, *, moved: bool = False) -> np.ndarray:
    """What a checkpoint would answer for the picture this asset holds.

    The stand-ins derive a vector from the image's label, and every upload here
    uses the same picture, so the expected answer is computable without running
    anything — which is what makes "the repaired vector is the new
    checkpoint's" an assertion rather than a comparison with itself.
    """
    del asset_id
    embedder = (
        OtherCheckpoint(key, dimension_of(key)) if moved else FakeEmbedder(key, dimension_of(key))
    )
    return embedder.embed_images([Image.open(io.BytesIO(picture_bytes(1)))]).vectors[0]


async def upload(client: httpx.AsyncClient, seed: int) -> str:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def vectors_of(engine: AsyncEngine, model: str) -> dict[str, str]:
    """Each stored vector in the text form a raw connection hands back.

    Kept as text on purpose: two of them are compared for equality, and the
    string is the exact value the column holds.
    """
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT asset_id, vector FROM embeddings WHERE model = :model"),
            {"model": model},
        )
    return {str(asset_id): str(vector) for asset_id, vector in rows}


async def states(engine: AsyncEngine, model: str) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT status FROM indexing_jobs WHERE model = :model ORDER BY created_at"),
            {"model": model},
        )
    return [status for (status,) in rows]


# --- a rebuild replaces what is there ------------------------------------------


async def test_a_rebuild_replaces_a_vector_rather_than_adding_one(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    before = await vectors_of(engine, CLIP_VIT_L14)
    assert len(before) == 1

    with moved_checkpoint():
        report = await indexing.rebuild(
            session_factory=sessions,
            storage=storage,
            settings=settings,
            pool=pool,
            model=CLIP_VIT_L14,
        )

    after = await vectors_of(engine, CLIP_VIT_L14)
    assert len(after) == 1, "a rebuild replaces a row, it does not add one"
    assert list(before) == list(after)
    assert after != before, "the weights moved, so the vector must have"
    assert report.work is not None and report.work.indexed == 1
    assert report.complete


async def test_a_run_finishes_what_an_interrupted_one_left(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """The hole the existing fill has: its selection passes over assets whose
    work is already waiting, and it drains only what it queued — so after a
    crash it queues nothing, drains nothing, and reports success."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert report.queued == [], "the work was already there"
    assert len(report.carried_over) == 1, "and this run carried it out"
    assert report.work is not None and report.work.indexed == 1
    assert await states(engine, CLIP_VIT_L14) == ["done", "done"], (
        "the upload's own job, and the rebuild's — both finished"
    )


async def test_work_a_live_claim_holds_is_left_alone_and_reported(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    async with sessions() as session, session.begin():
        repository = IndexingJobRepository(session)
        await repository.queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert len(report.held) == 1
    assert report.carried_over == []
    assert not report.complete, "a run cannot be complete over work somebody else holds"


async def test_a_repair_refuses_to_begin_while_a_live_claim_is_held(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """A process is writing this key now and nothing can say which checkpoint it
    holds — which is the one thing a repair cannot work around."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)

    with pytest.raises(indexing.HeldElsewhere, match="another runner"):
        await indexing.rebuild(
            session_factory=sessions,
            storage=storage,
            settings=settings,
            pool=pool,
            model=CLIP_VIT_L14,
            refuse_while_held=True,
        )


async def test_a_repair_does_not_refuse_on_an_expired_claim(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """An expired claim is what an interrupted repair leaves. Refusing on it
    would make a repair unable to finish itself, which is what the first draft
    of this change did."""
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 minute'")
        )

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
        refuse_while_held=True,
    )

    assert len(report.carried_over) == 1
    assert report.work is not None and report.work.indexed == 1


async def test_failed_work_is_neither_queued_nor_run(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET status = 'failed' WHERE model = :model"),
            {"model": CLIP_VIT_L14},
        )

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert report.queued == []
    assert len(report.skipped_failed) == 1
    assert not report.complete, "only an explicit reset runs failed work again"


# --- which runner carries it out -----------------------------------------------


async def test_a_deployment_with_its_own_runner_queues_and_executes_nothing(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """The rule every other creator of work already follows."""
    await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
    worker_only = settings.model_copy(update={"indexing_runner": WORKER_RUNNER})

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=worker_only,
        pool=pool,
        model=CLIP_VIT_L14,
        index=indexing.carries_out_work(worker_only),
    )

    assert len(report.queued) == 1
    assert report.work is None, "nothing is executed where a runner of its own exists"
    lines = indexing.describe_rebuild(report, settings=worker_only)
    assert any("INDEXING_RUNNER=worker" in line for line in lines), lines


# --- the two sentences, through the command line -------------------------------


async def run_cli(arguments: Sequence[str], settings: Settings) -> Result:
    """The command in a thread of its own, against this test's database.

    It is a synchronous entry point that calls `asyncio.run`, so the test's own
    loop must not be the one it finds.
    """
    environment = {
        "DATABASE_URL": settings.database_url,
        "MEDIA_ROOT": str(settings.media_root),
        "ENABLED_MODELS": ",".join(settings.enabled_models),
        "INDEXING_RUNNER": settings.indexing_runner,
        "LOG_LEVEL": "warning",
    }
    return await asyncio.to_thread(CliRunner().invoke, cli, list(arguments), env=environment)


async def test_a_plan_computes_nothing_and_queues_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings
) -> None:
    """The count is the answer to "can I afford this now", and it is cheap."""
    await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))

    result = await run_cli(["models", "reembed", CLIP_VIT_L14], settings)

    assert result.exit_code == 0, result.output
    assert "vectors to compute: 1" in result.output
    assert "nothing was queued or computed" in result.output
    assert await states(engine, CLIP_VIT_L14) == [], "a plan queues nothing"


async def test_the_plan_s_number_is_what_apply_then_does(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings
) -> None:
    for seed in (1, 2, 3):
        await upload(client, seed)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))

    planned = await run_cli(["models", "reembed", CLIP_VIT_L14], settings)
    applied = await run_cli(["models", "reembed", CLIP_VIT_L14, "--apply"], settings)

    assert "vectors to compute: 3" in planned.output, planned.output
    assert "queued: 3" in applied.output, applied.output
    assert "indexed: 3" in applied.output


async def test_a_key_the_schema_does_not_allow_is_refused(settings: Settings) -> None:
    result = await run_cli(["models", "reembed", "no-such-key"], settings)

    assert result.exit_code == 2
    assert "unknown model key" in result.output


async def test_a_key_this_build_does_not_run_is_refused(settings: Settings) -> None:
    """Its work would be queued and carried out by nobody."""
    one_model = settings.model_copy(update={"enabled_models": (CLIP_VIT_L14,)})

    result = await run_cli(["models", "reembed", DINOV2_LARGE], one_model)

    assert result.exit_code == 2
    assert "not enabled in this build" in result.output


async def test_a_key_cannot_replace_itself(settings: Settings) -> None:
    result = await run_cli(["models", "migrate", CLIP_VIT_L14, CLIP_VIT_L14], settings)

    assert result.exit_code == 2
    assert "cannot replace itself" in result.output
    assert "models reembed" in result.output, "and it says which command does mean that"


async def test_a_replacement_fills_only_what_the_old_key_answers_for(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """A corpus holds assets the old key never answered for either. Pulling them
    in would turn a replacement into a backfill nobody asked for."""
    both = await upload(client, 1)
    neither = await upload(client, 2)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE asset_id = :asset_id"),
            {"asset_id": neither},
        )
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE model = :model"), {"model": DINOV2_LARGE}
        )

    both_keys = settings.model_copy(update={"enabled_models": (CLIP_VIT_L14, DINOV2_LARGE)})
    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=both_keys,
        pool=pool,
        model=DINOV2_LARGE,
        answering_for=CLIP_VIT_L14,
    )

    assert [str(asset_id) for asset_id in report.queued] == [both]
    assert neither not in [str(asset_id) for asset_id in report.queued]


async def test_a_runner_that_wakes_after_its_lease_cannot_undo_the_repair(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """The mechanism the repair's safety rests on, exercised rather than quoted.

    A runner still holding the previous checkpoint claims work and is abandoned.
    Its lease runs out, the repair finishes that work with the new checkpoint,
    and the abandoned runner then tries to finish what it claimed: its result
    matches nothing, because a finish lands only where the lease expiry its own
    claim wrote is still the row's.
    """
    await upload(client, 1)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with sessions() as session, session.begin():
        stale = (await IndexingJobRepository(session).claim(limit=1, lease_seconds=600))[0]
    # What the abandoned runner computed with the weights it still holds: the
    # default stand-in's answer, which is not the moved checkpoint's.
    stale_vector = list(vectors_of_label(CLIP_VIT_L14, stale.job.asset_id))
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET lease_expires_at = now() - interval '1 minute'")
        )
    expected_from_moved_checkpoint = list(
        vectors_of_label(CLIP_VIT_L14, stale.job.asset_id, moved=True)
    )

    with moved_checkpoint():
        report = await indexing.rebuild(
            session_factory=sessions,
            storage=storage,
            settings=settings,
            pool=pool,
            model=CLIP_VIT_L14,
            refuse_while_held=True,
        )
    repaired = await vectors_of(engine, CLIP_VIT_L14)

    # The abandoned runner finishes the way any runner does: one transaction
    # that marks the work done and writes its vector, together. Calling the
    # repository alone would test the ownership check and not the write it
    # guards.
    landed = await indexing.finish(
        indexing.Executed(claimed=stale, vector=tuple(stale_vector)),
        session_factory=sessions,
    )

    assert report.work is not None and report.work.indexed == 1
    assert landed is False, "the abandoned runner is not the owner any more"
    after = await vectors_of(engine, CLIP_VIT_L14)
    assert after == repaired, "and its vector did not land"
    assert expected_from_moved_checkpoint == pytest.approx(
        [float(value) for value in _parsed(next(iter(after.values())))], abs=1e-5
    ), "every vector under the key is the new checkpoint's"


async def test_a_replacement_does_not_drain_the_new_key_s_unrelated_backlog(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """A run recovers its own selection's work and nobody else's.

    An asset the old key never answered for is outside the replacement, and
    finishing its pending job would be expensive work this run's own plan never
    counted — the difference between a replacement and a backfill nobody asked
    for.
    """
    outsider = await upload(client, 2)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE model = :model"), {"model": DINOV2_LARGE}
        )
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE asset_id = :asset_id"), {"asset_id": outsider}
        )
    both_keys = settings.model_copy(update={"enabled_models": (CLIP_VIT_L14, DINOV2_LARGE)})
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).add(asset_id=UUID(outsider), model=DINOV2_LARGE)

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=both_keys,
        pool=pool,
        model=DINOV2_LARGE,
        answering_for=CLIP_VIT_L14,
    )

    assert report.carried_over == [], "the outsider's job is not this run's to carry out"
    async with engine.connect() as connection:
        left = (
            await connection.execute(
                sa.text("SELECT status FROM indexing_jobs WHERE asset_id = :asset_id"),
                {"asset_id": outsider},
            )
        ).scalar_one()
    assert left == "pending", "and it is still waiting for whoever it belongs to"


async def test_a_run_whose_work_fails_terminally_is_not_complete(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    storage: MediaStorage,
    pool: ThreadPoolExecutor,
) -> None:
    """A job that exhausts its attempts during the run lands in `failed`, not in
    `queued` — and a report that printed both "failed: 1" and "complete" would
    be telling an operator the corpus was rebuilt when it was not."""
    asset = await upload(client, 1)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
    media = MediaStorage.at(settings.media_root).original(UUID(asset), "png")
    media.unlink()
    # Queued before the run, with its retries already spent: one more failure is
    # terminal, which is the state this test is about. A fresh job would simply
    # go back to the queue, and "waiting" is not "gave up".
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=CLIP_VIT_L14)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET attempts = :spent"),
            {"spent": settings.job_max_attempts},
        )

    report = await indexing.rebuild(
        session_factory=sessions,
        storage=storage,
        settings=settings,
        pool=pool,
        model=CLIP_VIT_L14,
    )

    assert report.work is not None and report.work.failed, report.work
    assert not report.complete
    lines = indexing.describe_rebuild(report, settings=settings)
    assert any("not complete" in line for line in lines), lines


@pytest.mark.parametrize(
    ("state", "sql"),
    [
        ("pending", "SELECT 1"),
        (
            "expired",
            "UPDATE indexing_jobs SET status = 'running', "
            "lease_expires_at = now() - interval '1 minute'",
        ),
        ("delayed", "UPDATE indexing_jobs SET available_at = now() + interval '1 hour'"),
    ],
)
async def test_a_plan_counts_only_its_own_selection(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings, state: str, sql: str
) -> None:
    """A plan whose counts came from the whole key would promise work the run
    will not do, which is the opposite of what a dry run is for.

    Three shapes of unrelated work, because they are reported on three different
    lines and each could leak in separately.
    """
    outsider = await upload(client, 2)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE asset_id = :asset_id"), {"asset_id": outsider}
        )
        await connection.execute(
            sa.text("INSERT INTO indexing_jobs (asset_id, model) VALUES (:asset_id, :model)"),
            {"asset_id": outsider, "model": CLIP_VIT_L14},
        )
        await connection.execute(sa.text(sql))

    result = await run_cli(["models", "reembed", CLIP_VIT_L14], settings)

    assert "vectors to compute: 0" in result.output, result.output
    assert "already waiting: 0" in result.output, f"{state}: {result.output}"
    assert "retry not yet due" not in result.output, f"{state}: {result.output}"


async def test_a_plan_still_names_a_live_claim_anywhere_on_the_key(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Key-wide on purpose: a repair refuses on any live claim, whichever assets
    it covers, because nothing can say which weights that runner holds."""
    outsider = await upload(client, 2)
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE asset_id = :asset_id"), {"asset_id": outsider}
        )
        await connection.execute(
            sa.text("INSERT INTO indexing_jobs (asset_id, model) VALUES (:asset_id, :model)"),
            {"asset_id": outsider, "model": CLIP_VIT_L14},
        )
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).claim(limit=1, lease_seconds=600)

    result = await run_cli(["models", "reembed", CLIP_VIT_L14], settings)

    assert "already waiting: 0" in result.output, result.output
    assert f"live claims anywhere on {CLIP_VIT_L14}: 1" in result.output, result.output
