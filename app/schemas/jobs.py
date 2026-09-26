"""What the indexing queue looks like on the wire.

The state of an asset's work is part of the asset (`index_status`); this module
is the detail behind it — the jobs themselves, and what a reset answers.
"""

from datetime import datetime
from typing import Any, Self
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


#: The work of one asset, for the OpenAPI document (FR-OPS-4): both models of
#: the demo corpus, finished, with the timestamps a real run left behind. A job
#: that failed would carry its reason in `last_error` and its count in
#: `attempts`.
JOB_LIST_EXAMPLE: dict[str, Any] = {
    "items": [
        {
            "id": "0e5ebb60-6a67-4ee1-be76-ffcef1650d51",
            "model": "clip-vit-l14",
            "status": "done",
            "attempts": 1,
            "available_at": "2026-09-26T18:35:22.564927Z",
            "lease_expires_at": None,
            "last_error": None,
            "created_at": "2026-09-26T18:35:22.564927Z",
            "started_at": "2026-09-26T18:36:14.452970Z",
            "finished_at": "2026-09-26T18:36:15.601243Z",
        },
        {
            "id": "e825f80e-b6cd-48ac-b3e1-32efd21696d0",
            "model": "dinov2-large",
            "status": "done",
            "attempts": 1,
            "available_at": "2026-09-26T18:35:22.564927Z",
            "lease_expires_at": None,
            "last_error": None,
            "created_at": "2026-09-26T18:35:22.564927Z",
            "started_at": "2026-09-26T18:36:14.452970Z",
            "finished_at": "2026-09-26T18:36:15.969375Z",
        },
    ]
}

#: What a reset answers: the work that was actually put back, which is not
#: always what was asked for — a model the asset never had work for is not in
#: the list.
REINDEX_RESULT_EXAMPLE: dict[str, Any] = {
    "asset_id": "8e5567c3-22a2-4dd7-a625-61e07a03a46f",
    "models": ["clip-vit-l14"],
    "jobs": 1,
}
