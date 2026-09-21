"""What the indexing queue looks like on the wire.

The state of an asset's work is part of the asset (`index_status`); this module
is the detail behind it — the jobs themselves, and what a reset answers.
"""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain import IndexingJob


class IndexingJobRead(BaseModel):
    """One unit of work, as `GET /assets/{id}/jobs` returns it."""

    id: UUID
    model: str
    status: str
    attempts: int
    available_at: datetime
    lease_expires_at: datetime | None = Field(
        description=(
            "When the current claim stops being the owner. Set only while the job is "
            "running: after it, another runner may take the job, and the runner that "
            "held it can no longer finish it. Null at rest."
        )
    )
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: IndexingJob) -> Self:
        return cls(
            id=job.id,
            model=job.model,
            status=job.status,
            attempts=job.attempts,
            available_at=job.available_at,
            lease_expires_at=job.lease_expires_at,
            last_error=job.last_error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class IndexingJobList(BaseModel):
    """An asset's work. Not paged: an asset has one job per model."""

    items: list[IndexingJobRead]


class ReindexRequest(BaseModel):
    """Which work to put back in the queue. Omitted means all of it."""

    models: list[str] | None = Field(
        default=None,
        description=(
            "Model keys to reset. Omitted or null resets every model's work; an empty "
            "list selects nothing and resets nothing."
        ),
    )


class ReindexResult(BaseModel):
    """What the reset actually did, which is not always what was asked for."""

    asset_id: UUID
    models: list[str] = Field(description="The models whose work was reset, in order.")
    jobs: int = Field(description="How many units of work went back in the queue.")
