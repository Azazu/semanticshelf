"""Changing an asset's tags and metadata, and removing it entirely."""

import io
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"


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
def app(db_settings: Settings, media_root: Path) -> FastAPI:
    return create_app(db_settings.model_copy(update={"media_root": media_root}))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


async def upload(client: httpx.AsyncClient, seed: int = 0, **fields: str) -> dict[str, object]:
    response = await client.post(
        ASSETS, files={"file": ("p.png", picture_bytes(seed))}, data=fields or None
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_tags_alone_are_replaced_and_metadata_is_left_alone(
    client: httpx.AsyncClient,
) -> None:
    created = await upload(client, tags="dragon", meta='{"origin": "test"}')

    response = await client.patch(f"{ASSETS}/{created['id']}", json={"tags": [" Castle ", "FOG"]})

    assert response.status_code == 200
    body = response.json()
    assert body["tags"] == ["castle", "fog"]
    assert body["meta"] == {"origin": "test"}


async def test_metadata_is_cleared_by_an_explicit_null(client: httpx.AsyncClient) -> None:
    created = await upload(client, tags="dragon", meta='{"origin": "test"}')

    response = await client.patch(f"{ASSETS}/{created['id']}", json={"meta": None})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {}
    assert body["tags"] == ["dragon"], "an omitted field is untouched"


async def test_metadata_is_replaced_by_a_new_object(client: httpx.AsyncClient) -> None:
    created = await upload(client, meta='{"origin": "test", "keep": "me"}')

    response = await client.patch(f"{ASSETS}/{created['id']}", json={"meta": {"origin": "edited"}})

    assert response.json()["meta"] == {"origin": "edited"}


async def test_an_empty_patch_changes_nothing(client: httpx.AsyncClient) -> None:
    created = await upload(client, tags="dragon", meta='{"origin": "test"}')

    response = await client.patch(f"{ASSETS}/{created['id']}", json={})

    assert response.status_code == 200
    assert response.json() == created


async def test_the_picture_itself_cannot_be_changed(client: httpx.AsyncClient) -> None:
    created = await upload(client)

    response = await client.patch(
        f"{ASSETS}/{created['id']}",
        json={"sha256": "0" * 64, "width": 1, "content_type": "image/webp", "tags": ["dragon"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sha256"] == created["sha256"]
    assert body["width"] == created["width"]
    assert body["content_type"] == created["content_type"]
    assert body["tags"] == ["dragon"], "what may change, changed"


async def test_an_invalid_tag_leaves_the_asset_untouched(client: httpx.AsyncClient) -> None:
    created = await upload(client, tags="dragon")

    response = await client.patch(f"{ASSETS}/{created['id']}", json={"tags": ["not a tag!"]})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-tags"
    assert (await client.get(f"{ASSETS}/{created['id']}")).json()["tags"] == ["dragon"]


async def test_patching_an_asset_that_is_not_stored_is_404(client: httpx.AsyncClient) -> None:
    response = await client.patch(
        f"{ASSETS}/0f9b1d2c-3e4f-4a5b-8c7d-9e0f1a2b3c4d", json={"tags": ["dragon"]}
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_deleting_an_asset_removes_its_row_and_its_files(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    created = await upload(client)
    assert len([path for path in media_root.rglob("*") if path.is_file()]) == 2

    response = await client.delete(f"{ASSETS}/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"{ASSETS}/{created['id']}")).status_code == 404
    assert [path for path in media_root.rglob("*") if path.is_file()] == []


async def test_deleting_twice_answers_404_the_second_time(client: httpx.AsyncClient) -> None:
    created = await upload(client)

    assert (await client.delete(f"{ASSETS}/{created['id']}")).status_code == 204
    second = await client.delete(f"{ASSETS}/{created['id']}")

    assert second.status_code == 404
    assert second.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_a_file_that_cannot_be_removed_is_a_warning_not_a_failure(
    client: httpx.AsyncClient, media_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    created = await upload(client)
    shard = media_root / str(created["id"])[:2]
    shard.chmod(0o500)  # readable, not writable: unlink will be refused
    try:
        with caplog.at_level(logging.WARNING):
            response = await client.delete(f"{ASSETS}/{created['id']}")
    finally:
        shard.chmod(0o700)

    assert response.status_code == 204, "the row is gone, so the request succeeded"
    assert any("could not be removed" in record.getMessage() for record in caplog.records)
    assert (await client.get(f"{ASSETS}/{created['id']}")).status_code == 404
    assert [path for path in shard.iterdir()], "the files are left for prune"


async def test_deleting_an_asset_removes_its_embeddings(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    created = await upload(client)
    # Nothing is inserted by hand any more: the upload's own drain indexes the
    # picture, so the asset really has the vector this test then deletes.
    async with engine.connect() as connection:
        stored = (await connection.execute(sa.text("SELECT count(*) FROM embeddings"))).scalar_one()
    assert stored == 1, "the background runner wrote the vector"

    assert (await client.delete(f"{ASSETS}/{created['id']}")).status_code == 204

    async with engine.connect() as connection:
        left = (await connection.execute(sa.text("SELECT count(*) FROM embeddings"))).scalar_one()
    assert left == 0
