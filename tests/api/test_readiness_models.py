"""The probe against a schema that agrees with the code, and one that does not.

The database here is a stand-in: what is under test is the comparison and the
body it produces, and both must hold on a machine with no weights and no
container. The integration suite runs the same check against a real schema.
"""

from typing import Any

import httpx
import pytest

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14
from app.main import create_app
from app.ml import registry
from app.services.readiness import code_head
from tests.conftest import make_client

AGREEING = (
    "CHECK ((((model = 'clip-vit-l14'::text) AND (vector_dims(vector) = 768))"
    " OR ((model = 'dinov2-large'::text) AND (vector_dims(vector) = 1024))))"
)
NARROWER = "CHECK (((model = 'clip-vit-l14'::text) AND (vector_dims(vector) = 512)))"
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


class StubConnection:
    """Answers `SELECT 1`, reports the code's head, and returns one constraint."""

    def __init__(self, definition: str) -> None:
        self._definition = definition

    async def __aenter__(self) -> "StubConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, statement: Any) -> list[tuple[Any, ...]]:
        if "pg_constraint" in str(statement):
            return [(self._definition,)]
        return [(1,)]

    async def run_sync(self, function: Any) -> str | None:
        return code_head()


class StubEngine:
    def __init__(self, definition: str) -> None:
        self._definition = definition

    def connect(self) -> StubConnection:
        return StubConnection(self._definition)

    async def dispose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def empty_registry() -> None:
    registry.clear()


async def probe(definition: str) -> httpx.Response:
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)
    app = create_app(settings)
    async for client in make_client(app):
        app.state.engine = StubEngine(definition)
        return await client.get("/ready")
    raise AssertionError("the client fixture yielded nothing")


async def test_a_schema_that_agrees_reports_ready_with_three_checks() -> None:
    response = await probe(AGREEING)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "ok", "models": "ok"},
    }


async def test_a_schema_of_another_width_answers_503_naming_both_widths() -> None:
    response = await probe(NARROWER)

    assert response.status_code == 503
    body = response.json()
    assert body["type"] == "/errors/not-ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["models"] == f"{CLIP_VIT_L14}: code 768, schema 512"


async def test_the_probe_loads_no_model() -> None:
    await probe(NARROWER)
    await probe(AGREEING)

    assert registry.loaded_keys() == frozenset()
