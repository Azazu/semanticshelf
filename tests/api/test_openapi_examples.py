"""Every operation shows what it answers, and the example is true.

FR-OPS-4 asks each operation for a summary, a description and an example. The
first version of this test named the three operations it knew about, which meant
an operation added without an example passed it; this one reads the document and
requires an example of **every** operation, unless that operation is in the
table of exemptions below with a reason attached.

An example that does not parse as the answer it illustrates is worse than none,
because a reader trusts it — so what the **published document** carries is
validated by the model the service answers with, not the constant in the code
that FastAPI may have encoded on the way out (`app/core/openapi.py`).
"""

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.api.health import HEALTH_EXAMPLE, READY_EXAMPLE, HealthResponse, ReadyResponse
from app.schemas.assets import ASSET_PAGE_EXAMPLE, ASSET_READ_EXAMPLE, AssetPage, AssetRead
from app.schemas.jobs import (
    JOB_LIST_EXAMPLE,
    REINDEX_RESULT_EXAMPLE,
    IndexingJobList,
    ReindexResult,
)
from app.schemas.search import SEARCH_PAGE_EXAMPLE, SearchPage
from app.schemas.stats import STATS_EXAMPLE, TAG_LIST_EXAMPLE, StatsRead, TagList

#: Operations with nothing to exemplify, and why. There are exactly three, and
#: an entry here is a claim somebody can check rather than a silence.
EXEMPT: dict[tuple[str, str], str] = {
    ("delete", "/api/v1/assets/{asset_id}"): "answers 204: there is no body to show",
    ("get", "/api/v1/assets/{asset_id}/file"): "answers with the picture's bytes, not a document",
    ("get", "/api/v1/assets/{asset_id}/thumbnail"): "the same, for the thumbnail",
}

#: Every example the document carries, with the model that must accept it.
EXAMPLES: dict[str, tuple[dict[str, Any], type[BaseModel]]] = {
    "health": (HEALTH_EXAMPLE, HealthResponse),
    "ready": (READY_EXAMPLE, ReadyResponse),
    "asset": (ASSET_READ_EXAMPLE, AssetRead),
    "asset page": (ASSET_PAGE_EXAMPLE, AssetPage),
    "indexing jobs": (JOB_LIST_EXAMPLE, IndexingJobList),
    "reindex": (REINDEX_RESULT_EXAMPLE, ReindexResult),
    "search page": (SEARCH_PAGE_EXAMPLE, SearchPage),
    "tags": (TAG_LIST_EXAMPLE, TagList),
    "stats": (STATS_EXAMPLE, StatsRead),
}

#: Where each example has to appear, so that what is tested is what ships.
WHERE: dict[str, tuple[str, str]] = {
    "health": ("get", "/health"),
    "ready": ("get", "/ready"),
    "asset": ("get", "/api/v1/assets/{asset_id}"),
    "asset page": ("get", "/api/v1/assets"),
    "indexing jobs": ("get", "/api/v1/assets/{asset_id}/jobs"),
    "reindex": ("post", "/api/v1/assets/{asset_id}/reindex"),
    "search page": ("get", "/api/v1/search/text"),
    "tags": ("get", "/api/v1/tags"),
    "stats": ("get", "/api/v1/stats"),
}


def examples_in(operation: dict[str, Any]) -> list[Any]:
    return [
        media["example"]
        for response in operation.get("responses", {}).values()
        for media in response.get("content", {}).values()
        if "example" in media
    ]


async def document(client: httpx.AsyncClient) -> dict[str, Any]:
    answer: dict[str, Any] = (await client.get("/api/openapi.json")).json()
    return answer


async def test_every_operation_shows_what_it_answers(client: httpx.AsyncClient) -> None:
    paths = (await document(client))["paths"]
    without = [
        (method, path)
        for path, methods in paths.items()
        for method, operation in methods.items()
        if not examples_in(operation) and (method, path) not in EXEMPT
    ]

    assert without == [], (
        "these operations carry no example: add one, or add the operation to EXEMPT with "
        f"the reason it has nothing to show — {without}"
    )


async def test_every_operation_also_carries_a_summary_and_a_description(
    client: httpx.AsyncClient,
) -> None:
    paths = (await document(client))["paths"]
    thin = [
        (method, path)
        for path, methods in paths.items()
        for method, operation in methods.items()
        if not operation.get("summary") or not operation.get("description")
    ]

    assert thin == []


async def test_no_exemption_outlives_its_operation(client: httpx.AsyncClient) -> None:
    """A hole for an operation that no longer exists is a hole nobody notices."""
    paths = (await document(client))["paths"]

    for (method, path), reason in EXEMPT.items():
        assert path in paths, f"{path} is exempt from carrying an example and does not exist"
        assert method in paths[path], f"{method.upper()} {path} is exempt and does not exist"
        assert reason.strip(), f"{method.upper()} {path} is exempt for no stated reason"


@pytest.mark.parametrize("name", EXAMPLES)
async def test_the_document_carries_the_example_the_code_declares(
    client: httpx.AsyncClient, name: str
) -> None:
    """Verbatim: a null the service really answers with is in the document too.

    FastAPI encodes the finished document with `exclude_none`, which eats the
    nulls inside an example; `app/core/openapi.py` writes each one back. Without
    that, `lease_expires_at` and `last_error` would be missing from the jobs
    example while the schema beside it still required them.
    """
    method, path = WHERE[name]
    example, _ = EXAMPLES[name]

    operation = (await document(client))["paths"][path][method]

    assert example in examples_in(operation)


@pytest.mark.parametrize("name", EXAMPLES)
async def test_the_published_example_parses_as_the_answer_it_illustrates(
    client: httpx.AsyncClient, name: str
) -> None:
    """What a reader copies out of the document is what is validated here."""
    method, path = WHERE[name]
    _, model = EXAMPLES[name]

    operation = (await document(client))["paths"][path][method]
    published = examples_in(operation)

    assert published, f"{method.upper()} {path} publishes no example"
    for example in published:
        parsed = model.model_validate(example)
        assert parsed.model_dump(mode="json", exclude_none=True)
