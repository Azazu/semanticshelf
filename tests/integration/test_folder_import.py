"""Importing a folder: what is stored, what is refused, and what is reported.

The store is what decides a duplicate and what enforces the value domains, so
these need the real database. The walk itself — which files are considered and
which are refused before anything is opened — is a unit test.
"""

import io
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14
from app.main import create_app
from app.services import folder
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
