"""What the store guarantees about asset records."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import EMBEDDING_MODELS, Asset, Narrowing
from app.repositories import AssetRepository, EmbeddingRepository, IndexingJobRepository
from tests.integration.conftest import explain

pytestmark = pytest.mark.integration

CLIP = "clip-vit-l14"


async def add_asset(
    repository: AssetRepository,
    sha: str,
    *,
    content_type: str = "image/png",
    file_ext: str = "png",
    width: int = 640,
    height: int = 480,
    size_bytes: int = 12345,
    source: str = "upload",
    tags: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
) -> Asset:
    return await repository.add(
        sha256=sha,
        content_type=content_type,
        file_ext=file_ext,
        width=width,
        height=height,
        size_bytes=size_bytes,
        source=source,
        tags=tags,
        meta=meta,
    )


async def test_the_same_content_cannot_be_stored_twice(session: AsyncSession) -> None:
    assets = AssetRepository(session)
    stored = await add_asset(assets, "a" * 64)

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await add_asset(assets, "a" * 64, width=1000)

    again = await assets.get_by_sha256("a" * 64)
    assert again is not None
    assert again.id == stored.id
    assert again.width == 640  # the stored record is untouched


async def test_different_content_gets_its_own_identity(session: AsyncSession) -> None:
    assets = AssetRepository(session)
    first = await add_asset(assets, "b" * 64)
    second = await add_asset(assets, "c" * 64)
    assert first.id != second.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"content_type": "image/gif"},
        {"file_ext": "gif"},
        {"source": "ftp"},
        {"width": 0},
        {"height": -1},
        {"size_bytes": 0},
    ],
    ids=["content-type", "extension", "source", "width", "height", "size"],
)
async def test_the_store_rejects_values_outside_its_domains(
    session: AsyncSession, overrides: dict[str, Any]
) -> None:
    assets = AssetRepository(session)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await add_asset(assets, "d" * 64, **overrides)


async def test_tags_and_metadata_are_queryable(session: AsyncSession) -> None:
    assets = AssetRepository(session)
    dragon = await add_asset(
        assets, "e" * 64, tags=["dragon", "fog"], meta={"dataset": "demo", "lot": "1"}
    )
    castle = await add_asset(assets, "f" * 64, tags=["castle"], meta={"dataset": "other"})

    assert [a.id for a in await assets.find(tags_all=["dragon", "fog"])] == [dragon.id]
    assert [a.id for a in await assets.find(tags_all=["dragon", "castle"])] == []
    assert {a.id for a in await assets.find(tags_any=["dragon", "castle"])} == {
        dragon.id,
        castle.id,
    }
    assert [a.id for a in await assets.find(meta={"dataset": "demo"})] == [dragon.id]
    assert [a.id for a in await assets.find(meta={"dataset": "demo", "lot": "9"})] == []


async def test_an_index_answers_each_containment_query(session: AsyncSession) -> None:
    """The plan of the statement the repository itself builds, so a filter that
    regresses to a non-indexable predicate cannot pass this unnoticed."""
    assets = AssetRepository(session)
    await add_asset(assets, "1" * 64, tags=["dragon"], meta={"dataset": "demo"})
    await session.flush()

    tags_plan = await explain(session, assets.find_statement(tags_all=["dragon"]), no_seqscan=True)
    meta_plan = await explain(
        session, assets.find_statement(meta={"dataset": "demo"}), no_seqscan=True
    )
    assert "ix_assets_tags" in tags_plan, tags_plan
    assert "ix_assets_meta" in meta_plan, meta_plan

    # And the statement the listing itself runs, which since change 12 carries
    # the same filter object a search carries: the narrowing must still be a
    # containment an index can answer, on both columns.
    listed_tags = await explain(
        session,
        assets.page_statement(narrowing=Narrowing(tags_all=("dragon",))),
        no_seqscan=True,
    )
    listed_meta = await explain(
        session,
        assets.page_statement(narrowing=Narrowing(meta={"dataset": "demo"})),
        no_seqscan=True,
    )
    assert "ix_assets_tags" in listed_tags, listed_tags
    assert "ix_assets_meta" in listed_meta, listed_meta


async def test_removing_an_asset_removes_what_was_derived_from_it(
    session: AsyncSession,
) -> None:
    assets = AssetRepository(session)
    embeddings = EmbeddingRepository(session)
    jobs = IndexingJobRepository(session)

    asset = await add_asset(assets, "9" * 64)
    for model, dimension in EMBEDDING_MODELS.items():
        await embeddings.upsert(asset_id=asset.id, model=model, vector=[0.1] * dimension)
    await jobs.add_for_models(asset_id=asset.id)
    await session.flush()

    assert await assets.delete(asset.id) is True
    await session.flush()

    assert await assets.get(asset.id) is None
    for model in EMBEDDING_MODELS:
        assert await embeddings.get(asset_id=asset.id, model=model) is None
    assert await jobs.list_for_asset(asset.id) == []


async def test_deleting_an_absent_asset_reports_nothing_removed(session: AsyncSession) -> None:
    assert await AssetRepository(session).delete(uuid4()) is False


async def test_a_derived_row_cannot_outlive_its_asset(session: AsyncSession) -> None:
    embeddings = EmbeddingRepository(session)
    jobs = IndexingJobRepository(session)
    absent = uuid4()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await embeddings.upsert(asset_id=absent, model=CLIP, vector=[0.1] * 768)

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await jobs.add(asset_id=absent, model=CLIP)
