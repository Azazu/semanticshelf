"""Narrowing a search on the wire: what arrives, what is refused, what is said.

What a narrowing *does* to a ranking needs a real index and lives in the
integration suite. What lives here is the translation: the parameters a client
writes become the one filter object the service takes — `meta.<key>` included,
which no framework can declare because the caller invents its name — and every
filter this service will not apply comes back as the same problem type, naming
the value that was wrong.

The service functions are replaced by ones that record what they were handed.
That is the whole point: the assertion is about the router, and a real search
would only put a database between the question and the answer.
"""

import io
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.api import search as search_router
from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Narrowing
from app.main import create_app
from app.services.search import SearchPage as ServicePage
from app.services.tagging import MAX_META_CONDITIONS
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

TEXT = "/api/v1/search/text"
IMAGE = "/api/v1/search/image"
SIMILAR = f"/api/v1/assets/{uuid4()}/similar"
ASSETS = "/api/v1/assets"

INVALID_FILTER = "/errors/invalid-filter"


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, database_url=UNREACHABLE_DATABASE_URL, media_root=root
    )
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


def a_page(*, model: str = CLIP_VIT_L14, scan_limited: bool = False) -> ServicePage:
    return ServicePage(
        hits=[],
        statuses={},
        has_more=False,
        model=model,
        query_truncated=False,
        scan_limited=scan_limited,
    )


class Asked:
    """What the router handed the service."""

    def __init__(self) -> None:
        self.narrowing: Narrowing | None = None
        self.answer = a_page()

    def taking(self) -> Any:
        async def run(*args: Any, **kwargs: Any) -> ServicePage:
            self.narrowing = kwargs["narrowing"]
            return self.answer

        return run


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> Iterator[Asked]:
    recorder = Asked()
    for name in ("run_text_search", "run_image_search", "run_similar_search"):
        monkeypatch.setattr(search_router, name, recorder.taking())
    yield recorder


def as_form(filters: list[tuple[str, str]]) -> dict[str, list[str]]:
    """The same conditions as form fields. Repeated names are a list, which is
    how the picture search can be given one key twice at all."""
    form: dict[str, list[str]] = {}
    for key, value in filters:
        form.setdefault(key, []).append(value)
    return form


def a_picture() -> dict[str, tuple[str, bytes, str]]:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 30, 30)).save(buffer, format="PNG")
    return {"file": ("query.png", buffer.getvalue(), "image/png")}


# --- what arrives at the service ------------------------------------------------


