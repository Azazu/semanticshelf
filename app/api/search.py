"""Search: the one endpoint this whole service was built to answer.

The router is thin on purpose — validation, the service call, and the
translation of its refusals into problem details. What a page is, how deep it
may go and what a score means live in `app/services/search.py`.
"""

from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse

from app.api.deps import PoolDep, SessionDep, SettingsDep
from app.core.errors import problem, problem_response
from app.schemas.assets import AssetRead
from app.schemas.search import SEARCH_PAGE_EXAMPLE, SearchHit, SearchPage
from app.services.search import (
    QUERY_MAX_LENGTH,
    PageTooDeepError,
    SearchUnavailableError,
    search_text,
)

PREFIX = "/api/v1/search"
ASSET_PREFIX = "/api/v1/assets"
router = APIRouter(prefix=PREFIX, tags=["search"])

#: The listing's bounds, so that paging feels the same everywhere.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

EMPTY_QUERY_TYPE = "/errors/invalid-query"
PAGE_TOO_DEEP_TYPE = "/errors/page-too-deep"
MODEL_UNAVAILABLE_TYPE = "/errors/model-unavailable"


def _refuse(status: HTTPStatus, type_: str, detail: str) -> JSONResponse:
    return problem_response(problem(status=status, title=status.phrase, detail=detail, type_=type_))


@router.get(
    "/text",
    summary="Find pictures by describing them",
    description=(
        "Embeds the query with the CLIP text tower and ranks the stored image vectors of "
        "`clip-vit-l14` by cosine similarity. `q` is required and at most 256 characters; the "
        "answer says when the model had to cut it. `limit` defaults to 20 and is at most 100, "
        "and `limit + offset` may not exceed 999 — the index answers at most 1000 candidates "
        "for one query and the last of them is the row that says whether more exist, so a "
        "deeper page is refused rather than answered worse. `min_score` drops "
        "results below it after ranking, which makes a page shorter rather than reaching "
        "further down. Scores are comparable only within one model, which the answer names. "
        "The query is English: the model was trained on English captions."
    ),
    response_model=SearchPage,
    responses={HTTPStatus.OK: {"content": {"application/json": {"example": SEARCH_PAGE_EXAMPLE}}}},
)
async def search_by_text(
    session: SessionDep,
    settings: SettingsDep,
    pool: PoolDep,
    q: Annotated[str, Query(max_length=QUERY_MAX_LENGTH, description="What to look for.")],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_score: Annotated[float | None, Query(ge=-1.0, le=1.0)] = None,
) -> Any:
    query = q.strip()
    if not query:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, EMPTY_QUERY_TYPE, "q must not be empty")

    try:
        page = await search_text(
            query,
            session=session,
            settings=settings,
            pool=pool,
            limit=limit,
            offset=offset,
            min_score=min_score,
        )
    except PageTooDeepError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, PAGE_TOO_DEEP_TYPE, str(exc))
    except SearchUnavailableError as exc:
        return _refuse(HTTPStatus.SERVICE_UNAVAILABLE, MODEL_UNAVAILABLE_TYPE, str(exc))

    return SearchPage(
        items=[
            SearchHit(
                asset=AssetRead.of(
                    hit.asset, prefix=ASSET_PREFIX, index_status=page.statuses.get(hit.asset.id)
                ),
                score=hit.score,
            )
            for hit in page.hits
        ],
        limit=limit,
        offset=offset,
        has_more=page.has_more,
        model=page.model,
        query_truncated=page.query_truncated,
    )


def install(app: FastAPI) -> None:
    """Mount the resource. Kept here so `app/main.py` stays a factory."""
    app.include_router(router)
