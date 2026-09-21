"""Indexing jobs: the queue's rows and every transition they make.

Claiming is the query the requirements fix (§3.3): the rows that are pending
and due, plus the rows whose lease has expired, locked `FOR UPDATE SKIP
LOCKED` so that two claimers are disjoint without coordinating anywhere
outside the database — a claimer passes over what another holds rather than
waiting for it.

Every finishing transition is conditional. A claim hands back the lease expiry
it wrote, and a finish only lands `WHERE status = 'running' AND
lease_expires_at = <that value>`. Once a lease has expired and another runner
has reclaimed the row, the first runner's result matches nothing and its whole
transaction rolls back — which is what keeps a slow runner from writing over
the state of the one that took its work. A reset clears the expiry for the
same reason: it invalidates every claim still outstanding.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import EMBEDDING_MODELS, IndexingJob
from app.models import IndexingJob as IndexingJobRow
from app.repositories.embeddings import UnknownModelError


def to_domain(row: IndexingJobRow) -> IndexingJob:
    return IndexingJob(
        id=row.id,
        asset_id=row.asset_id,
        model=row.model,
        status=row.status,
        attempts=row.attempts,
        available_at=row.available_at,
        lease_expires_at=row.lease_expires_at,
        last_error=row.last_error,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A job this runner holds, and the proof that it still does.

    `owned_until` is the lease expiry the claim wrote. Every finish carries it
    back; when it no longer matches the row, this runner is not the owner any
    more and its result must not land.
    """

    job: IndexingJob
    owned_until: datetime


class IndexingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, asset_id: UUID, model: str) -> IndexingJob:
        """Queue extraction of one model's vector for one asset."""
        if model not in EMBEDDING_MODELS:
            raise UnknownModelError(f"unknown embedding model: {model!r}")
        row = IndexingJobRow(asset_id=asset_id, model=model)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return to_domain(row)

    async def add_for_models(
        self, *, asset_id: UUID, models: Sequence[str] | None = None
    ) -> list[IndexingJob]:
        """Queue every enabled model for one asset, in registry order."""
        keys = list(models) if models is not None else list(EMBEDDING_MODELS)
        return [await self.add(asset_id=asset_id, model=key) for key in keys]

    async def fail_for_asset(self, asset_id: UUID, reason: str) -> int:
        """Finish every unfinished job of one asset as failed, with a reason.

        Used when an asset's file has gone missing: the work cannot be done and
        will not become doable, so it is closed rather than retried.
        """
        statement = (
            sa.update(IndexingJobRow)
            .where(IndexingJobRow.asset_id == asset_id)
            .where(IndexingJobRow.status.in_(("pending", "running")))
            .values(status="failed", last_error=reason, finished_at=sa.func.now())
        )
        result = await self._session.execute(statement)
        return int(result.rowcount)  # type: ignore[attr-defined]  # an UPDATE result has one

    async def list_for_asset(self, asset_id: UUID) -> list[IndexingJob]:
        """An asset's jobs, newest first per model."""
        statement = (
            sa.select(IndexingJobRow)
            .where(IndexingJobRow.asset_id == asset_id)
            .order_by(
                IndexingJobRow.model,
                IndexingJobRow.created_at.desc(),
                IndexingJobRow.id.desc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [to_domain(row) for row in rows]

    # --- claiming -------------------------------------------------------------

    @staticmethod
    def claim_statement(
        *, limit: int, asset_ids: Sequence[UUID] | None = None
    ) -> sa.Select[tuple[UUID]]:
        """The rows a claim would take. Exposed so a test can read its plan.

        `asset_ids` restricts the claim to those assets' work — a runner that
        created work of its own can finish it without waiting behind everything
        else the queue holds. Everything else about a claim is unchanged, and a
        claim that names no assets behaves exactly as it always has.
        """
        due = sa.or_(
            sa.and_(
                IndexingJobRow.status == "pending",
                IndexingJobRow.available_at <= sa.func.now(),
            ),
            sa.and_(
                IndexingJobRow.status == "running",
                IndexingJobRow.lease_expires_at < sa.func.now(),
            ),
        )
        statement = sa.select(IndexingJobRow.id).where(due)
        if asset_ids is not None:
            statement = statement.where(IndexingJobRow.asset_id.in_(list(asset_ids)))
        return (
            statement.order_by(IndexingJobRow.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

    async def claim(
        self, *, limit: int, lease_seconds: int, asset_ids: Sequence[UUID] | None = None
    ) -> list[ClaimedJob]:
        """Take up to `limit` due jobs, count an attempt and set a lease."""
        ids = (
            (await self._session.execute(self.claim_statement(limit=limit, asset_ids=asset_ids)))
            .scalars()
            .all()
        )
        if not ids:
            return []
        rows = (
            await self._session.execute(
                sa.update(IndexingJobRow)
                .where(IndexingJobRow.id.in_(list(ids)))
                .values(
                    status="running",
                    attempts=IndexingJobRow.attempts + 1,
                    started_at=sa.func.now(),
                    lease_expires_at=sa.func.now() + timedelta(seconds=lease_seconds),
                )
                .returning(IndexingJobRow)
            )
        ).scalars()
        claimed = []
        for row in rows:
            # The update above set it in the same statement; the column is
            # nullable because a job at rest has no lease.
            assert row.lease_expires_at is not None
            claimed.append(ClaimedJob(job=to_domain(row), owned_until=row.lease_expires_at))
        return claimed

    # --- finishing, always against the lease the claim wrote ------------------

    async def _finish(self, job_id: UUID, owned_until: datetime, **values: object) -> bool:
        """True when this runner still owned the job and the change landed."""
        result = await self._session.execute(
            sa.update(IndexingJobRow)
            .where(IndexingJobRow.id == job_id)
            .where(IndexingJobRow.status == "running")
            .where(IndexingJobRow.lease_expires_at == owned_until)
            .values(**values)
        )
        return int(result.rowcount) == 1  # type: ignore[attr-defined]  # an UPDATE result has one

    async def mark_done(self, job_id: UUID, owned_until: datetime) -> bool:
        return await self._finish(
            job_id,
            owned_until,
            status="done",
            finished_at=sa.func.now(),
            last_error=None,
            lease_expires_at=None,
        )

    async def return_to_queue(
        self, job_id: UUID, owned_until: datetime, *, delay_seconds: int, reason: str
    ) -> bool:
        """A failure with attempts left: due again later, with what happened."""
        return await self._finish(
            job_id,
            owned_until,
            status="pending",
            available_at=sa.func.now() + timedelta(seconds=delay_seconds),
            last_error=reason,
            lease_expires_at=None,
            started_at=None,
        )

    async def mark_failed(self, job_id: UUID, owned_until: datetime, reason: str) -> bool:
        """A failure with no attempts left: finished, with what happened."""
        return await self._finish(
            job_id,
            owned_until,
            status="failed",
            finished_at=sa.func.now(),
            last_error=reason,
            lease_expires_at=None,
        )

    async def reset(self, asset_id: UUID, models: Sequence[str] | None = None) -> list[str]:
        """Put an asset's work back in the queue with a clean slate.

        Returns the model of every row it reset, so the caller can say what
        actually happened rather than what was asked for. Clearing the lease is
        not housekeeping: it invalidates any claim still outstanding, so a
        runner that comes back late cannot write over the state this reset just
        created.
        """
        statement = (
            sa.update(IndexingJobRow)
            .where(IndexingJobRow.asset_id == asset_id)
            .values(
                status="pending",
                attempts=0,
                available_at=sa.func.now(),
                last_error=None,
                lease_expires_at=None,
                started_at=None,
                finished_at=None,
            )
            .returning(IndexingJobRow.model)
        )
        if models is not None:
            # `is not None`, not truthiness: an empty selection selects nothing,
            # and must not fall through to "every model".
            statement = statement.where(IndexingJobRow.model.in_(list(models)))
        return list((await self._session.execute(statement)).scalars().all())

    # --- what the API shows ---------------------------------------------------

    async def latest_status(self, asset_id: UUID) -> Mapping[str, str]:
        """The state of the newest job per model: `index_status`, derived."""
        return (await self.latest_status_for([asset_id])).get(asset_id, {})

    async def latest_status_for(
        self, asset_ids: Sequence[UUID]
    ) -> Mapping[UUID, Mapping[str, str]]:
        """The same, for a whole page of assets in one query.

        A listing of a hundred assets must not become a hundred queries, and
        `ix_jobs_asset` — `(asset_id, model, created_at desc)` — is exactly the
        order this reads in, so `DISTINCT ON` takes the newest per pair without
        sorting anything twice. Assets with no work at all are absent from the
        result rather than present with an empty map: the caller knows which
        identifiers it asked about.
        """
        if not asset_ids:
            return {}
        newest = (
            sa.select(IndexingJobRow.asset_id, IndexingJobRow.model, IndexingJobRow.status)
            .distinct(IndexingJobRow.asset_id, IndexingJobRow.model)
            .where(IndexingJobRow.asset_id.in_(list(asset_ids)))
            .order_by(
                IndexingJobRow.asset_id,
                IndexingJobRow.model,
                IndexingJobRow.created_at.desc(),
            )
        )
        statuses: dict[UUID, dict[str, str]] = {}
        for asset_id, model, status in await self._session.execute(newest):
            statuses.setdefault(asset_id, {})[model] = status
        return statuses

    @staticmethod
    def newest_status_of(
        asset_id: sa.ColumnElement[UUID] | sa.orm.InstrumentedAttribute[UUID], model: str
    ) -> sa.ScalarSelect[str]:
        """The state of one model's newest job for an asset, as a subquery.

        Given so the listing can filter on it without the assets repository
        having to know how the newest job is found.
        """
        return (
            sa.select(IndexingJobRow.status)
            .where(IndexingJobRow.asset_id == asset_id, IndexingJobRow.model == model)
            .order_by(IndexingJobRow.created_at.desc(), IndexingJobRow.id.desc())
            .limit(1)
            .scalar_subquery()
        )
