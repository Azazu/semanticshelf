"""Settings: required database URL, driver scheme, defaults."""

import pytest
from pydantic import ValidationError

from app.core.settings import Settings

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert any(error["loc"] == ("database_url",) for error in excinfo.value.errors())


def test_database_url_must_use_asyncpg() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg://"):
        Settings(_env_file=None, database_url="postgresql://localhost/semanticshelf")


def test_defaults() -> None:
    settings = Settings(_env_file=None, database_url=VALID_URL)
    assert settings.log_level == "info"
    assert settings.log_json is True
    assert settings.readiness_timeout_seconds == 3.0


def test_log_level_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", " WARNING ")
    settings = Settings(_env_file=None, database_url=VALID_URL)
    assert settings.log_level == "warning"


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=VALID_URL, log_level="loud")
