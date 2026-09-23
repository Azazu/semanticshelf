"""Narrowing a search, against a real index.

The defect this change exists to prevent cannot be reproduced against a stand-in
— it is the index's own behaviour — so the corpus here is three thousand rows
with a rare tag shuffled through it, and the assertions are about what a page
holds and what the answer says about its own completeness.

The vectors are planar: one direction per asset, the query another, so the
ranking is arithmetic a reader can check.
"""

import json
import math
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.db.engine import create_session_factory
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Narrowing, dimension_of
from app.ml import registry
from app.ml.base import EmbeddingResult, normalise
from app.ml.fake import FakeEmbedder
from app.ml.pool import create_pool
from app.repositories import EmbeddingRepository
from app.services import search

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"
CLIP_DIM = dimension_of(CLIP_VIT_L14)
DINO_DIM = dimension_of(DINOV2_LARGE)
RARE = "rare"
COMMON = "common"


def plane_vector(dimension: int, x: float, y: float) -> list[float]:
    values = [0.0] * dimension
    values[0], values[1] = x, y
    return values


class PlanarEmbedder(FakeEmbedder):
    """A text tower that always answers with the direction the fixtures rank by."""

    def __init__(self) -> None:
        super().__init__(CLIP_VIT_L14, CLIP_DIM)

    def embed_text(self, texts: Sequence[str]) -> EmbeddingResult:
        rows = normalise([plane_vector(CLIP_DIM, 1.0, 0.0) for _ in texts])  # type: ignore[arg-type]
        return EmbeddingResult(vectors=rows, truncated=(False,) * len(texts))


@pytest.fixture
def embedder() -> Iterator[PlanarEmbedder]:
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
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


@pytest.fixture
def pool(db_settings: Settings) -> Iterator[Any]:
    executor = create_pool(db_settings)
    yield executor
    executor.shutdown(wait=True)


async def seed(
    session: AsyncSession,
    *,
    assets: int,
    rare_every: int,
    model: str = CLIP_VIT_L14,
    seed_value: int = 7,
) -> list[UUID]:
    """A ranking of `assets` rows, with one in `rare_every` carrying `RARE`.

    The rare ones are shuffled through the ranking rather than gathered at its
    head: a narrowing that matches only what the index would have returned
    anyway proves nothing about filtering.

    Written in two statements: this is the only fixture that needs thousands of
    rows, and the point is the index's behaviour, not the insert.
    """
    dimension = dimension_of(model)
    order = list(range(assets))
    random.Random(seed_value).shuffle(order)
    identifiers = [uuid4() for _ in range(assets)]
    rows, vectors = [], []
    for position, (identifier, rank) in enumerate(zip(identifiers, order, strict=True)):
        angle = (rank + 1) * (math.pi / 2) / (assets + 2)
        rows.append(
            {
                "id": identifier,
                "sha256": f"{rank:064d}",
                "content_type": "image/png",
                "file_ext": "png",
                "width": 64,
                "height": 64,
                "size_bytes": 1024,
                "source": "upload",
                "tags": [RARE] if position % rare_every == 0 else [COMMON],
                "meta": {"dataset": "coco"} if position % rare_every == 0 else {},
            }
        )
        vectors.append(
            {
                "asset_id": identifier,
                "model": model,
                "vector": plane_vector(dimension, math.cos(angle), math.sin(angle)),
            }
        )
    await session.execute(
        sa.text(
            "INSERT INTO assets (id, sha256, content_type, file_ext, width, height,"
            " size_bytes, source, tags, meta) VALUES (:id, :sha256, :content_type,"
            " :file_ext, :width, :height, :size_bytes, :source, :tags, CAST(:meta AS jsonb))"
        ),
        [{**row, "meta": json.dumps(row["meta"])} for row in rows],
    )
    await session.execute(
        sa.text(
            "INSERT INTO embeddings (asset_id, model, vector) "
            "VALUES (:asset_id, :model, CAST(:vector AS vector))"
        ),
        [{**vector, "vector": str(vector["vector"])} for vector in vectors],
    )
    await session.commit()
    # In ranking order: the nearest first.
    return [identifiers[order.index(rank)] for rank in range(assets)]


async def tagged(session: AsyncSession, tag: str) -> list[UUID]:
    """In a transaction of its own: a read left open is a transaction the next
    search cannot begin inside."""
    async with session.begin():
        rows = await session.execute(
            sa.text("SELECT id FROM assets WHERE tags @> ARRAY[:tag]::text[]"), {"tag": tag}
        )
        return [identifier for (identifier,) in rows]


# --- the defect, reproduced and prevented ---------------------------------------


async def test_a_narrowing_that_matches_rarely_still_fills_a_page(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    """One asset in three hundred carries the tag. With the scan left as it is,
    the index produces its candidates once and the narrowing removes all of
    them: an empty page over a store holding ten matches."""
    await seed(session, assets=3000, rare_every=300)

    page = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=5,
        narrowing=Narrowing(tags_all=(RARE,)),
    )

    assert len(page.hits) == 5, "a full page of the nearest rare assets"
    assert all(RARE in hit.asset.tags for hit in page.hits)
    assert [hit.score for hit in page.hits] == sorted(
        (hit.score for hit in page.hits), reverse=True
    ), "nearest first"
    assert page.scan_limited is False, "ten exist and five were asked for"


