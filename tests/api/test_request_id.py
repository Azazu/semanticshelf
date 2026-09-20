"""Request id contract: honoured when well-formed, generated otherwise, present in logs."""

import json
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.core.settings import Settings
from app.main import create_app
from tests.conftest import make_client


async def test_valid_client_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc-123.v2_ok"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "abc-123.v2_ok"


@pytest.mark.parametrize(
    "bad",
    ["", "with space", "a" * 129, "semi;colon", "юникод", "slash/inside"],
    ids=["empty", "space", "too-long", "punctuation", "non-ascii", "slash"],
)
async def test_invalid_client_id_is_replaced(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get(
        "/health", headers={"X-Request-ID": bad.encode("latin-1", "replace")}
    )
    generated = response.headers["x-request-id"]
    assert generated != bad
    assert uuid.UUID(generated).version == 4


async def test_missing_id_is_generated(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert uuid.UUID(response.headers["x-request-id"]).version == 4


async def test_error_responses_carry_the_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/no-such-route", headers={"X-Request-ID": "err-1"})
    assert response.status_code == 404
    assert response.headers["x-request-id"] == "err-1"
    assert response.json()["instance"] == "urn:request:err-1"


async def test_log_lines_carry_request_context(
    test_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    # The app is created inside the test so its stdout handler binds the captured stream.
    app: FastAPI = create_app(test_settings)
    async for client in make_client(app):
        await client.get("/health", headers={"X-Request-ID": "log-42"})
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    completed = [line for line in lines if line.get("event") == "request completed"]
    assert completed, lines
    record = completed[-1]
    assert record["request_id"] == "log-42"
    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["status_code"] == 200
    assert {"timestamp", "level", "event"} <= record.keys()
