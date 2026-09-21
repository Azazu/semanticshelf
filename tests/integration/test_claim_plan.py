"""The claim reaches its rows by the index built for it."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.jobs import IndexingJobRepository
from tests.integration.conftest import explain

pytestmark = pytest.mark.integration


async def test_the_claim_uses_the_index_built_for_it(session: AsyncSession) -> None:
    statement = IndexingJobRepository.claim_statement(limit=4)

    plan = await explain(session, statement, no_seqscan=True)

    assert "ix_jobs_claim" in plan, plan
    assert "Seq Scan" not in plan, plan


async def test_the_claim_locks_and_skips(session: AsyncSession) -> None:
    # The clause is what makes two claimers disjoint rather than serialised,
    # so it is asserted on the statement itself as well as in behaviour.
    compiled = str(
        IndexingJobRepository.claim_statement(limit=4).compile(
            dialect=session.bind.dialect  # type: ignore[union-attr]
        )
    )
    assert "FOR UPDATE SKIP LOCKED" in compiled
