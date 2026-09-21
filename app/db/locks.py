"""The advisory lock that keeps `storage prune` off a live upload.

An upload writes its two files before it stores its row, so between the two it
looks exactly like rubbish left by a crash — and it may stay there for any
length of time, because a disk can be slow and a process can be stopped. No
timeout is safe against that, so the two are serialised instead: every upload
holds this lock in shared mode for the whole of its write, and prune takes it
exclusively, without waiting, before it deletes anything.

The locks are transaction-scoped, so they are released by the commit, by the
rollback and by a connection that dies — there is no path that leaks one.
"""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

#: One fixed key for the media store. Arbitrary, but it must never change:
#: two processes agree only if they use the same number.
MEDIA_LOCK_KEY = 7_265_431_982_004_117


async def hold_media_shared(session: AsyncSession) -> None:
    """Held by an upload for the whole of its write. Shared: uploads never
    block each other, only prune."""
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": MEDIA_LOCK_KEY}
    )


async def try_take_media_exclusive(session: AsyncSession) -> bool:
    """Taken by prune before it touches anything. Never waits: an upload in
    flight means prune does not run, and says so."""
    result = await session.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MEDIA_LOCK_KEY}
    )
    return bool(result.scalar_one())
