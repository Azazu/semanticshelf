"""What a failure may say, and how long it waits — decided without a database."""

from app.services.indexing import (
    REASON_MAX_BYTES,
    TRUNCATION_MARK,
    ModelNotEnabled,
    StoredFileUnusable,
    bounded,
    reason_for,
)


def test_a_failure_the_service_raised_keeps_its_message() -> None:
    reason = reason_for(ModelNotEnabled("model 'dinov2-large' is not enabled in this build"))

    assert reason == "ModelNotEnabled: model 'dinov2-large' is not enabled in this build"


def test_a_foreign_failure_leaves_only_its_class() -> None:
    # The message of a library's exception may hold anything it was reading,
    # and nothing can tell which part came from the picture.
    picture_bytes = "\x89PNG\r\n\x1a\n" + "binary-looking payload" * 10
    reason = reason_for(ValueError(f"cannot decode {picture_bytes}"))

    assert reason == "ValueError"
    assert "PNG" not in reason
    assert "payload" not in reason


def test_a_reason_never_carries_a_traceback() -> None:
    try:
        raise StoredFileUnusable("UndecodableImageError: the file is not a readable image")
    except StoredFileUnusable as error:
        reason = reason_for(error)

    assert "Traceback" not in reason
    assert "\n" not in reason


def test_a_reason_is_cut_to_what_the_column_holds() -> None:
    reason = reason_for(ModelNotEnabled("x" * (REASON_MAX_BYTES * 2)))

    assert len(reason.encode("utf-8")) <= REASON_MAX_BYTES
    assert reason.endswith(TRUNCATION_MARK)


def test_a_reason_at_the_bound_is_left_alone() -> None:
    text = "y" * REASON_MAX_BYTES
    assert bounded(text) == text
    assert bounded(text + "y").endswith(TRUNCATION_MARK)


def test_the_cut_never_splits_a_character() -> None:
    # Multi-byte text truncated by bytes must still decode.
    reason = bounded("дракон" * REASON_MAX_BYTES)

    assert reason.endswith(TRUNCATION_MARK)
    assert len(reason.encode("utf-8")) <= REASON_MAX_BYTES
