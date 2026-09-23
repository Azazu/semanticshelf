"""Search: the endpoints this whole service was built to answer.

Three questions, one shape of answer. Words find what a picture is *about*
(CLIP), a picture finds what *looks like* it (DINOv2), and a stored asset finds
its own neighbours without any inference at all. The router is thin on purpose
— validation, the service call, and the translation of its refusals into
problem details. What a page is, how deep it may go and what a score means live
in `app/services/search.py`.

The picture search parses its multipart body itself, for the reason the upload
gives (`app/api/assets.py`): the parser's own bounds have to be ours, and its
page fields are form fields, which a schema validates.
"""

from http import HTTPStatus
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.api.deps import PoolDep, SessionDep, SettingsDep, StorageDep
from app.core.errors import problem, problem_response, problem_responses
from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.schemas.assets import AssetRead
from app.schemas.search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SEARCH_PAGE_EXAMPLE,
    ImageSearchQuery,
    SearchHit,
    SearchPage,
)
from app.services import images
from app.services.search import (
    MAX_PAGE_DEPTH,
    MAX_PAGE_DEPTH_EXCLUDING,
    QUERY_MAX_LENGTH,
    RAW_QUERY_MAX_LENGTH,
    AssetUnknownError,
    InvalidQueryError,
    NotIndexedError,
    PageTooDeepError,
    SearchUnavailableError,
    WrongModalityError,
    normalised_query,
)
from app.services.search import SearchPage as ServicePage
from app.services.search import search_image as run_image_search
from app.services.search import search_similar as run_similar_search
from app.services.search import search_text as run_text_search

PREFIX = "/api/v1/search"
ASSET_PREFIX = "/api/v1/assets"
router = APIRouter(prefix=PREFIX, tags=["search"])
#: The neighbours of one asset are a search, but they live under the asset they
#: are about — a second router rather than a second module, so that everything
#: about ranking stays in one place.
asset_router = APIRouter(prefix=ASSET_PREFIX, tags=["search"])

#: An image search is one picture and a handful of fields, like an upload.
MAX_FILE_PARTS = 2
MAX_FIELD_PARTS = 40
PARSER_PART_BYTES = 64 * 1024

FILE_FIELD = "file"

INVALID_QUERY_TYPE = "/errors/invalid-query"
PAGE_TOO_DEEP_TYPE = "/errors/page-too-deep"
MODEL_UNAVAILABLE_TYPE = "/errors/model-unavailable"
WRONG_MODALITY_TYPE = "/errors/wrong-modality"
INVALID_UPLOAD_TYPE = "/errors/invalid-upload"
UNSUPPORTED_TYPE = "/errors/unsupported-media-type"
TOO_LARGE_TYPE = "/errors/image-too-large"
TOO_SMALL_TYPE = "/errors/image-too-small"
NOT_INDEXED_TYPE = "/errors/not-indexed"
NOT_FOUND_TYPE = "/errors/not-found"

MODEL_DESCRIPTION = (
    "Which model answers. It must be one this build runs — otherwise 503 — and one that can "
    "take this kind of query — otherwise 422. Scores of different models are never comparable, "
    "and the query is always embedded by the model whose vectors are searched."
)


def _refuse(status: HTTPStatus, type_: str, detail: str) -> JSONResponse:
    return problem_response(problem(status=status, title=status.phrase, detail=detail, type_=type_))


def _rendered(page: ServicePage, *, limit: int, offset: int) -> SearchPage:
    """The one envelope every search answers in."""
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


