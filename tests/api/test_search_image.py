"""A picture as the query: what is refused, and what is never kept.

Every case here is decided before the store is touched — the picture is
received, inspected and embedded first — so the suite runs with no container
and no weights. The unreachable database is the evidence in both directions: a
422 or a 415 proves the refusal came before any query, and a 500 proves the
picture was accepted and the search got as far as the store.
"""

import io
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from app.services.search import MAX_PAGE_DEPTH
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

SEARCH = "/api/v1/search/image"


def picture_bytes(size: tuple[int, int] = (64, 64), fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


def a_picture() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("query.png", picture_bytes(), "image/png")}


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def app(media_root: Path) -> FastAPI:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=UNREACHABLE_DATABASE_URL,
        media_root=media_root,
        max_upload_bytes=64 * 1024,
        max_image_pixels=10_000,
        min_image_side=32,
    )
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


def stored(media_root: Path) -> list[Path]:
    return [path for path in media_root.rglob("*") if path.is_file()]


# --- the picture itself -------------------------------------------------------


async def test_a_valid_picture_gets_past_every_refusal(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    """It fails on the unreachable database, which is what proves the picture
    was decoded, embedded and carried to the store."""
    response = await client.post(SEARCH, files=a_picture())

    assert response.status_code == 500
    assert stored(media_root) == [], "a query picture is never stored"


async def test_a_file_that_is_not_a_picture_is_refused_as_an_upload_would_be(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(SEARCH, files={"file": ("notes.txt", b"not a picture")})

    assert response.status_code == 415
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["type"] == "/errors/unsupported-media-type"
    assert stored(media_root) == []


async def test_a_format_the_service_does_not_accept_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(SEARCH, files={"file": ("p.bmp", picture_bytes(fmt="BMP"))})

    assert response.status_code == 415
    assert "BMP" in response.json()["detail"]
    assert stored(media_root) == []


async def test_a_picture_with_too_many_pixels_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(SEARCH, files={"file": ("big.png", picture_bytes((200, 200)))})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/image-too-large"
    assert stored(media_root) == []


async def test_a_picture_smaller_than_the_minimum_side_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(SEARCH, files={"file": ("tiny.png", picture_bytes((16, 16)))})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/image-too-small"
    assert stored(media_root) == []


async def test_a_body_beyond_the_bound_is_refused_before_it_is_read(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    """The body-size middleware bounds the whole request, as it does an upload:
    the framework parses a multipart body before an endpoint runs."""
    response = await client.post(
        SEARCH, files={"file": ("huge.png", b"\x89PNG\r\n\x1a\n" + b"0" * (65 * 1024))}
    )

    assert response.status_code == 413
    assert stored(media_root) == []


async def test_a_request_without_a_picture_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(SEARCH, data={"limit": "5"})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-upload"


async def test_a_second_picture_is_not_silently_ignored(client: httpx.AsyncClient) -> None:
    response = await client.post(
        SEARCH,
        files=[
            ("file", ("one.png", picture_bytes(), "image/png")),
            ("other", ("two.png", picture_bytes(), "image/png")),
        ],
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-upload"


async def test_the_file_part_has_to_be_called_file(client: httpx.AsyncClient) -> None:
    response = await client.post(SEARCH, files={"picture": ("q.png", picture_bytes())})

    assert response.status_code == 422
    assert "'file'" in response.json()["detail"]


# --- the page fields, which are form fields here ------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"offset": "-1"},
        {"min_score": "1.5"},
        {"min_score": "-1.5"},
        {"limit": "not a number"},
    ],
    ids=[
        "limit below one",
        "limit above max",
        "negative offset",
        "score high",
        "score low",
        "text",
    ],
)
async def test_a_page_field_outside_its_bounds_is_refused(
    client: httpx.AsyncClient, fields: dict[str, str]
) -> None:
    response = await client.post(SEARCH, files=a_picture(), data=fields)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert next(iter(fields)) in response.json()["detail"]


async def test_a_page_too_deep_is_refused_before_the_picture_is_read(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        SEARCH, files=a_picture(), data={"limit": "100", "offset": str(MAX_PAGE_DEPTH - 99)}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/page-too-deep"
    assert str(MAX_PAGE_DEPTH) in body["detail"]
    assert stored(media_root) == []


async def test_the_deepest_allowed_page_is_the_same_as_the_text_search(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        SEARCH, files=a_picture(), data={"limit": "100", "offset": str(MAX_PAGE_DEPTH - 100)}
    )

    assert response.status_code != 422


# --- the document -------------------------------------------------------------


async def test_the_operation_is_in_the_openapi_document(client: httpx.AsyncClient) -> None:
    document = (await client.get("/api/openapi.json")).json()

    operation = document["paths"][SEARCH]["post"]
    assert operation["summary"]
    assert "never stored" in operation["description"]
    assert operation["responses"]["200"]["content"]["application/json"]["example"]


async def test_every_status_this_operation_answers_is_documented(
    client: httpx.AsyncClient,
) -> None:
    document = (await client.get("/api/openapi.json")).json()

    responses = document["paths"][SEARCH]["post"]["responses"]

    assert {"200", "415", "422", "500", "503"} <= responses.keys()
    assert set(responses["503"]["content"]) == {PROBLEM_MEDIA_TYPE}
