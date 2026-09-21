"""Reconciling the media root with the store, and never with an upload in flight."""

import asyncio
import io
import os
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.main import create_app
from app.services import assets as assets_service
from app.services.prune import FILE_MISSING, prune
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"
LONG_AGO = 7 * 24 * 3600


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
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
def storage(media_root: Path) -> MediaStorage:
    return MediaStorage.at(media_root)


@pytest.fixture
def app(db_settings: Settings, media_root: Path) -> FastAPI:
    return create_app(db_settings.model_copy(update={"media_root": media_root}))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def prune_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session of its own: prune is a separate process in real life."""
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


def age(path: Path, seconds: int = LONG_AGO) -> None:
    moment = time.time() - seconds
    os.utime(path, (moment, moment))


async def upload(client: httpx.AsyncClient, seed: int = 0) -> dict[str, object]:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_an_orphan_file_is_reported_and_only_removed_when_asked(
    client: httpx.AsyncClient, prune_session: AsyncSession, storage: MediaStorage
) -> None:
    await upload(client)
    orphan = storage.root / "ab" / "abandoned.png"
    orphan.parent.mkdir(exist_ok=True)
    orphan.write_bytes(b"left behind")
    age(orphan)

    dry = await prune(prune_session, storage, min_age_seconds=3600, apply=False)

    assert dry.ran is True
    assert dry.orphan_files == (orphan,)
    assert orphan.exists(), "a dry run changes nothing"

    applied = await prune(prune_session, storage, min_age_seconds=3600, apply=True)

    assert applied.removed_files == (orphan,)
    assert not orphan.exists()


async def test_a_staged_file_left_behind_is_an_orphan(
    prune_session: AsyncSession, storage: MediaStorage
) -> None:
    from uuid import uuid4

    staged = storage.stage(uuid4())
    storage.fill(staged, [b"half an upload"])
    age(staged)

    report = await prune(prune_session, storage, min_age_seconds=3600, apply=True)

    assert report.orphan_files == (staged,)
    assert not staged.exists()


async def test_a_young_orphan_is_ignored_and_counted(
    prune_session: AsyncSession, storage: MediaStorage
) -> None:
    fresh = storage.root / "cd"
    fresh.mkdir()
    (fresh / "just-written.png").write_bytes(b"new")

    report = await prune(prune_session, storage, min_age_seconds=3600, apply=True)

    assert report.orphan_files == ()
    assert report.ignored_young == 1
    assert (fresh / "just-written.png").exists()


async def test_an_asset_whose_file_is_gone_is_reported_and_its_work_failed(
    client: httpx.AsyncClient,
    prune_session: AsyncSession,
    storage: MediaStorage,
    engine: AsyncEngine,
) -> None:
    created = await upload(client)
    asset_id = str(created["id"])
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO indexing_jobs (asset_id, model, status) "
                "VALUES (:asset_id, 'clip-vit-l14', 'pending')"
            ),
            {"asset_id": asset_id},
        )
    (storage.root / asset_id[:2] / f"{asset_id}.png").unlink()

    dry = await prune(prune_session, storage, min_age_seconds=0, apply=False)
    assert [str(one) for one in dry.assets_missing_files] == [asset_id]

    async with engine.connect() as connection:
        still_pending = (
            await connection.execute(sa.text("SELECT status FROM indexing_jobs"))
        ).scalar_one()
    assert still_pending == "pending", "a dry run changes no row"

    applied = await prune(prune_session, storage, min_age_seconds=0, apply=True)

    assert applied.failed_jobs == 1
    async with engine.connect() as connection:
        status, error = (
            await connection.execute(sa.text("SELECT status, last_error FROM indexing_jobs"))
        ).one()
    assert (status, error) == ("failed", FILE_MISSING)


async def test_a_healthy_store_reports_nothing(
    client: httpx.AsyncClient, prune_session: AsyncSession, storage: MediaStorage
) -> None:
    await upload(client)
    for path, _ in storage.walk():
        age(path)

    report = await prune(prune_session, storage, min_age_seconds=3600, apply=True)

    assert report.clean
    assert len(list(storage.walk())) == 2


async def test_prune_does_not_run_while_an_upload_is_in_flight(
    client: httpx.AsyncClient,
    prune_session: AsyncSession,
    storage: MediaStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason the lock exists. No time bound anywhere: the upload is held
    until prune has finished, and the grace period is set to zero so that it
    cannot be what protects the files.
    """
    published = threading.Event()
    release = threading.Event()
    publish_files = assets_service.publish_files

    def hold_after_publishing(*args: object, **kwargs: object) -> None:
        publish_files(*args, **kwargs)  # type: ignore[arg-type]
        published.set()
        assert release.wait(timeout=60), "the test never released the upload"

    monkeypatch.setattr(assets_service, "publish_files", hold_after_publishing)
    upload_in_flight = asyncio.create_task(
        client.post(ASSETS, files={"file": ("p.png", picture_bytes())})
    )
    await asyncio.to_thread(published.wait, 30)
    assert len(list(storage.walk())) == 2, "both files are published, the row is not written"

    report = await prune(prune_session, storage, min_age_seconds=0, apply=True)

    assert report.ran is False, "prune must not act while an upload is in flight"
    assert report.removed_files == ()
    assert len(list(storage.walk())) == 2

    release.set()
    response = await upload_in_flight
    assert response.status_code == 201
    assert len(list(storage.walk())) == 2, "the upload kept its files"
