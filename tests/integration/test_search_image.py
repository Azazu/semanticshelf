"""Asking with a picture, against a real index.

Two questions share one ranking here, as they do in the service: a picture sent
in the request, and a picture the store already holds. The vectors are planar
again — one direction per asset, the query another — so the order, the
distances and the scores are arithmetic a reader can check rather than a
plausible-looking list.
"""

import io
import math
import tempfile
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Asset, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import EmbeddingResult, normalise
from app.ml.fake import FakeEmbedder
from app.models import Asset as AssetRow
from app.models import Embedding as EmbeddingRow
from app.repositories import AssetRepository, EmbeddingRepository
from app.services.search import MAX_PAGE_DEPTH, MAX_PAGE_DEPTH_EXCLUDING
from tests.conftest import make_client

pytestmark = pytest.mark.integration

IMAGE_SEARCH = "/api/v1/search/image"
TABLES = "assets, embeddings, indexing_jobs"
DINO_DIM = dimension_of(DINOV2_LARGE)
CLIP_DIM = dimension_of(CLIP_VIT_L14)


def plane_vector(dimension: int, x: float, y: float) -> list[float]:
    """A vector in the first two coordinates, so cosine distance is easy to read."""
    values = [0.0] * dimension
    values[0], values[1] = x, y
    return values


class PlanarImageEmbedder(FakeEmbedder):
    """An image tower that answers with one chosen direction, and no text tower.

    Image-only, like the real DINOv2: what the ranking contains is then decided
    entirely by the fixture, and asking it for words is refused here exactly as
    it would be refused in production.
    """

    def __init__(self, x: float = 1.0, y: float = 0.0) -> None:
        super().__init__(DINOV2_LARGE, DINO_DIM, supports_text=False)
        self.direction = (x, y)
        self.calls = 0

    def embed_images(self, images: Sequence[Any]) -> EmbeddingResult:
        self.calls += 1
        rows = normalise(
            [plane_vector(DINO_DIM, *self.direction) for _ in images]  # type: ignore[arg-type]
        )
        return EmbeddingResult(vectors=rows, truncated=(False,) * len(images))


@pytest.fixture
def embedder() -> Iterator[PlanarImageEmbedder]:
    """The model this suite searches with, in place of the real DINOv2."""
    planar = PlanarImageEmbedder()
    registry.clear()
    original = dict(registry.FACTORIES)
    registry.FACTORIES[DINOV2_LARGE] = lambda settings: planar
    yield planar
    registry.FACTORIES.clear()
    registry.FACTORIES.update(original)
    registry.clear()


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
def settings(db_settings: Settings, media_root: Path) -> Settings:
    """The real database, a media root of this test's own.

    Both models are enabled whatever the environment file says: what a
    deployment runs is not what this suite is about.
    """
    return db_settings.model_copy(
        update={"media_root": media_root, "enabled_models": (CLIP_VIT_L14, DINOV2_LARGE)}
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI, embedder: PlanarImageEmbedder) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


def picture_bytes() -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (64, 64), color=(200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def a_picture() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("query.png", picture_bytes(), "image/png")}


async def add_asset(repository: AssetRepository, seed: int, *, tags: Sequence[str] = ()) -> Asset:
    return await repository.add(
        sha256=f"{seed:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024 * seed,
        source="upload",
        tags=tags,
    )


async def seed_ranking(
    session: AsyncSession,
    angles: Sequence[tuple[float, float]],
    *,
    model: str = DINOV2_LARGE,
    tags: Sequence[Sequence[str]] | None = None,
) -> list[Asset]:
    """One asset per direction, nearest first when the query points at (1, 0).

    `tags` gives one set per direction, so a narrowing can be written against
    positions in the ranking rather than against identifiers.
    """
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    created = []
    for seed, (x, y) in enumerate(angles, start=1):
        asset = await add_asset(assets, seed, tags=() if tags is None else tags[seed - 1])
        await embeddings.upsert(
            asset_id=asset.id, model=model, vector=plane_vector(dimension_of(model), x, y)
        )
        created.append(asset)
    await session.commit()
    return created


#: Four assets, from exactly on the query to a right angle away.
RANKING = [(1.0, 0.0), (0.8, 0.6), (0.6, 0.8), (0.0, 1.0)]


