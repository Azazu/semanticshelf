"""Two views over the whole store: the tags in use, and how it is doing.

Neither belongs to one asset, which is why neither hangs off the asset
resource. They are what a browsing UI opens with, and what an operator reads
first when indexing looks slow.
"""

from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Query

from app.api.deps import SessionDep
from app.schemas.stats import STATS_EXAMPLE, TAG_LIST_EXAMPLE, StatsRead, TagCount, TagList
from app.services import stats

PREFIX = "/api/v1"
router = APIRouter(prefix=PREFIX, tags=["catalogue"])

DEFAULT_TAG_LIMIT = 100
MAX_TAG_LIMIT = 500


@router.get(
    "/tags",
    summary="The tags in use, with their counts",
    description=(
        "Every tag carried by at least one asset, with the number of assets carrying it, "
        "most used first and ties broken by the tag itself. A tag that no asset carries any "
        "more is absent. `limit` defaults to 100 and is at most 500."
    ),
    response_model=TagList,
    responses={HTTPStatus.OK: {"content": {"application/json": {"example": TAG_LIST_EXAMPLE}}}},
)
async def list_tags(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_TAG_LIMIT)] = DEFAULT_TAG_LIMIT,
) -> Any:
    counted = await stats.tags(session, limit=limit)
    return TagList(items=[TagCount(tag=tag, assets=assets) for tag, assets in counted], limit=limit)


@router.get(
    "/stats",
    summary="What the service holds, and what it still owes",
    description=(
        "The number of stored assets, the total size of their originals as the assets record "
        "it — thumbnails are not counted and nothing walks the media root — the amount of "
        "indexing work per model and state, and how long the oldest unfinished work has been "
        "waiting. Every number is derived when it is asked for, so none of them can drift "
        "from the store."
    ),
    response_model=StatsRead,
    responses={HTTPStatus.OK: {"content": {"application/json": {"example": STATS_EXAMPLE}}}},
    status_code=HTTPStatus.OK,
)
async def read_stats(session: SessionDep) -> Any:
    return StatsRead.of(await stats.collect(session))


def install(app: FastAPI) -> None:
    """Mount the resource. Kept here so `app/main.py` stays a factory."""
    app.include_router(router)
