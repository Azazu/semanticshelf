"""The asset resource: upload, read, list, edit, delete.

The upload parses the multipart body itself rather than taking an injected
file parameter, because the bounds have to be ours: Starlette's defaults leave
the number of parts at a thousand and apply a part size only to fields. What
the parser cannot bound — the file's own size — is bounded upstream by the
body-size middleware (`app/core/body_limit.py`).

A refusal from the parser itself (too many parts, a field over its bound)
arrives as the framework's own 400: Starlette turns a `MultiPartException`
into an `HTTPException` before it reaches this module. That is left alone —
it is a malformed request, 400 says so, and the project's exception handler
already renders it as problem details with the parser's message. What this
module answers are the refusals only it can judge.

Every refusal here is problem details with a stable type, and every one of
them leaves the store and the media root exactly as it found them.
"""

import os
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.api.deps import (
    PoolDep,
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    StorageDep,
)
from app.api.filters import INVALID_FILTER_TYPE, NARROWING_DESCRIPTION, narrowing_from
from app.core.errors import instance_for_current_request, problem, problem_response
from app.domain import ASSET_SOURCES, JOB_STATUSES, Asset, UnknownModelError
from app.schemas.assets import (
    DUPLICATE_TYPE,
    AssetPage,
    AssetPatch,
    AssetRead,
    DuplicateAssetProblem,
)
from app.schemas.jobs import IndexingJobList, IndexingJobRead, ReindexRequest, ReindexResult
from app.services import images
from app.services.assets import (
    DuplicateAssetError,
    create_asset,
    delete_asset,
    get_asset,
    list_assets,
    update_asset,
)
from app.services.indexing import drain, jobs_of, known_models, reset_work, status_of
from app.services.tagging import (
    METADATA_MAX_BYTES,
    MetadataError,
    NarrowingError,
    TagError,
    merge_metadata,
    normalise_filename,
    normalise_tags,
    parse_metadata,
    split_tag_fields,
)

PREFIX = "/api/v1/assets"
router = APIRouter(prefix=PREFIX, tags=["assets"])

#: An upload is one picture with a handful of fields. The parser enforces both,
#: which is what keeps a request with a thousand parts from being assembled.
MAX_FILE_PARTS = 2
MAX_FIELD_PARTS = 40
#: Deliberately above the metadata bound, so a value between the two is refused
#: by `parse_metadata` at the size the requirements name rather than by the
#: parser — each guard keeps its own band (design decision 2).
PARSER_PART_BYTES = 4 * METADATA_MAX_BYTES

FILE_FIELD = "file"
TAGS_FIELD = "tags"
META_FIELD = "meta"

INVALID_UPLOAD_TYPE = "/errors/invalid-upload"
INVALID_TAGS_TYPE = "/errors/invalid-tags"
INVALID_META_TYPE = "/errors/invalid-meta"
UNSUPPORTED_TYPE = "/errors/unsupported-media-type"
TOO_LARGE_TYPE = "/errors/image-too-large"
TOO_SMALL_TYPE = "/errors/image-too-small"
UNKNOWN_MODEL_TYPE = "/errors/unknown-model"

#: The listing's bounds, fixed by the requirements.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 10_000
#: A day, and private: an asset's bytes never change, but they are not public.
CACHE_CONTROL = "private, max-age=86400"
THUMBNAIL_MEDIA_TYPE = "image/webp"

log = structlog.stdlib.get_logger(__name__)


# The providers themselves live in `app/api/deps.py`, so that a second router
# does not have to import this one to ask for a session.


