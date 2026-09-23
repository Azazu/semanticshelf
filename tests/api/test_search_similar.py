"""An asset's neighbours: the bounds that differ from the other searches.

What this endpoint answers for a real asset — its neighbours, the 409 and the
404 — needs a store, and lives in the integration suite. What is decided before
the store is touched is here, and the unreachable database is the proof of
which came first.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from app.services.search import MAX_PAGE_DEPTH, MAX_PAGE_DEPTH_EXCLUDING
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

SIMILAR = f"/api/v1/assets/{uuid4()}/similar"
TEMPLATE = "/api/v1/assets/{asset_id}/similar"


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


async def test_an_identifier_that_is_not_one_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/assets/not-a-uuid/similar")

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (20, -1)],
    ids=["limit below one", "limit above the maximum", "negative offset"],
)
async def test_a_page_outside_its_bounds_is_refused(
    client: httpx.AsyncClient, limit: int, offset: int
) -> None:
    response = await client.get(SIMILAR, params={"limit": limit, "offset": offset})

    assert response.status_code == 422


async def test_the_deepest_page_is_one_shallower_than_the_other_searches(
    client: httpx.AsyncClient,
) -> None:
    """Leaving the asset out of its own answer spends one of the candidates the
    index may produce, so this search stops one page short of where a text or
    picture query stops. It is refused, not answered from a shallower search.
    """
    assert MAX_PAGE_DEPTH_EXCLUDING == MAX_PAGE_DEPTH - 1

    response = await client.get(
        SIMILAR, params={"limit": 100, "offset": MAX_PAGE_DEPTH_EXCLUDING - 99}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/page-too-deep"
    assert str(MAX_PAGE_DEPTH_EXCLUDING) in body["detail"]


async def test_the_depth_the_text_search_allows_is_refused_here(
    client: httpx.AsyncClient,
) -> None:
    """The exact page a text query may ask for and this one may not."""
    response = await client.get(SIMILAR, params={"limit": 100, "offset": MAX_PAGE_DEPTH - 100})

    assert response.status_code == 422
    assert response.json()["type"] == "/errors/page-too-deep"


async def test_the_deepest_allowed_page_is_not_refused_for_its_depth(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        SIMILAR, params={"limit": 100, "offset": MAX_PAGE_DEPTH_EXCLUDING - 100}
    )

    assert response.status_code != 422


@pytest.mark.parametrize("score", [-1.5, 1.5], ids=["below -1", "above 1"])
async def test_a_threshold_outside_the_similarity_range_is_refused(
    client: httpx.AsyncClient, score: float
) -> None:
    response = await client.get(SIMILAR, params={"min_score": score})

    assert response.status_code == 422


async def test_the_operation_is_in_the_openapi_document(client: httpx.AsyncClient) -> None:
    document = (await client.get("/api/openapi.json")).json()

    operation = document["paths"][TEMPLATE]["get"]
    assert operation["summary"]
    assert "never among its neighbours" in operation["description"]
    assert {"asset_id", "limit", "offset", "min_score", "model"} <= {
        parameter["name"] for parameter in operation["parameters"]
    }


async def test_every_status_this_operation_answers_is_documented(
    client: httpx.AsyncClient,
) -> None:
    document = (await client.get("/api/openapi.json")).json()

    responses = document["paths"][TEMPLATE]["get"]["responses"]

    assert {"200", "404", "409", "422", "500", "503"} <= responses.keys()
    assert set(responses["409"]["content"]) == {PROBLEM_MEDIA_TYPE}
