"""Problem details for every error class."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Query

from app.core.errors import PROBLEM_MEDIA_TYPE, VALIDATION_TYPE
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import make_client


def build_app_with_test_routes(test_settings: Settings) -> FastAPI:
    app = create_app(test_settings)

    @app.get("/boom", summary="Test route", description="Raises an unhandled exception.")
    async def boom() -> dict[str, str]:
        raise RuntimeError("secret internal state")

    @app.get("/echo", summary="Test route", description="Validated query parameter.")
    async def echo(n: int = Query()) -> dict[str, int]:
        return {"n": n}

    return app


@pytest.fixture
async def test_client(test_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(build_app_with_test_routes(test_settings)):
        yield client


async def test_unknown_route_is_a_problem(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["instance"].startswith("urn:request:")
    assert "errors" not in body


async def test_method_not_allowed_is_a_problem(client: httpx.AsyncClient) -> None:
    response = await client.post("/health")
    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["title"] == "Method Not Allowed"


async def test_validation_failure_lists_locations_only(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/echo", params={"n": "not-a-number-SECRET"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == VALIDATION_TYPE
    assert body["status"] == 422
    assert body["errors"] and all(set(issue) == {"loc", "msg", "type"} for issue in body["errors"])
    assert body["errors"][0]["loc"] == ["query", "n"]
    assert "SECRET" not in response.text


async def test_unhandled_exception_is_a_bare_500(
    test_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    # Built inside the test so the log handler writes to the captured stdout.
    app = build_app_with_test_routes(test_settings)
    async for client in make_client(app):
        response = await client.get("/boom", headers={"X-Request-ID": "boom-1"})
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "",
        "instance": "urn:request:boom-1",
    }
    assert "secret internal state" not in response.text
    records = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    errors = [
        r for r in records if r.get("level") == "error" and r.get("event") == "unhandled exception"
    ]
    assert len(errors) == 1
    assert errors[0]["request_id"] == "boom-1"
    assert "RuntimeError: secret internal state" in errors[0]["exception"]
