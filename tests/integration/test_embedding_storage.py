"""What the store guarantees about embeddings: identity, width, and the lookup."""

from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Asset, vector_index_name
from app.models import Embedding as EmbeddingRow
from app.repositories import AssetRepository, EmbeddingRepository
from tests.integration.conftest import explain

pytestmark = pytest.mark.integration

CLIP, CLIP_DIM = "clip-vit-l14", 768
DINO, DINO_DIM = "dinov2-large", 1024


def plane_vector(dimension: int, x: float, y: float) -> list[float]:
    """A vector in the first two coordinates, so cosine distance is easy to read."""
    values = [0.0] * dimension
    values[0], values[1] = x, y
    return values


#: As PostgreSQL words it, with the quotes: matching the bare name would
#: also match a constraint called `ck_embeddings_ck_embeddings_model_dimension`,
#: which is how this assertion stayed green while the schema drifted (0003).
DIMENSION_VIOLATION = 'constraint "ck_embeddings_model_dimension"'


async def add_asset(repository: AssetRepository, sha: str) -> Asset:
    return await repository.add(
        sha256=sha,
        content_type="image/png",
        file_ext="png",
        width=64,
        height=64,
        size_bytes=1024,
        source="upload",
    )


async def count_rows(session: AsyncSession, asset_id: UUID, model: str) -> int:
    statement = (
        sa.select(sa.func.count())
        .select_from(EmbeddingRow)
        .where(EmbeddingRow.asset_id == asset_id, EmbeddingRow.model == model)
    )
    return int((await session.execute(statement)).scalar_one())


async def test_re_extraction_replaces_the_vector(session: AsyncSession) -> None:
    asset = await add_asset(AssetRepository(session), "a" * 64)
    embeddings = EmbeddingRepository(session)

    first = await embeddings.upsert(
        asset_id=asset.id, model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0)
    )
    second = await embeddings.upsert(
        asset_id=asset.id, model=CLIP, vector=plane_vector(CLIP_DIM, 0.0, 1.0)
    )

    assert await count_rows(session, asset.id, CLIP) == 1
    assert second.id == first.id
    stored = await embeddings.get(asset_id=asset.id, model=CLIP)
    assert stored is not None
    assert stored.vector[:2] == (0.0, 1.0)


async def test_two_models_for_one_asset_coexist(session: AsyncSession) -> None:
    asset = await add_asset(AssetRepository(session), "b" * 64)
    embeddings = EmbeddingRepository(session)

    await embeddings.upsert(asset_id=asset.id, model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0))
    await embeddings.upsert(asset_id=asset.id, model=DINO, vector=plane_vector(DINO_DIM, 1.0, 0.0))

    assert await count_rows(session, asset.id, CLIP) == 1
    assert await count_rows(session, asset.id, DINO) == 1
    clip = await embeddings.get(asset_id=asset.id, model=CLIP)
    dino = await embeddings.get(asset_id=asset.id, model=DINO)
    assert clip is not None and dino is not None
    assert len(clip.vector) == CLIP_DIM
    assert len(dino.vector) == DINO_DIM


async def test_the_store_rejects_a_wrong_width(session: AsyncSession) -> None:
    # Straight to the table: the repository would refuse first, and the point
    # here is that the database refuses too.
    asset = await add_asset(AssetRepository(session), "c" * 64)
    with pytest.raises(IntegrityError, match=DIMENSION_VIOLATION):
        async with session.begin_nested():
            await session.execute(
                sa.insert(EmbeddingRow).values(
                    asset_id=asset.id, model=CLIP, vector=plane_vector(DINO_DIM, 1.0, 0.0)
                )
            )


async def test_the_store_rejects_an_unknown_model(session: AsyncSession) -> None:
    asset = await add_asset(AssetRepository(session), "d" * 64)
    with pytest.raises(IntegrityError, match=DIMENSION_VIOLATION):
        async with session.begin_nested():
            await session.execute(
                sa.insert(EmbeddingRow).values(
                    asset_id=asset.id,
                    model="clip-vit-l14-v2",
                    vector=plane_vector(CLIP_DIM, 1.0, 0.0),
                )
            )


