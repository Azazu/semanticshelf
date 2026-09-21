"""Readiness checks: the database answers, the schema is at the code's head,
the schema declares the models this build is configured to run, and the media
root can hold a picture.

Each check returns a `CheckResult`. A failure reason names exception classes
only — never a message, which for a database driver can carry the connection
URL, the user or the password. All checks run under the same time budget, and
the later ones are skipped when the database check failed, so a silent database
yields a 503 within the configured timeout. No check loads a model: the probe
compares declarations, and it must stay answerable on a machine that has never
downloaded a weight.
"""

import asyncio
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

import app
from app.domain import EMBEDDING_MODELS

ALEMBIC_DIR = Path(app.__file__).resolve().parent.parent / "alembic"
SKIPPED_AFTER_DATABASE_FAILURE = "skipped: database check failed"

#: Every CHECK constraint on `embeddings`. Read by table rather than by name:
#: the name is a migration's choice, the shape of the rule is the contract.
DIMENSION_CONSTRAINTS = text(
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conrelid = 'embeddings'::regclass AND contype = 'c'"
)

#: One branch of that constraint: `(model = 'clip-vit-l14'::text) AND
#: (vector_dims(vector) = 768)`, as PostgreSQL renders it back.
DIMENSION_BRANCH = re.compile(
    r"model\s*=\s*'([^']+)'::text\s*\)?\s*AND\s*\(?\s*vector_dims\(vector\)\s*=\s*(\d+)"
)


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


def schema_dimensions(definitions: Iterable[str]) -> dict[str, int]:
    """The model keys and widths the database's own constraint declares."""
    found: dict[str, int] = {}
    for definition in definitions:
        for key, width in DIMENSION_BRANCH.findall(definition):
            found[key] = int(width)
    return found


def compare_declarations(enabled: Sequence[str], schema: Mapping[str, int]) -> CheckResult:
    """Every enabled model, as the code declares it, against the schema.

    A disagreement here means vectors would be written against a rule the
    database does not hold — a wrong width rejected at insert in the best case,
    a model the schema has never heard of in the worst. It is a configuration
    or migration mistake, and it is cheap to see before the first request.
    """
    problems: list[str] = []
    for key in enabled:
        declared = EMBEDDING_MODELS.get(key)
        found = schema.get(key)
        if declared is None:
            problems.append(f"{key}: enabled, but the application declares no such model")
        elif found != declared:
            problems.append(f"{key}: code {declared}, schema {found if found else 'absent'}")
    return CheckResult(not problems, "; ".join(problems) or None)


async def check_models(engine: AsyncEngine, timeout: float, enabled: Sequence[str]) -> CheckResult:
    """The enabled models against the schema's dimension constraint, within `timeout`.

    Reads the catalog; loads nothing. Whether a checkpoint really produces the
    declared width is a different question, answered when the adapter loads it
    (`app/ml/base.py`), because no database can see inside a set of weights.
    """
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                result = await connection.execute(DIMENSION_CONSTRAINTS)
                definitions = [row[0] for row in result]
    except TimeoutError:
        return CheckResult(False, _timeout_reason(timeout))
    except Exception as exc:
        return CheckResult(False, describe(exc))
    return compare_declarations(enabled, schema_dimensions(definitions))


def media_state(root: Path) -> str | None:
    """What is wrong with the media root, or `None` when nothing is.

    Blocking (three system calls); called in a thread. It asks the operating
    system rather than writing a probe file: readiness is polled continuously,
    and a health check should not have side effects. It therefore cannot catch
    a mount that reports writable and then refuses the write — that surfaces at
    the first upload, loudly.
    """
    if not root.exists():
        return "the media root does not exist"
    if not root.is_dir():
        return "the media root is not a directory"
    if not os.access(root, os.W_OK):
        return "the media root is not writable"
    return None


async def check_media(root: Path, timeout: float) -> CheckResult:
    """The media root, within `timeout` seconds.

    Independent of the database, so it runs whatever the database is doing. The
    reason never quotes the path: a readiness body is unauthenticated, and
    where a deployment keeps its files is not a probe's news to publish.
    """
    try:
        async with asyncio.timeout(timeout):
            reason = await asyncio.to_thread(media_state, root)
    except TimeoutError:
        return CheckResult(False, _timeout_reason(timeout))
    except Exception as exc:
        return CheckResult(False, describe(exc))
    return CheckResult(reason is None, reason)


async def run_checks(
    engine: AsyncEngine,
    timeout: float,
    enabled_models: Sequence[str],
    media_root: Path,
    script_dir: Path = ALEMBIC_DIR,
) -> dict[str, CheckResult]:
    """All readiness checks, in two rounds of one budget each.

    The database and the media root are independent of each other, so they run
    together; the two checks that need a working database run together after
    them, and are skipped when it failed. That keeps the whole probe within
    about twice the timeout however many checks it grows — a bound a third
    sequential check had already broken once.
    """
    database, media = await asyncio.gather(
        check_database(engine, timeout),
        check_media(media_root, timeout),
    )
    if not database.ok:
        skipped = CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
        return {"database": database, "migrations": skipped, "models": skipped, "media": media}
    migrations, models = await asyncio.gather(
        check_migrations(engine, timeout, script_dir),
        check_models(engine, timeout, enabled_models),
    )
    return {"database": database, "migrations": migrations, "models": models, "media": media}


def summarize(results: dict[str, CheckResult]) -> tuple[bool, dict[str, str]]:
    """Whether the service is ready, and one line per check for the probe body."""
    ready = all(result.ok for result in results.values())
    checks = {
        name: "ok" if result.ok else (result.reason or "failed") for name, result in results.items()
    }
    return ready, checks
