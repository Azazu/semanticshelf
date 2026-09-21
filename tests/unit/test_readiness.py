"""Readiness aggregation, reason formatting and the skip rule, without a database."""

from pathlib import Path

from app.domain import CLIP_VIT_L14, DINOV2_LARGE
from app.services.readiness import (
    SKIPPED_AFTER_DATABASE_FAILURE,
    CheckResult,
    check_migrations,
    code_head,
    compare_declarations,
    describe,
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
        }
    )
    assert ready is True
    assert checks == {"database": "ok", "migrations": "ok", "models": "ok"}


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


async def test_later_checks_are_skipped_when_the_database_fails() -> None:
    _FailingEngine.calls = 0
    results = await run_checks(_FailingEngine(), 0.5, (CLIP_VIT_L14,))  # type: ignore[arg-type]
    assert results["database"] == CheckResult(False, "ConnectionRefusedError")
    assert results["migrations"] == CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
    assert results["models"] == CheckResult(False, SKIPPED_AFTER_DATABASE_FAILURE)
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