async def seed_two_models(session: AsyncSession) -> tuple[Asset, Asset, Asset]:
    """Three assets whose clip order is a, b, c and whose dinov2 order is reversed."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    a = await add_asset(assets, "1" * 64)
    b = await add_asset(assets, "2" * 64)
    c = await add_asset(assets, "3" * 64)

    for asset, (x, y) in ((a, (1.0, 0.0)), (b, (0.6, 0.8)), (c, (0.0, 1.0))):
        await embeddings.upsert(asset_id=asset.id, model=CLIP, vector=plane_vector(CLIP_DIM, x, y))
    for asset, (x, y) in ((a, (0.0, 1.0)), (b, (0.6, 0.8)), (c, (1.0, 0.0))):
        await embeddings.upsert(asset_id=asset.id, model=DINO, vector=plane_vector(DINO_DIM, x, y))
    await session.flush()
    return a, b, c


async def test_nearest_orders_by_cosine_distance(session: AsyncSession) -> None:
    a, b, c = await seed_two_models(session)
    hits = await EmbeddingRepository(session).nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=3
    )

    assert [hit.asset_id for hit in hits] == [a.id, b.id, c.id]
    assert [round(hit.distance, 3) for hit in hits] == [0.0, 0.4, 1.0]


async def test_a_lookup_sees_only_its_own_model(session: AsyncSession) -> None:
    a, b, c = await seed_two_models(session)
    embeddings = EmbeddingRepository(session)

    clip_hits = await embeddings.nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=10
    )
    dino_hits = await embeddings.nearest(
        model=DINO, vector=plane_vector(DINO_DIM, 1.0, 0.0), limit=10
    )

    # Every asset carries a vector under both models, so a leak would show up
    # as six hits or as the other model's order.
    assert [hit.asset_id for hit in clip_hits] == [a.id, b.id, c.id]
    assert [hit.asset_id for hit in dino_hits] == [c.id, b.id, a.id]


async def test_limit_is_honoured(session: AsyncSession) -> None:
    a, b, _ = await seed_two_models(session)
    hits = await EmbeddingRepository(session).nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=2
    )
    assert [hit.asset_id for hit in hits] == [a.id, b.id]


async def test_the_model_index_answers_the_lookup(session: AsyncSession) -> None:
    """The guard on ADR-001: the statement must keep the dimension cast, or the
    expression stops matching the index and the plan degrades to a scan."""
    await seed_two_models(session)
    statement = EmbeddingRepository(session).nearest_statement(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=3
    )

    plan = await explain(session, statement, no_seqscan=True)

    assert vector_index_name(CLIP) in plan, plan
    assert "Seq Scan on embeddings" not in plan, plan


# --- a page of results, and a threshold over it --------------------------------


async def test_an_offset_returns_the_tail_of_the_same_ranking(session: AsyncSession) -> None:
    a, b, c = await seed_two_models(session)
    embeddings = EmbeddingRepository(session)
    query = plane_vector(CLIP_DIM, 1.0, 0.0)

    whole = await embeddings.nearest(model=CLIP, vector=query, limit=3)
    tail = await embeddings.nearest(model=CLIP, vector=query, limit=3, offset=1)

    assert [hit.asset_id for hit in tail] == [hit.asset_id for hit in whole][1:]
    assert [hit.asset_id for hit in tail] == [b.id, c.id]
    assert a.id not in [hit.asset_id for hit in tail]


async def test_an_offset_past_the_end_is_an_empty_page(session: AsyncSession) -> None:
    await seed_two_models(session)

    hits = await EmbeddingRepository(session).nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=3, offset=10
    )

    assert hits == []


async def test_a_maximum_distance_drops_results_without_refilling(
    session: AsyncSession,
) -> None:
    """The threshold applies to the page the lookup was asked for: the third
    asset is not pulled up to replace the one that was dropped."""
    a, b, c = await seed_two_models(session)
    embeddings = EmbeddingRepository(session)
    query = plane_vector(CLIP_DIM, 1.0, 0.0)

    page = await embeddings.nearest(model=CLIP, vector=query, limit=2, max_distance=0.2)

    assert [hit.asset_id for hit in page] == [a.id], "b is 0.4 away, c is 1.0"
    assert b.id not in [hit.asset_id for hit in page]
    assert c.id not in [hit.asset_id for hit in page]


async def test_a_maximum_distance_that_nothing_reaches_is_an_empty_page(
    session: AsyncSession,
) -> None:
    await seed_two_models(session)

    hits = await EmbeddingRepository(session).nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=3, max_distance=-0.5
    )

    assert hits == []


async def test_an_offset_and_a_threshold_together(session: AsyncSession) -> None:
    a, b, c = await seed_two_models(session)

    page = await EmbeddingRepository(session).nearest(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=2, offset=1, max_distance=0.5
    )

    assert [hit.asset_id for hit in page] == [b.id], "a is skipped, c is beyond the distance"
    assert a.id not in [hit.asset_id for hit in page]
    assert c.id not in [hit.asset_id for hit in page]


async def test_two_assets_at_the_same_distance_keep_one_order(session: AsyncSession) -> None:
    """Without a tie-break in SQL the two could swap between requests, and a
    test of a page's contents would become a test of the planner's mood."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    first = await add_asset(assets, "a" * 64)
    second = await add_asset(assets, "b" * 64)
    same = plane_vector(CLIP_DIM, 0.6, 0.8)
    for asset in (first, second):
        await embeddings.upsert(asset_id=asset.id, model=CLIP, vector=same)
    await session.flush()
    expected = sorted([first.id, second.id], key=str)

    orders = [
        [
            hit.asset_id
            for hit in await embeddings.nearest(
                model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=2
            )
        ]
        for _ in range(3)
    ]

    assert orders == [expected, expected, expected]


