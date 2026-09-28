"""Asking for a query encoder, and the refusals around it.

An encoder is named the same way a model is — `model=` — and resolves to a
pair: the space whose vectors are ranked, and the thing that embedded the
question. What this file checks is the routing and the two refusals; what the
answer looks like when there is a corpus is in the integration suite, because
it needs vectors to rank.

The store is unreachable here, so a 500 is the evidence that a combination was
accepted: the request got all the way to a query.
"""

import io
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, MCLIP_XLMR_L14
from app.main import create_app
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

TEXT = "/api/v1/search/text"
IMAGE = "/api/v1/search/image"
SIMILAR = f"/api/v1/assets/{uuid4()}/similar"
INVENTED_ENCODER = "mclip-of-the-future"

Ask = Callable[[httpx.AsyncClient, str], Awaitable[httpx.Response]]


def picture_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


def build(media_root: Path, **overrides: object) -> FastAPI:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=UNREACHABLE_DATABASE_URL,
        media_root=media_root,
        **overrides,
    )
    return create_app(settings)


@pytest.fixture
async def with_encoder(media_root: Path) -> AsyncIterator[httpx.AsyncClient]:
    """A build that runs the encoder beside the model it answers in."""
    app = build(media_root, enabled_query_encoders=(MCLIP_XLMR_L14,))
    async for client in make_client(app):
        yield client


@pytest.fixture
async def without_encoder(media_root: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The default build: no encoder enabled, which is most deployments."""
    async for client in make_client(build(media_root)):
        yield client


async def ask_picture(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.post(
        IMAGE, files={"file": ("q.png", picture_bytes(), "image/png")}, data={"model": model}
    )


async def ask_similar(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.get(SIMILAR, params={"model": model})


async def test_a_text_search_may_name_an_enabled_encoder(
    with_encoder: httpx.AsyncClient,
) -> None:
    response = await with_encoder.get(TEXT, params={"q": "зебра в траве", "model": MCLIP_XLMR_L14})

    assert response.status_code == 500, "accepted, and then the unreachable store answered"


async def test_an_encoder_this_build_does_not_run_is_unavailable(
    without_encoder: httpx.AsyncClient,
) -> None:
    """503, not 422: the request is fine, this deployment does not serve it."""
    response = await without_encoder.get(TEXT, params={"q": "зебра", "model": MCLIP_XLMR_L14})

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "/errors/model-unavailable"
    assert MCLIP_XLMR_L14 in body["detail"]


async def test_an_encoder_nobody_declares_is_unavailable_too(
    with_encoder: httpx.AsyncClient,
) -> None:
    response = await with_encoder.get(TEXT, params={"q": "зебра", "model": INVENTED_ENCODER})

    assert response.status_code == 503
    assert INVENTED_ENCODER in response.json()["detail"]


@pytest.mark.parametrize(
    "ask", [ask_picture, ask_similar], ids=["a picture in the request", "a stored asset"]
)
async def test_a_picture_asked_of_an_encoder_is_refused(
    with_encoder: httpx.AsyncClient, ask: Ask
) -> None:
    """422 and it names what the encoder can take: no deployment serves this."""
    response = await ask(with_encoder, MCLIP_XLMR_L14)

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/wrong-modality"
    assert MCLIP_XLMR_L14 in body["detail"]
    assert "text" in body["detail"], "it names what that encoder can be asked"


async def test_enabling_an_encoder_does_not_change_what_answers_by_default(
    with_encoder: httpx.AsyncClient,
) -> None:
    """The default stays the storage model: an encoder is asked for by name.

    Both halves are checked, because they can disagree: what the document
    promises, and what a request that names nothing is actually answered by.
    """
    document = (await with_encoder.get("/api/openapi.json")).json()
    parameters = document["paths"][TEXT]["get"]["parameters"]
    model = next(one for one in parameters if one["name"] == "model")
    assert model["schema"]["default"] == CLIP_VIT_L14

    unnamed = await with_encoder.get(TEXT, params={"q": "a zebra in the grass"})

    assert unnamed.status_code == 500, "accepted as before, and the store is unreachable"