@router.get(
    "/text",
    summary="Find pictures by describing them",
    description=(
        "Embeds the query with the search model's text tower and ranks that model's stored image "
        "vectors by cosine similarity. `q` is required and at most 256 characters after "
        "trimming; the answer says when the model had to cut it. `limit` defaults to 20 and is "
        "at most 100, "
        f"and `limit + offset` may not exceed {MAX_PAGE_DEPTH} — the index answers at most 1000 "
        "candidates for one query and the last of them is the row that says whether more exist, "
        "so a deeper page is refused rather than answered worse. `min_score` drops "
        "results below it after ranking, which makes a page shorter rather than reaching "
        "further down. Scores are comparable only within one model, which the answer names. "
        "The query is English: the model was trained on English captions."
    ),
    response_model=SearchPage,
    responses={
        HTTPStatus.OK: {"content": {"application/json": {"example": SEARCH_PAGE_EXAMPLE}}},
        # 422 and 500 are the application's, declared once in the factory; the 503 belongs to
        # this operation alone — it is what a build without the search model answers.
        **problem_responses(HTTPStatus.SERVICE_UNAVAILABLE),
    },
)
async def search_by_text(
    session: SessionDep,
    settings: SettingsDep,
    pool: PoolDep,
    q: Annotated[
        str,
        Query(
            max_length=RAW_QUERY_MAX_LENGTH,
            description=(
                f"What to look for. At most {QUERY_MAX_LENGTH} characters **after** "
                f"trimming, which is why that bound is not the parameter's; the "
                f"parameter's own {RAW_QUERY_MAX_LENGTH} only keeps padding from making "
                "the request unbounded."
            ),
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_score: Annotated[float | None, Query(ge=-1.0, le=1.0)] = None,
    model: Annotated[str, Query(description=MODEL_DESCRIPTION)] = CLIP_VIT_L14,
) -> Any:
    try:
        query = normalised_query(q)
    except InvalidQueryError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_QUERY_TYPE, str(exc))

    try:
        page = await run_text_search(
            query,
            session=session,
            settings=settings,
            pool=pool,
            limit=limit,
            offset=offset,
            min_score=min_score,
            model=model,
        )
    except PageTooDeepError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, PAGE_TOO_DEEP_TYPE, str(exc))
    except WrongModalityError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, WRONG_MODALITY_TYPE, str(exc))
    except SearchUnavailableError as exc:
        return _refuse(HTTPStatus.SERVICE_UNAVAILABLE, MODEL_UNAVAILABLE_TYPE, str(exc))

    return _rendered(page, limit=limit, offset=offset)


@router.post(
    "/image",
    summary="Find pictures that look like this one",
    description=(
        "Takes a picture as a multipart `file` part and ranks the stored vectors of the search "
        "model by cosine similarity to it. The picture is accepted under exactly the rules an "
        "upload is accepted by — the format is decided from the bytes, and the same size and "
        "dimension bounds apply — and it is **never stored**: no asset is created for it and "
        "nothing of it remains after the answer. The page fields (`limit`, `offset`, "
        "`min_score`, `model`) are form fields beside the file, with the bounds the text search "
        "has. The default model is `dinov2-large`, which describes appearance rather than "
        "subject: what comes back looks like the query, it is not about the same thing."
    ),
    response_model=SearchPage,
    responses={
        HTTPStatus.OK: {"content": {"application/json": {"example": SEARCH_PAGE_EXAMPLE}}},
        **problem_responses(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            HTTPStatus.SERVICE_UNAVAILABLE,
        ),
    },
)
async def search_by_image(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    pool: PoolDep,
) -> Any:
    async with request.form(
        max_files=MAX_FILE_PARTS,
        max_fields=MAX_FIELD_PARTS,
        max_part_size=PARSER_PART_BYTES,
    ) as form:
        # Every file part, whatever it is called: a second picture under
        # another field name is a second query, and picking one silently would
        # answer a question the client did not ask.
        files = [(key, value) for key, value in form.multi_items() if isinstance(value, UploadFile)]
        if len(files) != 1:
            return _refuse(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                INVALID_UPLOAD_TYPE,
                f"exactly one {FILE_FIELD!r} part is required, got {len(files)} file part(s)",
            )
        field_name, picture = files[0]
        if field_name != FILE_FIELD:
            return _refuse(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                INVALID_UPLOAD_TYPE,
                f"the file part must be called {FILE_FIELD!r}, not {field_name!r}",
            )
        try:
            asked = ImageSearchQuery.model_validate(
                {key: value for key, value in form.multi_items() if isinstance(value, str)}
            )
        except ValidationError as exc:
            return _refuse(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                INVALID_QUERY_TYPE,
                "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                ),
            )

        try:
            page = await run_image_search(
                picture.file,
                session=session,
                storage=storage,
                settings=settings,
                pool=pool,
                limit=asked.limit,
                offset=asked.offset,
                min_score=asked.min_score,
                model=asked.model,
            )
        except PageTooDeepError as exc:
            return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, PAGE_TOO_DEEP_TYPE, str(exc))
        except WrongModalityError as exc:
            return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, WRONG_MODALITY_TYPE, str(exc))
        except SearchUnavailableError as exc:
            return _refuse(HTTPStatus.SERVICE_UNAVAILABLE, MODEL_UNAVAILABLE_TYPE, str(exc))
        except (images.UnsupportedFormatError, images.UndecodableImageError) as exc:
            return _refuse(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_TYPE, str(exc))
        except images.ImageTooLargeError as exc:
            return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, TOO_LARGE_TYPE, str(exc))
        except images.ImageTooSmallError as exc:
            return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, TOO_SMALL_TYPE, str(exc))

    return _rendered(page, limit=asked.limit, offset=asked.offset)


