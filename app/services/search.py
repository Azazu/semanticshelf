"""Finding pictures by describing them.

One request is one query vector and one page of the ranking. The vector is made
on the inference pool, because a CLIP text pass is tens of milliseconds of CPU
and the service answers other requests meanwhile; the page comes from the one
vector query the index answers (`app/repositories/embeddings.py`, ADR-001).

Everything the page needs is read inside a single transaction, and that
transaction exists for one reason beyond tidiness: `hnsw.ef_search` is set for
the transaction, so a deep page is searched as deeply as it asks instead of
quietly getting a worse ranking than a shallow one.
"""

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, Asset
from app.ml.base import TextNotSupportedError
from app.ml.pool import acquire, run_in_pool
from app.repositories.assets import AssetRepository
from app.repositories.embeddings import EmbeddingRepository
from app.services import indexing

#: What a query may be. Fixed by the requirements rather than configured: a
#: bound no deployment turns is not a setting.
QUERY_MAX_LENGTH = 256
#: pgvector's own maximum for `hnsw.ef_search`, which is also the most
#: candidates one index scan will produce: past it the index cannot answer
#: accurately at all.
MAX_SEARCH_EFFORT = 1000
#: How deep a page may reach. One of the candidates above is the row beyond the
#: page, and that row is the whole of `has_more`; a page that used the last
#: candidate for itself would leave the question to be guessed at, so the page
#: stops one short of the index's ceiling.
MAX_PAGE_DEPTH = MAX_SEARCH_EFFORT - 1


class SearchUnavailableError(Exception):
    """The model a search needs is not one this build can run."""


class PageTooDeepError(ValueError):
    """The page asked for lies beyond the depth the index can answer."""


@dataclass(frozen=True, slots=True)
class Hit:
    """One result: the asset, and how near it was."""

    asset: Asset
    score: float


@dataclass(frozen=True, slots=True)
class SearchPage:
    """A page of a ranking, and what the answer has to say about itself."""

    hits: list[Hit]
    statuses: Mapping[UUID, Mapping[str, str]]
    has_more: bool
    model: str
    query_truncated: bool


def effort_for(*, settings: Settings, limit: int, offset: int) -> int:
    """How hard the index should look for this page.

    At least the configured effort, at least the depth the page reaches — the
    row beyond it included, since that row is what says whether more exist —
    and never beyond what pgvector accepts. `check_depth` keeps the two
    compatible: the deepest page it allows still leaves a candidate for the row
    beyond it.
    """
    return min(MAX_SEARCH_EFFORT, max(settings.hnsw_ef_search, limit + offset + 1))


def score_of(distance: float) -> float:
    """Cosine similarity from cosine distance: what a client can reason about."""
    return 1.0 - distance


def check_depth(*, limit: int, offset: int) -> None:
    """Refuse a page the index cannot answer, before anything is embedded.

    The bound is one short of the index's ceiling on purpose: the row beyond
    the page answers `has_more`, and it has to be one of the candidates the
    index is willing to produce.
    """
    if limit + offset > MAX_PAGE_DEPTH:
        raise PageTooDeepError(
            f"limit + offset must be at most {MAX_PAGE_DEPTH}, got {limit + offset}"
        )


async def embed_query(
    query: str, *, model: str, settings: Settings, pool: ThreadPoolExecutor
) -> tuple[Sequence[float], bool]:
    """The query as a vector, and whether the model had to cut it short."""
    if model not in settings.enabled_models:
        raise SearchUnavailableError(f"model {model!r} is not enabled in this build")
    embedder = await acquire(pool, model, settings)
    try:
        result = await run_in_pool(pool, embedder.embed_text, [query])
    except TextNotSupportedError as error:
        raise SearchUnavailableError(str(error)) from error
    return [float(value) for value in result.vectors[0]], bool(result.truncated[0])


async def search_text(
    query: str,
    *,
    session: AsyncSession,
    settings: Settings,
    pool: ThreadPoolExecutor,
    limit: int,
    offset: int = 0,
    min_score: float | None = None,
    model: str = CLIP_VIT_L14,
) -> SearchPage:
    """One page of the assets nearest to what the query describes."""
    check_depth(limit=limit, offset=offset)
    vector, truncated = await embed_query(query, model=model, settings=settings, pool=pool)

    async with session.begin():
        # `SET LOCAL` takes no parameters; `set_config(..., true)` is the same
        # thing with a bind, and the `true` is what makes it local to this
        # transaction rather than to the connection the pool hands on.
        await session.execute(
            sa.select(
                sa.func.set_config(
                    "hnsw.ef_search",
                    str(effort_for(settings=settings, limit=limit, offset=offset)),
                    True,
                )
            )
        )
        # One row beyond the page: that row is the whole of `has_more`. With a
        # threshold it stays exact — the ranking is ordered by distance, so a
        # row the threshold removes has only further rows after it.
        neighbours = await EmbeddingRepository(session).nearest(
            model=model,
            vector=vector,
            limit=limit + 1,
            offset=offset,
            max_distance=None if min_score is None else score_of(min_score),
        )
        has_more = len(neighbours) > limit
        page = neighbours[:limit]
        assets = await AssetRepository(session).by_ids([one.asset_id for one in page])
        statuses = await indexing.status_of(session, list(assets))

    hits = [
        Hit(asset=assets[one.asset_id], score=score_of(one.distance))
        for one in page
        if one.asset_id in assets
    ]
    return SearchPage(
        hits=hits,
        statuses=statuses,
        has_more=has_more,
        model=model,
        query_truncated=truncated,
    )
