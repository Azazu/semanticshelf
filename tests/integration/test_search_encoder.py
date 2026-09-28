"""A search asked of a query encoder, against a real index.

Two things only a real store can show. That an encoder ranks **another
model's** vectors — the ones already written under `clip-vit-l14`, with no row
of its own anywhere — and that the answer says which pair produced the scores.

The encoder here is planar like the model in `test_search.py`: the ranking is
arithmetic, so what is asserted is the routing rather than a model's opinion.
"""

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, MCLIP_XLMR_L14, Asset, dimension_of
from app.main import create_app
from app.ml import registry
from app.ml.base import EmbeddingResult, normalise
from app.ml.fake import FakeEmbedder
from app.repositories import AssetRepository, EmbeddingRepository
from tests.conftest import make_client

pytestmark = pytest.mark.integration

SEARCH = "/api/v1/search/text"
STATS = "/api/v1/stats"
TABLES = "assets, embeddings, indexing_jobs"
CLIP_DIM = dimension_of(CLIP_VIT_L14)


def plane_vector(x: float, y: float) -> list[float]:
    values = [0.0] * CLIP_DIM
    values[0], values[1] = x, y
    return values


class PlanarEncoder(FakeEmbedder):
    """A query encoder that answers with one chosen direction in CLIP's space.

    Which is the whole claim in miniature: its key is its own, its vectors are
    the width and the space of the model it names.
    """

    def __init__(self, x: float = 1.0, y: float = 0.0) -> None:
        super().__init__(MCLIP_XLMR_L14, CLIP_DIM)
        self.direction = (x, y)

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        rows = normalise([plane_vector(*self.direction) for _ in texts])  # type: ignore[arg-type]
        return EmbeddingResult(vectors=rows, truncated=(False,) * len(texts))


class PlanarModel(FakeEmbedder):
    """The storage model's own text side, pointed the other way.

    Deliberately the opposite direction: if a search with the encoder were
    quietly answered by the model, the ranking would come back reversed.
    """

    def __init__(self) -> None:
        super().__init__(CLIP_VIT_L14, CLIP_DIM)

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        rows = normalise([plane_vector(0.0, 1.0) for _ in texts])  # type: ignore[arg-type]
        return EmbeddingResult(vectors=rows, truncated=(False,) * len(texts))


@pytest.fixture
def embedders() -> Iterator[None]:
    registry.clear()
    original = dict(registry.FACTORIES)
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: PlanarModel()
    registry.FACTORIES[MCLIP_XLMR_L14] = lambda settings: PlanarEncoder()
    yield
    registry.FACTORIES.clear()
    registry.FACTORIES.update(original)
    registry.clear()


@pytest.fixture
def encoder_settings(db_settings: Settings) -> Settings:
    return db_settings.model_copy(update={"enabled_query_encoders": (MCLIP_XLMR_L14,)})


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app(encoder_settings: Settings) -> FastAPI:
    return create_app(encoder_settings)


@pytest.fixture
async def client(app: FastAPI, embedders: None) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_client(app):
        yield client


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def a_corpus(session: AsyncSession) -> list[Asset]:
    """Three assets with CLIP vectors, spread across the plane."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    stored = []
    for seed, (x, y) in enumerate(((1.0, 0.0), (0.7, 0.7), (0.0, 1.0)), start=1):
        asset = await assets.add(
            sha256=f"{seed:064d}",
            content_type="image/png",
            file_ext="png",
            width=64,
            height=64,
            size_bytes=1024 * seed,
            source="upload",
            tags=(),
            meta=None,
        )
        await embeddings.upsert(asset_id=asset.id, model=CLIP_VIT_L14, vector=plane_vector(x, y))
        stored.append(asset)
    await session.commit()
    return stored


async def rows_under(engine: AsyncEngine, table: str, model: str) -> int:
    async with engine.connect() as connection:
        found = await connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE model = :model"), {"model": model}
        )
    return int(found.scalar_one())


async def test_an_encoder_ranks_the_vectors_of_the_space_it_answers_in(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    stored = await a_corpus(session)

    answer = await client.get(SEARCH, params={"q": "зебра", "model": MCLIP_XLMR_L14, "limit": 3})

    assert answer.status_code == 200
    body = answer.json()
    # The encoder points at (1, 0), the model's own text side at (0, 1): this
    # order is the encoder's, and the reverse of it would be the model's.
    assert [hit["asset"]["id"] for hit in body["items"]] == [str(one.id) for one in stored]


async def test_the_answer_names_the_pair_that_produced_the_scores(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await a_corpus(session)

    by_encoder = (await client.get(SEARCH, params={"q": "зебра", "model": MCLIP_XLMR_L14})).json()
    by_model = (await client.get(SEARCH, params={"q": "a zebra", "model": CLIP_VIT_L14})).json()

    assert (by_encoder["model"], by_encoder["encoder"]) == (CLIP_VIT_L14, MCLIP_XLMR_L14)
    assert (by_model["model"], by_model["encoder"]) == (CLIP_VIT_L14, None)


async def test_a_search_through_an_encoder_writes_nothing_under_its_name(
    client: httpx.AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    """An encoder owns no rows: not a vector, not a job, not a count."""
    await a_corpus(session)

    await client.get(SEARCH, params={"q": "зебра", "model": MCLIP_XLMR_L14})

    assert await rows_under(engine, "embeddings", MCLIP_XLMR_L14) == 0
    assert await rows_under(engine, "indexing_jobs", MCLIP_XLMR_L14) == 0
    assert await rows_under(engine, "embeddings", CLIP_VIT_L14) == 3, "and the space is untouched"

    stats: dict[str, Any] = (await client.get(STATS)).json()
    assert MCLIP_XLMR_L14 not in [work["model"] for work in stats["work"]]