@asset_router.get(
    "/{asset_id}/similar",
    summary="Find the pictures that look most like a stored one",
    description=(
        "Ranks the stored vectors of the search model against this asset's own vector. Nothing "
        "is embedded — the vector is already there — so this answers even on a build that never "
        "downloaded the weights. The asset itself is never among its neighbours, at any page. "
        f"`limit + offset` may not exceed {MAX_PAGE_DEPTH_EXCLUDING}, one less than the other "
        "searches: leaving the asset out spends one of the candidates the index produces, and a "
        "page is refused rather than answered from a search that could not reach it. An asset "
        "with no vector for that model is 409, not an empty page: nothing is known about what "
        "it looks like, which is not the same as nothing being like it."
    ),
    response_model=SearchPage,
    responses={
        HTTPStatus.OK: {"content": {"application/json": {"example": SEARCH_PAGE_EXAMPLE}}},
        **problem_responses(
            HTTPStatus.NOT_FOUND,
            HTTPStatus.CONFLICT,
            HTTPStatus.SERVICE_UNAVAILABLE,
        ),
    },
)
async def search_similar_to_asset(
    asset_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_score: Annotated[float | None, Query(ge=-1.0, le=1.0)] = None,
    model: Annotated[str, Query(description=MODEL_DESCRIPTION)] = DINOV2_LARGE,
) -> Any:
    try:
        page = await run_similar_search(
            asset_id,
            session=session,
            settings=settings,
            limit=limit,
            offset=offset,
            min_score=min_score,
            model=model,
        )
    except PageTooDeepError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, PAGE_TOO_DEEP_TYPE, str(exc))
    except WrongModalityError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, WRONG_MODALITY_TYPE, str(exc))
    except SearchUnavailableError as exc:
        return _refuse(HTTPStatus.SERVICE_UNAVAILABLE, MODEL_UNAVAILABLE_TYPE, str(exc))
    except AssetUnknownError:
        return _refuse(HTTPStatus.NOT_FOUND, NOT_FOUND_TYPE, "no such asset")
    except NotIndexedError as exc:
        return _refuse(HTTPStatus.CONFLICT, NOT_INDEXED_TYPE, str(exc))

    return _rendered(page, limit=limit, offset=offset)


def install(app: FastAPI) -> None:
    """Mount the resource. Kept here so `app/main.py` stays a factory."""
    app.include_router(router)
    app.include_router(asset_router)
