"""Searching, against a real index.

The ranking here is exact rather than plausible: every asset gets a vector in
one plane and the query gets another, so the order, the distances and therefore
the scores are arithmetic a reader can check. What that buys is a test that
fails when the ranking is subtly wrong, not only when it is absent.
"""

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Asset, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import EmbeddingResult, normalise
from app.ml.fake import FakeEmbedder
from app.ml.pool import create_pool
from app.repositories import AssetRepository, EmbeddingRepository
from app.services import search
from tests.conftest import make_client

pytestmark = pytest.mark.integration

SEARCH = "/api/v1/search/text"
TABLES = "assets, embeddings, indexing_jobs"
CLIP_DIM = dimension_of(CLIP_VIT_L14)
DINO_DIM = dimension_of(DINOV2_LARGE)


def plane_vector(dimension: int, x: float, y: float) -> list[float]:
    """A vector in the first two coordinates, so cosine distance is easy to read."""
    values = [0.0] * dimension
    values[0], values[1] = x, y
    return values


class PlanarEmbedder(FakeEmbedder):
    """A text tower that answers with one chosen direction.

    The ranking a search returns is then decided entirely by the fixture, which
    is what makes an exact assertion possible.
    """

    def __init__(self, x: float = 1.0, y: float = 0.0, *, truncated: bool = False) -> None:
        super().__init__(CLIP_VIT_L14, CLIP_DIM)
        self.direction = (x, y)
        self.truncated = truncated

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        rows = normalise(
            [plane_vector(CLIP_DIM, *self.direction) for _ in texts]  # type: ignore[arg-type]
        )
        return EmbeddingResult(vectors=rows, truncated=(self.truncated,) * len(texts))


@pytest.fixture
def embedder() -> Iterator[PlanarEmbedder]:
    """The model this suite searches with, in place of the real CLIP."""
    planar = PlanarEmbedder()
    registry.clear()
    original = dict(registry.FACTORIES)
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: planar
    yield planar
    registry.FACTORIES.clear()
    registry.FACTORIES.update(original)
    registry.clear()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app(db_settings: Settings) -> FastAPI:
    return create_app(db_settings)


@pytest.fixture
async def client(app: FastAPI, embedder: PlanarEmbedder) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


@pytest.fixture
def pool(db_settings: Settings) -> Iterator[Any]:
    executor = create_pool(db_settings)
    yield executor
    executor.shutdown(wait=True)


async def add_asset(
    repository: AssetRepository,
    seed: int,
    *,
    tags: Sequence[str] = (),
    meta: dict[str, Any] | None = None,
) -> Asset:
    return await repository.add(
        sha256=f"{seed:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024 * seed,
        source="upload",
        tags=tags,
        meta=meta,
    )


async def seed_ranking(
    session: AsyncSession,
    angles: Sequence[tuple[float, float]],
    *,
    tags: Sequence[Sequence[str]] | None = None,
    meta: Sequence[dict[str, Any]] | None = None,
) -> list[Asset]:
    """One asset per direction, nearest first when the query points at (1, 0).

    `tags` and `meta` give one per direction, so a narrowing can be written
    against positions in the ranking rather than against identifiers.
    """
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    created = []
    for seed, (x, y) in enumerate(angles, start=1):
        asset = await add_asset(
            assets,
            seed,
            tags=() if tags is None else tags[seed - 1],
            meta=None if meta is None else meta[seed - 1],
        )
        await embeddings.upsert(
            asset_id=asset.id, model=CLIP_VIT_L14, vector=plane_vector(CLIP_DIM, x, y)
        )
        created.append(asset)
    await session.commit()
    return created


#: Four assets, from exactly on the query to a right angle away.
RANKING = [(1.0, 0.0), (0.8, 0.6), (0.6, 0.8), (0.0, 1.0)]


