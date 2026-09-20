"""Async engine and request-scoped sessions.

The engine is created by the application lifespan and kept on `app.state`;
nothing here opens a connection at import or at startup, so a booting API
with a database that is still starting reports `not-ready` instead of crashing.
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # pool_pre_ping drops stale connections after a database restart.
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, from the application's engine."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
