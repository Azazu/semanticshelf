"""Deleting a key's vectors, and every reason not to.

The deletion is irreversible and the pictures it describes are still there, so
the guards matter more than the act: coverage tested inside the deleting
statement, both keys' queue locks held across it, nothing owed by the queue, and
an operator who said the word. Each of those has a test that watches it refuse.
"""

import asyncio
import io
from collections.abc import AsyncIterator, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner, Result

from app.cli import app as cli
from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.main import create_app
from app.ml.pool import create_pool
from app.repositories import EmbeddingRepository
from app.repositories.jobs import IndexingJobRepository
from app.services import indexing
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"
BOTH = (CLIP_VIT_L14, DINOV2_LARGE)


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
    """Both keys: a retirement is about one replacing the other."""
    return db_settings.model_copy(update={"media_root": media_root, "enabled_models": BOTH})


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def storage(media_root: Path) -> MediaStorage:
    return MediaStorage.at(media_root)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = create_pool(settings)
    yield executor
    executor.shutdown(wait=True)


async def upload(client: httpx.AsyncClient, seed: int) -> str:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            sa.text("SELECT model, count(*) FROM embeddings GROUP BY model")
        )
    return {model: count for model, count in rows}


async def drain_queue(engine: AsyncEngine) -> None:
    """Every upload leaves its work done; this clears the rows so a retirement
    sees a queue that owes nothing."""
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM indexing_jobs"))


async def run_cli(arguments: Sequence[str], settings: Settings) -> Result:
    environment = {
        "DATABASE_URL": settings.database_url,
        "MEDIA_ROOT": str(settings.media_root),
        "ENABLED_MODELS": ",".join(settings.enabled_models),
        "LOG_LEVEL": "warning",
    }
    return await asyncio.to_thread(CliRunner().invoke, cli, list(arguments), env=environment)


# --- when it goes ahead ---------------------------------------------------------


