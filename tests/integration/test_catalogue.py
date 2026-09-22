"""The two views over the whole store: the tags in use, and how it is doing.

Both are aggregates the store computes, so both need the real one.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, Asset
from app.main import create_app
from app.repositories import AssetRepository, IndexingJobRepository
from tests.conftest import make_client

pytestmark = pytest.mark.integration

TAGS = "/api/v1/tags"
STATS = "/api/v1/stats"
TABLES = "assets, embeddings, indexing_jobs"


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app(db_settings: Settings) -> FastAPI:
    return create_app(db_settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def add_asset(session: AsyncSession, seed: int, *tags: str, size: int = 1024) -> Asset:
    asset = await AssetRepository(session).add(
        sha256=f"{seed:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=size,
        source="upload",
        tags=tags,
    )
    await session.commit()
    return asset


# --- the tags in use ------------------------------------------------------------


async def test_tags_come_back_most_used_first(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await add_asset(session, 1, "dragon", "blue")
    await add_asset(session, 2, "dragon", "castle")
    await add_asset(session, 3, "dragon")

    body = (await client.get(TAGS)).json()

    assert body["items"] == [
        {"tag": "dragon", "assets": 3},
        {"tag": "blue", "assets": 1},
        {"tag": "castle", "assets": 1},
    ]
    assert body["limit"] == 100


async def test_two_tags_used_equally_often_keep_one_order(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await add_asset(session, 1, "zebra", "aardvark")

    pages = [[item["tag"] for item in (await client.get(TAGS)).json()["items"]] for _ in range(3)]

    assert pages == [["aardvark", "zebra"]] * 3, "the tag itself breaks the tie"


async def test_a_tag_no_asset_carries_any_more_is_absent(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    kept = await add_asset(session, 1, "dragon")
    removed = await add_asset(session, 2, "unicorn")

    assert (await client.delete(f"/api/v1/assets/{removed.id}")).status_code == 204
    body = (await client.get(TAGS)).json()

    assert [item["tag"] for item in body["items"]] == ["dragon"]
    assert kept.id is not None


async def test_a_store_with_no_tags_answers_an_empty_list(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await add_asset(session, 1)

    body = (await client.get(TAGS)).json()

    assert body["items"] == []


async def test_the_tag_limit_is_honoured_and_bounded(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await add_asset(session, 1, "dragon", "blue", "castle")

    limited = (await client.get(TAGS, params={"limit": 2})).json()
    refused = await client.get(TAGS, params={"limit": 501})

    assert len(limited["items"]) == 2
    assert limited["limit"] == 2
    assert refused.status_code == 422
    assert refused.headers["content-type"] == PROBLEM_MEDIA_TYPE


# --- what the service holds -------------------------------------------------------


async def test_an_empty_store_answers_zeros(client: httpx.AsyncClient) -> None:
    body = (await client.get(STATS)).json()

    assert body["assets"] == 0
    assert body["stored_bytes"] == 0
    assert body["work"] == []
    assert body["oldest_waiting_seconds"] is None, "absent, not zero"


async def test_the_statistics_count_what_the_store_holds(
    client: httpx.AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    first = await add_asset(session, 1, size=1000)
    second = await add_asset(session, 2, size=2500)
    jobs = IndexingJobRepository(session)
    await jobs.add(asset_id=first.id, model=CLIP_VIT_L14)
    await jobs.add(asset_id=second.id, model=CLIP_VIT_L14)
    await session.commit()
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET status = 'done' WHERE asset_id = :id"),
            {"id": str(first.id)},
        )

    body = (await client.get(STATS)).json()

    assert body["assets"] == 2
    assert body["stored_bytes"] == 3500, "the sizes the assets record, not a walk of the disk"
    assert body["work"] == [
        {"model": CLIP_VIT_L14, "status": "done", "jobs": 1},
        {"model": CLIP_VIT_L14, "status": "pending", "jobs": 1},
    ]


async def test_the_oldest_waiting_work_is_reported_in_seconds(
    client: httpx.AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=CLIP_VIT_L14)
    await session.commit()
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("UPDATE indexing_jobs SET created_at = :when"), {"when": an_hour_ago}
        )

    body = (await client.get(STATS)).json()

    assert body["oldest_waiting_seconds"] == pytest.approx(3600, abs=60)


async def test_work_that_is_finished_is_not_waiting(
    client: httpx.AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    asset = await add_asset(session, 1)
    await IndexingJobRepository(session).add(asset_id=asset.id, model=CLIP_VIT_L14)
    await session.commit()
    async with engine.begin() as connection:
        await connection.execute(sa.text("UPDATE indexing_jobs SET status = 'done'"))

    body = (await client.get(STATS)).json()

    assert body["oldest_waiting_seconds"] is None
    assert body["work"] == [{"model": CLIP_VIT_L14, "status": "done", "jobs": 1}]


async def test_both_views_are_in_the_openapi_document(client: httpx.AsyncClient) -> None:
    document: dict[str, Any] = (await client.get("/api/openapi.json")).json()

    tags_operation = document["paths"]["/api/v1/tags"]["get"]
    stats_operation = document["paths"]["/api/v1/stats"]["get"]
    assert tags_operation["summary"] and stats_operation["summary"]
    assert "most used first" in tags_operation["description"]
    assert "thumbnails are not counted" in stats_operation["description"].lower()
