"""Readiness checks: the database answers, the schema is at the code's head.

Each check returns a `CheckResult`. A failure reason names exception classes
only — never a message, which for a database driver can carry the connection
URL, the user or the password. Both checks run under the same time budget,
and the migration check is skipped when the database check failed, so a
silent database yields a 503 within the configured timeout. No check loads a
model.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

import app

ALEMBIC_DIR = Path(app.__file__).resolve().parent.parent / "alembic"
SKIPPED_AFTER_DATABASE_FAILURE = "skipped: database check failed"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str | None = None


def describe(exc: BaseException) -> str:
    """Exception class names only; messages may contain URLs or credentials."""
    name = type(exc).__name__
    cause = exc.__cause__
    return f"{name} from {type(cause).__name__}" if cause is not None else name


def _timeout_reason(timeout: float) -> str:
    return f"TimeoutError: no response within {timeout:g}s"


async def check_database(engine: AsyncEngine, timeout: float) -> CheckResult:
    """`SELECT 1` within `timeout` seconds."""
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError:
        return CheckResult(False, _timeout_reason(timeout))
    except Exception as exc:
        return CheckResult(False, describe(exc))
    return CheckResult(True)


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def code_head(script_dir: Path = ALEMBIC_DIR) -> str | None:
    """The single head revision of the migration scripts (None when there is none or several)."""
    heads = ScriptDirectory(str(script_dir)).get_heads()
    return heads[0] if len(heads) == 1 else None


async def check_migrations(
    engine: AsyncEngine, timeout: float, script_dir: Path = ALEMBIC_DIR
) -> CheckResult:
    """The database's Alembic revision equals the code's head, within `timeout` seconds."""
    head = code_head(script_dir)
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                current = await connection.run_sync(_current_revision)
    except TimeoutError:
        return CheckResult(False, _timeout_reason(timeout))
    except Exception as exc:
        return CheckResult(False, describe(exc))
    if head is not None and current == head:
        return CheckResult(True)
    return CheckResult(False, f"database at {current or 'none'}, code head {head or 'none'}")


async def run_checks(
    engine: AsyncEngine, timeout: float, script_dir: Path = ALEMBIC_DIR
) -> dict[str, CheckResult]:
    """All readiness checks; the migration check is skipped when the database is not answering."""
    database = await check_database(engine, timeout)
    migrations = (
        await check_migrations(engine, timeout, script_dir)
        if database.ok
        else CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
    )
    return {"database": database, "migrations": migrations}


def summarize(results: dict[str, CheckResult]) -> tuple[bool, dict[str, str]]:
    """Whether the service is ready, and one line per check for the probe body."""
    ready = all(result.ok for result in results.values())
    checks = {
        name: "ok" if result.ok else (result.reason or "failed") for name, result in results.items()
    }
    return ready, checks
