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
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.settings import Settings
from app.domain import (
    CLIP_VIT_L14,
    DINOV2_LARGE,
    NO_NARROWING,
    Asset,
    Narrowing,
    NeighbourHit,
    modality_of,
)
from app.ml.base import TextNotSupportedError
from app.ml.pool import acquire, run_in_pool
from app.repositories.assets import AssetRepository
from app.repositories.embeddings import EmbeddingRepository
from app.services import images, indexing
from app.services.assets import discard_temporary, receive
from app.storage import MediaStorage

#: What a query may be. Fixed by the requirements rather than configured: a
#: bound no deployment turns is not a setting.
QUERY_MAX_LENGTH = 256
#: The bound on the raw parameter, before it is trimmed. It exists only so that
#: padding cannot make a request unbounded (NFR-SEC-5): the bound that matters
#: is the one above, measured after trimming, and four times it is more room
#: than any query written by a person or a client needs.
RAW_QUERY_MAX_LENGTH = 4 * QUERY_MAX_LENGTH
#: pgvector's own maximum for `hnsw.ef_search`, which is also the most
#: candidates one index scan will produce: past it the index cannot answer
#: accurately at all.
MAX_SEARCH_EFFORT = 1000


def depth_bound(*, excluded: int = 0) -> int:
    """How deep a page may reach.

    One of the candidates above is the row beyond the page, and that row is the
    whole of `has_more`; a page that used the last candidate for itself would
    leave the question to be guessed at. `excluded` counts the further rows the
    index will produce that the page may not use — an asset left out of its own
    answer is one — and each of them costs a page of depth.
    """
    return MAX_SEARCH_EFFORT - 1 - excluded


#: The deepest `limit + offset` an ordinary search may ask for, and the deepest
#: one that leaves an asset out of its own answer. Both from the one rule
#: above, so they cannot drift apart.
MAX_PAGE_DEPTH = depth_bound()
MAX_PAGE_DEPTH_EXCLUDING = depth_bound(excluded=1)

#: What a query is made of. A model answers one kind or both (`MODEL_MODALITIES`).
QueryKind = Literal["text", "picture"]


class SearchUnavailableError(Exception):
    """The model a search needs is not one this build can run."""


class InvalidQueryError(ValueError):
    """The query is outside the bounds a query has to be within."""


class PageTooDeepError(ValueError):
    """The page asked for lies beyond the depth the index can answer."""


class WrongModalityError(ValueError):
    """The model named cannot be asked that kind of question."""


class AssetUnknownError(LookupError):
    """No asset carries that identifier."""


class NotIndexedError(LookupError):
    """The asset has no vector of the search model, so it has no neighbours yet.

    Not an empty page: nothing is known about what it looks like, which is not
    the same as nothing being like it.
    """


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
    #: True when the search stopped at the bound on how far it may look rather
    #: than at the end of the ranking. Only a narrowed search can set it, and a
    #: client that sees it knows a short page is not the whole answer.
    scan_limited: bool = False


def effort_for(*, settings: Settings, limit: int, offset: int, excluded: int = 0) -> int:
    """How hard the index should look for this page.

    At least the configured effort, at least the depth the page reaches — the
    row beyond it included, since that row is what says whether more exist, and
    any row the search will discard — and never beyond what pgvector accepts.
    `check_depth` keeps the two compatible: the deepest page it allows still
    leaves a candidate for every row the page cannot use.
    """
    return min(MAX_SEARCH_EFFORT, max(settings.hnsw_ef_search, limit + offset + 1 + excluded))


def score_of(distance: float) -> float:
    """Cosine similarity from cosine distance: what a client can reason about."""
    return 1.0 - distance


def normalised_query(raw: str) -> str:
    """The query as the service uses it: trimmed, and within its bounds.

    The bound is on the trimmed value (FR-TXT-2), which is why it cannot be a
    constraint on the parameter: FastAPI would measure the raw string, and a
    query padded with spaces would be refused for a length it does not have.
    """
    query = raw.strip()
    if not query:
        raise InvalidQueryError("q must not be empty")
    if len(query) > QUERY_MAX_LENGTH:
        raise InvalidQueryError(
            f"q must be at most {QUERY_MAX_LENGTH} characters after trimming, got {len(query)}"
        )
    return query


def check_depth(*, limit: int, offset: int, excluded: int = 0) -> None:
    """Refuse a page the index cannot answer, before anything is embedded.

    The bound is short of the index's ceiling on purpose: the row beyond the
    page answers `has_more` and an excluded asset takes another, and both have
    to be candidates the index is willing to produce. Answering such a page
    from a shallower search instead would make `has_more` a guess.
    """
    bound = depth_bound(excluded=excluded)
    if limit + offset > bound:
        raise PageTooDeepError(f"limit + offset must be at most {bound}, got {limit + offset}")