async def test_the_index_answers_a_page_with_a_threshold(session: AsyncSession) -> None:
    """The statement the search endpoint runs, not merely the simplest one: an
    offset and a threshold must not cost the index scan."""
    await seed_two_models(session)
    statement = EmbeddingRepository(session).nearest_statement(
        model=CLIP, vector=plane_vector(CLIP_DIM, 1.0, 0.0), limit=3, offset=1, max_distance=0.9
    )

    plan = await explain(session, statement, no_seqscan=True)

    assert vector_index_name(CLIP) in plan, plan
    assert "Seq Scan on embeddings" not in plan, plan


async def test_a_page_holding_a_whole_tie_orders_it_by_identifier(
    session: AsyncSession,
) -> None:
    """What the page guarantees: once the equally distant rows are on it, the
    identifier decides their order, and the same page answers the same way."""
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    same = plane_vector(CLIP_DIM, 0.6, 0.8)
    tied = [await add_asset(assets, f"{letter * 64}") for letter in "abc"]
    for asset in tied:
        await embeddings.upsert(asset_id=asset.id, model=CLIP, vector=same)
    await session.flush()
    by_identifier = sorted([asset.id for asset in tied], key=str)
    query = plane_vector(CLIP_DIM, 1.0, 0.0)

    pages = [
        [hit.asset_id for hit in await embeddings.nearest(model=CLIP, vector=query, limit=3)]
        for _ in range(3)
    ]

    assert pages == [by_identifier] * 3


async def test_a_page_that_cuts_through_a_tie_is_ordered_and_stable_here(
    session: AsyncSession,
) -> None:
    """What is promised when a group of identical scores does not fit on one
    page: the page holds whichever members it got, in identifier order. Which
    ones those are is the index's choice.

    The repetition below is not part of that promise. This engine happens to
    answer such a page the same way every time, and the assertion records that
    — a change in it would be worth knowing about — but the specification
    deliberately does not require it, because nothing makes an approximate
    index choose the same members twice.
    """
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    same = plane_vector(CLIP_DIM, 0.6, 0.8)
    tied = [await add_asset(assets, f"{letter * 64}") for letter in "abcde"]
    for asset in tied:
        await embeddings.upsert(asset_id=asset.id, model=CLIP, vector=same)
    await session.flush()
    query = plane_vector(CLIP_DIM, 1.0, 0.0)

    pages = [
        [
            hit.asset_id
            for hit in await embeddings.nearest(model=CLIP, vector=query, limit=2, offset=2)
        ]
        for _ in range(5)
    ]

    assert pages[0] == sorted(pages[0], key=str), "the contract: identifier order"
    assert set(pages[0]) <= {asset.id for asset in tied}
    assert pages == [pages[0]] * 5, "this engine, today: the same members each time"
