"""Readiness aggregation, reason formatting, the skip rule and the time budget,
without a database."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.services.readiness import (
    SKIPPED_AFTER_DATABASE_FAILURE,
    CheckResult,
    check_media,
    check_migrations,
    code_head,
    compare_declarations,
    describe,
    media_state,
    run_checks,
    schema_dimensions,
    summarize,
)

# Built at runtime so no URL with credentials appears in the source.
URL_MATERIAL = "postgresql+asyncpg://" + "dbuser" + ":" + "supersecret" + "@db.internal/shelf"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_ok_is_ready() -> None:
    ready, checks = summarize(
        {
            "database": CheckResult(True),
            "migrations": CheckResult(True),
            "models": CheckResult(True),
            "media": CheckResult(True),
        }
    )
    assert ready is True
    assert checks == {"database": "ok", "migrations": "ok", "models": "ok", "media": "ok"}


def test_one_failure_is_not_ready_with_reason() -> None:
    ready, checks = summarize(
        {
            "database": CheckResult(True),
            "migrations": CheckResult(False, "database at none, code head x"),
            "models": CheckResult(True),
        }
    )
    assert ready is False
    assert checks == {
        "database": "ok",
        "migrations": "database at none, code head x",
        "models": "ok",
    }


def test_describe_names_classes_only() -> None:
    reason = describe(RuntimeError(f"could not connect to {URL_MATERIAL} as dbuser"))
    assert reason == "RuntimeError"
    for secret in ("dbuser", "supersecret", "db.internal", "postgresql"):
        assert secret not in reason


def test_describe_includes_the_cause_class() -> None:
    try:
        try:
            raise ConnectionRefusedError(URL_MATERIAL)
        except ConnectionRefusedError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert describe(outer) == "RuntimeError from ConnectionRefusedError"


class _FailingEngine:
    calls = 0

    def connect(self) -> None:
        _FailingEngine.calls += 1
        raise ConnectionRefusedError(URL_MATERIAL)


async def test_later_checks_are_skipped_when_the_database_fails(tmp_path: Path) -> None:
    _FailingEngine.calls = 0
    results = await run_checks(_FailingEngine(), 0.5, (CLIP_VIT_L14,), tmp_path)  # type: ignore[arg-type]
    assert results["database"] == CheckResult(False, "ConnectionRefusedError")
    assert results["migrations"] == CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
    assert results["models"] == CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
    assert results["media"] == CheckResult(True), "it runs whatever the database does"
    assert _FailingEngine.calls == 1  # no further connection attempts


async def test_migration_check_never_echoes_connection_material() -> None:
    result = await check_migrations(_FailingEngine(), timeout=0.5)  # type: ignore[arg-type]
    assert result == CheckResult(False, "ConnectionRefusedError")
    for secret in ("dbuser", "supersecret", "db.internal", "postgresql"):
        assert secret not in (result.reason or "")


def test_code_head_is_one_of_the_revisions_on_disk() -> None:
    # Whatever the head is, readiness compares the database against it, so it
    # must resolve to a revision this checkout actually carries.
    revisions = {path.stem for path in (REPO_ROOT / "alembic" / "versions").glob("[0-9]*.py")}
    assert revisions, "no migration files found"
    assert code_head() in revisions


# As PostgreSQL renders the constraint back — the shape the check has to read.
LIVE_CONSTRAINT = (
    "CHECK ((((model = 'clip-vit-l14'::text) AND (vector_dims(vector) = 768))"
    " OR ((model = 'dinov2-large'::text) AND (vector_dims(vector) = 1024))))"
)
UNRELATED_CONSTRAINT = "CHECK ((vector_dims(vector) > 0))"


def test_the_constraint_is_read_into_keys_and_widths() -> None:
    assert schema_dimensions([LIVE_CONSTRAINT, UNRELATED_CONSTRAINT]) == {
        CLIP_VIT_L14: 768,
        DINOV2_LARGE: 1024,
    }


def test_a_schema_without_the_constraint_declares_nothing() -> None:
    assert schema_dimensions([UNRELATED_CONSTRAINT]) == {}


def test_agreement_on_every_enabled_key_is_ok() -> None:
    schema = schema_dimensions([LIVE_CONSTRAINT])
    assert compare_declarations([CLIP_VIT_L14], schema) == CheckResult(True)
    assert compare_declarations([CLIP_VIT_L14, DINOV2_LARGE], schema) == CheckResult(True)


def test_a_key_the_schema_does_not_declare_is_reported_with_both_widths() -> None:
    result = compare_declarations([CLIP_VIT_L14], schema_dimensions([UNRELATED_CONSTRAINT]))
    assert result.ok is False
    assert result.reason == f"{CLIP_VIT_L14}: code 768, schema absent"


def test_a_width_the_schema_disagrees_about_is_reported() -> None:
    result = compare_declarations([CLIP_VIT_L14], {CLIP_VIT_L14: 512})
    assert result.ok is False
    assert result.reason == f"{CLIP_VIT_L14}: code 768, schema 512"


def test_a_key_the_application_does_not_declare_is_reported() -> None:
    # The mirror image: configuration naming a model this code has never heard
    # of. The settings guard catches it first, so this is the second line.
    result = compare_declarations(["ghost-model"], schema_dimensions([LIVE_CONSTRAINT]))
    assert result.ok is False
    assert "ghost-model" in (result.reason or "")


def test_every_disagreement_is_reported_not_only_the_first() -> None:
    result = compare_declarations([CLIP_VIT_L14, DINOV2_LARGE], {CLIP_VIT_L14: 512})
    assert result.reason is not None
    assert CLIP_VIT_L14 in result.reason and DINOV2_LARGE in result.reason


def test_nothing_enabled_is_trivially_consistent() -> None:
    assert compare_declarations([], schema_dimensions([LIVE_CONSTRAINT])) == CheckResult(True)


class _SlowConnection:
    """Answers `SELECT 1` at once, then never answers anything again."""

    async def __aenter__(self) -> "_SlowConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, statement: Any) -> list[tuple[Any, ...]]:
        if "pg_constraint" in str(statement):
            await asyncio.sleep(3600)
        return [(1,)]

    async def run_sync(self, function: Any) -> None:
        await asyncio.sleep(3600)


class _SlowEngine:
    def connect(self) -> _SlowConnection:
        return _SlowConnection()


async def test_the_checks_that_need_the_database_share_one_budget(tmp_path: Path) -> None:
    # The probe must answer within about twice the timeout however many checks
    # it grows; run one after the other, these two alone would cost two budgets
    # on top of the database check.
    timeout = 0.3
    started = time.monotonic()
    results = await run_checks(_SlowEngine(), timeout, (CLIP_VIT_L14,), tmp_path)  # type: ignore[arg-type]
    elapsed = time.monotonic() - started

    assert results["database"] == CheckResult(True)
    expected = f"TimeoutError: no response within {timeout:g}s"
    assert results["migrations"] == CheckResult(False, expected)
    assert results["models"] == CheckResult(False, expected)
    assert results["media"] == CheckResult(True), "it does not depend on the database"
    assert elapsed < timeout * 1.5, f"{elapsed:.2f}s for a {timeout:g}s budget"


# --- the media root ----------------------------------------------------------


def test_a_writable_directory_is_ok(tmp_path: Path) -> None:
    assert media_state(tmp_path) is None


def test_a_root_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    reason = media_state(tmp_path / "missing")
    assert reason is not None and "does not exist" in reason


def test_a_root_that_is_not_a_directory_is_reported(tmp_path: Path) -> None:
    file_root = tmp_path / "a-file"
    file_root.write_text("not a directory", encoding="utf-8")
    reason = media_state(file_root)
    assert reason is not None and "not a directory" in reason


def test_a_root_that_is_not_writable_is_reported(tmp_path: Path) -> None:
    read_only = tmp_path / "read-only"
    read_only.mkdir(mode=0o500)
    try:
        reason = media_state(read_only)
    finally:
        read_only.chmod(0o700)
    assert reason is not None and "not writable" in reason


@pytest.mark.parametrize("name", ["missing", "a-file", "read-only"], ids=str)
def test_no_reason_ever_quotes_the_path(tmp_path: Path, name: str) -> None:
    # A readiness body is unauthenticated; where a deployment keeps its files
    # is not a probe's news to publish.
    root = tmp_path / name
    if name == "a-file":
        root.write_text("x", encoding="utf-8")
    elif name == "read-only":
        root.mkdir(mode=0o500)

    reason = media_state(root)

    try:
        assert reason is not None
        assert str(root) not in reason
        assert str(tmp_path) not in reason
        assert name not in reason
    finally:
        if root.is_dir():
            root.chmod(0o700)


async def test_the_media_check_reports_a_missing_root(tmp_path: Path) -> None:
    result = await check_media(tmp_path / "missing", 0.5)

    assert result.ok is False
    assert result.reason is not None and "does not exist" in result.reason


def test_a_temporary_directory_inside_the_media_root_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The premise of the upload protocol: what is received lands where prune
    # cannot see it. With the media root above the temporary directory it does
    # not, and readiness says so before any traffic arrives.
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    import tempfile

    tempfile.tempdir = None  # the module caches its answer

    reason = media_state(tmp_path)

    assert reason is not None and "temporary directory" in reason
    assert str(tmp_path) not in reason
    tempfile.tempdir = None
