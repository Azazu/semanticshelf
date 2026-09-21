"""What the API says about indexing work: the state, the filter, the reset.

All of it is derived from the queue rather than stored on the asset, so all of
it needs the real table. The malformed filters, which are refused before the
service reaches the database, are in the api suite.
"""

import io
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.main import create_app
from app.repositories.jobs import IndexingJobRepository
from app.services.indexing import reset_work
from tests.conftest import make_client

pytestmark = pytest.mark.integration

ASSETS = "/api/v1/assets"
TABLES = "assets, embeddings, indexing_jobs"
NOT_STORED = "0f9b1d2c-3e4f-4a5b-8c7d-9e0f1a2b3c4d"


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def app(db_settings: Settings, media_root: Path) -> FastAPI:
    return create_app(db_settings.model_copy(update={"media_root": media_root}))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def upload(client: httpx.AsyncClient, seed: int = 0) -> dict[str, Any]:
    response = await client.post(ASSETS, files={"file": ("p.png", picture_bytes(seed))})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def set_state(engine: AsyncEngine, asset_id: str, **values: object) -> None:
    """Put an asset's work in a state a test needs, without a runner."""
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(f"UPDATE indexing_jobs SET {assignments} WHERE asset_id = :asset_id"),
            {"asset_id": asset_id, **values},
        )


# --- the state of the work ----------------------------------------------------


