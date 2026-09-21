"""Shared fixtures.

`test_settings` points at an unreachable database on purpose (no credentials,
a port nothing listens on): the api layer never needs a database, and the
readiness tests rely on the connection failing fast. Integration tests build
their own settings from the environment.
"""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.core.settings import Settings
from app.main import create_app

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


@pytest.fixture(autouse=True)
def decoder_guard() -> Iterator[None]:
    """Pillow's bomb guard is a process-global, and the application factory sets
    it from `MAX_IMAGE_PIXELS` (`app/services/images.py`). Any test that builds
    an app with a small cap would otherwise shrink every picture a later test
    in the same process may decode — which is exactly what happened once.
    """
    original = Image.MAX_IMAGE_PIXELS
    yield
    Image.MAX_IMAGE_PIXELS = original


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=UNREACHABLE_DATABASE_URL,
        log_level="debug",
        log_json=True,
        readiness_timeout_seconds=1.0,
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


async def make_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app's lifespan and yield a client; httpx's transport does not run the lifespan."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client
