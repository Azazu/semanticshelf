"""Readiness against the real database (`make migrate` must have run)."""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from app.main import create_app
from tests.conftest import make_client

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(*args: str) -> None:
    # In a subprocess: Alembic's async env.py calls asyncio.run(), which cannot
    # nest inside the test's running event loop.
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, cwd=REPO_ROOT)


@pytest.fixture
def db_settings() -> Settings:
    try:
        return Settings(log_json=True, log_level="warning")
    except ValidationError:
        pytest.skip("DATABASE_URL is not set: start the database and set it (see the how-to)")


async def test_ready_when_migrated(db_settings: Settings) -> None:
    app = create_app(db_settings)
    async for client in make_client(app):
        response = await client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}


async def test_not_ready_when_migrations_are_behind(db_settings: Settings) -> None:
    app = create_app(db_settings)
    _alembic("downgrade", "base")
    try:
        async for client in make_client(app):
            response = await client.get("/ready")
        assert response.status_code == 503, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["type"] == "/errors/not-ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["migrations"] == "database at none, code head 0001_baseline"
    finally:
        _alembic("upgrade", "head")
