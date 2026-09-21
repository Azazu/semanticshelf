"""What the listing refuses when the filter on indexing work is malformed.

Every case here is decided before the service reaches the database — the
filter is parsed first — so this suite runs with no container, against the
unreachable database of `tests/conftest.py`. That it also *works* is the
integration suite's business.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import UNREACHABLE_DATABASE_URL, make_client

ASSETS = "/api/v1/assets"
INVALID_FILTER = "/errors/invalid-filter"


@pytest.fixture
def app(tmp_path: object) -> FastAPI:
    return create_app(
        Settings(
            _env_file=None,
            database_url=UNREACHABLE_DATABASE_URL,
            log_json=True,
            readiness_timeout_seconds=1.0,
        )
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.mark.parametrize(
    ("value", "named"),
    [
        ("dinov2-xl:done", "dinov2-xl"),
        ("clip-vit-l14:finished", "finished"),
        ("clip-vit-l14", "clip-vit-l14"),
        (":done", ":done"),
        ("clip-vit-l14:", "clip-vit-l14:"),
    ],
    ids=["unknown model", "unknown state", "no state", "no model", "empty state"],
)
async def test_a_filter_the_service_cannot_read_is_refused(
    client: httpx.AsyncClient, value: str, named: str
) -> None:
    response = await client.get(ASSETS, params={"index_status": value})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == INVALID_FILTER
    assert named in body["detail"], "the refusal names the value that was wrong"


async def test_a_model_that_exists_but_is_not_implemented_is_still_filterable(
    client: httpx.AsyncClient,
) -> None:
    """`dinov2-large` is a model the schema knows and this build cannot run.

    Work queued for it before it was switched off is still work, so the filter
    must accept the key — the refusal above is for keys that mean nothing. The
    request then fails on the database, which is not what is under test here.
    """
    response = await client.get(ASSETS, params={"index_status": "dinov2-large:failed"})

    assert response.status_code != 422
