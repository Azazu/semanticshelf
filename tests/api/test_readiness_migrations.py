"""Where the probe looks for the migrations, and what it says when they are not
there.

The path used to be computed from the package's own location — right for a
checkout, where `app/` and `alembic/` sit side by side, and wrong for an
installed package, where one level up is `site-packages` and the `alembic` there
is the library rather than this project's revisions. The container stack of
change 15 is exactly that case: the probe answered "code head none" against a
database that had just been migrated successfully. So the path is a setting
whose default is the old computation.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.settings import DEFAULT_ALEMBIC_DIR, Settings
from app.main import create_app
from app.ml import registry
from app.services.readiness import code_head
from tests.conftest import make_client

AGREEING = (
    "CHECK ((((model = 'clip-vit-l14'::text) AND (vector_dims(vector) = 768))"
    " OR ((model = 'dinov2-large'::text) AND (vector_dims(vector) = 1024))))"
)
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


class StubConnection:
    """A database that answers, and that is at the head of the real scripts."""

    async def __aenter__(self) -> "StubConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, statement: Any) -> list[tuple[Any, ...]]:
        if "pg_constraint" in str(statement):
            return [(AGREEING,)]
        return [(1,)]

    async def run_sync(self, function: Any) -> str | None:
        return code_head(DEFAULT_ALEMBIC_DIR)


class StubEngine:
    def connect(self) -> StubConnection:
        return StubConnection()

    async def dispose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def empty_registry() -> None:
    registry.clear()


async def probe(*, media_root: Path, alembic_dir: Path) -> httpx.Response:
    settings = Settings(
        _env_file=None,
        database_url=UNREACHABLE_DATABASE_URL,
        media_root=media_root,
        alembic_dir=alembic_dir,
    )
    app = create_app(settings)
    async for client in make_client(app):
        app.state.engine = StubEngine()
        return await client.get("/ready")
    raise AssertionError("the client fixture yielded nothing")


async def test_the_migrations_where_the_setting_says_make_the_service_ready(
    tmp_path: Path,
) -> None:
    response = await probe(media_root=tmp_path, alembic_dir=DEFAULT_ALEMBIC_DIR)

    assert response.status_code == 200
    assert response.json()["checks"]["migrations"] == "ok"


async def test_migrations_the_probe_cannot_find_are_not_a_ready_service(tmp_path: Path) -> None:
    """The container's failure, reproduced: a migrated database and a probe
    pointed somewhere with no revisions in it."""
    elsewhere = tmp_path / "not-the-migrations"
    (elsewhere / "versions").mkdir(parents=True)
    (elsewhere / "env.py").write_text("", encoding="utf-8")

    response = await probe(media_root=tmp_path, alembic_dir=elsewhere)

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["migrations"].endswith("code head none")


def test_the_default_is_the_repository_s_own_migrations() -> None:
    """A checkout keeps working with no setting at all: the default is where the
    revisions actually are."""
    assert Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL).alembic_dir == (
        DEFAULT_ALEMBIC_DIR
    )
    assert (DEFAULT_ALEMBIC_DIR / "versions").is_dir()
    assert code_head(DEFAULT_ALEMBIC_DIR) is not None


def test_the_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ALEMBIC_DIR", str(tmp_path))
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)
    assert settings.alembic_dir == tmp_path