async def test_the_text_search_carries_the_whole_narrowing(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    response = await client.get(
        TEXT,
        params={
            "q": "a dragon",
            "tags_all": "Dragon, fog",
            "tags_any": "castle",
            "meta.dataset": "coco",
        },
    )

    assert response.status_code == 200
    assert asked.narrowing == Narrowing(
        tags_all=("dragon", "fog"), tags_any=("castle",), meta={"dataset": "coco"}
    ), "normalised as the tags it must match were, and `meta.` read off the query string"


async def test_the_picture_search_takes_the_same_narrowing_as_form_fields(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    asked.answer = a_page(model=DINOV2_LARGE)

    response = await client.post(
        IMAGE,
        files=a_picture(),
        data={"tags_all": "dragon", "meta.dataset": "coco", "limit": "5"},
    )

    assert response.status_code == 200
    assert asked.narrowing == Narrowing(tags_all=("dragon",), meta={"dataset": "coco"})


async def test_an_asset_asks_for_its_neighbours_under_a_narrowing(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    asked.answer = a_page(model=DINOV2_LARGE)

    response = await client.get(SIMILAR, params={"tags_any": "dragon,castle"})

    assert response.status_code == 200
    assert asked.narrowing == Narrowing(tags_any=("dragon", "castle"))


async def test_a_search_without_filters_carries_an_empty_narrowing(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    """Which costs nothing: the repository asks whether it narrows at all."""
    response = await client.get(TEXT, params={"q": "a dragon"})

    assert response.status_code == 200
    assert asked.narrowing == Narrowing()
    assert not asked.narrowing


# --- what is refused ------------------------------------------------------------
#
# One type for all four ways of getting a filter wrong, on every surface: a
# client acts on the type, and the detail names the value.

#: Pairs rather than a mapping, because one of the four ways of getting it
#: wrong is writing the same name twice — which a mapping cannot express.
REFUSALS: list[tuple[list[tuple[str, str]], str, str]] = [
    ([("tags_all", "not a tag!")], "not a tag!", "a tag that is not a tag"),
    ([("meta.Dataset", "coco")], "'Dataset'", "a key outside the shape"),
    (
        [("meta.dataset", "coco"), ("meta.dataset", "unsplash")],
        "twice",
        "the same key twice",
    ),
    (
        [(f"meta.key_{index}", "value") for index in range(MAX_META_CONDITIONS + 1)],
        str(MAX_META_CONDITIONS),
        "more conditions than are allowed",
    ),
]


@pytest.mark.parametrize(
    ("filters", "named", "case"), REFUSALS, ids=[case for _, _, case in REFUSALS]
)
async def test_the_text_search_refuses_it_and_names_it(
    client: httpx.AsyncClient,
    asked: Asked,
    filters: list[tuple[str, str]],
    named: str,
    case: str,
) -> None:
    response = await client.get(TEXT, params=[("q", "a dragon"), *filters])

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == INVALID_FILTER
    assert named in body["detail"], body["detail"]
    assert asked.narrowing is None, "and nothing was searched"


@pytest.mark.parametrize(
    ("filters", "named", "case"), REFUSALS, ids=[case for _, _, case in REFUSALS]
)
async def test_an_asset_search_refuses_it_and_names_it(
    client: httpx.AsyncClient,
    asked: Asked,
    filters: list[tuple[str, str]],
    named: str,
    case: str,
) -> None:
    response = await client.get(SIMILAR, params=filters)

    assert response.status_code == 422
    assert response.json()["type"] == INVALID_FILTER
    assert named in response.json()["detail"]
    assert asked.narrowing is None


@pytest.mark.parametrize(
    ("filters", "named", "case"), REFUSALS, ids=[case for _, _, case in REFUSALS]
)
async def test_the_picture_search_refuses_it_and_names_it(
    client: httpx.AsyncClient,
    asked: Asked,
    filters: list[tuple[str, str]],
    named: str,
    case: str,
) -> None:
    response = await client.post(IMAGE, files=a_picture(), data=as_form(filters))

    assert response.status_code == 422
    assert response.json()["type"] == INVALID_FILTER
    assert named in response.json()["detail"]
    assert asked.narrowing is None, "the picture was parsed, and nothing was embedded"


@pytest.mark.parametrize(
    ("filters", "named", "case"), REFUSALS, ids=[case for _, _, case in REFUSALS]
)
async def test_the_listing_refuses_it_and_names_it(
    client: httpx.AsyncClient, filters: list[tuple[str, str]], named: str, case: str
) -> None:
    """The fourth surface, and the same refusal: what a listing narrows by and
    what a search narrows by are one thing (design decision 4). Refused before
    the store, which the unreachable database would otherwise turn into a 500."""
    response = await client.get(ASSETS, params=filters)

    assert response.status_code == 422
    assert response.json()["type"] == INVALID_FILTER
    assert named in response.json()["detail"]


async def test_a_metadata_parameter_with_no_key_is_refused(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    """`meta.` alone: the prefix is the whole parameter, so the key is empty."""
    response = await client.get(TEXT, params={"q": "a dragon", "meta.": "coco"})

    assert response.status_code == 422
    assert response.json()["type"] == INVALID_FILTER
    assert asked.narrowing is None


async def test_a_key_carrying_a_newline_is_refused_on_the_wire(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    """`meta.dataset%0A=coco` is what the parser's end-anchor let through
    (Gate 2 round 1, finding 4): the key reaches the query string as
    `dataset\n`, which is not the shape `meta.<key>` promises."""
    response = await client.get(TEXT, params=[("q", "a dragon"), ("meta.dataset\n", "coco")])

    assert response.status_code == 422
    assert response.json()["type"] == INVALID_FILTER
    assert asked.narrowing is None


async def test_a_parameter_that_merely_starts_like_one_is_not_a_condition(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    """`metadata=…` is not `meta.…`, and an unknown parameter is ignored as
    every unknown query parameter is."""
    response = await client.get(TEXT, params={"q": "a dragon", "metadata": "coco"})

    assert response.status_code == 200
    assert asked.narrowing == Narrowing()


# --- what the answer says about its own completeness ----------------------------


async def test_a_narrowed_answer_that_was_cut_short_says_so(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    asked.answer = a_page(scan_limited=True)

    response = await client.get(TEXT, params={"q": "a dragon", "tags_all": "dragon"})

    assert response.json()["scan_limited"] is True


async def test_a_narrowed_answer_that_was_not_says_so_too(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    response = await client.get(TEXT, params={"q": "a dragon", "tags_all": "dragon"})

    assert response.json()["scan_limited"] is False


async def test_an_unnarrowed_answer_carries_the_field_as_false(
    client: httpx.AsyncClient, asked: Asked
) -> None:
    """Always present, so a client reads one field rather than two shapes."""
    response = await client.get(TEXT, params={"q": "a dragon"})

    assert response.json()["scan_limited"] is False


# --- what the document says -----------------------------------------------------


OPERATIONS = [
    ("/api/v1/search/text", "get"),
    ("/api/v1/search/image", "post"),
    ("/api/v1/assets/{asset_id}/similar", "get"),
    ("/api/v1/assets", "get"),
]


@pytest.mark.parametrize(("path", "method"), OPERATIONS, ids=[path for path, _ in OPERATIONS])
async def test_every_narrowable_operation_describes_the_convention(
    client: httpx.AsyncClient, path: str, method: str
) -> None:
    """`meta.<key>` cannot be a listed parameter, so the description carries it
    (design decision 5) — and the declared ones are listed as parameters."""
    document = (await client.get("/api/openapi.json")).json()
    operation = document["paths"][path][method]

    assert "meta.<key>" in operation["description"]
    assert str(MAX_META_CONDITIONS) in operation["description"]
    assert {"tags_all", "tags_any"} <= {
        parameter["name"] for parameter in operation.get("parameters", [])
    } or method == "post", "the tag filters are form fields on the picture search"


async def test_the_document_carries_the_report_and_the_example_shows_it(
    client: httpx.AsyncClient,
) -> None:
    document = (await client.get("/api/openapi.json")).json()
    field = document["components"]["schemas"]["SearchPage"]["properties"]["scan_limited"]

    assert field["description"], "a field a client has to act on needs saying what it means"
    example = document["paths"][TEXT]["get"]["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert example["scan_limited"] is False
