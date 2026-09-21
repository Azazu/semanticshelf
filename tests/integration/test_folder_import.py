"""Importing a folder: what is stored, what is refused, and what is reported.

The store is what decides a duplicate and what enforces the value domains, so
these need the real database. The walk itself — which files are considered and
which are refused before anything is opened — is a unit test.
"""

import io
import json
import os
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.fake import FakeEmbedder
from app.ml.pool import create_pool
from app.services import folder, indexing
from app.services.folder import ALREADY_STORED, CREATED, REFUSED, SKIPPED, SOURCE_PATH_KEY
from app.services.tagging import METADATA_MAX_BYTES, TagError
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(seed: int = 0, size: tuple[int, int] = (400, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(seed % 255, 90, 200)).save(buffer, format="PNG")
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
def storage(media_root: Path) -> MediaStorage:
    return MediaStorage.at(media_root)


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
def incoming(tmp_path: Path) -> Path:
    directory = tmp_path / "incoming"
    directory.mkdir()
    return directory


async def rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        return list(
            (
                await connection.execute(
                    sa.text(
                        "SELECT id, sha256, content_type, width, height, size_bytes, source, "
                        "original_filename, tags, meta FROM assets ORDER BY created_at"
                    )
                )
            ).all()
        )


# --- the pipeline, through the other entrance ---------------------------------


async def test_an_imported_asset_matches_the_same_picture_uploaded(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    client: httpx.AsyncClient,
    engine: AsyncEngine,
) -> None:
    """The same bytes through both entrances, compared field by field. The
    import's asset is deleted in between, because identical bytes are one
    asset — which is itself the rule under test everywhere else."""
    data = picture_bytes()
    (incoming / "picture.png").write_bytes(data)

    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )

    assert [outcome.state for outcome in report.files] == [CREATED]
    imported = (await rows(engine))[0]
    assert (await client.delete(f"{ASSETS}/{imported.id}")).status_code == 204

    response = await client.post(ASSETS, files={"file": ("picture.png", data)})
    assert response.status_code == 201, response.text
    uploaded = (await rows(engine))[0]

    same = ("sha256", "content_type", "width", "height", "size_bytes", "original_filename", "tags")
    assert {field: getattr(imported, field) for field in same} == {
        field: getattr(uploaded, field) for field in same
    }
    assert (imported.source, uploaded.source) == ("folder", "upload")
    assert imported.meta == {SOURCE_PATH_KEY: "picture.png"}
    assert uploaded.meta == {}


async def test_an_imported_asset_has_its_work_queued(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "picture.png").write_bytes(picture_bytes())

    await folder.import_folder(incoming, session=session, storage=storage, settings=settings)

    async with engine.connect() as connection:
        jobs = (await connection.execute(sa.text("SELECT model, status FROM indexing_jobs"))).all()
    assert [(model, status) for model, status in jobs] == [(CLIP_VIT_L14, "pending")]


async def test_a_picture_in_a_subdirectory_records_where_it_came_from(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "trip" / "day-one").mkdir(parents=True)
    (incoming / "trip" / "day-one" / "dragon.png").write_bytes(picture_bytes())

    await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings, recursive=True
    )

    stored = (await rows(engine))[0]
    assert stored.original_filename == "dragon.png", "one name, no directory in it"
    assert stored.meta == {SOURCE_PATH_KEY: "trip/day-one/dragon.png"}


async def test_the_run_metadata_cannot_replace_the_recorded_origin(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "picture.png").write_bytes(picture_bytes())

    await folder.import_folder(
        incoming,
        session=session,
        storage=storage,
        settings=settings,
        meta={SOURCE_PATH_KEY: "../etc/passwd", "origin": "handbook"},
    )

    stored = (await rows(engine))[0]
    assert stored.meta == {SOURCE_PATH_KEY: "picture.png", "origin": "handbook"}