async def test_a_complete_replacement_retires_and_touches_nothing_else(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await upload(client, 1)
    await upload(client, 2)
    await drain_queue(engine)
    assert await counts(engine) == {CLIP_VIT_L14: 2, DINOV2_LARGE: 2}

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert await counts(engine) == {DINOV2_LARGE: 2}
    assert any("retired: 2 vector(s)" in line for line in lines), lines
    async with engine.connect() as connection:
        assets = (await connection.execute(sa.text("SELECT count(*) FROM assets"))).scalar_one()
    assert assets == 2, "the pictures are not the vectors"


async def test_retiring_says_the_key_is_still_enabled(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Deleting vectors is not disabling a key — the next upload would queue
    work for it again, and the setting is the operator's to change."""
    await upload(client, 1)
    await drain_queue(engine)

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert any("still enabled" in line and "ENABLED_MODELS" in line for line in lines), lines


async def test_retiring_touches_neither_the_settings_nor_the_schema(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await upload(client, 1)
    await drain_queue(engine)
    before = settings.enabled_models

    await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert settings.enabled_models == before
    async with engine.connect() as connection:
        constraints = (
            await connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conrelid = 'embeddings'::regclass AND contype = 'c'"
                )
            )
        ).scalar_one()
    assert constraints >= 1, "the schema's allowlist is a migration, not this command's business"


# --- when it refuses ------------------------------------------------------------


async def test_an_incomplete_replacement_deletes_nothing_and_says_how_many(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await upload(client, 1)
    await upload(client, 2)
    await drain_queue(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE model = :model"), {"model": DINOV2_LARGE}
        )

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert await counts(engine) == {CLIP_VIT_L14: 2}
    assert any("refused" in line and "2 asset(s)" in line for line in lines), lines


async def test_a_queue_that_owes_work_refuses_even_when_coverage_holds(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """A count taken while work is outstanding describes a corpus that is still
    changing, which is not a corpus anyone can vouch for."""
    await upload(client, 1)
    await drain_queue(engine)
    async with sessions() as session, session.begin():
        await IndexingJobRepository(session).queue_rebuild(model=DINOV2_LARGE)

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert await counts(engine) == {CLIP_VIT_L14: 1, DINOV2_LARGE: 1}
    assert any("outstanding" in line for line in lines), lines


async def test_an_asset_that_gained_the_old_key_after_the_fill_refuses(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Covered when the fill ended and not at the moment of the delete. The
    count lives inside the deleting statement for exactly this."""
    await upload(client, 1)
    await upload(client, 2)
    await drain_queue(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "DELETE FROM embeddings WHERE model = :model AND asset_id IN "
                "(SELECT asset_id FROM embeddings WHERE model = :model LIMIT 1)"
            ),
            {"model": DINOV2_LARGE},
        )

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert (await counts(engine))[CLIP_VIT_L14] == 2, "nothing was deleted"
    assert any("refused" in line for line in lines), lines


async def test_apply_without_retire_deletes_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings
) -> None:
    """Filling is additive and deleting is not, so they are separate words."""
    await upload(client, 1)
    await drain_queue(engine)

    result = await run_cli(["models", "migrate", CLIP_VIT_L14, DINOV2_LARGE, "--apply"], settings)

    assert result.exit_code == 0, result.output
    assert (await counts(engine))[CLIP_VIT_L14] == 1
    assert "retired" not in result.output


async def test_a_plan_says_what_a_retirement_would_do(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings
) -> None:
    await upload(client, 1)
    await drain_queue(engine)

    result = await run_cli(["models", "migrate", CLIP_VIT_L14, DINOV2_LARGE, "--retire"], settings)

    assert "retirement: would delete" in result.output, result.output
    assert (await counts(engine))[CLIP_VIT_L14] == 1, "a plan deletes nothing"


# --- two retirements at once ----------------------------------------------------


async def test_two_retirements_in_opposite_directions_cannot_undo_each_other(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """The case a statement snapshot does not cover: each sees itself covered,
    they delete disjoint rows, and the asset is left with neither vector.

    Both take the same two locks in the same order, so one goes first and the
    second finds the corpus the first left.
    """
    await upload(client, 1)
    await drain_queue(engine)
    assert await counts(engine) == {CLIP_VIT_L14: 1, DINOV2_LARGE: 1}

    first, second = await asyncio.gather(
        indexing.retire(
            session_factory=sessions,
            settings=settings,
            key=CLIP_VIT_L14,
            replaced_by=DINOV2_LARGE,
        ),
        indexing.retire(
            session_factory=sessions,
            settings=settings,
            key=DINOV2_LARGE,
            replaced_by=CLIP_VIT_L14,
        ),
    )

    remaining = await counts(engine)
    assert sum(remaining.values()) == 1, (
        f"one key survives; the asset is not left with nothing: {remaining}, {first}, {second}"
    )
    assert any("refused" in line for line in (*first, *second)), (first, second)


async def test_the_deleting_statement_deletes_nothing_when_it_is_not_covered(
    client: httpx.AsyncClient, engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The condition is part of the DELETE, not only of the service that calls it.

    The service refuses first, so its own test never reaches this statement —
    and the statement is where the guarantee lives: tested earlier and acted on
    later it is a race, which is the whole reason it was put there.
    """
    await upload(client, 1)
    await upload(client, 2)
    await drain_queue(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE model = :model"), {"model": DINOV2_LARGE}
        )

    async with sessions() as session, session.begin():
        removed = await EmbeddingRepository(session).retire(
            key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
        )

    assert removed == 0
    assert (await counts(engine))[CLIP_VIT_L14] == 2


async def test_the_deleting_statement_removes_what_is_covered(
    client: httpx.AsyncClient, engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await upload(client, 1)
    await drain_queue(engine)

    async with sessions() as session, session.begin():
        removed = await EmbeddingRepository(session).retire(
            key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
        )

    assert removed == 1
    assert await counts(engine) == {DINOV2_LARGE: 1}


async def test_a_retirement_waits_while_another_holds_the_same_locks(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """The serialisation itself, without racing for it.

    Two retirements in opposite directions take the same two locks in the same
    order, so one waits for the other rather than both reading a corpus that the
    other is about to change. Here the first pair of locks is simply held open,
    and the retirement that wants them has to wait — which is what "they cannot
    undo each other" means mechanically.
    """
    await upload(client, 1)
    await drain_queue(engine)

    async with sessions() as holder, holder.begin():
        await IndexingJobRepository(holder).lock_models(sorted({CLIP_VIT_L14, DINOV2_LARGE}))

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                indexing.retire(
                    session_factory=sessions,
                    settings=settings,
                    key=DINOV2_LARGE,
                    replaced_by=CLIP_VIT_L14,
                ),
                timeout=1.0,
            )
        assert await counts(engine) == {CLIP_VIT_L14: 1, DINOV2_LARGE: 1}

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=DINOV2_LARGE, replaced_by=CLIP_VIT_L14
    )

    assert any("retired: 1 vector(s)" in line for line in lines), lines


async def test_a_retirement_says_so_when_the_statement_refuses_where_the_read_did_not(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window nothing can close, made deterministic.

    Claiming, finishing and upserting a vector take none of the retirement's
    locks, so an old-key job can land between the service's coverage reading and
    the deleting statement. The statement's own condition then refuses — and a
    report that announced `retired: 0 vector(s)` over a key it did not touch
    would be the worst possible answer.

    Here the reading is made to say "covered" while the corpus is not, which is
    exactly what that interval looks like from the service's side.
    """
    await upload(client, 1)
    await upload(client, 2)
    await drain_queue(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("DELETE FROM embeddings WHERE model = :model"), {"model": DINOV2_LARGE}
        )
    truth = EmbeddingRepository.uncovered
    calls = {"n": 0}

    async def covered_the_first_time(self: EmbeddingRepository, **keywords: str) -> int:
        calls["n"] += 1
        return 0 if calls["n"] == 1 else await truth(self, **keywords)

    monkeypatch.setattr(EmbeddingRepository, "uncovered", covered_the_first_time)

    lines = await indexing.retire(
        session_factory=sessions, settings=settings, key=CLIP_VIT_L14, replaced_by=DINOV2_LARGE
    )

    assert (await counts(engine))[CLIP_VIT_L14] == 2, "the statement refused"
    assert any("corpus changed while this ran" in line for line in lines), lines
    assert not any("retired:" in line for line in lines), lines
