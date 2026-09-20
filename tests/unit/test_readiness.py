"""Readiness aggregation, reason formatting and the skip rule, without a database."""

from app.services.readiness import (
    SKIPPED_AFTER_DATABASE_FAILURE,
    CheckResult,
    check_migrations,
    code_head,
    describe,
    run_checks,
    summarize,
)

# Built at runtime so no URL with credentials appears in the source.
URL_MATERIAL = "postgresql+asyncpg://" + "dbuser" + ":" + "supersecret" + "@db.internal/shelf"


def test_all_ok_is_ready() -> None:
    ready, checks = summarize({"database": CheckResult(True), "migrations": CheckResult(True)})
    assert ready is True
    assert checks == {"database": "ok", "migrations": "ok"}


def test_one_failure_is_not_ready_with_reason() -> None:
    ready, checks = summarize(
        {
            "database": CheckResult(True),
            "migrations": CheckResult(False, "database at none, code head x"),
        }
    )
    assert ready is False
    assert checks == {"database": "ok", "migrations": "database at none, code head x"}


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


async def test_migration_check_is_skipped_when_the_database_fails() -> None:
    _FailingEngine.calls = 0
    results = await run_checks(_FailingEngine(), timeout=0.5)  # type: ignore[arg-type]
    assert results["database"] == CheckResult(False, "ConnectionRefusedError")
    assert results["migrations"] == CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
    assert _FailingEngine.calls == 1  # no second connection attempt


async def test_migration_check_never_echoes_connection_material() -> None:
    result = await check_migrations(_FailingEngine(), timeout=0.5)  # type: ignore[arg-type]
    assert result == CheckResult(False, "ConnectionRefusedError")
    for secret in ("dbuser", "supersecret", "db.internal", "postgresql"):
        assert secret not in (result.reason or "")


def test_code_head_is_the_baseline_for_now() -> None:
    assert code_head() == "0001_baseline"
