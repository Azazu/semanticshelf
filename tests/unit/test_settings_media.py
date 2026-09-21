"""The media settings: their defaults, their ranges, and the forms an operator writes."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import Settings

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"
MIB = 1024 * 1024


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=VALID_URL, **overrides)  # type: ignore[arg-type]


def test_defaults_are_exactly_what_the_requirements_fix() -> None:
    s = settings()
    assert s.media_root == Path(".data/media")
    assert s.max_upload_bytes == 20 * MIB
    assert s.max_image_pixels == 40_000_000
    assert s.min_image_side == 32
    assert s.prune_min_age_seconds == 3600


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_upload_bytes": 0},
        {"max_image_pixels": 0},
        {"min_image_side": 0},
        {"prune_min_age_seconds": 0},
        {"max_upload_bytes": -1},
    ],
    ids=["upload", "pixels", "side", "prune", "negative"],
)
def test_a_limit_that_is_not_positive_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)


def test_every_media_setting_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # The path a deployment actually takes; the constructor above is the test's
    # own shortcut, and the two have disagreed before (see the model settings).
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("MEDIA_ROOT", "/srv/shelf/media")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(5 * MIB))
    monkeypatch.setenv("MAX_IMAGE_PIXELS", "1000000")
    monkeypatch.setenv("MIN_IMAGE_SIDE", "64")
    monkeypatch.setenv("PRUNE_MIN_AGE_SECONDS", "60")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.media_root == Path("/srv/shelf/media")
    assert s.max_upload_bytes == 5 * MIB
    assert s.max_image_pixels == 1_000_000
    assert s.min_image_side == 64
    assert s.prune_min_age_seconds == 60
