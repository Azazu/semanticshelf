"""Liveness and readiness probes, outside the versioned API."""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.core.settings import Settings
from app.services.readiness import check_database, check_migrations, readiness_payload

router = APIRouter(tags=["probes"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not-ready"]
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
        "The service can serve: the database answers `SELECT 1` within the configured timeout "
        "and its Alembic revision is the code's head. 503 with a reason per failed check "
        "otherwise. Models are never loaded by this probe."
    ),
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse, "description": "Not ready"}},
)
async def ready(request: Request) -> JSONResponse:
    engine: AsyncEngine = request.app.state.engine
    settings: Settings = request.app.state.settings
    results = {
        "database": await check_database(engine, settings.readiness_timeout_seconds),
        "migrations": await check_migrations(engine),
    }
    status, body = readiness_payload(results)
    return JSONResponse(status_code=status, content=body)