def ids(body: dict[str, Any]) -> list[str]:
    return [item["asset"]["id"] for item in body["items"]]


async def searched(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    response = await client.post(
        IMAGE_SEARCH, files=a_picture(), data={key: str(value) for key, value in fields.items()}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def similar_to(client: httpx.AsyncClient, asset_id: UUID, **params: Any) -> dict[str, Any]:
    response = await client.get(f"/api/v1/assets/{asset_id}/similar", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- a picture in the request -------------------------------------------------


async def test_a_picture_returns_the_whole_ranking_in_order(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await searched(client)

    assert ids(body) == [str(asset.id) for asset in assets]
    assert [round(item["score"], 3) for item in body["items"]] == [1.0, 0.8, 0.6, 0.0]
    assert body["model"] == DINOV2_LARGE
    assert body["has_more"] is False
    assert body["query_truncated"] is False, "a picture is never cut short"


async def test_the_page_and_the_one_after_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    first = await searched(client, limit=2)
    second = await searched(client, limit=2, offset=2)

    assert ids(first) == [str(assets[0].id), str(assets[1].id)]
    assert first["has_more"] is True
    assert ids(second) == [str(assets[2].id), str(assets[3].id)]
    assert second["has_more"] is False


async def test_a_threshold_shortens_the_page_without_reaching_further(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await searched(client, limit=3, min_score=0.7)

    assert ids(body) == [str(assets[0].id), str(assets[1].id)]
    assert body["has_more"] is False


async def test_a_store_with_nothing_indexed_for_that_model_is_an_empty_page(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await seed_ranking(session, RANKING, model=CLIP_VIT_L14)

    body = await searched(client)

    assert body["items"] == []
    assert body["has_more"] is False


async def test_the_query_picture_leaves_nothing_behind(
    client: httpx.AsyncClient, session: AsyncSession, media_root: Path
) -> None:
    """Not an upload that forgot to save: no asset row, nothing under the media
    root, and no file left in the temporary directory either."""
    await seed_ranking(session, RANKING)
    before = await session.execute(sa.select(sa.func.count()).select_from(AssetRow))

    await searched(client)

    after = await session.execute(sa.select(sa.func.count()).select_from(AssetRow))
    assert after.scalar_one() == before.scalar_one()
    assert [path for path in media_root.rglob("*") if path.is_file()] == []
    assert list(Path(tempfile.gettempdir()).glob("semanticshelf-upload-*")) == []


# --- a picture the store already holds ----------------------------------------


async def test_an_asset_finds_its_neighbours_without_loading_a_model(
    client: httpx.AsyncClient, session: AsyncSession, embedder: PlanarImageEmbedder
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await similar_to(client, assets[0].id)

    assert ids(body) == [str(asset.id) for asset in assets[1:]]
    assert body["model"] == DINOV2_LARGE
    assert embedder.calls == 0, "the vector was already stored; nothing was embedded"
    assert registry.loaded_keys() == frozenset(), "and no model was even built"


async def test_an_asset_is_never_among_its_own_neighbours(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    for offset in range(3):
        body = await similar_to(client, assets[0].id, limit=1, offset=offset)
        assert str(assets[0].id) not in ids(body), f"at offset {offset}"


async def test_consecutive_pages_neither_repeat_nor_skip_a_neighbour(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The defect Gate 1 found: with the asset dropped after the page was cut,
    the second page would repeat the last neighbour of the first."""
    assets = await seed_ranking(session, RANKING)
    expected = [str(asset.id) for asset in assets[1:]]

    first = await similar_to(client, assets[0].id, limit=2)
    second = await similar_to(client, assets[0].id, limit=2, offset=2)

    assert ids(first) == expected[:2]
    assert len(ids(first)) == 2, "a full page, not one short"
    assert first["has_more"] is True
    assert ids(second) == expected[2:]
    assert second["has_more"] is False
    assert ids(first) + ids(second) == expected


async def test_a_threshold_applies_to_an_assets_neighbours_too(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING)

    body = await similar_to(client, assets[0].id, min_score=0.7)

    assert ids(body) == [str(assets[1].id)], "0.6 and 0.0 are below it"


async def test_an_asset_with_no_vector_for_that_model_is_a_conflict(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Nothing is known about what it looks like, which is not the same as
    nothing being like it — so 409, not an empty page."""
    await seed_ranking(session, RANKING)
    waiting = await add_asset(AssetRepository(session), 50)
    await session.execute(
        sa.text(
            "INSERT INTO indexing_jobs (asset_id, model, status) VALUES (:id, :model, 'pending')"
        ),
        {"id": str(waiting.id), "model": DINOV2_LARGE},
    )
    await session.commit()

    response = await client.get(f"/api/v1/assets/{waiting.id}/similar")

    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "/errors/not-indexed"
    assert DINOV2_LARGE in body["detail"]


async def test_an_asset_that_does_not_exist_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/assets/{uuid4()}/similar")

    assert response.status_code == 404
    assert response.json()["type"] == "/errors/not-found"


async def test_an_asset_indexed_under_another_model_only_is_a_conflict(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING[:1], model=CLIP_VIT_L14)

    response = await client.get(f"/api/v1/assets/{assets[0].id}/similar")

    assert response.status_code == 409


# --- the two models over the same assets --------------------------------------


async def test_a_search_never_returns_what_the_other_model_ranked(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Both models over one store, pointing in opposite directions: an answer
    that mixed them would be visibly out of order."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    near_under_dino = await add_asset(assets, 1)
    near_under_clip = await add_asset(assets, 2)
    await embeddings.upsert(
        asset_id=near_under_dino.id, model=DINOV2_LARGE, vector=plane_vector(DINO_DIM, 1.0, 0.0)
    )
    await embeddings.upsert(
        asset_id=near_under_dino.id, model=CLIP_VIT_L14, vector=plane_vector(CLIP_DIM, 0.0, 1.0)
    )
    await embeddings.upsert(
        asset_id=near_under_clip.id, model=CLIP_VIT_L14, vector=plane_vector(CLIP_DIM, 1.0, 0.0)
    )
    await session.commit()

    by_picture = await searched(client)

    assert ids(by_picture) == [str(near_under_dino.id)], "only the DINOv2 vectors were ranked"
    assert by_picture["model"] == DINOV2_LARGE


async def test_the_neighbours_of_one_asset_under_each_model(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    asking = await add_asset(assets, 1)
    looks_alike = await add_asset(assets, 2)
    is_about = await add_asset(assets, 3)
    for asset, model, vector in [
        (asking, DINOV2_LARGE, (1.0, 0.0)),
        (asking, CLIP_VIT_L14, (1.0, 0.0)),
        (looks_alike, DINOV2_LARGE, (0.9, 0.1)),
        (looks_alike, CLIP_VIT_L14, (0.0, 1.0)),
        (is_about, DINOV2_LARGE, (0.0, 1.0)),
        (is_about, CLIP_VIT_L14, (0.9, 0.1)),
    ]:
        await embeddings.upsert(
            asset_id=asset.id, model=model, vector=plane_vector(dimension_of(model), *vector)
        )
    await session.commit()

    by_look = await similar_to(client, asking.id, limit=1)
    by_subject = await similar_to(client, asking.id, limit=1, model=CLIP_VIT_L14)

    assert ids(by_look) == [str(looks_alike.id)]
    assert by_look["model"] == DINOV2_LARGE
    assert ids(by_subject) == [str(is_about.id)]
    assert by_subject["model"] == CLIP_VIT_L14


# --- the deepest page this search can answer ----------------------------------


async def seed_deep_ranking(session: AsyncSession, neighbours: int) -> tuple[UUID, list[UUID]]:
    """One asset on the query and `neighbours` behind it, at distinct angles.

    Written in two statements rather than one round trip per row: this is the
    only fixture in the suite that needs a thousand of them, and the point of
    the test is the boundary, not the insert.
    """
    asking = uuid4()
    others = [uuid4() for _ in range(neighbours)]
    rows = [
        {
            "id": identifier,
            "sha256": f"{index:064d}",
            "content_type": "image/png",
            "file_ext": "png",
            "width": 64,
            "height": 64,
            "size_bytes": 1024,
            "source": "upload",
        }
        for index, identifier in enumerate([asking, *others])
    ]
    # The cosine distance to the query is `index * step` exactly, which keeps
    # consecutive rows a thousand times further apart than float32 noise: a tie
    # anywhere in this ranking would blur the boundary the test is about.
    step = 0.9 / (neighbours + 1)
    vectors = [
        {
            "asset_id": identifier,
            "model": DINOV2_LARGE,
            "vector": plane_vector(
                DINO_DIM, 1.0 - index * step, math.sqrt(1.0 - (1.0 - index * step) ** 2)
            ),
        }
        for index, identifier in enumerate([asking, *others])
    ]
    await session.execute(sa.insert(AssetRow), rows)
    await session.execute(sa.insert(EmbeddingRow), vectors)
    await session.commit()
    return asking, others


async def test_the_deepest_page_is_answered_from_the_whole_of_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Arithmetic about the effort is not evidence that the statement asks for
    it. A window one candidate short would return the same items here and say
    that nothing follows them, which is the failure this asserts against.
    """
    limit, offset = 2, MAX_PAGE_DEPTH_EXCLUDING - 2
    asking, others = await seed_deep_ranking(session, neighbours=MAX_PAGE_DEPTH_EXCLUDING + 1)

    body = await similar_to(client, asking, limit=limit, offset=offset)

    assert ids(body) == [str(others[offset]), str(others[offset + 1])]
    assert body["has_more"] is True, "one neighbour is still behind this page"

    # And the same page over a store whose last neighbour ends it.
    await session.execute(sa.delete(AssetRow).where(AssetRow.id == others[-1]))
    await session.commit()

    ended = await similar_to(client, asking, limit=limit, offset=offset)

    assert ids(ended) == ids(body), "the same items"
    assert ended["has_more"] is False, "and now nothing follows them"


async def test_one_page_deeper_is_refused_rather_than_answered_shallow(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    asking, _ = await seed_deep_ranking(session, neighbours=4)

    response = await client.get(
        f"/api/v1/assets/{asking}/similar",
        params={"limit": 2, "offset": MAX_PAGE_DEPTH_EXCLUDING - 1},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert response.json()["type"] == "/errors/page-too-deep"
    assert f"at most {MAX_PAGE_DEPTH_EXCLUDING}" in detail, "its own bound, not the other one"
    assert f"at most {MAX_PAGE_DEPTH}" not in detail


# --- narrowed, on both ways of asking with a picture ----------------------------


async def test_a_picture_search_ranks_only_what_the_narrowing_admits(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The nearest asset does not carry the tag, and the answer starts with the
    nearest one that does — which is what makes this a narrowing of the ranking
    rather than of the page."""
    assets = await seed_ranking(session, RANKING, tags=[[], ["dragon"], ["dragon"], ["castle"]])

    body = await searched(client, tags_all="dragon")

    assert ids(body) == [str(assets[1].id), str(assets[2].id)]
    assert body["scan_limited"] is False


async def test_an_assets_neighbours_can_be_narrowed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    assets = await seed_ranking(session, RANKING, tags=[["dragon"], [], ["dragon"], ["dragon"]])

    body = await similar_to(client, assets[0].id, tags_all="dragon")

    assert ids(body) == [str(assets[2].id), str(assets[3].id)]
    assert str(assets[0].id) not in ids(body), "absent as it always is"


async def test_an_asset_may_ask_under_a_narrowing_it_does_not_satisfy(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The narrowing decides which neighbours are ranked, not whether the
    question may be asked: an asset carrying nothing may still ask what, among
    the dragons, looks most like it."""
    assets = await seed_ranking(session, RANKING, tags=[["castle"], ["dragon"], [], ["dragon"]])

    body = await similar_to(client, assets[0].id, tags_all="dragon")

    assert ids(body) == [str(assets[1].id), str(assets[3].id)]
    assert str(assets[0].id) not in ids(body)


async def test_a_narrowing_by_metadata_reaches_the_picture_search(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """`meta.<key>` travels as a form field beside the picture, which no
    framework can declare for it (change 12, design decision 5)."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    wanted = await assets.add(
        sha256=f"{1:064d}",
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024,
        source="upload",
        meta={"dataset": "coco"},
    )
    other = await add_asset(assets, 2)
    for asset, (x, y) in zip([wanted, other], RANKING[1:3], strict=True):
        await embeddings.upsert(
            asset_id=asset.id,
            model=DINOV2_LARGE,
            vector=plane_vector(DINO_DIM, x, y),
        )
    await session.commit()

    body = await searched(client, **{"meta.dataset": "coco"})

    assert ids(body) == [str(wanted.id)]
