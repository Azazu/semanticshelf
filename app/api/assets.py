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

from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.core.errors import instance_for_current_request, problem, problem_response
from app.core.settings import Settings
from app.db.engine import get_session
from app.schemas.assets import DUPLICATE_TYPE, AssetRead, DuplicateAssetProblem
from app.services import images
from app.services.assets import DuplicateAssetError, create_asset
from app.services.tagging import (
    METADATA_MAX_BYTES,
    MetadataError,
    TagError,
    normalise_filename,
    parse_metadata,
    split_tag_fields,
)
from app.storage import MediaStorage

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


def get_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.storage
    return storage


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[MediaStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


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
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Any:
    try:
        async with request.form(
            max_files=MAX_FILE_PARTS,
            max_fields=MAX_FIELD_PARTS,
            max_part_size=PARSER_PART_BYTES,
        ) as form:
            files = [
                value
                for key, value in form.multi_items()
                if key == FILE_FIELD and isinstance(value, UploadFile)
            ]
            if len(files) != 1:
                return _refuse(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    INVALID_UPLOAD_TYPE,
                    f"exactly one {FILE_FIELD!r} part is required, got {len(files)}",
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
                source=files[0].file,
                original_filename=normalise_filename(files[0].filename),
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
    return AssetRead.of(asset, prefix=PREFIX)


def install(app: FastAPI) -> None:
    """Mount the resource. Kept here so `app/main.py` stays a factory."""
    app.include_router(router)