async def test_the_run_tags_and_metadata_reach_every_asset(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    for index, name in enumerate(("one.png", "two.png")):
        (incoming / name).write_bytes(picture_bytes(seed=index + 1))

    await folder.import_folder(
        incoming,
        session=session,
        storage=storage,
        settings=settings,
        tags=[" Dragon ", "BLUE", "dragon"],
        meta={"origin": "handbook"},
    )

    stored = await rows(engine)
    assert [row.tags for row in stored] == [["dragon", "blue"], ["dragon", "blue"]]
    assert all(row.meta["origin"] == "handbook" for row in stored)


# --- what the run refuses before it starts ------------------------------------


async def test_a_tag_the_service_refuses_stops_the_run_before_it_reads_anything(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
    media_root: Path,
) -> None:
    (incoming / "picture.png").write_bytes(picture_bytes())

    with pytest.raises(TagError, match="not a tag"):
        await folder.import_folder(
            incoming, session=session, storage=storage, settings=settings, tags=["not a tag!"]
        )

    assert await rows(engine) == []
    assert [path for path in media_root.rglob("*") if path.is_file()] == []


async def test_a_recorded_path_that_breaks_the_metadata_bound_refuses_that_file_alone(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    """The bound is on the metadata, and the recorded path is part of it. A
    path long enough on its own is impossible — a filesystem stops at 4 KiB —
    so what this shows is the straw: the same run's metadata fits for a file at
    the top and does not fit for the one two directories down."""
    buried = incoming / "photos" / "spring"
    buried.mkdir(parents=True)
    (buried / "a-rather-long-picture-name.png").write_bytes(picture_bytes(seed=1))
    (incoming / "short.png").write_bytes(picture_bytes(seed=2))
    long_path = "photos/spring/a-rather-long-picture-name.png"
    overhead = len(
        json.dumps({"pad": "", SOURCE_PATH_KEY: long_path}, separators=(",", ":")).encode("utf-8")
    )
    padding = "x" * (METADATA_MAX_BYTES - overhead + 1)

    report = await folder.import_folder(
        incoming,
        session=session,
        storage=storage,
        settings=settings,
        recursive=True,
        meta={"pad": padding},
    )

    outcomes = {str(outcome.path): outcome for outcome in report.files}
    assert outcomes[long_path].state == REFUSED
    reason = outcomes[long_path].reason
    assert reason is not None and "meta must be at most" in reason
    assert outcomes["short.png"].state == CREATED, "the run went on"
    assert [row.original_filename for row in await rows(engine)] == ["short.png"]


# --- what the pipeline refuses -------------------------------------------------


async def test_a_zero_byte_file_is_refused_as_an_upload_of_nothing_is(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "empty.png").write_bytes(b"")

    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )

    assert [(outcome.state, outcome.reason) for outcome in report.files] == [
        (REFUSED, "the file does not decode as an image")
    ]
    assert await rows(engine) == []


async def test_the_same_bytes_twice_in_one_folder_make_one_asset(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    data = picture_bytes()
    (incoming / "first.png").write_bytes(data)
    (incoming / "second.png").write_bytes(data)

    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )

    assert [outcome.state for outcome in report.files] == [CREATED, ALREADY_STORED]
    assert len(await rows(engine)) == 1


async def test_a_run_over_the_same_folder_twice_creates_nothing_the_second_time(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "picture.png").write_bytes(picture_bytes())
    await folder.import_folder(incoming, session=session, storage=storage, settings=settings)

    again = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )

    assert [outcome.state for outcome in again.files] == [ALREADY_STORED]
    assert len(await rows(engine)) == 1


# --- the report ---------------------------------------------------------------


async def test_a_mixed_folder_is_accounted_for_file_by_file(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))
    (incoming / "stored.png").write_bytes(picture_bytes(seed=2))
    (incoming / "lying.png").write_bytes(b"not a picture at all")
    (incoming / "notes.txt").write_bytes(b"a document")
    os.mkfifo(incoming / "pipe.png")
    # One of them is stored before the run, so the import must find it there.
    (incoming.parent / "seed").mkdir()
    (incoming.parent / "seed" / "stored.png").write_bytes(picture_bytes(seed=2))
    await folder.import_folder(
        incoming.parent / "seed", session=session, storage=storage, settings=settings
    )

    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )

    assert {str(outcome.path): outcome.state for outcome in report.files} == {
        "good.png": CREATED,
        "stored.png": ALREADY_STORED,
        "lying.png": REFUSED,
        "notes.txt": SKIPPED,
        "pipe.png": SKIPPED,
    }
    assert report.count(CREATED) == 1
    assert [outcome.reason for outcome in report.files if outcome.state == SKIPPED] == [
        folder.SKIP_NO_PICTURE_SUFFIX,
        folder.SKIP_NOT_REGULAR,
    ]
    assert len(report.created_assets) == 1