def _refuse(status: HTTPStatus, type_: str, detail: str) -> JSONResponse:
    return problem_response(problem(status=status, title=status.phrase, detail=detail, type_=type_))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Upload a picture",
    description=(
        "Multipart: one `file` part, optional `tags` (repeated or comma-separated) and "
        "optional `meta` (a JSON object as a string). The format is detected from the bytes; "
        "the filename and the declared content type are not trusted. Answers 201 with the "
        "asset and a Location header, 409 when those bytes are already stored, 413 when the "
        "body is over the limit, 415 when the file is not an accepted picture, 422 when a "
        "limit, a tag or the metadata is not acceptable, and 400 when the multipart body "
        "itself is malformed."
    ),
    response_model=AssetRead,
)
async def upload_asset(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    pool: PoolDep,
) -> Any:
    try:
        async with request.form(
            max_files=MAX_FILE_PARTS,
            max_fields=MAX_FIELD_PARTS,
            max_part_size=PARSER_PART_BYTES,
        ) as form:
            # Every file part, whatever it is called: a second picture under
            # another field name is still a second picture, and silently
            # ignoring it would store something the client did not ask for.
            files = [
                (key, value) for key, value in form.multi_items() if isinstance(value, UploadFile)
            ]
            if len(files) != 1:
                return _refuse(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    INVALID_UPLOAD_TYPE,
                    f"exactly one {FILE_FIELD!r} part is required, got {len(files)} file part(s)",
                )
            field_name, upload = files[0]
            if field_name != FILE_FIELD:
                return _refuse(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    INVALID_UPLOAD_TYPE,
                    f"the file part must be called {FILE_FIELD!r}, not {field_name!r}",
                )
            raw_meta = form.get(META_FIELD)
            try:
                tags = split_tag_fields(
                    [
                        value
                        for key, value in form.multi_items()
                        if key == TAGS_FIELD and isinstance(value, str)
                    ]
                )
                meta = parse_metadata(raw_meta if isinstance(raw_meta, str) else None)
            except TagError as exc:
                return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_TAGS_TYPE, str(exc))
            except MetadataError as exc:
                return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_META_TYPE, str(exc))

            asset = await create_asset(
                session=session,
                storage=storage,
                settings=settings,
                source=upload.file,
                original_filename=normalise_filename(upload.filename),
                tags=tags,
                meta=meta,
            )
    except DuplicateAssetError as exc:
        status = HTTPStatus.CONFLICT
        return problem_response(
            DuplicateAssetProblem(
                type=DUPLICATE_TYPE,
                title=status.phrase,
                status=status,
                detail="those bytes are already stored",
                instance=instance_for_current_request(),
                existing_asset_id=exc.existing_asset_id,
            )
        )
    except (images.UnsupportedFormatError, images.UndecodableImageError) as exc:
        return _refuse(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_TYPE, str(exc))
    except images.ImageTooLargeError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, TOO_LARGE_TYPE, str(exc))
    except images.ImageTooSmallError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, TOO_SMALL_TYPE, str(exc))

    response.headers["Location"] = f"{PREFIX}/{asset.id}"
    # After the response, not before it: the caller waits for the asset, never
    # for its vectors. The task takes a session of its own, because this
    # request's is closed by then.
    background.add_task(
        drain, session_factory=session_factory, storage=storage, settings=settings, pool=pool
    )
    # The work was queued in the same transaction as the asset, so this says
    # `pending` for every enabled model — the state of the asset as the caller
    # is being told about it, before the runner above has touched anything.
    return AssetRead.of(
        asset, prefix=PREFIX, index_status=(await status_of(session, [asset.id])).get(asset.id)
    )


async def _asset_or_404(session: AsyncSession, asset_id: UUID) -> Asset:
    asset = await get_asset(session, asset_id)
    if asset is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="no such asset")
    return asset


async def _serve(path: Path, *, asset: Asset, media_type: str, filename: str) -> FileResponse:
    """A stored file, streamed, with the validators a client can revalidate on.

    The entity tag is the content hash the service already stores, so
    revalidation costs no read. A file that is gone is a 404 with a warning:
    the asset exists, its bytes do not, and that is an operational fact
    (`storage prune` reconciles it), not a server error.
    """
    try:
        stat_result = await run_in_threadpool(os.stat, path)
    except OSError:
        log.warning("stored file missing", asset_id=str(asset.id), file=path.name)
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="the stored file is missing"
        ) from None
    return FileResponse(
        path,
        media_type=media_type,
        stat_result=stat_result,
        content_disposition_type="inline",
        filename=filename,
        headers={"cache-control": CACHE_CONTROL, "etag": f'"{asset.sha256}"'},
    )


