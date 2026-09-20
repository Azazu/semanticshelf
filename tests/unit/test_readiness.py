"""Readiness aggregation and reason formatting, without a database."""

from app.services.readiness import CheckResult, code_head, describe, readiness_payload


def test_all_ok_is_ready() -> None:
    status, body = readiness_payload(
        {"database": CheckResult(True), "migrations": CheckResult(True)}
    )
    assert status == 200
    assert body == {"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}


def test_one_failure_is_not_ready_with_reason() -> None:
    status, body = readiness_payload(
        {
            "database": CheckResult(True),
            "migrations": CheckResult(False, "database at none, code head x"),
        }
    )
    assert status == 503
    assert body["status"] == "not-ready"
    assert body["checks"] == {"database": "ok", "migrations": "database at none, code head x"}


def test_describe_keeps_class_and_first_line_only() -> None:
    reason = describe(ConnectionRefusedError("first line\npassword=hunter2"))
    assert reason == "ConnectionRefusedError: first line"
    assert describe(ValueError()) == "ValueError"
    assert len(describe(RuntimeError("x" * 500))) <= 200


def test_code_head_is_the_baseline_for_now() -> None:
    assert code_head() == "0001_baseline"
