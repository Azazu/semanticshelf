"""Reading an asset: its representation, its bytes, its thumbnail, the listing."""

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


def picture_bytes(size: tuple[int, int] = (400, 200), fmt: str = "PNG", seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(seed % 255, 90, 200)).save(buffer, format=fmt)
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


async def upload(client: httpx.AsyncClient, **fields: object) -> dict[str, object]:
    data = fields.pop("content", None) or picture_bytes(seed=fields.pop("seed", 0))  # type: ignore[arg-type]
    response = await client.post(
        ASSETS,
        files={"file": ("p.png", data)},
        data=fields or None,  # type: ignore[arg-type]
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_an_asset_is_read_by_its_identifier(client: httpx.AsyncClient) -> None:
    created = await upload(client)
    assert created["index_status"] == {"clip-vit-l14": "pending"}, "as the upload answered"

    response = await client.get(f"{ASSETS}/{created['id']}")

    assert response.status_code == 200
    # Everything is as the upload reported it, except the state of the work:
    # the runner the upload scheduled has finished it by now.
    assert response.json() == created | {"index_status": {"clip-vit-l14": "done"}}


async def test_an_identifier_that_is_not_stored_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{ASSETS}/0f9b1d2c-3e4f-4a5b-8c7d-9e0f1a2b3c4d")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_the_original_bytes_come_back_with_their_validators(
    client: httpx.AsyncClient,
) -> None:
    data = picture_bytes()
    created = await upload(client, content=data)

    response = await client.get(f"{ASSETS}/{created['id']}/file")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["etag"] == f'"{created["sha256"]}"'
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert f'filename="{created["id"]}.png"' in response.headers["content-disposition"]
    assert response.headers["content-disposition"].startswith("inline")


async def test_the_thumbnail_comes_back_as_webp(client: httpx.AsyncClient) -> None:
    created = await upload(client)

    response = await client.get(f"{ASSETS}/{created['id']}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(response.content)) as thumb:
        assert thumb.format == "WEBP"


async def test_a_file_that_is_gone_is_404_with_a_warning(
    client: httpx.AsyncClient, media_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    created = await upload(client)
    stored = media_root / str(created["id"])[:2] / f"{created['id']}.png"
    stored.unlink()

    with caplog.at_level(logging.WARNING):
        response = await client.get(f"{ASSETS}/{created['id']}/file")

    assert response.status_code == 404, "never a server error"
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert any("stored file missing" in record.getMessage() for record in caplog.records)
    # The asset itself is still readable: only its bytes are gone.
    assert (await client.get(f"{ASSETS}/{created['id']}")).status_code == 200


async def test_a_page_is_newest_first_and_says_whether_more_exist(
    client: httpx.AsyncClient,
) -> None:
    created = [await upload(client, seed=index) for index in range(5)]

    first = await client.get(ASSETS, params={"limit": 2})
    second = await client.get(ASSETS, params={"limit": 2, "offset": 2})
    last = await client.get(ASSETS, params={"limit": 2, "offset": 4})

    assert [item["id"] for item in first.json()["items"]] == [
        created[4]["id"],
        created[3]["id"],
    ]
    assert first.json()["has_more"] is True
    assert second.json()["has_more"] is True
    assert last.json()["has_more"] is False
    assert "total" not in first.json()

    seen = [item["id"] for page in (first, second, last) for item in page.json()["items"]]
    assert sorted(seen) == sorted(asset["id"] for asset in created), "each asset exactly once"


@pytest.mark.parametrize(
    "params",
    [{"limit": 101}, {"limit": 0}, {"offset": 10_001}, {"offset": -1}],
    ids=["over-max-limit", "zero-limit", "over-max-offset", "negative-offset"],
)
async def test_a_page_outside_its_bounds_is_refused(
    client: httpx.AsyncClient, params: dict[str, int]
) -> None:
    response = await client.get(ASSETS, params=params)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_the_tag_filters_select_exactly_what_they_say(client: httpx.AsyncClient) -> None:
    dragon_castle = await upload(client, seed=1, tags="dragon,castle")
    dragon = await upload(client, seed=2, tags="dragon")
    fog = await upload(client, seed=3, tags="fog")

    both = await client.get(ASSETS, params={"tags_all": "dragon,castle"})
    either = await client.get(ASSETS, params={"tags_any": "dragon,fog"})

    assert [item["id"] for item in both.json()["items"]] == [dragon_castle["id"]]
    assert {item["id"] for item in either.json()["items"]} == {
        dragon_castle["id"],
        dragon["id"],
        fog["id"],
    }


async def test_an_invalid_tag_in_a_filter_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get(ASSETS, params={"tags_all": "not a tag!"})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-tags"


async def test_the_source_filter_selects_uploads(client: httpx.AsyncClient) -> None:
    await upload(client, seed=7)

    uploads = await client.get(ASSETS, params={"source": "upload"})
    folders = await client.get(ASSETS, params={"source": "folder"})

    assert len(uploads.json()["items"]) == 1
    assert folders.json()["items"] == []