# --- the dry run --------------------------------------------------------------


async def snapshot(engine: AsyncEngine, media_root: Path) -> tuple[Any, ...]:
    """Everything a run could change: the store's three tables and every byte
    under the media root."""
    async with engine.connect() as connection:
        tables = []
        for table in ("assets", "embeddings", "indexing_jobs"):
            result = await connection.execute(sa.text(f"SELECT * FROM {table} ORDER BY id"))
            tables.append(tuple(result.all()))
    files = tuple(
        (str(path.relative_to(media_root)), path.read_bytes())
        for path in sorted(media_root.rglob("*"))
        if path.is_file()
    )
    return (*tables, files)


async def mixed_folder(incoming: Path) -> None:
    (incoming / "fresh.png").write_bytes(picture_bytes(seed=1))
    (incoming / "stored.png").write_bytes(picture_bytes(seed=2))
    (incoming / "lying.png").write_bytes(b"not a picture at all")
    (incoming / "notes.txt").write_bytes(b"a document")


async def test_a_dry_run_changes_nothing_at_all(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
    media_root: Path,
    tmp_path: Path,
) -> None:
    await mixed_folder(incoming)
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "stored.png").write_bytes(picture_bytes(seed=2))
    await folder.import_folder(seed, session=session, storage=storage, settings=settings)
    before = await snapshot(engine, media_root)

    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings, dry_run=True
    )

    assert await snapshot(engine, media_root) == before, "a dry run writes nothing"
    assert {str(outcome.path): outcome.state for outcome in report.files} == {
        "fresh.png": CREATED,
        "stored.png": ALREADY_STORED,
        "lying.png": REFUSED,
        "notes.txt": SKIPPED,
    }
    assert report.dry_run is True
    assert report.created_assets == [], "nothing was created, so nothing is named"


async def test_a_dry_run_says_what_the_real_run_then_does(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    tmp_path: Path,
) -> None:
    await mixed_folder(incoming)
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "stored.png").write_bytes(picture_bytes(seed=2))
    await folder.import_folder(seed, session=session, storage=storage, settings=settings)

    rehearsal = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings, dry_run=True
    )
    real = await folder.import_folder(incoming, session=session, storage=storage, settings=settings)

    def verdicts(report: folder.ImportReport) -> dict[str, tuple[str, str | None]]:
        return {str(one.path): (one.state, one.reason) for one in report.files}

    assert verdicts(rehearsal) == verdicts(real)


async def test_a_run_leaves_the_session_as_it_found_it(
    incoming: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
) -> None:
    """A read that left a transaction open would make the next run — or the
    next file — unable to begin one. It has cost this project three sessions;
    here it is a test."""
    await mixed_folder(incoming)

    await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings, dry_run=True
    )
    assert not session.in_transaction(), "after a dry run"

    await folder.import_folder(incoming, session=session, storage=storage, settings=settings)
    assert not session.in_transaction(), "after a real run"


# --- finishing the work the import created ------------------------------------


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = create_pool(settings)
    yield executor
    executor.shutdown(wait=True)


def breaking_embedder() -> None:
    """Make the model fail, whatever it is handed."""

    def refuse(images: Any) -> Any:
        raise RuntimeError("the model fell over")

    embedder = FakeEmbedder(CLIP_VIT_L14, dimension_of(CLIP_VIT_L14))
    embedder.embed_images = refuse  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: embedder
    registry.clear()