async def test_the_scan_is_iterative_only_when_something_is_narrowed(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    """The setting is per query, read from inside the transaction that runs it."""
    await seed(session, assets=50, rare_every=5)
    seen: list[str] = []

    class Watching(EmbeddingRepository):
        async def nearest(self, **kwargs: Any) -> Any:
            value = await self._session.execute(
                sa.select(sa.func.current_setting("hnsw.iterative_scan", True))
            )
            seen.append(value.scalar_one())
            return await super().nearest(**kwargs)

    original = search.EmbeddingRepository
    search.EmbeddingRepository = Watching  # type: ignore[misc]
    try:
        await search.search_text(
            "anything", session=session, settings=db_settings, pool=pool, limit=3
        )
        await search.search_text(
            "anything",
            session=session,
            settings=db_settings,
            pool=pool,
            limit=3,
            narrowing=Narrowing(tags_all=(RARE,)),
        )
    finally:
        search.EmbeddingRepository = original  # type: ignore[misc]

    assert seen == ["off", "strict_order"]


async def test_a_narrowing_changes_which_assets_are_ranked_not_their_scores(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    await seed(session, assets=200, rare_every=4)

    wide = await search.search_text(
        "anything", session=session, settings=db_settings, pool=pool, limit=50
    )
    narrow = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=50,
        narrowing=Narrowing(tags_all=(RARE,)),
    )

    wide_scores = {hit.asset.id: hit.score for hit in wide.hits}
    shared = [hit for hit in narrow.hits if hit.asset.id in wide_scores]
    assert shared, "the two answers overlap"
    for hit in shared:
        assert hit.score == wide_scores[hit.asset.id]


async def test_both_tag_conditions_and_metadata_narrow_the_ranking(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    await seed(session, assets=100, rare_every=10)
    rare = set(await tagged(session, RARE))

    by_all = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=20,
        narrowing=Narrowing(tags_all=(RARE,)),
    )
    by_any = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=20,
        narrowing=Narrowing(tags_any=(RARE, "nothing-carries-this")),
    )
    by_meta = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=20,
        narrowing=Narrowing(meta={"dataset": "coco"}),
    )

    for answer in (by_all, by_any, by_meta):
        assert {hit.asset.id for hit in answer.hits} <= rare
        assert len(answer.hits) == len(rare)


async def test_a_narrowing_nothing_satisfies_is_an_empty_page(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    await seed(session, assets=100, rare_every=10)

    page = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=20,
        narrowing=Narrowing(tags_all=("nothing-carries-this",)),
    )

    assert page.hits == []
    assert page.has_more is False
    assert page.scan_limited is False, "the scan reached the end of a ranking with nothing in it"


# --- what the answer says when the scan stops ----------------------------------


class Counting(EmbeddingRepository):
    """Counts the bounded question decision 3 asks only on the slow path."""

    asked: list[int] = []

    async def reachable(self, **kwargs: Any) -> int:
        found = await super().reachable(**kwargs)
        Counting.asked.append(found)
        return found


@pytest.fixture
def counting() -> Iterator[list[int]]:
    Counting.asked = []
    original = search.EmbeddingRepository
    search.EmbeddingRepository = Counting  # type: ignore[misc]
    yield Counting.asked
    search.EmbeddingRepository = original  # type: ignore[misc]


async def test_an_exhausted_ranking_is_not_reported_as_cut_short(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    """The same shape of answer over a store that genuinely holds no more."""
    await seed(session, assets=100, rare_every=25)

    page = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=20,
        narrowing=Narrowing(tags_all=(RARE,)),
    )

    assert len(page.hits) == 4, "every rare asset there is"
    assert page.has_more is False
    assert page.scan_limited is False


async def test_an_empty_page_because_the_ranking_ran_out(
    session: AsyncSession, db_settings: Settings, pool: Any, embedder: PlanarEmbedder
) -> None:
    await seed(session, assets=100, rare_every=25)

    page = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=5,
        offset=10,
        narrowing=Narrowing(tags_all=(RARE,)),
    )

    assert page.hits == [], "four matches, and the offset skips past all of them"
    assert page.scan_limited is False, "the scan found every one of them"


async def test_a_threshold_emptying_a_page_is_not_a_cut_short_scan(
    session: AsyncSession,
    db_settings: Settings,
    pool: Any,
    embedder: PlanarEmbedder,
    counting: list[int],
) -> None:
    await seed(session, assets=100, rare_every=5)

    page = await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=5,
        min_score=0.999,
        narrowing=Narrowing(tags_all=(RARE,)),
    )

    assert page.hits == [], "the threshold removed everything the page held"
    assert page.scan_limited is False
    assert counting == [], "and the bounded question was never asked"


async def test_the_bounded_question_is_asked_only_when_the_scan_ran_out(
    session: AsyncSession,
    db_settings: Settings,
    pool: Any,
    embedder: PlanarEmbedder,
    counting: list[int],
) -> None:
    await seed(session, assets=200, rare_every=2)

    await search.search_text("anything", session=session, settings=db_settings, pool=pool, limit=5)
    assert counting == [], "an unnarrowed search never asks"

    await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=5,
        narrowing=Narrowing(tags_all=(RARE,)),
    )
    assert counting == [], "nor does a narrowing the scan satisfies comfortably"

    await search.search_text(
        "anything",
        session=session,
        settings=db_settings,
        pool=pool,
        limit=5,
        narrowing=Narrowing(tags_all=("nothing-carries-this",)),
    )
    assert len(counting) == 1, "only the one where the scan ran out"
