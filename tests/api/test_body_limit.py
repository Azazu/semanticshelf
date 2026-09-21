"""The bound on a request body, counted as it arrives.

Built on a small application of its own: what is under test is the middleware,
not the upload endpoint, and the two should be able to fail separately.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Request

from app.core.body_limit import TOO_LARGE_TYPE, BodySizeLimitMiddleware
from app.core.errors import PROBLEM_MEDIA_TYPE, register_exception_handlers
from app.core.request_id import RequestIdMiddleware

LIMIT = 1024


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    # Order matters and is counter-intuitive: `add_middleware` inserts at the
    # front, so the LAST one added is the outermost. The request-id layer
    # renders unhandled exceptions as 500, so the body limit must sit inside
    # it — added first — or its refusal would be swallowed into a 500.
    application.add_middleware(BodySizeLimitMiddleware, max_bytes=LIMIT)
    application.add_middleware(RequestIdMiddleware)
    register_exception_handlers(application)

    @application.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"read": len(await request.body())}

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_a_body_under_the_limit_is_untouched(client: httpx.AsyncClient) -> None:
    response = await client.post("/echo", content=b"x" * LIMIT)

    assert response.status_code == 200
    assert response.json() == {"read": LIMIT}


async def test_a_body_over_the_limit_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post("/echo", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == TOO_LARGE_TYPE
    assert body["status"] == 413
    assert str(LIMIT) in body["detail"]


async def test_a_body_without_a_declared_length_is_refused(client: httpx.AsyncClient) -> None:
    # A chunked request: there is no length to trust, only bytes that arrive.
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"y" * (LIMIT // 2)

    response = await client.post("/echo", content=chunks())

    assert "content-length" not in {name.lower() for name in response.request.headers}
    assert response.status_code == 413


async def test_a_body_whose_declared_length_understates_it_is_refused(
    client: httpx.AsyncClient,
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"z" * (LIMIT + 1)

    response = await client.post(
        "/echo", content=chunks(), headers={"Content-Length": str(LIMIT // 2)}
    )

    assert response.status_code == 413


async def test_the_sum_of_several_parts_is_what_counts(client: httpx.AsyncClient) -> None:
    # Each chunk is comfortably under the limit; together they are over it.
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"p" * (LIMIT // 2)

    response = await client.post("/echo", content=chunks())

    assert response.status_code == 413
