"""Every operation this change adds carries an example, and the example is true.

FR-OPS-4 asks each operation for a summary, a description and an example. An
example that does not parse as the answer it illustrates is worse than none, so
each one is validated by the model it belongs to as well as looked up in the
document.
"""

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.schemas.search import SEARCH_PAGE_EXAMPLE, SearchPage
from app.schemas.stats import STATS_EXAMPLE, TAG_LIST_EXAMPLE, StatsRead, TagList

OPERATIONS: dict[str, tuple[dict[str, Any], type[BaseModel]]] = {
    "/api/v1/search/text": (SEARCH_PAGE_EXAMPLE, SearchPage),
    "/api/v1/tags": (TAG_LIST_EXAMPLE, TagList),
    "/api/v1/stats": (STATS_EXAMPLE, StatsRead),
}


@pytest.mark.parametrize("path", OPERATIONS)
async def test_the_operation_documents_an_example(client: httpx.AsyncClient, path: str) -> None:
    document = (await client.get("/api/openapi.json")).json()

    content = document["paths"][path]["get"]["responses"]["200"]["content"]

    assert content["application/json"]["example"] == OPERATIONS[path][0]


@pytest.mark.parametrize("path", OPERATIONS)
def test_the_example_parses_as_the_answer_it_illustrates(path: str) -> None:
    example, model = OPERATIONS[path]

    parsed = model.model_validate(example)

    assert parsed.model_dump(mode="json", exclude_none=True)
