"""Probes against an app whose database is unreachable, refusing, or silent."""

import asyncio
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app import __version__
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import make_client

# Built at runtime so no URL with credentials appears in the source.
URL_MATERIAL = "postgresql+asyncpg://" + "dbuser" + ":" + "supersecret" + "@db.internal/shelf"


class _RefusingEngine:
    """Stands in for the engine: any connection attempt is a test failure."""

    def connect(self) -> None:
        raise AssertionError("the liveness probe must not open a database connection")

    async def dispose(self) -> None:
        return None


class _LeakyEngine:
    """Every connection attempt raises with the connection URL in the message."""

    def connect(self) -> None:
        raise RuntimeError(f"could not connect to {URL_MATERIAL}")

    async def dispose(self) -> None:
        return None


async def test_health_touches_no_dependency(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.state.engine = _RefusingEngine()
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_ready_reports_unreachable_database_as_a_problem(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/ready", headers={"X-Request-ID": "ready-1"})
    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "/errors/not-ready"
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
    assert body["detail"]
    assert body["instance"] == "urn:request:ready-1"
    assert body["checks"]["database"] != "ok"
    assert body["checks"]["migrations"] == "skipped: database check failed"
    assert body["checks"]["models"] == "skipped: database check failed"
    assert "postgresql" not in response.text
    assert "127.0.0.1" not in response.text


async def test_ready_never_echoes_connection_material(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    app.state.engine = _LeakyEngine()
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "RuntimeError"
    for secret in ("dbuser", "supersecret", "db.internal", "postgresql"):
        assert secret not in response.text, secret


@pytest.fixture
async def silent_database_port() -> AsyncIterator[int]:
    """A TCP server that accepts and never answers: a black-holed database."""

    stop = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await stop.wait()
        finally:
            writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        # Release the handlers first: Server.wait_closed() waits for them (Python 3.12).
        stop.set()
        server.close()
        await server.wait_closed()


async def test_ready_returns_within_the_budget_when_the_database_is_silent(
    silent_database_port: int,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"postgresql+asyncpg://127.0.0.1:{silent_database_port}/silent",
        readiness_timeout_seconds=0.3,
    )
    started = time.monotonic()
    async for client in make_client(create_app(settings)):
        response = await client.get("/ready")
    elapsed = time.monotonic() - started
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "TimeoutError: no response within 0.3s"
    assert body["checks"]["migrations"] == "skipped: database check failed"
    assert body["checks"]["models"] == "skipped: database check failed"
    assert elapsed < 3.0, elapsed