def _parse_index_status(value: str) -> tuple[str, str]:
    """`<model>:<state>`, or a refusal naming what was wrong with it.

    Both halves are checked against what the service knows rather than against
    what it currently runs: work queued for a model that has since been
    switched off is still work, and a filter must be able to find it.
    """
    model, separator, state = value.partition(":")
    if not separator or not model or not state:
        raise ValueError(f"expected <model>:<state>, got {value!r}")
    known_models([model])
    if state not in JOB_STATUSES:
        raise ValueError(f"unknown state: {state!r}; expected one of {', '.join(JOB_STATUSES)}")
    return model, state


@router.get(
    "",
    summary="List assets",
    description=(
        "Newest first, with the identifier as tie-break. `limit` defaults to 20 and is at "
        f"most 100, `offset` at most 10 000. {NARROWING_DESCRIPTION} Beside that narrowing, "
        "filter by `source` and by `index_status` as `<model>:<state>` — the "
        "state of that model's newest indexing job. The page says whether more items exist; "
        "there is no total, which would be stale the moment it was read."
    ),
    response_model=AssetPage,
)
async def list_asset_page(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
    tags_all: str | None = None,
    tags_any: str | None = None,
    source: Literal[ASSET_SOURCES] | None = None,  # type: ignore[valid-type]
    index_status: Annotated[
        str | None, Query(description="`<model>:<state>`, for example `clip-vit-l14:done`.")
    ] = None,
) -> Any:
    try:
        narrowing = narrowing_from(
            request.query_params.multi_items(), tags_all=tags_all, tags_any=tags_any
        )
    except NarrowingError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_FILTER_TYPE, str(exc))
    try:
        work = _parse_index_status(index_status) if index_status else None
    except (ValueError, UnknownModelError) as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_FILTER_TYPE, str(exc))

    assets, has_more = await list_assets(
        session,
        narrowing=narrowing,
        source=source,
        index_status=work,
        limit=limit,
        offset=offset,
    )
    statuses = await status_of(session, [asset.id for asset in assets])
    return AssetPage(
        items=[
            AssetRead.of(asset, prefix=PREFIX, index_status=statuses.get(asset.id))
            for asset in assets
        ],
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/{asset_id}",
    summary="Read an asset",
    description="The asset's representation, or 404 when no asset carries that identifier.",
    response_model=AssetRead,
)
async def read_asset(asset_id: UUID, session: SessionDep) -> Any:
    asset = await _asset_or_404(session, asset_id)
    return AssetRead.of(
        asset, prefix=PREFIX, index_status=(await status_of(session, [asset.id])).get(asset.id)
    )


@router.get(
    "/{asset_id}/file",
    summary="The original bytes",
    description=(
        "The stored original, streamed, with the detected content type, a private cache "
        "lifetime and the content hash as the entity tag. 404 when the asset is unknown or "
        "its file is missing from storage."
    ),
    response_class=FileResponse,
)
async def read_file(asset_id: UUID, session: SessionDep, storage: StorageDep) -> FileResponse:
    asset = await _asset_or_404(session, asset_id)
    return await _serve(
        storage.original(asset.id, asset.file_ext),
        asset=asset,
        media_type=asset.content_type,
        filename=f"{asset.id}.{asset.file_ext}",
    )


@router.get(
    "/{asset_id}/thumbnail",
    summary="The thumbnail",
    description=(
        "The WebP thumbnail made at upload, with the same caching and validator rules as the "
        "original. 404 when the asset is unknown or its thumbnail is missing from storage."
    ),
    response_class=FileResponse,
)
async def read_thumbnail(asset_id: UUID, session: SessionDep, storage: StorageDep) -> FileResponse:
    asset = await _asset_or_404(session, asset_id)
    return await _serve(
        storage.thumbnail(asset.id),
        asset=asset,
        media_type=THUMBNAIL_MEDIA_TYPE,
        filename=f"{asset.id}.thumb.webp",
    )