async def searched(client: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
    response = await client.get(SEARCH, params={"q": "a blue dragon", **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def ids(body: dict[str, Any]) -> list[str]:
    return [item["asset"]["id"] for item in body["items"]]


# --- the ranking ---------------------------------------------------------------


async def test_a_search_returns_the_whole_ranking_in_order(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await searched(client)

    assert ids(body) == [str(asset.id) for asset in assets]
    assert [round(item["score"], 3) for item in body["items"]] == [1.0, 0.8, 0.6, 0.0]
    assert body["model"] == CLIP_VIT_L14
    assert body["has_more"] is False
    assert body["query_truncated"] is False


async def test_the_page_and_the_one_after_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    first = await searched(client, limit=2)
    second = await searched(client, limit=2, offset=2)

    assert ids(first) == [str(assets[0].id), str(assets[1].id)]
    assert first["has_more"] is True
    assert ids(second) == [str(assets[2].id), str(assets[3].id)]
    assert second["has_more"] is False, "there is nothing beyond the fourth"


async def test_an_item_carries_the_asset_as_every_other_endpoint_returns_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING[:1])

    body = await searched(client)

    asset = body["items"][0]["asset"]
    assert asset["id"] == str(assets[0].id)
    assert asset["sha256"] == assets[0].sha256
    assert asset["links"]["file"].endswith(f"/{assets[0].id}/file")
    assert "index_status" in asset


async def test_an_empty_store_is_an_empty_page(client: httpx.AsyncClient) -> None:
    body = await searched(client)

    assert body["items"] == []
    assert body["has_more"] is False


# --- the threshold --------------------------------------------------------------


async def test_a_threshold_shortens_the_page_without_reaching_further(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await searched(client, limit=3, min_score=0.7)

    assert ids(body) == [str(assets[0].id), str(assets[1].id)], "0.6 and 0.0 are below it"
    assert body["has_more"] is False, "nothing further can reach the threshold"


async def test_a_threshold_nothing_reaches_is_an_empty_page(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Nothing sits exactly on the query here: the nearest scores 0.8, so a
    # threshold of 0.99 excludes the whole store rather than nearly all of it.
    await seed_ranking(session, RANKING[1:])

    body = await searched(client, min_score=0.99)

    assert body["items"] == []
    assert body["has_more"] is False


async def test_a_threshold_that_keeps_a_full_page_still_says_more_exist(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await searched(client, limit=2, min_score=0.5)

    assert ids(body) == [str(assets[0].id), str(assets[1].id)]
    assert body["has_more"] is True, "the third asset still passes the threshold"


# --- what the answer says about itself -------------------------------------------


async def test_a_query_the_model_had_to_cut_says_so(
    client: httpx.AsyncClient, session: AsyncSession, embedder: PlanarEmbedder
) -> None:
    await seed_ranking(session, RANKING[:1])
    embedder.truncated = True

    body = await searched(client)

    assert body["query_truncated"] is True
    assert len(body["items"]) == 1, "and the results still come back"


async def test_vectors_of_another_model_are_not_searched(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING[:2])
    embeddings = EmbeddingRepository(session)
    stranger = await add_asset(AssetRepository(session), 99)
    await embeddings.upsert(
        asset_id=stranger.id, model=DINOV2_LARGE, vector=plane_vector(DINO_DIM, 1.0, 0.0)
    )
    await session.commit()

    body = await searched(client)

    assert ids(body) == [str(asset.id) for asset in assets]
    assert str(stranger.id) not in ids(body), "it is nearest, under a model nobody asked for"


async def test_an_asset_with_no_vector_is_not_found(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await seed_ranking(session, RANKING[:1])
    never_indexed = await add_asset(AssetRepository(session), 50)
    await session.commit()

    body = await searched(client)

    assert str(never_indexed.id) not in ids(body)


async def test_an_asset_whose_work_was_queued_again_is_still_found(
    client: httpx.AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    """A reset puts the work back and leaves the vector; hiding the asset until
    the work runs would take it out of search for no gain."""
    assets = await seed_ranking(session, RANKING[:1])
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO indexing_jobs (asset_id, model, status) "
                "VALUES (:id, :model, 'pending')"
            ),
            {"id": str(assets[0].id), "model": CLIP_VIT_L14},
        )

    body = await searched(client)

    assert ids(body) == [str(assets[0].id)]
    assert body["items"][0]["asset"]["index_status"] == {CLIP_VIT_L14: "pending"}


# --- how the search is run --------------------------------------------------------


async def test_the_search_leaves_the_session_as_it_found_it(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    await seed_ranking(session, RANKING)

    first = await search.search_text(
        "a blue dragon", session=session, settings=db_settings, pool=pool, limit=2
    )
    assert not session.in_transaction(), "the search's transaction is its own"

    second = await search.search_text(
        "a blue dragon", session=session, settings=db_settings, pool=pool, limit=2
    )

    assert [hit.asset.id for hit in first.hits] == [hit.asset.id for hit in second.hits]


async def test_the_index_effort_is_in_force_while_the_query_runs(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    """`SET LOCAL` outside a transaction does nothing at all, so the setting is
    read from inside the very query it is supposed to govern."""
    await seed_ranking(session, RANKING)
    seen: list[str] = []

    class Watching(EmbeddingRepository):
        async def nearest(self, **kwargs: Any) -> Any:
            value = await self._session.execute(
                sa.select(sa.func.current_setting("hnsw.ef_search", True))
            )
            seen.append(value.scalar_one())
            return await super().nearest(**kwargs)

    original = search.EmbeddingRepository
    search.EmbeddingRepository = Watching  # type: ignore[misc]
    try:
        await search.search_text(
            "a blue dragon", session=session, settings=db_settings, pool=pool, limit=100, offset=300
        )
    finally:
        search.EmbeddingRepository = original  # type: ignore[misc]

    assert seen == ["401"], "the page reaches 400, and the row beyond it makes 401"


async def test_a_page_costs_the_same_number_of_queries_however_large_it_is(
    session: AsyncSession,
    db_settings: Settings,
    pool: Any,
    engine: AsyncEngine,
    embedder: PlanarEmbedder,
) -> None:
    """The assets of a page are fetched together; a page of ten must not be ten
    lookups."""
    await seed_ranking(session, [(1.0, index / 10) for index in range(10)])
    counted: list[int] = []

    def count(*args: Any, **kwargs: Any) -> None:
        counted[-1] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        for size in (2, 10):
            counted.append(0)
            await search.search_text(
                "a blue dragon", session=session, settings=db_settings, pool=pool, limit=size
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)

    assert counted[0] == counted[1], (
        f"a page of 2 cost {counted[0]}, a page of 10 cost {counted[1]}"
    )


async def test_two_assets_at_the_same_distance_come_back_in_one_order(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, [(0.6, 0.8), (0.6, 0.8)])
    expected = sorted([str(asset.id) for asset in assets])

    pages = [ids(await searched(client)) for _ in range(3)]

    assert pages == [expected, expected, expected]


# --- narrowed -------------------------------------------------------------------


async def test_a_narrowed_search_ranks_only_what_the_narrowing_admits(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The nearest asset carries neither tag, so an answer that merely removed
    rows from the page would come back one item short of what was asked for."""
    assets = await seed_ranking(session, RANKING, tags=[[], ["dragon"], ["dragon"], ["fog"]])

    body = await searched(client, tags_all="dragon", limit=2)

    assert ids(body) == [str(assets[1].id), str(assets[2].id)], "a full page, in order"
    assert body["has_more"] is False
    assert body["scan_limited"] is False


async def test_a_narrowing_by_metadata_reaches_the_text_search(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """`meta.<key>` is read off the query string, which is the only way a
    parameter whose name the caller invents can arrive (design decision 5)."""
    assets = await seed_ranking(
        session, RANKING, meta=[{"dataset": "unsplash"}, {"dataset": "coco"}, {}, {}]
    )

    body = await searched(client, **{"meta.dataset": "coco"})

    assert ids(body) == [str(assets[1].id)]


async def test_a_score_means_the_same_thing_narrowed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """A narrowing decides which assets are ranked, never how near they are."""
    assets = await seed_ranking(session, RANKING, tags=[[], ["dragon"], [], []])
    wide = await searched(client)
    narrow = await searched(client, tags_all="dragon")

    scored = {item["asset"]["id"]: item["score"] for item in wide["items"]}
    assert ids(narrow) == [str(assets[1].id)]
    assert narrow["items"][0]["score"] == scored[str(assets[1].id)]
