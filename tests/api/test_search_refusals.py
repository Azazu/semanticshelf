"""What a search is refused for, before it reaches the store.

Every case here is decided by the endpoint or by the service's own bounds, so
they run with no database and no model — against the unreachable database of
`tests/conftest.py`, which is exactly what proves nothing was queried.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from app.services.search import MAX_PAGE_DEPTH, QUERY_MAX_LENGTH, RAW_QUERY_MAX_LENGTH
from tests.conftest import make_client

SEARCH = "/api/v1/search/text"


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


async def test_a_search_without_a_query_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get(SEARCH)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert "q" in response.text


@pytest.mark.parametrize("query", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
async def test_a_query_with_nothing_in_it_is_refused(client: httpx.AsyncClient, query: str) -> None:
    response = await client.get(SEARCH, params={"q": query})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] in ("/errors/invalid-query", "/errors/validation")
    assert "q" in body["detail"]


async def test_a_query_beyond_the_maximum_length_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get(SEARCH, params={"q": "d" * (QUERY_MAX_LENGTH + 1)})

    assert response.status_code == 422
    assert str(QUERY_MAX_LENGTH) in response.text


async def test_a_query_whose_padding_pushes_it_over_the_bound_is_accepted(
    client: httpx.AsyncClient,
) -> None:
    """FR-TXT-2 bounds the trimmed query. A `max_length` on the parameter would
    measure the raw string and refuse this one, whose query is exactly at the
    maximum; the 500 from the unreachable database is the proof it was accepted.
    """
    response = await client.get(SEARCH, params={"q": " " + "d" * QUERY_MAX_LENGTH + " "})

    assert response.status_code != 422


async def test_a_raw_query_beyond_the_padding_guard_is_refused_by_the_parameter(
    client: httpx.AsyncClient,
) -> None:
    """The guard NFR-SEC-5 asks for: padding may not make the request unbounded.
    It is deliberately far above the bound that matters, so it can only be hit
    by something that is not a query."""
    response = await client.get(SEARCH, params={"q": " " * (RAW_QUERY_MAX_LENGTH + 1)})

    assert response.status_code == 422


async def test_a_query_too_long_even_after_trimming_says_which_bound(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(SEARCH, params={"q": "  " + "d" * (QUERY_MAX_LENGTH + 1) + "  "})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/invalid-query"
    assert "after trimming" in body["detail"]


async def test_a_query_at_the_maximum_length_is_not_refused_for_its_length(
    client: httpx.AsyncClient,
) -> None:
    """It fails on the unreachable database instead, which is the proof that
    the length was accepted."""
    response = await client.get(SEARCH, params={"q": "d" * QUERY_MAX_LENGTH})

    assert response.status_code != 422


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (20, -1)],
    ids=["limit below one", "limit above the maximum", "negative offset"],
)
async def test_a_page_outside_its_bounds_is_refused(
    client: httpx.AsyncClient, limit: int, offset: int
) -> None:
    response = await client.get(SEARCH, params={"q": "dragon", "limit": limit, "offset": offset})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_a_page_too_deep_is_refused_before_anything_is_searched(
    client: httpx.AsyncClient,
) -> None:
    """The database is unreachable, so a 422 rather than a 500 is the evidence
    that the refusal came first."""
    response = await client.get(
        SEARCH, params={"q": "dragon", "limit": 100, "offset": MAX_PAGE_DEPTH - 99}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/errors/page-too-deep"
    assert str(MAX_PAGE_DEPTH) in body["detail"]


async def test_the_deepest_allowed_page_is_not_refused_for_its_depth(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        SEARCH, params={"q": "dragon", "limit": 100, "offset": MAX_PAGE_DEPTH - 100}
    )

    assert response.status_code != 422


@pytest.mark.parametrize("score", [-1.5, 1.5], ids=["below -1", "above 1"])
async def test_a_threshold_outside_the_similarity_range_is_refused(
    client: httpx.AsyncClient, score: float
) -> None:
    response = await client.get(SEARCH, params={"q": "dragon", "min_score": score})

    assert response.status_code == 422


async def test_a_model_this_build_does_not_run_answers_503(
    test_settings: Settings,
) -> None:
    """A search the deployment cannot perform is a fact about the deployment,
    not a mistake in the request."""
    app = create_app(test_settings.model_copy(update={"enabled_models": ()}))

    async for client in make_client(app):
        response = await client.get(SEARCH, params={"q": "dragon"})

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "/errors/model-unavailable"
    assert "clip-vit-l14" in body["detail"]


async def test_the_operation_is_in_the_openapi_document(client: httpx.AsyncClient) -> None:
    document = (await client.get("/api/openapi.json")).json()

    operation = document["paths"]["/api/v1/search/text"]["get"]
    assert operation["summary"]
    assert "cosine" in operation["description"]
    assert {"q", "limit", "offset", "min_score"} <= {
        parameter["name"] for parameter in operation["parameters"]
    }


async def test_every_status_this_operation_answers_is_documented(
    client: httpx.AsyncClient,
) -> None:
    """FR-OPS-4 asks for the problem-details responses per status code. 422 and
    500 are the application's, declared in the factory; the 503 is this
    operation's own and has to be declared with it.
    """
    document = (await client.get("/api/openapi.json")).json()

    responses = document["paths"]["/api/v1/search/text"]["get"]["responses"]

    assert {"200", "422", "500", "503"} <= responses.keys()
    assert set(responses["503"]["content"]) == {PROBLEM_MEDIA_TYPE}