def check_model(model: str, *, settings: Settings, kind: QueryKind) -> None:
    """Refuse a model that cannot answer this query, before anything is loaded.

    Two different refusals, in this order. A model this build does not run is
    unavailable — which is also the answer for a key the application has never
    heard of, since configuration cannot name one. A model this build does run
    but that cannot take this kind of question is a bad request: it names what
    that model can be asked, because a client can act on that.

    The order matters when both hold: what a deployment runs is the fact about
    *this* service, and it is the one worth reporting.
    """
    if model not in settings.enabled_models:
        raise SearchUnavailableError(f"model {model!r} is not enabled in this build")
    modality = modality_of(model)
    if kind == "text" and not modality.text:
        raise WrongModalityError(f"model {model!r} takes {modality.described}, not text")
    if kind == "picture" and not modality.images:
        raise WrongModalityError(f"model {model!r} takes {modality.described}, not pictures")


async def embed_query(
    query: str, *, model: str, settings: Settings, pool: ThreadPoolExecutor
) -> tuple[Sequence[float], bool]:
    """The query as a vector, and whether the model had to cut it short."""
    check_model(model, settings=settings, kind="text")
    embedder = await acquire(pool, model, settings)
    try:
        result = await run_in_pool(pool, embedder.embed_text, [query])
    except TextNotSupportedError as error:
        # Unreachable through `check_model`, and kept anyway: an adapter is
        # free to refuse text the table thought it took, and that is a
        # disagreement to report rather than a stack trace.
        raise SearchUnavailableError(str(error)) from error
    return [float(value) for value in result.vectors[0]], bool(result.truncated[0])


async def embed_picture(
    path: Path, *, model: str, settings: Settings, pool: ThreadPoolExecutor
) -> Sequence[float]:
    """One picture as a vector, decoded and embedded on the inference pool."""
    # Inspected before the model is asked for: a picture the service refuses
    # must not first cost a checkpoint load on a cold process.
    await run_in_threadpool(images.inspect, path, settings)
    embedder = await acquire(pool, model, settings)
    # Which inspects again, deliberately: that is its contract for a file that
    # may have changed under it, and here it costs one open of a small file.
    picture = await run_in_threadpool(images.open_for_inference, path, settings)
    try:
        result = await run_in_pool(pool, embedder.embed_images, [picture])
    finally:
        await run_in_threadpool(picture.close)
    return [float(value) for value in result.vectors[0]]


async def _set_effort(session: AsyncSession, effort: int, *, narrowed: bool) -> None:
    """How hard the index looks, for this transaction only.

    `SET LOCAL` takes no parameters; `set_config(..., true)` is the same thing
    with a bind, and the `true` is what makes it local to this transaction
    rather than to the connection the pool hands on.

    A narrowed search also turns the scan iterative, in the order-preserving
    mode: without it the index chooses its candidates once and the narrowing
    then removes them, which is how a tag matching one asset in three hundred
    answers an empty page (change 12, design decision 2). `relaxed_order` is
    faster and may hand rows back slightly out of order, which this statement
    cuts by distance before it re-orders — so, `strict_order`.
    """
    await session.execute(sa.select(sa.func.set_config("hnsw.ef_search", str(effort), True)))
    if narrowed:
        await session.execute(
            sa.select(sa.func.set_config("hnsw.iterative_scan", "strict_order", True))
        )


def cut(
    candidates: Sequence[NeighbourHit], *, offset: int, limit: int, max_distance: float | None
) -> tuple[list[NeighbourHit], bool]:
    """The page, and whether more exist — cut from the candidates the scan gave.

    The offset skips, the threshold removes results the page already holds, and
    the row beyond the page is what `has_more` reads. All three were in the SQL
    until change 12 needed the count of candidates *before* them (design
    decision 3); what they do is unchanged, and the tests change 8 wrote for the
    threshold say so.

    With a threshold `has_more` stays exact: the candidates are ordered by
    distance, so a row the threshold removes has only further rows after it.
    """
    page = list(candidates[offset : offset + limit + 1])
    if max_distance is not None:
        page = [one for one in page if one.distance <= max_distance]
    return page[:limit], len(page) > limit


def was_cut_short(*, reached: int, needed: int, matching: int) -> bool:
    """Did the scan stop at its own budget rather than at the end of the ranking?

    Only two facts decide it, and neither is the shape of the answer: how many
    candidates the scan reached, and how many matching rows the store holds
    beyond them. A full page proves nothing (a scan that finds exactly `limit`
    rows while more exist returns one), and a short page proves nothing either
    (the threshold shortens a page for an honest reason).
    """
    return reached < needed and matching > reached


@dataclass(frozen=True, slots=True)
class Page:
    """What a ranking answered, before it is turned into a response."""

    hits: list[Hit]
    has_more: bool
    statuses: Mapping[UUID, Mapping[str, str]]
    scan_limited: bool


