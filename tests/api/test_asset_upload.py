"""What an upload is refused for, and what it leaves behind when it is.

Every case here is answered before the service touches the database — that is
the point of the order in `app/services/assets.py` — so this suite runs in
`make check` with no container. The successful paths need a real store and
live in the integration suite.
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
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

ASSETS = "/api/v1/assets"


def picture_bytes(size: tuple[int, int] = (64, 64), fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


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


async def test_a_file_that_is_not_a_picture_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"file": ("notes.txt", b"not a picture")})

    assert response.status_code == 415
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["type"] == "/errors/unsupported-media-type"
    assert stored(media_root) == []


async def test_a_format_the_service_does_not_accept_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"file": ("p.bmp", picture_bytes(fmt="BMP"))})

    assert response.status_code == 415
    assert "BMP" in response.json()["detail"]
    assert stored(media_root) == []


async def test_a_picture_under_the_minimum_side_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes((31, 64)))})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/image-too-small"
    assert stored(media_root) == []


async def test_a_picture_over_the_pixel_cap_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes((200, 200)))})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/image-too-large"
    assert stored(media_root) == []


async def test_a_body_over_the_limit_is_refused_before_anything_is_read(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"file": ("big.png", b"x" * (64 * 1024 + 1))})

    assert response.status_code == 413
    assert response.json()["type"] == "/errors/upload-too-large"
    assert stored(media_root) == []


async def test_an_invalid_tag_is_refused_by_name(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        ASSETS, files={"file": ("p.png", picture_bytes())}, data={"tags": "not a tag!"}
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-tags"
    assert "not a tag!" in response.json()["detail"]
    assert stored(media_root) == []


@pytest.mark.parametrize(
    ("meta", "reason"),
    [
        ("[]", "object"),
        ("{not json", "valid JSON"),
        ('{"a": ' + '{"b": ' * 5 + "1" + "}" * 5 + "}", "deep"),
    ],
    ids=["not-an-object", "malformed", "too-deep"],
)
async def test_metadata_outside_the_rules_is_refused(
    client: httpx.AsyncClient, media_root: Path, meta: str, reason: str
) -> None:
    response = await client.post(
        ASSETS, files={"file": ("p.png", picture_bytes())}, data={"meta": meta}
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-meta"
    assert reason in response.json()["detail"]
    assert stored(media_root) == []


async def test_an_upload_without_a_file_part_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, data={"tags": "dragon"})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-upload"
    assert "got 0" in response.json()["detail"]
    assert stored(media_root) == []


async def test_an_upload_with_two_file_parts_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        ASSETS,
        files=[
            ("file", ("one.png", picture_bytes())),
            ("file", ("two.png", picture_bytes((40, 40)))),
        ],
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-upload"
    assert stored(media_root) == []


async def test_a_second_file_part_under_another_name_is_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    # A picture is a picture whatever the field is called; ignoring the extra
    # one would store something the client did not ask to store.
    response = await client.post(
        ASSETS,
        files=[
            ("file", ("one.png", picture_bytes())),
            ("attachment", ("two.png", picture_bytes((40, 40)))),
        ],
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-upload"
    assert "2 file part" in response.json()["detail"]
    assert stored(media_root) == []


async def test_the_single_file_part_must_be_called_file(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(ASSETS, files={"attachment": ("one.png", picture_bytes())})

    assert response.status_code == 422
    assert "must be called 'file'" in response.json()["detail"]
    assert stored(media_root) == []


async def test_more_file_parts_than_the_parser_allows_are_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        ASSETS,
        files=[("file", (f"{index}.png", picture_bytes((40, 40)))) for index in range(5)],
    )

    # The parser's own refusal, rendered as problem details by the project's
    # handler: a malformed request is a 400, and the message names the bound.
    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert "files" in response.json()["detail"].lower()
    assert stored(media_root) == []


async def test_more_fields_than_the_parser_allows_are_refused(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    response = await client.post(
        ASSETS,
        files={"file": ("p.png", picture_bytes())},
        data={f"tags{index}": "x" for index in range(60)},
    )

    assert response.status_code == 400
    assert "fields" in response.json()["detail"].lower()
    assert stored(media_root) == []


async def test_metadata_beyond_the_parser_bound_never_reaches_the_parser(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    # Two guards refuse an oversized meta; this asserts it was the parser's,
    # which is what makes each of them independently testable.
    from app.api.assets import PARSER_PART_BYTES

    response = await client.post(
        ASSETS,
        files={"file": ("p.png", picture_bytes())},
        data={"meta": '{"a":"' + "x" * (PARSER_PART_BYTES + 10) + '"}'},
    )

    # The parser refused it: a 400 naming the part, not the application's 422
    # naming the metadata bound. That difference is what makes each guard
    # independently testable.
    assert response.status_code == 400
    assert "Part exceeded" in response.json()["detail"]


async def test_metadata_between_the_two_bounds_is_refused_by_the_application(
    client: httpx.AsyncClient, media_root: Path
) -> None:
    from app.api.assets import PARSER_PART_BYTES
    from app.services.tagging import METADATA_MAX_BYTES

    filler = "x" * ((METADATA_MAX_BYTES + PARSER_PART_BYTES) // 2)
    response = await client.post(
        ASSETS, files={"file": ("p.png", picture_bytes())}, data={"meta": f'{{"a":"{filler}"}}'}
    )

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/invalid-meta"
    assert str(METADATA_MAX_BYTES) in response.json()["detail"]
