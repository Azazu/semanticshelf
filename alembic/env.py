"""Alembic environment: async engine, URL from the application settings.

The URL is never written into alembic.ini: configparser would choke on a `%`
in a password, and the settings module is the single source anyway.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app import models as _models  # noqa: F401  (importing populates Base.metadata)
from app.core.settings import Settings
from app.db.base import Base

config = context.config

# Alembic's own logging configuration applies to CLI runs only; an in-process
# run (tests) already has the application's logging.
if config.config_file_name is not None and not context.is_offline_mode():
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a database connection."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
