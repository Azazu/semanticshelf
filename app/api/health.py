"""Liveness and readiness probes, outside the versioned API."""

from http import HTTPStatus
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.core.errors import (
    ProblemDetails,
    instance_for_current_request,
    problem_response,
    problem_responses,
)
from app.core.settings import Settings
from app.services.readiness import run_checks, summarize

router = APIRouter(tags=["probes"])

NOT_READY_TYPE = "/errors/not-ready"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    checks: dict[str, str]


class NotReadyProblem(ProblemDetails):
    """The 503 of the readiness probe: problem details plus one line per check."""

    checks: dict[str, str]


@router.get(
    "/health",
    summary="Liveness probe",
    description="The process is up. Touches no dependency: no database, no filesystem, no model.",
    response_model=HealthResponse,
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/ready",
    summary="Readiness probe",
    description=(
        "The service can serve: the database answers `SELECT 1` within the configured timeout, "
        "its Alembic revision is the code's head, its dimension constraint declares every "
        "enabled model with the width the code declares, and the media root is a writable "
        "directory (the database-dependent checks are skipped when the database check fails; "
        "the media check runs regardless). Otherwise 503 as problem details "
        "with `type` `/errors/not-ready` and a `checks` member naming each check's outcome. "
        "Models are never loaded by this probe: it compares declarations, not weights."
    ),
    response_model=ReadyResponse,
    responses=problem_responses(HTTPStatus.SERVICE_UNAVAILABLE, model=NotReadyProblem),
)
async def ready(request: Request) -> Response:
    engine: AsyncEngine = request.app.state.engine
    settings: Settings = request.app.state.settings
    is_ready, checks = summarize(
        await run_checks(
            engine,
            settings.readiness_timeout_seconds,
            settings.enabled_models,
            settings.media_root,
            settings.alembic_dir,
        )
    )
    if is_ready:
        return JSONResponse({"status": "ready", "checks": checks})
    status = HTTPStatus.SERVICE_UNAVAILABLE
    return problem_response(
        NotReadyProblem(
            type=NOT_READY_TYPE,
            title=status.phrase,
            status=status,
            detail="One or more readiness checks failed",
            instance=instance_for_current_request(),
            checks=checks,
        )
    )
