"""Which model answers, across all three searches.

Two refusals, and the difference between them matters to a client. A model this
build does not run is 503: the request was fine, this deployment cannot serve
it. A model that cannot take the kind of query it was given is 422 and names
what it can take: no deployment would serve that.

Everything here is decided before the store is touched, so the unreachable
database is the evidence that a combination was accepted — a 500 means the
request got all the way to a query.
"""

import io
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app import domain
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Modality
from app.main import create_app
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

TEXT = "/api/v1/search/text"
IMAGE = "/api/v1/search/image"
SIMILAR = f"/api/v1/assets/{uuid4()}/similar"
INVENTED = "dinov2-enormous"

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
async def client(media_root: Path) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(build(media_root)):
        yield client


async def ask_text(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.get(TEXT, params={"q": "a dragon", "model": model})


async def ask_picture(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.post(
        IMAGE,
        files={"file": ("q.png", picture_bytes(), "image/png")},
        data={"model": model},
    )


async def ask_similar(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.get(SIMILAR, params={"model": model})


# --- the combinations that work -----------------------------------------------


@pytest.mark.parametrize(
    ("ask", "model"),
    [
        (ask_text, CLIP_VIT_L14),
        (ask_picture, DINOV2_LARGE),
        (ask_picture, CLIP_VIT_L14),
        (ask_similar, DINOV2_LARGE),
        (ask_similar, CLIP_VIT_L14),
    ],
    ids=["text+clip", "picture+dinov2", "picture+clip", "similar+dinov2", "similar+clip"],
)
async def test_a_model_that_can_take_the_query_is_accepted(
    client: httpx.AsyncClient, ask: Ask, model: str
) -> None:
    """500 from the unreachable store: the combination was never the problem."""
    response = await ask(client, model)

    assert response.status_code == 500


# --- the combinations that cannot work ----------------------------------------


async def test_words_asked_of_a_model_with_no_text_tower_are_refused(
    client: httpx.AsyncClient,
) -> None:
    response = await ask_text(client, DINOV2_LARGE)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "/errors/wrong-modality"
    assert "pictures" in body["detail"], "it names what that model can be asked"
    assert DINOV2_LARGE in body["detail"]


@pytest.mark.parametrize(
    "ask", [ask_picture, ask_similar], ids=["a picture in the request", "a stored asset"]
)
async def test_a_picture_asked_of_a_model_with_no_image_side_is_refused(
    client: httpx.AsyncClient, ask: Ask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No implemented model is text-only today, so the table says one is: the
    branch is real, and a third model will one day walk into it."""
    monkeypatch.setitem(domain.MODEL_MODALITIES, CLIP_VIT_L14, Modality(text=True, images=False))

    response = await ask(client, CLIP_VIT_L14)

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/wrong-modality"
    assert "text" in body["detail"]


@pytest.mark.parametrize(
    "ask",
    [ask_text, ask_picture, ask_similar],
    ids=["text", "picture", "similar"],
)
async def test_a_key_this_build_has_never_heard_of_is_unavailable(
    client: httpx.AsyncClient, ask: Ask
) -> None:
    """Not 422: a client cannot know which keys a deployment runs, and looking
    the key up in the application's table first would be a different answer for
    the same situation."""
    response = await ask(client, INVENTED)

    assert response.status_code == 503
    body = response.json()
    assert body["type"] == "/errors/model-unavailable"
    assert INVENTED in body["detail"]


@pytest.mark.parametrize(
    ("ask", "model"),
    [(ask_text, CLIP_VIT_L14), (ask_picture, DINOV2_LARGE), (ask_similar, DINOV2_LARGE)],
    ids=["text", "picture", "similar"],
)
async def test_a_model_this_deployment_does_not_run_is_unavailable(
    media_root: Path, ask: Ask, model: str
) -> None:
    app = build(media_root, enabled_models=())

    async for client in make_client(app):
        response = await ask(client, model)

    assert response.status_code == 503
    body = response.json()
    assert body["type"] == "/errors/model-unavailable"
    assert model in body["detail"]


async def test_what_a_deployment_runs_is_reported_before_what_a_model_can_take(
    media_root: Path,
) -> None:
    """Both hold for words asked of a disabled DINOv2. The fact about this
    service is the one worth reporting."""
    app = build(media_root, enabled_models=(CLIP_VIT_L14,))

    async for client in make_client(app):
        response = await ask_text(client, DINOV2_LARGE)

    assert response.status_code == 503