async def test_the_representation_reports_the_state_of_each_model(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    done = await upload(client, seed=1)
    waiting = await upload(client, seed=2)
    failed = await upload(client, seed=3)
    # After every upload: each one drains the queue, and a job put back to
    # pending before the last upload would be picked up by that upload's runner.
    await set_state(engine, waiting["id"], status="pending")
    await set_state(engine, failed["id"], status="failed", last_error="ModelNotEnabled: no")

    states = {
        one["id"]: (await client.get(f"{ASSETS}/{one['id']}")).json()["index_status"]
        for one in (done, waiting, failed)
    }

    assert states == {
        done["id"]: {CLIP_VIT_L14: "done"},
        waiting["id"]: {CLIP_VIT_L14: "pending"},
        failed["id"]: {CLIP_VIT_L14: "failed"},
    }


async def test_the_listing_carries_the_state_of_each_asset(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    indexed = await upload(client, seed=1)
    failed = await upload(client, seed=2)
    await set_state(engine, failed["id"], status="failed", last_error="RuntimeError")

    items = (await client.get(ASSETS)).json()["items"]

    assert {one["id"]: one["index_status"] for one in items} == {
        indexed["id"]: {CLIP_VIT_L14: "done"},
        failed["id"]: {CLIP_VIT_L14: "failed"},
    }


# --- the filter ---------------------------------------------------------------


async def test_the_listing_filters_on_the_state_of_the_work(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    indexed = await upload(client, seed=1)
    failed = await upload(client, seed=2)
    await set_state(engine, failed["id"], status="failed", last_error="RuntimeError")
    waiting = await upload(client, seed=3)
    await set_state(engine, waiting["id"], status="pending")

    def ids(body: dict[str, Any]) -> list[str]:
        return [one["id"] for one in body["items"]]

    for state, expected in (
        ("done", [indexed["id"]]),
        ("failed", [failed["id"]]),
        ("pending", [waiting["id"]]),
        ("running", []),
    ):
        response = await client.get(ASSETS, params={"index_status": f"{CLIP_VIT_L14}:{state}"})
        assert response.status_code == 200, response.text
        assert ids(response.json()) == expected, state


async def test_a_filter_naming_a_model_an_asset_has_no_work_for_matches_nothing(
    client: httpx.AsyncClient,
) -> None:
    await upload(client)

    response = await client.get(ASSETS, params={"index_status": f"{DINOV2_LARGE}:done"})

    assert response.status_code == 200
    assert response.json()["items"] == [], "no work for that model is not work that is done"


async def test_the_filter_combines_with_the_other_filters(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    indexed = await upload(client, seed=1)
    await client.patch(f"{ASSETS}/{indexed['id']}", json={"tags": ["dragon"]})
    other = await upload(client, seed=2)
    await client.patch(f"{ASSETS}/{other['id']}", json={"tags": ["castle"]})

    response = await client.get(
        ASSETS, params={"index_status": f"{CLIP_VIT_L14}:done", "tags_all": "dragon"}
    )

    assert [one["id"] for one in response.json()["items"]] == [indexed["id"]]


# --- the work itself ----------------------------------------------------------


async def test_the_jobs_of_an_asset_carry_what_an_operator_needs(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    created = await upload(client)
    await set_state(engine, created["id"], status="failed", attempts=3, last_error="RuntimeError")

    response = await client.get(f"{ASSETS}/{created['id']}/jobs")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    job = items[0]
    assert job["model"] == CLIP_VIT_L14
    assert (job["status"], job["attempts"], job["last_error"]) == ("failed", 3, "RuntimeError")
    assert job["created_at"] and job["available_at"]
    assert UUID(job["id"])


async def test_the_jobs_of_an_asset_that_is_not_stored_are_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"{ASSETS}/{NOT_STORED}/jobs")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


# --- the reset ----------------------------------------------------------------


async def test_failed_work_is_reset_and_runs_again(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    created = await upload(client)
    await set_state(engine, created["id"], status="failed", attempts=3, last_error="RuntimeError")
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM embeddings"))

    response = await client.post(f"{ASSETS}/{created['id']}/reindex")

    assert response.status_code == 202, response.text
    assert response.json() == {
        "asset_id": created["id"],
        "models": [CLIP_VIT_L14],
        "jobs": 1,
    }
    # The reset queues the work and the same runner an upload uses drains it.
    read = (await client.get(f"{ASSETS}/{created['id']}")).json()
    assert read["index_status"] == {CLIP_VIT_L14: "done"}
    async with engine.connect() as connection:
        vectors = (
            await connection.execute(sa.text("SELECT count(*) FROM embeddings"))
        ).scalar_one()
    assert vectors == 1, "the vector that was missing is there again"


async def test_a_reset_clears_the_attempts_and_the_reason(
    client: httpx.AsyncClient, engine: AsyncEngine, session: AsyncSession
) -> None:
    """Without the HTTP endpoint, so nothing drains the work underneath: what
    the reset itself leaves is what is under test."""
    created = await upload(client, seed=7)
    await set_state(engine, created["id"], status="failed", attempts=3, last_error="RuntimeError")

    reset = await reset_work(session, UUID(created["id"]))

    assert reset == [CLIP_VIT_L14]
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                sa.text(
                    "SELECT status, attempts, last_error, lease_expires_at, finished_at "
                    "FROM indexing_jobs WHERE asset_id = :id"
                ),
                {"id": created["id"]},
            )
        ).one()
    assert row.status == "pending"
    assert (row.attempts, row.last_error) == (0, None)
    assert (row.lease_expires_at, row.finished_at) == (None, None)


async def test_a_reset_of_chosen_models_leaves_the_others_alone(
    client: httpx.AsyncClient, engine: AsyncEngine, session: AsyncSession
) -> None:
    created = await upload(client, seed=8)
    asset_id = UUID(created["id"])
    async with session.begin():
        await IndexingJobRepository(session).add(asset_id=asset_id, model=DINOV2_LARGE)
    await set_state(engine, created["id"], status="failed", attempts=2, last_error="RuntimeError")

    reset = await reset_work(session, asset_id, models=[DINOV2_LARGE])

    assert reset == [DINOV2_LARGE]
    async with engine.connect() as connection:
        states = dict(
            (
                await connection.execute(
                    sa.text(
                        "SELECT model, status || ':' || attempts FROM indexing_jobs "
                        "WHERE asset_id = :id"
                    ),
                    {"id": created["id"]},
                )
            ).all()
        )
    assert states == {DINOV2_LARGE: "pending:0", CLIP_VIT_L14: "failed:2"}


async def test_a_reset_naming_a_model_the_service_does_not_know_is_422(
    client: httpx.AsyncClient,
) -> None:
    created = await upload(client)

    response = await client.post(
        f"{ASSETS}/{created['id']}/reindex", json={"models": ["dinov2-xl"]}
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "/errors/unknown-model"
    assert "dinov2-xl" in body["detail"]


async def test_a_reset_of_an_asset_that_is_not_stored_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{ASSETS}/{NOT_STORED}/reindex")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_a_reset_of_work_an_asset_never_had_says_so(
    client: httpx.AsyncClient,
) -> None:
    created = await upload(client)

    response = await client.post(
        f"{ASSETS}/{created['id']}/reindex", json={"models": [DINOV2_LARGE]}
    )

    assert response.status_code == 202
    assert response.json() == {"asset_id": created["id"], "models": [], "jobs": 0}
