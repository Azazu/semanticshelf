"""The demo corpus in the store: the layout it has, and the rule it does not bend.

The pictures are fetched through a stubbed transport — nothing here reaches the
network — and then imported by the ordinary folder import, which is the whole
point: the corpus has no path into the store of its own.
"""

import io
import json
import zipfile
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
from app.services import demo_dataset, folder
from app.services.demo_dataset import MANIFEST_MEMBER, corpus_of
from app.services.folder import ALREADY_STORED, CREATED, SOURCE_PATH_KEY
from app.storage import MediaStorage
from tests.conftest import make_client

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(colour: str = "red") -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(raw, format="PNG")
    return raw.getvalue()


def archive_bytes(identifiers: tuple[int, ...]) -> bytes:
    manifest = {
        "licenses": [
            {
                "id": 4,
                "name": "Attribution License",
                "url": "http://creativecommons.org/licenses/by/2.0/",
            }
        ],
        "images": [{"id": identifier, "license": 4} for identifier in identifiers],
        "categories": [{"id": 1, "name": "traffic light"}],
        "annotations": [{"image_id": identifier, "category_id": 1} for identifier in identifiers],
    }
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as bundle:
        bundle.writestr(MANIFEST_MEMBER, json.dumps(manifest))
    return raw.getvalue()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


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
def downloaded(tmp_path: Path, settings: Settings) -> Path:
    """A corpus of two pictures, fetched exactly as the command fetches one."""
    into = tmp_path / "demo"
    bodies = {1: picture_bytes("red"), 2: picture_bytes("blue")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".zip"):
            return httpx.Response(200, content=archive_bytes((1, 2)))
        identifier = int(Path(request.url.path).stem)
        return httpx.Response(200, content=bodies[identifier])

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with client:
        demo_dataset.download(client, into=into, count=2, settings=settings)
    return into


async def rows(engine: AsyncEngine) -> list[sa.Row[tuple[str, list[str], dict[str, object]]]]:
    async with engine.connect() as connection:
        return list(
            (
                await connection.execute(
                    sa.text("SELECT original_filename, tags, meta FROM assets ORDER BY created_at")
                )
            ).all()
        )


async def test_the_corpus_imports_with_its_provenance(
    downloaded: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    report = await folder.import_folder(
        corpus_of(downloaded),
        session=session,
        storage=storage,
        settings=settings,
        recursive=True,
    )

    assert report.count(CREATED) == 2
    stored = await rows(engine)
    assert [row.original_filename for row in stored] == [
        "000000000001.png",
        "000000000002.png",
    ]
    for row in stored:
        assert list(row.tags) == ["traffic-light"]
        assert row.meta["dataset"] == demo_dataset.DATASET
        assert row.meta["licence"] == "http://creativecommons.org/licenses/by/2.0/"
        assert row.meta["source_url"].startswith(demo_dataset.BASE_URL)
        assert "author" not in row.meta
        assert row.meta[SOURCE_PATH_KEY].endswith(".png")


async def test_neither_the_archive_nor_the_staging_area_is_imported(
    downloaded: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
) -> None:
    """The corpus is one directory under `--into`; the archive and the staging
    area are outside it, so the import is never given them."""
    (downloaded / ".staging" / "leftover.bad").parent.mkdir(exist_ok=True)
    (downloaded / ".staging" / "leftover.png").write_bytes(picture_bytes("green"))

    report = await folder.import_folder(
        corpus_of(downloaded),
        session=session,
        storage=storage,
        settings=settings,
        recursive=True,
    )

    assert report.count(CREATED) == 2
    assert [outcome.path.name for outcome in report.files] == [
        "000000000001.png",
        "000000000002.png",
    ], "nothing from the staging area or the archive reached the import"


async def test_a_picture_already_stored_keeps_what_it_has(
    downloaded: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """The duplicate rule is the content hash and it is global. A picture of the
    corpus whose bytes are already stored is reported and left alone: the import
    does not rewrite an asset it did not create, so the demo provenance lands
    only on the assets it does create.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "mine.png").write_bytes(picture_bytes("red"))  # the same bytes as picture 1
    first = await folder.import_folder(
        elsewhere,
        session=session,
        storage=storage,
        settings=settings,
        tags=("mine",),
        meta={"why": "kept"},
    )
    assert first.count(CREATED) == 1

    report = await folder.import_folder(
        corpus_of(downloaded),
        session=session,
        storage=storage,
        settings=settings,
        recursive=True,
    )

    assert (report.count(CREATED), report.count(ALREADY_STORED)) == (1, 1)
    stored = await rows(engine)
    kept = next(row for row in stored if row.original_filename == "mine.png")
    assert list(kept.tags) == ["mine"], "the earlier asset's tags are untouched"
    assert kept.meta["why"] == "kept" and "dataset" not in kept.meta
    assert len(stored) == 2, "no second asset for the same bytes"


async def test_a_second_import_of_the_corpus_adds_nothing(
    downloaded: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    for _ in range(2):
        report = await folder.import_folder(
            corpus_of(downloaded),
            session=session,
            storage=storage,
            settings=settings,
            recursive=True,
        )

    assert report.count(ALREADY_STORED) == 2
    assert len(await rows(engine)) == 2


async def test_a_picture_uploaded_before_the_corpus_is_also_left_alone(
    downloaded: Path,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    engine: AsyncEngine,
    app: FastAPI,
) -> None:
    """The other ordering: the bytes arrived through the API first. The rule is
    the same, because it is the store's and not the import's."""
    async for client in make_client(app):
        response = await client.post(
            "/api/v1/assets",
            files={"file": ("uploaded.png", picture_bytes("red"), "image/png")},
            data={"tags": "uploaded"},
        )
    assert response.status_code == 201

    report = await folder.import_folder(
        corpus_of(downloaded),
        session=session,
        storage=storage,
        settings=settings,
        recursive=True,
    )

    assert (report.count(CREATED), report.count(ALREADY_STORED)) == (1, 1)
    stored = await rows(engine)
    kept = next(row for row in stored if row.original_filename == "uploaded.png")
    assert list(kept.tags) == ["uploaded"]
    assert "dataset" not in kept.meta, "the corpus did not rewrite an asset it did not create"
