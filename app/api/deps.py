"""What every router needs from the application, and where it comes from.

The providers live here rather than in one router, so that a second router does
not have to import the first to ask for a session. Everything is read from
`app.state`, which the lifespan filled.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import get_session
from app.storage import MediaStorage


def get_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.storage
    return storage


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_pool(request: Request) -> ThreadPoolExecutor:
    pool: ThreadPoolExecutor = request.app.state.inference_pool
    return pool


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
PoolDep = Annotated[ThreadPoolExecutor, Depends(get_pool)]
StorageDep = Annotated[MediaStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
