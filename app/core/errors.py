"""RFC 9457 problem details for every non-2xx response.

Request validation (422 with the offending locations, never the submitted
values) and HTTP exceptions raised by routes or by routing itself (404, 405,
...) are mapped here. Unhandled exceptions are rendered by
`RequestIdMiddleware`, the outermost application-owned layer, so the 500 body
and the single error log line share the request id.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import current_request_id

PROBLEM_MEDIA_TYPE = "application/problem+json"
VALIDATION_TYPE = "/errors/validation"


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ProblemDetails(BaseModel):
    """The body of every error response (RFC 9457)."""

    type: str = Field(default="about:blank", description="about:blank or a stable /errors/<slug>.")
    title: str
    status: int
    detail: str = ""
    instance: str = Field(description="urn:request:<request id>, the id of this occurrence.")
    errors: list[ValidationIssue] | None = Field(
        default=None, description="Validation issues (422 only): location, message, type."
    )


def problem_response(
    *,
    status: int,
    title: str,
    detail: str = "",
    type_: str = "about:blank",
    errors: list[ValidationIssue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=type_,
        title=title,
        status=status,
        detail=detail,
        instance=f"urn:request:{current_request_id()}",
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def internal_error_response() -> JSONResponse:
    """The 500 body: no detail, no exception text."""
    status = HTTPStatus.INTERNAL_SERVER_ERROR
    return problem_response(status=status, title=status.phrase)


async def validation_error_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    issues = [
        ValidationIssue(loc=list(error["loc"]), msg=str(error["msg"]), type=str(error["type"]))
        for error in exc.errors()
    ]
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    return problem_response(
        status=status,
        title=status.phrase,
        detail="Request validation failed",
        type_=VALIDATION_TYPE,
        errors=issues,
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    status = HTTPStatus(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != status.phrase else ""
    return problem_response(
        status=exc.status_code, title=status.phrase, detail=detail, headers=exc.headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries documenting the problem-details body for the given statuses."""
    return {
        status: {"model": ProblemDetails, "description": HTTPStatus(status).phrase}
        for status in statuses
    }