async def vectors(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = (await connection.execute(sa.text("SELECT asset_id FROM embeddings"))).scalars()
        return {str(one) for one in rows}


async def test_an_import_finishes_its_own_work_and_not_the_queue_s(
    incoming: Path,
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """A queue holding more older work than a batch can take must not be able
    to swallow the passes this import needs."""
    older = tmp_path / "older"
    older.mkdir()
    for seed in range(1, 7):
        (older / f"old-{seed}.png").write_bytes(picture_bytes(seed=seed))
    await folder.import_folder(older, session=session, storage=storage, settings=settings)
    for seed in (20, 21):
        (incoming / f"mine-{seed}.png").write_bytes(picture_bytes(seed=seed))
    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )
    mine = {str(asset_id) for asset_id in report.created_assets}
    assert len(mine) == 2

    work = await folder.index_imported(
        report, session_factory=sessions, storage=storage, settings=settings, pool=pool
    )

    assert work.indexed == 2
    assert (work.queued, work.failed) == ([], [])
    assert await vectors(engine) == mine, "only this run's work was carried out"
    async with engine.connect() as connection:
        waiting = (
            await connection.execute(
                sa.text("SELECT count(*) FROM indexing_jobs WHERE status = 'pending'")
            )
        ).scalar_one()
    assert waiting == 6, "the older queue is exactly as it was"


async def test_work_that_will_be_attempted_again_is_reported_as_queued(
    incoming: Path,
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The queue puts a failed attempt back with a growing delay; the import
    reports that rather than sleeping through it — and stops as soon as there
    is nothing of its own to claim, rather than spinning to its pass bound."""
    (incoming / "picture.png").write_bytes(picture_bytes())
    report = await folder.import_folder(
        incoming, session=session, storage=storage, settings=settings
    )
    breaking_embedder()
    passes = 0
    claiming = indexing.run_batch

    async def counted(**arguments: Any) -> int:
        nonlocal passes
        passes += 1
        return await claiming(**arguments)

    monkeypatch.setattr(indexing, "run_batch", counted)
    started = time.monotonic()

    work = await folder.index_imported(
        report, session_factory=sessions, storage=storage, settings=settings, pool=pool
    )

    assert time.monotonic() - started < 5, "it did not wait out the backoff"
    assert passes <= 2, (
        f"it claimed {passes} times: a pass that takes nothing ends the wait, "
        "rather than running to the bound"
    )
    assert work.indexed == 0
    assert work.failed == []
    assert work.queued == [(report.created_assets[0], folder.QUEUED_WAITING)]
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                sa.text("SELECT status, attempts, available_at > now() AS later FROM indexing_jobs")
            )
        ).one()
    assert (row.status, row.attempts, row.later) == ("pending", 1, True)


async def test_work_whose_attempts_are_spent_is_reported_as_failed(
    incoming: Path,
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
) -> None:
    (incoming / "picture.png").write_bytes(picture_bytes())
    spent = settings.model_copy(update={"job_max_attempts": 1})
    report = await folder.import_folder(incoming, session=session, storage=storage, settings=spent)
    breaking_embedder()

    work = await folder.index_imported(
        report, session_factory=sessions, storage=storage, settings=spent, pool=pool
    )

    assert work.indexed == 0
    assert work.queued == []
    assert work.failed == [(report.created_assets[0], "RuntimeError")]


async def test_the_three_states_of_the_work_are_reported_apart(
    incoming: Path,
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))
    (incoming / "doomed.png").write_bytes(picture_bytes(seed=2))
    (incoming / "held.png").write_bytes(picture_bytes(seed=3))
    spent = settings.model_copy(update={"job_max_attempts": 1})
    report = await folder.import_folder(incoming, session=session, storage=storage, settings=spent)
    # The walk is sorted, so the ids come back in name order; ask by name.
    by_name = {outcome.path.name: outcome.asset_id for outcome in report.files}
    good, doomed, held = by_name["good.png"], by_name["doomed.png"], by_name["held.png"]
    assert good is not None and doomed is not None and held is not None

    # Another runner takes one of them and keeps it: a valid lease is not
    # reclaimable, so this import can only report it.
    holder = await indexing.claim(sessions, spent, asset_ids=[held])
    assert len(holder) == 1
    # The first picture succeeds, the second does not.
    real = FakeEmbedder(CLIP_VIT_L14, dimension_of(CLIP_VIT_L14))
    original = real.embed_images

    def sometimes(pictures: Any) -> Any:
        if any(
            picture.size == (400, 200) and picture.getpixel((0, 0))[0] == 2 for picture in pictures
        ):
            raise RuntimeError("the model fell over")
        return original(pictures)

    real.embed_images = sometimes  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: real
    registry.clear()

    work = await folder.index_imported(
        report, session_factory=sessions, storage=storage, settings=spent, pool=pool
    )

    assert work.indexed == 1
    assert work.failed == [(doomed, "RuntimeError")]
    assert work.queued == [(held, folder.QUEUED_HELD)]
    assert good not in [asset for asset, _ in work.queued + work.failed]