@router.patch(
    "/{asset_id}",
    summary="Change an asset's tags or metadata",
    description=(
        "An omitted field is left alone; an explicit null clears it. Tags and metadata go "
        "through the same rules as at upload. The picture itself — its bytes, its hash, its "
        "dimensions, its content type — cannot be changed through any endpoint."
    ),
    response_model=AssetRead,
)
async def patch_asset(asset_id: UUID, patch: AssetPatch, session: SessionDep) -> Any:
    try:
        tags = normalise_tags(patch.tags or []) if patch.gives("tags") else None
        meta = merge_metadata({}, patch.meta) if patch.gives("meta") else None
    except TagError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_TAGS_TYPE, str(exc))
    except MetadataError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, INVALID_META_TYPE, str(exc))

    updated = await update_asset(session, asset_id, tags=tags, meta=meta)
    if updated is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="no such asset")
    return AssetRead.of(
        updated,
        prefix=PREFIX,
        index_status=(await status_of(session, [updated.id])).get(updated.id),
    )


@router.delete(
    "/{asset_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete an asset",
    description=(
        "Removes the asset with everything derived from it in one transaction, then its "
        "files. Deleting an asset that is not stored answers 404: the second caller is told "
        "it does not exist."
    ),
)
async def delete_one_asset(asset_id: UUID, session: SessionDep, storage: StorageDep) -> Response:
    if not await delete_asset(session, storage, asset_id):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="no such asset")
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.get(
    "/{asset_id}/jobs",
    summary="The indexing work of an asset",
    description=(
        "Every unit of work for the asset with its attempts, its timestamps and the reason "
        "its last attempt failed, newest first per model. 404 when no asset carries that "
        "identifier."
    ),
    response_model=IndexingJobList,
)
async def read_asset_jobs(asset_id: UUID, session: SessionDep) -> Any:
    await _asset_or_404(session, asset_id)
    return IndexingJobList(
        items=[IndexingJobRead.of(job) for job in await jobs_of(session, asset_id)]
    )


@router.post(
    "/{asset_id}/reindex",
    status_code=HTTPStatus.ACCEPTED,
    summary="Run an asset's indexing work again",
    description=(
        "Puts the asset's work back in the queue with its attempts and its last reason "
        "cleared — the only way failed work runs again. `models` selects which work to "
        "reset; omitted or null, it resets all of it, and an empty list resets nothing. "
        "The answer says what was actually reset, which is not what was asked for when "
        "the asset never had work for a model. 404 when no asset carries that identifier, "
        "422 when a model is one the service does not know."
    ),
    response_model=ReindexResult,
)
async def reindex_asset(
    asset_id: UUID,
    session: SessionDep,
    background: BackgroundTasks,
    storage: StorageDep,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    pool: PoolDep,
    request: ReindexRequest | None = None,
) -> Any:
    await _asset_or_404(session, asset_id)
    # `None` and `[]` are different answers: no selection resets everything, a
    # selection of nothing resets nothing. Collapsing the two would turn an
    # empty list built by a caller's own filter into "reset all of it".
    asked = request.models if request is not None else None
    try:
        models = known_models(asked) if asked is not None else None
    except UnknownModelError as exc:
        return _refuse(HTTPStatus.UNPROCESSABLE_ENTITY, UNKNOWN_MODEL_TYPE, str(exc))

    reset = await reset_work(session, asset_id, models=models)
    # The same runner an upload schedules: work put back is work to do.
    background.add_task(
        drain, session_factory=session_factory, storage=storage, settings=settings, pool=pool
    )
    return ReindexResult(asset_id=asset_id, models=sorted(set(reset)), jobs=len(reset))


def install(app: FastAPI) -> None:
    """Mount the resource. Kept here so `app/main.py` stays a factory."""
    app.include_router(router)
