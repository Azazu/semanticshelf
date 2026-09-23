"""An upload that succeeds: what comes back, what lands on disk, what is stored.

These need a real database — the store is what decides a duplicate, and the
race between two identical uploads is decided by a constraint. The refusals,
which never reach the database, are in the api suite.
"""

import asyncio
import io
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.main import create_app
from app.repositories.assets import AssetRepository
from app.services import assets as assets_service
from app.storage import THUMBNAIL_SUFFIX
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(size: tuple[int, int] = (400, 200), fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(30, 90, 200)).save(buffer, format=fmt)
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
def app(db_settings: Settings, media_root: Path) -> FastAPI:
    return create_app(db_settings.model_copy(update={"media_root": media_root}))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


def files_under(media_root: Path) -> list[Path]:
    return sorted(path for path in media_root.rglob("*") if path.is_file())


@pytest.mark.parametrize(
    ("fmt", "content_type", "file_ext"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
async def test_a_picture_of_each_accepted_format_is_stored(
    client: httpx.AsyncClient, media_root: Path, fmt: str, content_type: str, file_ext: str
) -> None:
    data = picture_bytes(fmt=fmt)

    response = await client.post(ASSETS, files={"file": (f"p.{file_ext}", data)})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == content_type
    assert (body["width"], body["height"]) == (400, 200)
    assert body["size_bytes"] == len(data)
    assert body["source"] == "upload"
    assert response.headers["location"] == f"{ASSETS}/{body['id']}"
    assert body["links"] == {
        "file": f"{ASSETS}/{body['id']}/file",
        "thumbnail": f"{ASSETS}/{body['id']}/thumbnail",
    }

    original = media_root / body["id"][:2] / f"{body['id']}.{file_ext}"
    thumbnail = media_root / body["id"][:2] / f"{body['id']}{THUMBNAIL_SUFFIX}"
    assert original.read_bytes() == data, "the original is stored byte for byte"
    with Image.open(io.BytesIO(thumbnail.read_bytes())) as thumb:
        assert thumb.format == "WEBP"
        assert thumb.size == (256, 128), "bounded by its longest side, proportions kept"
    assert files_under(media_root) == sorted([original, thumbnail]), "no staged file is left"


async def test_the_format_comes_from_the_bytes_not_the_name(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        ASSETS,
        files={"file": ("misleading.jpg", picture_bytes(fmt="PNG"), "image/jpeg")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == "image/png"
    assert (media_root / body["id"][:2] / f"{body['id']}.png").exists()


async def test_the_recorded_filename_is_normalised(client: httpx.AsyncClient) -> None:
    # A raw control character cannot travel in a multipart header — the client
    # escapes it — so the separators are what this asserts end to end; the
    # control characters are covered by the unit tests of the normaliser.
    response = await client.post(ASSETS, files={"file": ("../../etc/passwd.png", picture_bytes())})

    assert response.status_code == 201
    assert response.json()["original_filename"] == "passwd.png"


async def test_tags_and_metadata_are_stored_normalised(client: httpx.AsyncClient) -> None:
    response = await client.post(
        ASSETS,
        files={"file": ("p.png", picture_bytes())},
        data={"tags": [" Dragon ", "castle,dragon"], "meta": '{"origin": "test"}'},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["tags"] == ["dragon", "castle"]
    assert body["meta"] == {"origin": "test"}


async def test_the_same_bytes_twice_are_one_asset(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    data = picture_bytes()
    first = await client.post(ASSETS, files={"file": ("one.png", data)})
    assert first.status_code == 201

    second = await client.post(ASSETS, files={"file": ("again.png", data)})

    assert second.status_code == 409
    body = second.json()
    assert body["type"] == "/errors/duplicate-asset"
    assert body["existing_asset_id"] == first.json()["id"]
    assert len(files_under(media_root)) == 2, "the refused upload left nothing behind"


async def test_two_identical_uploads_at_once_leave_one_asset(
    client: httpx.AsyncClient, media_root: Path, engine: AsyncEngine
) -> None:
    data = picture_bytes()

    first, second = await asyncio.gather(
        client.post(ASSETS, files={"file": ("a.png", data)}),
        client.post(ASSETS, files={"file": ("b.png", data)}),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    winner = first if first.status_code == 201 else second
    loser = second if first.status_code == 201 else first
    assert loser.json()["existing_asset_id"] == winner.json()["id"]

    async with engine.connect() as connection:
        count = (await connection.execute(sa.text("SELECT count(*) FROM assets"))).scalar_one()
    assert count == 1
    assert len(files_under(media_root)) == 2, "the loser removed its own files"


async def test_the_files_are_on_disk_before_the_row_is_written(
    client: httpx.AsyncClient, media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The order the invariant rests on. Both files must already be in place
    when the row is written, so a commit can never produce an asset whose
    bytes are not there."""
    seen: list[int] = []
    add = AssetRepository.add

    async def counting_add(self: AssetRepository, **kwargs: object) -> object:
        seen.append(len(files_under(media_root)))
        return await add(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(AssetRepository, "add", counting_add)

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 201
    assert seen == [2], "both files were published before the row was written"


async def test_a_duplicate_is_refused_before_anything_is_published(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = picture_bytes()
    assert (await client.post(ASSETS, files={"file": ("one.png", data)})).status_code == 201

    published: list[object] = []
    publish_files = assets_service.publish_files

    def counting_publish(*args: object, **kwargs: object) -> None:
        published.append(args)
        publish_files(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(assets_service, "publish_files", counting_publish)

    response = await client.post(ASSETS, files={"file": ("again.png", data)})

    assert response.status_code == 409
    assert published == [], "the duplicate was caught before a file was published"


async def test_a_thumbnail_that_cannot_be_made_leaves_nothing_behind(
    client: httpx.AsyncClient, media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import images

    def refuse(path: Path) -> bytes:
        raise OSError("the encoder gave up")

    monkeypatch.setattr(images, "thumbnail", refuse)

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 500, "the upload failed"
    assert files_under(media_root) == [], "not even a staging file remains"
    assert (await client.get(ASSETS)).json()["items"] == []


async def test_a_failed_write_of_the_thumbnail_leaves_nothing_behind(
    client: httpx.AsyncClient, media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The thumbnail is written first, so its failure is the earliest moment a
    file of this upload exists under the media root."""
    from app.storage import MediaStorage

    def fail_after_writing_part_of_it(staged: Path, chunks: object) -> int:
        staged.write_bytes(b"half a thumbnail")
        raise OSError("the disk gave up")

    monkeypatch.setattr(MediaStorage, "fill", staticmethod(fail_after_writing_part_of_it))

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 500
    assert files_under(media_root) == [], "no staging file, no final file"
    assert (await client.get(ASSETS)).json()["items"] == []


async def test_a_failed_publication_of_the_thumbnail_leaves_nothing_behind(
    client: httpx.AsyncClient, media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And the moment after: written, flushed, and then the rename fails."""
    from app.storage import MediaStorage

    def refuse(staged: Path, final: Path) -> None:
        raise OSError("the rename gave up")

    monkeypatch.setattr(MediaStorage, "publish", staticmethod(refuse))

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 500
    assert files_under(media_root) == [], "the staged thumbnail did not survive"
    assert (await client.get(ASSETS)).json()["items"] == []


async def test_a_failed_write_of_the_original_leaves_nothing_behind(
    client: httpx.AsyncClient, media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.storage import MediaStorage

    fill = MediaStorage.fill
    calls = {"n": 0}

    def fail_on_the_original(staged: Path, chunks: object) -> int:
        calls["n"] += 1
        if calls["n"] == 1:  # the thumbnail goes first; the original is second
            return fill(staged, chunks)  # type: ignore[arg-type]
        staged.write_bytes(b"half a picture")  # a partial file, then the failure
        raise OSError("the disk gave up")

    monkeypatch.setattr(MediaStorage, "fill", staticmethod(fail_on_the_original))

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 500
    assert files_under(media_root) == [], "the partial file and the thumbnail are both gone"
    assert (await client.get(ASSETS)).json()["items"] == []


async def queued_models(engine: AsyncEngine, asset_id: str) -> list[str]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text("SELECT model FROM indexing_jobs WHERE asset_id = :id ORDER BY model"),
                {"id": asset_id},
            )
        ).all()
    return [model for (model,) in rows]


async def test_an_upload_queues_one_job_per_enabled_model(
    client: httpx.AsyncClient, engine: AsyncEngine, db_settings: Settings
) -> None:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})
    assert response.status_code == 201

    # One row per enabled model is what the upload owes — derived from the
    # settings rather than written out, because that is the rule. What state
    # the row is in a moment later belongs to the runner that drains the queue
    # (`test_indexing_runner.py`), which in this process has already run.
    assert await queued_models(engine, response.json()["id"]) == sorted(db_settings.enabled_models)


async def test_an_upload_under_two_models_queues_work_for_both(
    db_settings: Settings, media_root: Path, engine: AsyncEngine
) -> None:
    """The scenario the capability names: an asset stored while two models are
    enabled has exactly two units of work, each naming one model."""
    both = (CLIP_VIT_L14, DINOV2_LARGE)
    app = create_app(
        db_settings.model_copy(update={"media_root": media_root, "enabled_models": both})
    )

    async for client in make_client(app):
        response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 201
    assert await queued_models(engine, response.json()["id"]) == sorted(both)
    assert response.json()["index_status"].keys() == set(both), "and the answer says so"


async def test_a_failed_store_leaves_neither_the_asset_nor_its_work(
    client: httpx.AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.repositories.jobs import IndexingJobRepository

    add_for_models = IndexingJobRepository.add_for_models

    async def refuse(self: IndexingJobRepository, **kwargs: object) -> None:
        await add_for_models(self, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("the store gave up after the jobs were written")

    monkeypatch.setattr(IndexingJobRepository, "add_for_models", refuse)

    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 500
    async with engine.connect() as connection:
        assets = (await connection.execute(sa.text("SELECT count(*) FROM assets"))).scalar_one()
        jobs = (
            await connection.execute(sa.text("SELECT count(*) FROM indexing_jobs"))
        ).scalar_one()
    assert (assets, jobs) == (0, 0), "the asset and its work were rolled back together"


async def test_an_upload_with_no_model_enabled_stores_the_asset_and_no_work(
    db_settings: Settings, media_root: Path, engine: AsyncEngine
) -> None:
    app = create_app(
        db_settings.model_copy(update={"media_root": media_root, "enabled_models": ()})
    )
    async for client in make_client(app):
        response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes())})

    assert response.status_code == 201
    async with engine.connect() as connection:
        jobs = (
            await connection.execute(sa.text("SELECT count(*) FROM indexing_jobs"))
        ).scalar_one()
    assert jobs == 0
