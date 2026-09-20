"""Readiness checks: the database answers, the schema is at the code's head.

Each check returns a `CheckResult`; a failure reason is the exception class
and the first line of its message, trimmed, so a probe body can never carry a
connection string or a stack trace. No check loads a model.
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
_REASON_MAX = 200


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str | None = None


def describe(exc: BaseException) -> str:
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    return f"{type(exc).__name__}: {first_line}"[:_REASON_MAX].rstrip(": ")


async def check_database(engine: AsyncEngine, timeout: float) -> CheckResult:
    """`SELECT 1` within `timeout` seconds."""
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError:
        return CheckResult(False, f"TimeoutError: no response within {timeout:g}s")
    except Exception as exc:
        return CheckResult(False, describe(exc))
    return CheckResult(True)


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def code_head(script_dir: Path = ALEMBIC_DIR) -> str | None:
    """The single head revision of the migration scripts (None when there is none or several)."""
    heads = ScriptDirectory(str(script_dir)).get_heads()
    return heads[0] if len(heads) == 1 else None


async def check_migrations(engine: AsyncEngine, script_dir: Path = ALEMBIC_DIR) -> CheckResult:
    """The database's Alembic revision equals the code's head."""
    head = code_head(script_dir)
    try:
        async with engine.connect() as connection:
            current = await connection.run_sync(_current_revision)
    except Exception as exc:
        return CheckResult(False, describe(exc))
    if head is not None and current == head:
        return CheckResult(True)
    return CheckResult(False, f"database at {current or 'none'}, code head {head or 'none'}")


def readiness_payload(results: dict[str, CheckResult]) -> tuple[int, dict[str, object]]:
    """HTTP status and body for the readiness probe from the check results."""
    ready = all(result.ok for result in results.values())
    checks = {
        name: "ok" if result.ok else (result.reason or "failed") for name, result in results.items()
    }
    return (200 if ready else 503), {"status": "ready" if ready else "not-ready", "checks": checks}