async def _page_of(
    vector: Sequence[float],
    *,
    session: AsyncSession,
    model: str,
    limit: int,
    offset: int,
    min_score: float | None,
    narrowing: Narrowing,
    exclude_asset_id: UUID | None = None,
) -> Page:
    """One page of the ranking around a vector, whatever made that vector.

    Called inside an open transaction whose search effort is already set. The
    scan is asked for every candidate the answer needs — the offset's worth, the
    page's, and the one beyond it — and the page is cut from what came back.
    """
    needed = offset + limit + 1
    embeddings = EmbeddingRepository(session)
    candidates = await embeddings.nearest(
        model=model,
        vector=vector,
        limit=needed,
        exclude_asset_id=exclude_asset_id,
        narrowing=narrowing or None,
    )
    reached = len(candidates)
    page, has_more = cut(
        candidates,
        offset=offset,
        limit=limit,
        max_distance=None if min_score is None else score_of(min_score),
    )

    scan_limited = False
    if narrowing and reached < needed:
        # Only here: the scan ran out, and one bounded question says of what.
        matching = await embeddings.reachable(
            model=model,
            narrowing=narrowing,
            at_most=reached + 1,
            exclude_asset_id=exclude_asset_id,
        )
        scan_limited = was_cut_short(reached=reached, needed=needed, matching=matching)

    assets = await AssetRepository(session).by_ids([one.asset_id for one in page])
    statuses = await indexing.status_of(session, list(assets))
    hits = [
        Hit(asset=assets[one.asset_id], score=score_of(one.distance))
        for one in page
        if one.asset_id in assets
    ]
    return Page(hits=hits, has_more=has_more, statuses=statuses, scan_limited=scan_limited)


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
    narrowing: Narrowing = NO_NARROWING,
) -> SearchPage:
    """One page of the assets nearest to what the query describes."""
    check_depth(limit=limit, offset=offset)
    vector, truncated = await embed_query(query, model=model, settings=settings, pool=pool)

    async with session.begin():
        await _set_effort(
            session,
            effort_for(settings=settings, limit=limit, offset=offset),
            narrowed=bool(narrowing),
        )
        page = await _page_of(
            vector,
            session=session,
            model=model,
            limit=limit,
            offset=offset,
            min_score=min_score,
            narrowing=narrowing,
        )

    return SearchPage(
        hits=page.hits,
        statuses=page.statuses,
        has_more=page.has_more,
        model=model,
        query_truncated=truncated,
        scan_limited=page.scan_limited,
    )


async def search_image(
    picture: BinaryIO,
    *,
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    limit: int,
    offset: int = 0,
    min_score: float | None = None,
    model: str = DINOV2_LARGE,
    narrowing: Narrowing = NO_NARROWING,
) -> SearchPage:
    """One page of the assets that look most like the picture in the request.

    The picture is written to a temporary file outside the media root, decoded
    under the rules an upload is decoded under, embedded, and unlinked in a
    `finally`. Nothing is stored: no asset row, no file under the media root,
    no lookup by hash. A search is not an upload that forgot to save.
    """
    check_depth(limit=limit, offset=offset)
    check_model(model, settings=settings, kind="picture")

    received = await run_in_threadpool(receive, storage, picture)
    try:
        vector = await embed_picture(received.path, model=model, settings=settings, pool=pool)
    finally:
        await run_in_threadpool(discard_temporary, received.path)

    async with session.begin():
        await _set_effort(
            session,
            effort_for(settings=settings, limit=limit, offset=offset),
            narrowed=bool(narrowing),
        )
        page = await _page_of(
            vector,
            session=session,
            model=model,
            limit=limit,
            offset=offset,
            min_score=min_score,
            narrowing=narrowing,
        )

    return SearchPage(
        hits=page.hits,
        statuses=page.statuses,
        has_more=page.has_more,
        model=model,
        query_truncated=False,
        scan_limited=page.scan_limited,
    )


async def search_similar(
    asset_id: UUID,
    *,
    session: AsyncSession,
    settings: Settings,
    limit: int,
    offset: int = 0,
    min_score: float | None = None,
    model: str = DINOV2_LARGE,
    narrowing: Narrowing = NO_NARROWING,
) -> SearchPage:
    """One page of the assets that look most like a stored one.

    The asset's own stored vector is the query, so no model is loaded and no
    inference runs — which is what makes this answerable on a build whose
    weights were never downloaded. The asset is never among its own neighbours,
    at any page: the exclusion happens inside the query, above the index scan
    and before anything is cut from the candidates (change 11, design decision
    5), and it costs one of the candidates the index may produce, which is why
    the page may not reach as deep as a text or picture query.
    """
    check_depth(limit=limit, offset=offset, excluded=1)
    check_model(model, settings=settings, kind="picture")

    async with session.begin():
        assets = AssetRepository(session)
        if await assets.get(asset_id) is None:
            raise AssetUnknownError(f"no asset {asset_id}")
        embedding = await EmbeddingRepository(session).get(asset_id=asset_id, model=model)
        if embedding is None:
            raise NotIndexedError(f"asset {asset_id} has no {model!r} vector yet")
        await _set_effort(
            session,
            effort_for(settings=settings, limit=limit, offset=offset, excluded=1),
            narrowed=bool(narrowing),
        )
        page = await _page_of(
            embedding.vector,
            session=session,
            model=model,
            limit=limit,
            offset=offset,
            min_score=min_score,
            narrowing=narrowing,
            exclude_asset_id=asset_id,
        )

    return SearchPage(
        hits=page.hits,
        statuses=page.statuses,
        has_more=page.has_more,
        model=model,
        query_truncated=False,
        scan_limited=page.scan_limited,
    )
