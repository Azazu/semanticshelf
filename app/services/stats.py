"""What the service holds, and what it still owes.

Everything here is derived when it is asked for. A running total kept beside
the store is a second copy of the truth, and the first thing that happens to a
second copy is that it drifts.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.assets import AssetRepository
from app.repositories.jobs import IndexingJobRepository


@dataclass(frozen=True, slots=True)
class WorkCount:
    """How much work of one model is in one state."""

    model: str
    status: str
    jobs: int


@dataclass(frozen=True, slots=True)
class Stats:
    """The store in one answer."""

    assets: int
    stored_bytes: int
    work: list[WorkCount] = field(default_factory=list)
    #: How long the oldest unfinished work has been waiting, or `None` when
    #: nothing is waiting — which is not the same as zero seconds.
    oldest_waiting_seconds: float | None = None


async def collect(session: AsyncSession, *, now: datetime | None = None) -> Stats:
    """The statistics, read from the store as it is at this moment."""
    assets, stored_bytes = await AssetRepository(session).summary()
    jobs = IndexingJobRepository(session)
    work = [
        WorkCount(model=model, status=status, jobs=count)
        for model, status, count in await jobs.counts_by_model_and_status()
    ]
    oldest = await jobs.oldest_waiting()
    waited = None if oldest is None else (now or datetime.now(UTC)) - oldest
    return Stats(
        assets=assets,
        stored_bytes=stored_bytes,
        work=work,
        oldest_waiting_seconds=None if waited is None else max(0.0, waited.total_seconds()),
    )


async def tags(session: AsyncSession, *, limit: int) -> list[tuple[str, int]]:
    """The tags in use with their counts, most used first."""
    return await AssetRepository(session).tag_counts(limit=limit)
