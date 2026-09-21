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
