"""Readiness against the real database (`make migrate` must have run)."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.main import create_app
from app.services.readiness import code_head
from tests.conftest import make_client

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(*args: str) -> None:
    # In a subprocess: Alembic's async env.py calls asyncio.run(), which cannot
    # nest inside the test's running event loop.
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, cwd=REPO_ROOT)


async def test_ready_when_migrated(db_settings: Settings, tmp_path: Path) -> None:
    app = create_app(db_settings.model_copy(update={"media_root": tmp_path}))
    async for client in make_client(app):
        response = await client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ready",
        # The third check read the real dimension constraint out of the catalog
        # and found the width the code declares for every enabled model.
        "checks": {"database": "ok", "migrations": "ok", "models": "ok", "media": "ok"},
    }


async def test_not_ready_when_migrations_are_behind(db_settings: Settings, tmp_path: Path) -> None:
    app = create_app(db_settings.model_copy(update={"media_root": tmp_path}))
    _alembic("downgrade", "base")
    try:
        async for client in make_client(app):
            response = await client.get("/ready")
        assert response.status_code == 503, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["type"] == "/errors/not-ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["migrations"] == f"database at none, code head {code_head()}"
        # No table, so no constraint to compare against: the check fails with a
        # class name, never with a message that could carry connection material.
        assert body["checks"]["models"] != "ok"
        assert "postgresql" not in response.text
    finally:
        _alembic("upgrade", "head")
