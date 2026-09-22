"""The two read-only views the demo UI is built from."""

from typing import Any

from pydantic import BaseModel, Field

from app.services.stats import Stats


class TagCount(BaseModel):
    """One tag, and how many assets carry it."""

    tag: str
    assets: int


class TagList(BaseModel):
    """The tags in use, most used first. No total: the list is the answer."""

    items: list[TagCount]
    limit: int


class WorkCountRead(BaseModel):
    """How much indexing work of one model is in one state."""

    model: str
    status: str
    jobs: int


class StatsRead(BaseModel):
    """What the service holds and what it still owes."""

    assets: int
    stored_bytes: int = Field(
        description=(
            "The total size of the stored originals, as the assets record it. Thumbnails "
            "are not counted, and nothing walks the media root to produce this number."
        )
    )
    work: list[WorkCountRead]
    oldest_waiting_seconds: float | None = Field(
        description=(
            "How long the oldest unfinished indexing work has been waiting. Absent when "
            "nothing is waiting, which is not the same as zero."
        )
    )

    @classmethod
    def of(cls, stats: Stats) -> "StatsRead":
        return cls(
            assets=stats.assets,
            stored_bytes=stats.stored_bytes,
            work=[
                WorkCountRead(model=one.model, status=one.status, jobs=one.jobs)
                for one in stats.work
            ],
            oldest_waiting_seconds=stats.oldest_waiting_seconds,
        )


#: The answers of the run recorded in `docs/how-to/searching.md`, carried into
#: the OpenAPI document as this operation's example (FR-OPS-4).
TAG_LIST_EXAMPLE: dict[str, Any] = {
    "items": [{"tag": "demo", "assets": 5}],
    "limit": 100,
}

#: The same five assets, one of them still waiting: an example carrying `null`
#: would be dropped from the document, and a waiting job is the shape an
#: operator reads this view for anyway.
STATS_EXAMPLE: dict[str, Any] = {
    "assets": 5,
    "stored_bytes": 11878,
    "work": [
        {"model": "clip-vit-l14", "status": "done", "jobs": 4},
        {"model": "clip-vit-l14", "status": "pending", "jobs": 1},
    ],
    "oldest_waiting_seconds": 12.4,
}
