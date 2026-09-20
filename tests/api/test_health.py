"""Probes against an app whose database is unreachable."""

import httpx
from fastapi import FastAPI

from app import __version__


class _RefusingEngine:
    """Stands in for the engine: any connection attempt is a test failure."""

    def connect(self) -> None:
        raise AssertionError("the liveness probe must not open a database connection")

    async def dispose(self) -> None:
        return None


async def test_health_touches_no_dependency(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.state.engine = _RefusingEngine()
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_ready_reports_unreachable_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not-ready"
    assert body["checks"]["database"] != "ok"
    assert body["checks"]["migrations"] != "ok"
    assert "postgresql" not in response.text
    assert "nobody" not in response.text
